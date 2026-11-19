#include "contract.hpp"
#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>
#include <mcp/McpError.hpp>
#include <mcp/client/McpClient.hpp>
#include <mcp/transport/StdioClientTransport.hpp>

namespace slang_mcp::test {
namespace {
auto stdio_client() {
    mcp::StdioClientTransportOptions options;
    options.command = SLANG_MCP_TEST_BINARY;
    auto transport = std::make_shared<mcp::StdioClientTransport>(options);
    return mcp::McpClient::Create(transport->Connect(), mcp::ClientOptions{});
}

Json failed_compilation(const mcp::CallToolResult& response, bool single_unit = true) {
    REQUIRE(response.is_error);
    REQUIRE(response.structured_content.has_value());
    const auto payload = Json::parse(response.structured_content->Dump());
    REQUIRE(response.content.size() == 1);
    REQUIRE(Json::parse(std::get<mcp::TextContent>(response.content.front()).text) == payload);
    REQUIRE(payload.at("status") == "compilation_failed");
    REQUIRE(payload.at("active_project_unchanged") == true);
    REQUIRE(payload.at("requested_top_modules") == Json::array({"top"}));
    REQUIRE(payload.at("analysis").at("context") == "attempted_candidate");
    REQUIRE(payload.at("analysis").at("analysis_scope") == "fragment");
    REQUIRE(payload.at("analysis").at("source_file_count") == 1);
    REQUIRE(payload.at("analysis").at("single_unit") == single_unit);
    REQUIRE(payload.at("analysis").at("completeness") == "not_verified");
    REQUIRE_FALSE(payload.at("diagnostics").empty());
    REQUIRE(std::ranges::any_of(payload.at("diagnostics"), [](const auto& diagnostic) {
        return diagnostic.at("severity") == "error";
    }));
    return payload;
}
} // namespace

TEST_CASE("Stdio project info keeps configuration cursors tied to the active load") {
    Project project;
    project.write("design.sv", "module top; endmodule\n");
    project.write("empty.sv", "// Empty compilation source.\n");
    auto client = stdio_client();
    const auto load = mcp::JsonValue::Parse(Json{
        {"source_files", {project.path("design.sv").string(), project.path("empty.sv").string()}},
        {"top_module", "top"}}
                                                .dump());
    REQUIRE_FALSE(client->CallTool("project_load", load).is_error);
    const auto info = client->CallTool("project_info", mcp::JsonValue::Object{});
    REQUIRE_FALSE(info.is_error);
    const auto compact = Json::parse(info.structured_content->Dump());
    REQUIRE(compact.size() == 5);
    REQUIRE(compact.at("summary").at("source_file_count") == 2);
    const auto first = client->CallTool(
        "project_info", mcp::JsonValue::Parse(R"({"section":"source_files","limit":1})"));
    REQUIRE_FALSE(first.is_error);
    const auto page = Json::parse(first.structured_content->Dump());
    REQUIRE(page.at("items") == Json::array({project.path("design.sv").string()}));
    REQUIRE(page.at("returned_count") == 1);
    REQUIRE(page.at("total_count") == 2);
    REQUIRE(page.at("truncated") == true);

    const auto cursor = page.at("next_cursor");
    const auto continuation =
        mcp::JsonValue::Parse(Json{{"section", "source_files"}, {"cursor", cursor}}.dump());
    REQUIRE(client
                ->CallTool(
                    "project_info",
                    mcp::JsonValue::Parse(Json{{"section", "defines"}, {"cursor", cursor}}.dump()))
                .is_error);
    auto broken = Json::parse(load.Dump());
    broken["top_module"] = "missing";
    REQUIRE(client->CallTool("project_load", mcp::JsonValue::Parse(broken.dump())).is_error);
    const auto continued = client->CallTool("project_info", continuation);
    REQUIRE_FALSE(continued.is_error);
    const auto last = Json::parse(continued.structured_content->Dump());
    REQUIRE(last.at("items") == Json::array({project.path("empty.sv").string()}));
    REQUIRE(last.at("truncated") == false);
    REQUIRE(last.at("next_cursor").is_null());
    REQUIRE_FALSE(client->CallTool("project_load", load).is_error);
    REQUIRE(client->CallTool("project_info", continuation).is_error);
}

TEST_CASE("Failed stdio load preserves candidate diagnostics and the active project") {
    Project project;
    project.write("design.sv", "module top; logic preserved; endmodule\n");
    auto client = stdio_client();
    const auto arguments = mcp::JsonValue::Parse(Json{
        {"source_files", {project.path("design.sv").string()}},
        {"top_module", "top"},
        {"single_unit", false}}.dump());
    REQUIRE_FALSE(client->CallTool("project_load", arguments).is_error);
    const auto before = client->CallTool("project_info", mcp::JsonValue::Object{});
    project.write("design.sv", "module broken(input logic ; endmodule\n");
    const auto failure = failed_compilation(client->CallTool("project_load", arguments), false);
    REQUIRE(std::ranges::any_of(failure.at("diagnostics"), [](const auto& diagnostic) {
        return diagnostic.at("location").at("filename").is_string();
    }));
    REQUIRE(client->CallTool("project_info", mcp::JsonValue::Object{}).structured_content->Dump() ==
            before.structured_content->Dump());
    REQUIRE_FALSE(client
                      ->CallTool("describe_symbol",
                                 mcp::JsonValue::Parse(R"({"identifier":"top.preserved"})"))
                      .is_error);
}

TEST_CASE("First failed stdio load reports diagnostics without creating an active project") {
    Project project;
    project.write("design.sv", "module broken(input logic ; endmodule\n");
    auto client = stdio_client();
    const auto failed = failed_compilation(client->CallTool(
        "project_load",
        mcp::JsonValue::Parse(
            Json{{"source_files", {project.path("design.sv").string()}}, {"top_module", "top"}}
                .dump())));
    REQUIRE(client->CallTool("project_info", mcp::JsonValue::Object{}).is_error);
    const auto args = mcp::JsonValue::Parse(
        Json{{"attempt_id", failed.at("attempt_id")}, {"summary", true}, {"severity", "error"}}
            .dump());
    const auto summary = client->CallTool("get_diagnostics", args);
    REQUIRE_FALSE(summary.is_error);
    REQUIRE(Json::parse(summary.structured_content->Dump()).at("analysis") ==
            failed.at("analysis"));
}

TEST_CASE("Stdio can continue diagnostics from a failed candidate after the first hundred") {
    Project project;
    std::string source;
    for (int index = 0; index < 130; ++index) {
        source += "`include \"not_found_" + std::to_string(index) + ".svh\"\n";
    }
    project.write("design.sv", source);
    auto client = stdio_client();
    const auto failed = failed_compilation(
        client->CallTool("project_load", mcp::JsonValue::Parse(project.arguments().dump())));
    REQUIRE(failed.at("returned_count") == 100);
    const auto page = client->CallTool(
        "get_diagnostics", mcp::JsonValue::Parse(Json{{"attempt_id", failed.at("attempt_id")},
                                                      {"cursor", failed.at("next_cursor")}}
                                                     .dump()));
    REQUIRE_FALSE(page.is_error);
    REQUIRE(Json::parse(page.structured_content->Dump()).at("returned_count") >= 30);
}

TEST_CASE("Symbol lookup errors include candidates or a module-to-instance hint") {
    Project project;
    project.write("design.sv", "module leaf(input logic d); endmodule\n"
                               "module top(input logic a); leaf u(.d(a)); endmodule\n");
    auto client = stdio_client();
    REQUIRE_FALSE(
        client->CallTool("project_load", mcp::JsonValue::Parse(project.arguments().dump()))
            .is_error);
    const auto ambiguous =
        client->CallTool("describe_symbol", mcp::JsonValue::Parse(R"({"identifier":"top.u.d"})"));
    REQUIRE(ambiguous.is_error);
    REQUIRE(Json::parse(ambiguous.structured_content->Dump()).at("candidates").size() == 2);
    const auto wrong_module =
        client->CallTool("get_references", mcp::JsonValue::Parse(R"({"symbol":"leaf.d"})"));
    REQUIRE(wrong_module.is_error);
    REQUIRE(Json::parse(wrong_module.structured_content->Dump()).at("suggested_tool") ==
            "list_instances");
}

namespace {
void write_reference_fixture(const Project& project) {
    std::string rtl = "module top(input logic src, output wire [512:0] dst);\n";
    for (int index = 0; index < 513; ++index) {
        rtl += "assign dst[" + std::to_string(index) + "] = src;\n";
    }
    project.write("design.sv", rtl + "endmodule\n");
}

Json reference_page(mcp::McpClient& client, const Json& arguments) {
    const auto result = client.CallTool("get_references", mcp::JsonValue::Parse(arguments.dump()));
    REQUIRE_FALSE(result.is_error);
    return Json::parse(result.structured_content->Dump());
}

void check_reference_lines(const Json& page, int first, int count) {
    REQUIRE(page.at("total_count") == 513);
    REQUIRE(page.at("returned_count") == count);
    REQUIRE(page.at("items").size() == static_cast<std::size_t>(count));
    for (const auto& item : page.at("items")) {
        REQUIRE(item.at("location").at("line") == first++);
    }
}
} // namespace

TEST_CASE("Stdio reference pages preserve order and belong to the active compilation") {
    Project project;
    write_reference_fixture(project);
    auto client = stdio_client();
    const auto load = mcp::JsonValue::Parse(project.arguments().dump());
    REQUIRE_FALSE(client->CallTool("project_load", load).is_error);
    Json query = {{"symbol", "top.src"}, {"kind", "read"}, {"limit", 500}};
    const auto first = reference_page(*client, query);
    check_reference_lines(first, 2, 500);
    REQUIRE(first.at("truncated") == true);
    query["cursor"] = first.at("next_cursor");
    query["limit"] = 20;
    auto wrong = query;
    wrong["kind"] = "write";
    REQUIRE(client->CallTool("get_references", mcp::JsonValue::Parse(wrong.dump())).is_error);
    auto broken = project.arguments();
    broken["top_module"] = "missing";
    REQUIRE(client->CallTool("project_load", mcp::JsonValue::Parse(broken.dump())).is_error);
    const auto last = reference_page(*client, query);
    check_reference_lines(last, 502, 13);
    REQUIRE(last.at("next_cursor").is_null());
    REQUIRE(last.at("truncated") == false);
    REQUIRE_FALSE(client->CallTool("project_load", load).is_error);
    REQUIRE(client->CallTool("get_references", mcp::JsonValue::Parse(query.dump())).is_error);
    const auto empty = reference_page(*client, {{"symbol", "top.src"}, {"kind", "write"}});
    REQUIRE(empty.at("items").empty());
    REQUIRE(empty.at("total_count") == 0);
    REQUIRE(empty.at("next_cursor").is_null());
}

TEST_CASE(
    "Stdio type descriptions validate nested arrays structs and unions against the contract") {
    Project project;
    project.write("design.sv", R"sv(
module top;
  typedef struct packed {logic [7:0] data; logic valid;} word_t;
  typedef union packed {word_t word; logic [8:0] raw;} overlay_t;
  overlay_t entries[4];
endmodule
)sv");
    auto client = stdio_client();
    REQUIRE_FALSE(
        client->CallTool("project_load", mcp::JsonValue::Parse(project.arguments().dump()))
            .is_error);
    const auto response = client->CallTool(
        "describe_symbol", mcp::JsonValue::Parse(R"({"identifier":"top.entries","type_depth":4})"));
    REQUIRE_FALSE(response.is_error);
    REQUIRE(response.structured_content.has_value());
    const auto payload = Json::parse(response.structured_content->Dump());
    REQUIRE(payload.at("width") == 9);
    REQUIRE(payload.at("type_info").at("total_bits") == 36);
    REQUIRE(payload.at("type_info").at("element_type").at("kind") == "packed_union");
    REQUIRE(payload.at("type_info")
                .at("element_type")
                .at("fields")
                .front()
                .at("type_info")
                .at("fields")
                .size() == 2);
    REQUIRE(Json::parse(std::get<mcp::TextContent>(response.content.front()).text) == payload);
    REQUIRE_FALSE(
        client
            ->CallTool("describe_symbol",
                       mcp::JsonValue::Parse(R"({"identifier":"top.entries","type_depth":null})"))
            .is_error);
}

TEST_CASE("Stdio catalog exposes the focused semantic tools") {
    auto client = stdio_client();
    std::vector<std::string> names;
    for (const auto& tool : client->ListToolsAll().tools) {
        names.push_back(tool.name);
    }
    std::ranges::sort(names);
    REQUIRE(names == std::vector<std::string>{
                         "describe_symbol", "expand_macro", "find_symbol", "get_diagnostics",
                         "get_hierarchy", "get_references", "get_state_elements",
                         "inspect_instance", "inspect_module", "list_instance_facts",
                         "list_instances", "list_symbols", "project_info", "project_load"});
    REQUIRE_THROWS_AS(client->CallTool("project_load_partial", mcp::JsonValue::Object{}),
                      mcp::McpError);
    REQUIRE_THROWS_AS(client->CallTool("semantic_diff", mcp::JsonValue::Object{}), mcp::McpError);
}

TEST_CASE("Real stdio MCP publishes the contract and serves semantic queries") {
    mcp::StdioClientTransportOptions transport_options;
    transport_options.command = SLANG_MCP_TEST_BINARY;
    auto transport = std::make_shared<mcp::StdioClientTransport>(transport_options);
    mcp::ClientOptions options;
    options.connect_mode = GENERATE(mcp::ConnectMode::Legacy, mcp::ConnectMode::Auto);
    auto client = mcp::McpClient::Create(transport->Connect(), options);
    const auto tools = client->ListToolsAll().tools;
    REQUIRE(tools.size() == 14);
    for (const auto& expected : Json::parse(tool_contract)) {
        const auto tool = std::ranges::find_if(tools, [&](const auto& value) {
            return value.name == expected.at("name").get<std::string>();
        });
        REQUIRE(tool != tools.end());
        REQUIRE(tool->description.value() == expected.at("description").get<std::string>());
        REQUIRE(Json::parse(tool->input_schema.Dump()) == expected.at("inputSchema"));
        REQUIRE(tool->output_schema.has_value());
        REQUIRE(Json::parse(tool->output_schema->Dump()) == expected.at("outputSchema"));
        REQUIRE(tool->annotations.value().read_only_hint.value());
    }
    Project project;
    project.write("design.sv", hierarchy_rtl);
    const auto loaded = client->CallTool(
        "project_load",
        mcp::JsonValue::Parse(
            Json{{"source_files", {project.path("design.sv").string()}}, {"top_module", "top"}}
                .dump()));
    REQUIRE_FALSE(loaded.is_error);
    REQUIRE(loaded.structured_content.has_value());
    REQUIRE(Json::parse(loaded.structured_content->Dump()).at("top_modules") ==
            Json::array({"top"}));
    REQUIRE(Json::parse(loaded.structured_content->Dump()).at("single_unit") == true);
    const auto hierarchy = client->CallTool("get_hierarchy", mcp::JsonValue::Object{});
    REQUIRE_FALSE(hierarchy.is_error);
    REQUIRE(
        Json::parse(hierarchy.structured_content.value().Dump()).at("items").front().at("path") ==
        "top");
    const auto partial = client->CallTool(
        "project_load",
        mcp::JsonValue::Parse(
            Json{{"source_files", {project.path("design.sv").string()}}, {"top_module", "leaf"}}
                .dump()));
    REQUIRE_FALSE(partial.is_error);
    REQUIRE(Json::parse(partial.structured_content.value().Dump()).at("analysis_scope") ==
            "fragment");
}

TEST_CASE("Real stdio macro expansion returns generated declarations") {
    Project project;
    project.write("design.sv",
                  "`define DECL(n) logic n``_ff;\nmodule top;\n`DECL(bank_sel)\nendmodule\n");
    auto client = stdio_client();
    REQUIRE_FALSE(
        client->CallTool("project_load", mcp::JsonValue::Parse(project.arguments().dump()))
            .is_error);
    const auto result = client->CallTool(
        "expand_macro",
        mcp::JsonValue::Parse(
            Json{{"file", project.path("design.sv").string()}, {"line", 3}, {"column", 1}}.dump()));
    REQUIRE_FALSE(result.is_error);
    REQUIRE(result.structured_content.has_value());
    const auto payload = Json::parse(result.structured_content->Dump());
    REQUIRE(payload.at("name") == "DECL");
    REQUIRE(payload.at("expanded_text").get<std::string>().contains("bank_sel_ff"));
    REQUIRE(payload.at("truncated") == false);
    REQUIRE(Json::parse(std::get<mcp::TextContent>(result.content.front()).text) == payload);
}

TEST_CASE("Stdio project load reports the selected compilation unit mode") {
    Project project;
    project.write("design.sv", "module top; endmodule\n");
    auto client = stdio_client();
    const auto single_unit = GENERATE(true, false);
    const auto loaded =
        client->CallTool("project_load", mcp::JsonValue::Parse(Json{
                                             {"source_files", {project.path("design.sv").string()}},
                                             {"top_module", "top"},
                                             {"single_unit",
                                              single_unit}}.dump()));
    REQUIRE_FALSE(loaded.is_error);
    REQUIRE(Json::parse(loaded.structured_content->Dump()).at("single_unit") == single_unit);
    const auto info = client->CallTool("project_info", mcp::JsonValue::Object{});
    REQUIRE(Json::parse(info.structured_content->Dump()).at("single_unit") == single_unit);
    const auto diagnostics = client->CallTool("get_diagnostics", mcp::JsonValue::Object{});
    REQUIRE(Json::parse(diagnostics.structured_content->Dump()).at("analysis").at("single_unit") ==
            single_unit);
}
} // namespace slang_mcp::test
