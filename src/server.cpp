#include "server.hpp"
#include "compilation_error.hpp"
#include "contract.hpp"
#include "semantic_service.hpp"

#include <mcp/server/McpServer.hpp>
#include <mcp/transport/StdioServerTransport.hpp>

#include <algorithm>
#include <array>
#include <iostream>
#include <string_view>

namespace slang_mcp {
namespace {
class DeferredStdioTransport final : public mcp::StdioServerTransport {
  public:
    void Start() override {}
    void activate() {
        mcp::StdioServerTransport::Start();
    }
};

mcp::CallToolResult tool_error(const std::string& message) {
    mcp::CallToolResult result;
    result.is_error = true;
    result.content.push_back(mcp::TextContent{"text", message});
    return result;
}

mcp::CallToolResult compilation_error(const CompilationError& error) {
    const auto diagnostics = page(error.diagnostics);
    const Json payload = {{"status", "compilation_failed"},
                          {"message", error.what()},
                          {"diagnostics", diagnostics.items},
                          {"returned_count", diagnostics.items.size()},
                          {"total_count", diagnostics.total_count},
                          {"truncated", diagnostics.truncated},
                          {"analysis",
                           {{"context", "attempted_candidate"},
                            {"analysis_scope", error.analysis_scope},
                            {"completeness", "not_verified"},
                            {"top_modules", error.requested_top_modules},
                            {"source_file_count", error.source_file_count}}},
                          {"requested_top_modules", error.requested_top_modules},
                          {"active_project_unchanged", true}};
    auto result = tool_error(payload.dump());
    result.structured_content = mcp::JsonValue::Parse(payload.dump());
    return result;
}

mcp::CallToolResult
successful_result(SemanticService& service, const std::string& name,
                  const mcp::RequestContext<mcp::CallToolRequestParams>& context) {
    const auto arguments = context.Params().arguments
                               ? Json::parse(context.Params().arguments->Dump())
                               : Json::object();
    const auto payload = service.call(name, arguments).dump();
    mcp::CallToolResult result;
    result.structured_content = mcp::JsonValue::Parse(payload);
    result.content.push_back(mcp::TextContent{"text", payload});
    return result;
}

mcp::CallToolResult result_for(SemanticService& service, const std::string& name,
                               const mcp::RequestContext<mcp::CallToolRequestParams>& context) {
    try {
        return successful_result(service, name, context);
    } catch (const CompilationError& error) {
        return compilation_error(error);
    } catch (const std::invalid_argument& error) {
        return tool_error(error.what());
    } catch (const Json::exception& error) {
        return tool_error("invalid tool arguments: " + std::string(error.what()));
    } catch (const std::exception& error) {
        std::cerr << "semantic tool failure: " << error.what() << '\n';
        return tool_error("internal semantic server failure");
    }
}

bool enabled_tool(ToolProfile profile, std::string_view name) {
    constexpr std::array core_tools = {
        "project_load_partial", "project_info",      "get_diagnostics",   "find_symbol",
        "describe_symbol",      "list_symbols",      "get_references",    "get_hierarchy",
        "list_instances",       "inspect_module",    "inspect_instance",  "list_instance_facts",
        "get_signal_reads",     "get_signal_writes", "get_state_elements"};
    return profile == ToolProfile::Full || std::ranges::contains(core_tools, name);
}

void register_tools(mcp::McpServer& server, SemanticService& service, ToolProfile profile) {
    for (const auto& tool : Json::parse(tool_contract)) {
        const auto name = tool.at("name").get<std::string>();
        if (!enabled_tool(profile, name)) {
            continue;
        }
        mcp::ToolOptions options;
        options.description = tool.at("description").get<std::string>();
        options.input_schema = mcp::JsonValue::Parse(tool.at("inputSchema").dump());
        options.read_only_hint = true;
        options.destructive = false;
        options.open_world_hint = false;
        server.RegisterTool(
            name, options,
            [&service, tool_name = std::make_shared<const std::string>(name)](const auto& context) {
                return result_for(service, *tool_name, context);
            });
    }
}
} // namespace

int run_server(ToolProfile profile) {
    SemanticService service(profile == ToolProfile::Full ? SnapshotPolicy::Track
                                                         : SnapshotPolicy::Disabled);
    mcp::ServerOptions options;
    options.server_info = mcp::Implementation{"slang-mcp", SLANG_MCP_VERSION};
    options.server_instructions =
        "Read-only SystemVerilog source semantics. Choose ordered source_files and a top_module "
        "for project_load_partial; expand dependencies explicitly when diagnostics require them. "
        "Fragment analysis uses default parameter values, not caller overrides. Use optional "
        "fields on inspection tools to request only the needed sections. Inspect diagnostics "
        "before trusting unresolved types or instances. Diagnostic scope hints are possibilities, "
        "not proof that an error is harmless.";
    std::unique_ptr<mcp::McpServer> server;
    options.on_transport_close = [&server] {
        if (server) {
            server->Close();
        }
    };
    auto transport = std::make_shared<DeferredStdioTransport>();
    server = mcp::McpServer::Create(transport, options);
    register_tools(*server, service, profile);
    transport->activate();
    server->Run();
    return 0;
}
} // namespace slang_mcp
