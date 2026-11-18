#include "server.hpp"
#include "contract.hpp"
#include "pagination.hpp"
#include "semantic_service.hpp"
#include "symbol_lookup_error.hpp"

#include <mcp/server/McpServer.hpp>
#include <mcp/transport/StdioServerTransport.hpp>

#include <iostream>

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

mcp::CallToolResult structured_error(const Json& payload) {
    const auto encoded = payload.dump();
    auto result = tool_error(encoded);
    result.structured_content = mcp::JsonValue::Parse(encoded);
    return result;
}

mcp::CallToolResult lookup_error(const SymbolLookupError& error) {
    auto payload = error.details;
    payload["message"] = error.what();
    return structured_error(payload);
}

mcp::CallToolResult compilation_error(const CompilationError& error) {
    const Json args = {{"attempt_id", error.attempt_id}};
    const Pagination page(args, "get_diagnostics", error.attempt_id);
    const Json metadata = {{"status", "compilation_failed"},
                           {"message", error.what()},
                           {"attempt_id", error.attempt_id},
                           {"analysis", error.context()},
                           {"requested_top_modules", error.requested_top_modules},
                           {"active_project_unchanged", true}};
    try {
        return structured_error(
            page.render(error.diagnostics, "diagnostics", std::identity{}, metadata));
    } catch (const std::invalid_argument&) {
        return structured_error(metadata);
    }
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
    } catch (const SymbolLookupError& error) {
        return lookup_error(error);
    } catch (const std::invalid_argument& error) {
        return tool_error(error.what());
    } catch (const Json::exception& error) {
        return tool_error("invalid tool arguments: " + std::string(error.what()));
    } catch (const std::exception& error) {
        std::cerr << "semantic tool failure: " << error.what() << '\n';
        return tool_error("internal semantic server failure");
    }
}

void register_tools(mcp::McpServer& server, SemanticService& service) {
    for (const auto& tool : Json::parse(tool_contract)) {
        const auto name = tool.at("name").get<std::string>();
        mcp::ToolOptions options;
        options.description = tool.at("description").get<std::string>();
        options.input_schema = mcp::JsonValue::Parse(tool.at("inputSchema").dump());
        options.output_schema = mcp::JsonValue::Parse(tool.at("outputSchema").dump());
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

int run_server() {
    SemanticService service(SnapshotPolicy::Disabled);
    mcp::ServerOptions options;
    options.server_info = mcp::Implementation{"slang-mcp", SLANG_MCP_VERSION};
    options.server_instructions =
        "Read-only SystemVerilog source semantics. Choose ordered source_files and a top_module "
        "for project_load; expand dependencies explicitly when diagnostics require them. "
        "Sources share one compilation unit by default; set single_unit false for separate units. "
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
    register_tools(*server, service);
    transport->activate();
    server->Run();
    return 0;
}
} // namespace slang_mcp
