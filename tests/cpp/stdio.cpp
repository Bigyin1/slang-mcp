#include "contract.hpp"
#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>
#include <mcp/McpError.hpp>
#include <mcp/client/McpClient.hpp>
#include <mcp/transport/StdioClientTransport.hpp>

namespace slang_mcp::test {
namespace {
auto core_client() {
    mcp::StdioClientTransportOptions options;
    options.command = SLANG_MCP_TEST_BINARY;
    auto transport = std::make_shared<mcp::StdioClientTransport>(options);
    return mcp::McpClient::Create(transport->Connect(), mcp::ClientOptions{});
}

Json failed_compilation(const mcp::CallToolResult& response) {
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
    REQUIRE(payload.at("analysis").at("completeness") == "not_verified");
    REQUIRE_FALSE(payload.at("diagnostics").empty());
    REQUIRE(std::ranges::any_of(payload.at("diagnostics"), [](const auto& diagnostic) {
        return diagnostic.at("severity") == "error";
    }));
    return payload;
}
} // namespace

TEST_CASE("Failed stdio load preserves candidate diagnostics and the active project") {
    Project project;
    project.write("design.sv", "module top; logic preserved; endmodule\n");
    auto client = core_client();
    const auto arguments = mcp::JsonValue::Parse(
        Json{{"source_files", {project.path("design.sv").string()}}, {"top_module", "top"}}.dump());
    REQUIRE_FALSE(client->CallTool("project_load_partial", arguments).is_error);
    const auto before = client->CallTool("project_info", mcp::JsonValue::Object{});
    project.write("design.sv", "module broken(input logic ; endmodule\n");
    const auto failure = failed_compilation(client->CallTool("project_load_partial", arguments));
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
    auto client = core_client();
    (void)failed_compilation(client->CallTool(
        "project_load_partial",
        mcp::JsonValue::Parse(
            Json{{"source_files", {project.path("design.sv").string()}}, {"top_module", "top"}}
                .dump())));
    REQUIRE(client->CallTool("project_info", mcp::JsonValue::Object{}).is_error);
}

TEST_CASE("Core stdio catalog exposes only focused semantic tools") {
    mcp::StdioClientTransportOptions transport_options;
    transport_options.command = SLANG_MCP_TEST_BINARY;
    transport_options.arguments =
        GENERATE(std::vector<std::string>{}, std::vector<std::string>{"--tool-profile", "core"});
    auto transport = std::make_shared<mcp::StdioClientTransport>(transport_options);
    auto client = mcp::McpClient::Create(transport->Connect(), mcp::ClientOptions{});
    std::vector<std::string> names;
    for (const auto& tool : client->ListToolsAll().tools) {
        names.push_back(tool.name);
    }
    std::ranges::sort(names);
    REQUIRE(names ==
            std::vector<std::string>{"describe_symbol", "find_symbol", "get_diagnostics",
                                     "get_hierarchy", "get_references", "get_signal_reads",
                                     "get_signal_writes", "get_state_elements", "inspect_instance",
                                     "inspect_module", "list_instance_facts", "list_instances",
                                     "list_symbols", "project_info", "project_load_partial"});
    REQUIRE_THROWS_AS(client->CallTool("project_load", mcp::JsonValue::Object{}), mcp::McpError);
    REQUIRE_THROWS_AS(client->CallTool("semantic_diff", mcp::JsonValue::Object{}), mcp::McpError);
}

TEST_CASE("Real stdio MCP retains all old-style schemas and serves queries") {
    mcp::StdioClientTransportOptions transport_options;
    transport_options.command = SLANG_MCP_TEST_BINARY;
    transport_options.arguments = {"--tool-profile", "full"};
    auto transport = std::make_shared<mcp::StdioClientTransport>(transport_options);
    mcp::ClientOptions options;
    options.connect_mode = GENERATE(mcp::ConnectMode::Legacy, mcp::ConnectMode::Auto);
    auto client = mcp::McpClient::Create(transport->Connect(), options);
    const auto tools = client->ListToolsAll().tools;
    REQUIRE(tools.size() == 30);
    for (const auto& expected : Json::parse(tool_contract)) {
        const auto tool = std::ranges::find_if(tools, [&](const auto& value) {
            return value.name == expected.at("name").get<std::string>();
        });
        REQUIRE(tool != tools.end());
        REQUIRE(Json::parse(tool->input_schema.Dump()) == expected.at("inputSchema"));
        REQUIRE(tool->annotations.value().read_only_hint.value());
    }
    Project project;
    project.write("design.sv", hierarchy_rtl);
    const auto loaded =
        client->CallTool("project_load", mcp::JsonValue::Parse(project.arguments().dump()));
    REQUIRE_FALSE(loaded.is_error);
    REQUIRE(loaded.structured_content.has_value());
    REQUIRE(Json::parse(loaded.structured_content->Dump()).at("top_modules") ==
            Json::array({"top"}));
    const auto hierarchy = client->CallTool("get_hierarchy", mcp::JsonValue::Object{});
    REQUIRE_FALSE(hierarchy.is_error);
    REQUIRE(
        Json::parse(hierarchy.structured_content.value().Dump()).at("roots").front().at("path") ==
        "top");
    const auto partial = client->CallTool(
        "project_load_partial",
        mcp::JsonValue::Parse(
            Json{{"source_files", {project.path("design.sv").string()}}, {"top_module", "leaf"}}
                .dump()));
    REQUIRE_FALSE(partial.is_error);
    REQUIRE(Json::parse(partial.structured_content.value().Dump()).at("analysis_scope") ==
            "fragment");
}
} // namespace slang_mcp::test
