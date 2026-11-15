#include "contract.hpp"
#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>
#include <mcp/client/McpClient.hpp>
#include <mcp/transport/StdioClientTransport.hpp>

namespace slang_mcp::test {
TEST_CASE("Real stdio MCP retains all old-style schemas and serves queries") {
    mcp::StdioClientTransportOptions transport_options;
    transport_options.command = SLANG_MCP_TEST_BINARY;
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
