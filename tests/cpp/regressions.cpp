#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>

namespace slang_mcp::test {
TEST_CASE("Null and empty configured macro replacements follow Slang semantics") {
    Project project;
    project.write(
        "design.sv",
        "module top #(parameter int FLAG_VALUE=`FLAG); `EMPTY logic present; endmodule\n");
    auto arguments = project.arguments();
    arguments["defines"] = {{"FLAG", nullptr}, {"EMPTY", ""}};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", arguments).at("diagnostic_error_count") == 0);
    const auto result = service.call("inspect_module", {{"sv_module", "top"}});
    REQUIRE(result.at("parameters").at("parameters").at("items").front().at("integer_value") == 1);
    REQUIRE(service.call("find_symbol", {{"name", "present"}}).at("match_count") == 1);
}

TEST_CASE("Batch instance facts apply advertised name and path filters") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto result = service.call("list_instance_facts", {{"sv_module", "leaf"},
                                                             {"name", "u_leaf"},
                                                             {"path_prefix", "top.generated[1]"},
                                                             {"parameter_names", {"WIDTH"}},
                                                             {"port_names", {"i"}},
                                                             {"limit", 1},
                                                             {"fact_limit", 1}});
    REQUIRE(result.at("total_count") == 1);
    REQUIRE_FALSE(result.at("truncated").get<bool>());
    const auto& item = result.at("items").front();
    REQUIRE(item.at("instance").at("path") == "top.generated[1].u_leaf");
    REQUIRE(item.at("parameters").at("items").front().at("integer_value") == 32);
    REQUIRE(item.at("connections").at("items").front().at("port").at("name") == "i");
}

TEST_CASE("Preprocessing preserves ordered packages includes and defines") {
    Project project;
    project.write("defs.svh", "`define WIDTH 13\n");
    project.write(
        "types.sv",
        "`include \"defs.svh\"\npackage types; typedef logic [`WIDTH-1:0] word_t; endpackage\n");
    project.write(
        "design.sv",
        "module top; types::word_t data; `ifdef EXTRA\nlogic added;\n`endif\nendmodule\n");
    auto args = project.arguments({"types.sv", "design.sv"});
    args["include_directories"] = {project.path("").string()};
    args["defines"] = {{"EXTRA", nullptr}};
    SemanticService service;
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    REQUIRE(service.call("find_symbol", {{"name", "added"}}).at("match_count") == 1);
    REQUIRE(service.call("describe_symbol", {{"identifier", "top.data"}}).at("width") == 13);
    REQUIRE(service.call("find_symbol", {{"name", "types"}}).at("symbols").front().at("kind") ==
            "package");
}

TEST_CASE("Connections retain expressions and open ports without inventing routes") {
    Project project;
    project.write("design.sv", R"sv(
module leaf(input logic d, output logic q); assign q=d; endmodule
module top(input logic a,b);
  leaf expression(.d(a & b),.q());
endmodule
)sv");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto connections =
        service.call("get_instance_connections", {{"instance_path", "top.expression"}});
    REQUIRE(connections.at("items").front().at("kind") == "expression");
    REQUIRE(connections.at("items").front().at("expression") == "a & b");
    REQUIRE(connections.at("items").front().at("symbols") == Json::array({"top.a", "top.b"}));
    REQUIRE(connections.at("items").back().at("kind") == "unconnected");
    REQUIRE(service.call("trace_connectivity", {{"signal", "top.a"}, {"direction", "loads"}})
                .at("paths")
                .at("items")
                .front()
                .at("stop_reason") == "no_edges");
}

TEST_CASE("Port connections retain actual expressions through implicit binding wrappers") {
    Project project;
    project.write("design.sv", R"sv(
module leaf(input logic [7:0] d, output logic [1:0] q); assign q=d[1:0]; endmodule
module top;
  logic [3:0] source;
  logic [1:0] direct;
  logic [1:0] indexed [2][2];
  logic high, low;
  leaf u_direct(.d(source), .q(direct));
  leaf u_indexed(.d(source), .q(indexed[1][0]));
  leaf u_concat(.d(source), .q({high, low}));
endmodule
)sv");
    SemanticService service;
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto instance = GENERATE("u_direct", "u_indexed", "u_concat");
    const auto connections =
        service
            .call("get_instance_connections", {{"instance_path", std::string("top.") + instance}})
            .at("items");
    REQUIRE(connections.front().at("expression") == "source");
    REQUIRE(connections.front().at("actual_width") == 4);
    REQUIRE(connections.front().at("port").at("width") == 8);
    REQUIRE(connections.back().at("actual_width") == 2);
    if (std::string_view(instance) == "u_direct") {
        REQUIRE(connections.back().at("expression") == "direct");
        REQUIRE(connections.back().at("kind") == "signal");
        REQUIRE(connections.back().at("symbols") == Json::array({"top.direct"}));
    } else if (std::string_view(instance) == "u_indexed") {
        REQUIRE(connections.back().at("expression") == "indexed[1][0]");
        REQUIRE(connections.back().at("kind") == "expression");
        REQUIRE(connections.back().at("symbols") == Json::array({"top.indexed"}));
    } else {
        REQUIRE(connections.back().at("expression") == "{high, low}");
        REQUIRE(connections.back().at("kind") == "expression");
        REQUIRE(connections.back().at("symbols") == Json::array({"top.high", "top.low"}));
    }
}

TEST_CASE("Invalid output actuals retain diagnostics without invented symbol bindings") {
    Project project;
    project.write("design.sv", R"sv(
module leaf(output logic q); assign q=1'b0; endmodule
module top; leaf u(.q(1'b0)); endmodule
)sv");
    SemanticService service;
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") > 0);
    const auto connections =
        service.call("get_instance_connections", {{"instance_path", "top.u"}}).at("items");
    REQUIRE(connections.front().at("symbols").empty());
    REQUIRE(connections.front().at("kind") != "signal");
}

TEST_CASE("Connectivity reports cycles and honors bounded traversal") {
    Project project;
    project.write("design.sv", "module top; logic a,b; assign a=b; assign b=a; endmodule\n");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE(service.call("trace_connectivity", {{"signal", "top.a"}, {"direction", "loads"}})
                .at("paths")
                .at("items")
                .front()
                .at("stop_reason") == "cycle");
    const auto trace = service.call("trace_connectivity",
                                    {{"signal", "top.a"}, {"direction", "loads"}, {"limit", 1}});
    REQUIRE(trace.at("truncated") == true);
    REQUIRE(trace.at("edges_considered") == 1);
}

TEST_CASE("Interfaces packed structs and unpacked port dimensions retain semantic types") {
    Project project;
    project.write("design.sv", R"sv(
package types;
  typedef struct packed {logic [7:0] data; logic valid;} word_t;
endpackage
interface bus_if; logic data; modport sink(input data); endinterface
module leaf(bus_if.sink bus, input types::word_t words[2]); endmodule
module top;
  bus_if bus();
  types::word_t words[2];
  leaf u(.bus(bus),.words(words));
endmodule
)sv");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto ports = service.call("get_ports", {{"sv_module", "leaf"}}).at("items");
    REQUIRE(ports.front().at("interface") == "bus_if");
    REQUIRE(ports.front().at("modport") == "sink");
    REQUIRE(ports.back().at("width") == 9);
    REQUIRE(ports.back().at("unpacked_dimensions").size() == 1);
    REQUIRE(service.call("get_instance_connections", {{"instance_path", "top.u"}})
                .at("items")
                .front()
                .at("kind") == "interface");
}

TEST_CASE("Duplicate instance names require exact paths and collections report truncation") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE_THROWS_AS(service.call("find_instance", {{"query", "u_leaf"}}), std::invalid_argument);
    REQUIRE(service.call("find_instance", {{"query", "top.generated[0].u_leaf"}}).at("sv_module") ==
            "leaf");
    const auto instances = service.call("list_instances", {{"sv_module", "leaf"}, {"limit", 1}});
    REQUIRE(instances.at("truncated") == true);
    REQUIRE(instances.at("items").size() == 1);
    REQUIRE(instances.at("total_count") == 4);
}
TEST_CASE("Default-scope symbol identifiers round trip through descriptions") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto members = service.call("list_symbols", {{"scope", "leaf"}}).at("items");
    REQUIRE_FALSE(members.empty());
    for (const auto& member : members) {
        REQUIRE(member.at("symbol_id").get<std::string>().starts_with("default:"));
        REQUIRE(service.call("describe_symbol", {{"identifier", member.at("symbol_id")}})
                    .at("symbol")
                    .at("symbol_id") == member.at("symbol_id"));
    }
}
TEST_CASE("Instance scopes expose direct members with effective types") {
    Project project;
    project.write("design.sv", R"sv(
module leaf #(parameter int WIDTH = 8)(input logic [WIDTH-1:0] data);
  logic [WIDTH-1:0] payload, scratch;
endmodule
module top;
  logic top_signal;
  leaf #(.WIDTH(5)) first();
  leaf #(.WIDTH(9)) second();
endmodule
)sv");
    SemanticService service;
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto members = service.call("list_symbols", {{"scope", "top.first"}}).at("items");
    REQUIRE_FALSE(members.empty());
    for (const auto& member : members) {
        REQUIRE(member.at("containing_scope") == "top.first");
        const auto described =
            service.call("describe_symbol", {{"identifier", member.at("symbol_id")}});
        REQUIRE(described.at("symbol").at("symbol_id") == member.at("symbol_id"));
    }
    REQUIRE(service.call("describe_symbol", {{"identifier", "variable:top.first.payload"}})
                .at("width") == 5);
    REQUIRE(service.call("describe_symbol", {{"identifier", "variable:top.second.payload"}})
                .at("width") == 9);
    const auto variables =
        service.call("list_symbols", {{"scope", "top.first"}, {"kind", "variable"}});
    REQUIRE(variables.at("total_count").get<int>() >= 2);
    const auto limited =
        service.call("list_symbols", {{"scope", "top.first"}, {"kind", "variable"}, {"limit", 1}});
    REQUIRE(limited.at("total_count") == variables.at("total_count"));
    REQUIRE(limited.at("items").size() == 1);
    REQUIRE(limited.at("truncated") == true);
    REQUIRE(limited.at("items").front().at("kind") == "variable");
    const auto defaults = service.call("list_symbols", {{"scope", "leaf"}}).at("items");
    REQUIRE(std::ranges::any_of(defaults, [&](const auto& member) {
        return member.at("name") == "payload" &&
               service.call("describe_symbol", {{"identifier", member.at("symbol_id")}})
                       .at("width") == 8;
    }));
    REQUIRE(service.call("list_symbols", {{"scope", "top"}})
                .at("items")
                .front()
                .at("symbol_id")
                .get<std::string>()
                .starts_with("default:"));
    REQUIRE_THROWS_AS(service.call("list_symbols", {{"scope", "top.first.missing"}}),
                      std::invalid_argument);
}

TEST_CASE("Generated hierarchy scopes expose only their own direct members") {
    Project project;
    project.write("design.sv", R"sv(
module leaf #(parameter int WIDTH = 8); logic [WIDTH-1:0] payload; endmodule
module top;
  for (genvar i=0; i<2; i++) begin: generated
    logic [i+1:0] lane;
    leaf #(.WIDTH(i+3)) u();
  end
  if (1) begin: empty_scope end
endmodule
)sv");
    SemanticService service;
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto scope = GENERATE("top.generated[0]", "top.generated[1]");
    const auto members =
        service.call("list_symbols", {{"scope", scope}, {"kind", "variable"}}).at("items");
    REQUIRE(members.size() == 1);
    REQUIRE(members.front().at("name") == "lane");
    REQUIRE(members.front().at("containing_scope") == scope);
    REQUIRE(service.call("describe_symbol", {{"identifier", members.front().at("symbol_id")}})
                .at("width") == (std::string_view(scope) == "top.generated[0]" ? 2 : 3));
    const auto child_scope = std::string(scope) + ".u";
    const auto child =
        service.call("list_symbols", {{"scope", child_scope}, {"kind", "variable"}}).at("items");
    REQUIRE(child.size() == 1);
    REQUIRE(child.front().at("containing_scope") == child_scope);
    REQUIRE(service.call("describe_symbol", {{"identifier", child.front().at("symbol_id")}})
                .at("width") == (std::string_view(scope) == "top.generated[0]" ? 3 : 4));
    REQUIRE(service.call("list_symbols", {{"scope", "top.empty_scope"}}).at("items").empty());
    REQUIRE_THROWS_AS(service.call("list_symbols", {{"scope", "top.generated[2]"}}),
                      std::invalid_argument);
}
TEST_CASE("State inventories count all procedures before bounding the response") {
    Project project;
    std::string rtl = "module top(input logic clk,d);\n";
    for (int index = 0; index < 501; ++index) {
        rtl += "logic q_" + std::to_string(index) + "; always_ff @(posedge clk) q_" +
               std::to_string(index) + " <= d;\n";
    }
    project.write("design.sv", rtl + "endmodule\n");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto state = service.call("get_state_elements", {{"sv_module", "top"}, {"limit", 1}});
    REQUIRE(state.at("total_count") == 501);
    REQUIRE(state.at("items").size() == 1);
    REQUIRE(state.at("truncated") == true);
}
TEST_CASE(
    "Wide known constants retain their exact value without narrowing the convenience integer") {
    Project project;
    project.write("design.sv", "module top #(parameter logic [127:0] WIDE = "
                               "128'hfedcba98765432100123456789abcdef); endmodule\n");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto parameter = service.call("get_instance_parameters", {{"instance_path", "top"}})
                               .at("parameters")
                               .at("items")
                               .front();
    REQUIRE(parameter.at("integer_value").is_null());
    REQUIRE(parameter.at("value") == "128'hfedcba98765432100123456789abcdef");
}
TEST_CASE("Omitting hierarchy depth preserves the complete hierarchy beyond fifty levels") {
    Project project;
    std::string rtl = "module stage_0; endmodule\n";
    for (int index = 1; index <= 55; ++index) {
        rtl += "module stage_" + std::to_string(index) + "; stage_" + std::to_string(index - 1) +
               " u(); endmodule\n";
    }
    project.write("design.sv", rtl + "module top; stage_55 u(); endmodule\n");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    auto node = service.call("get_hierarchy", {}).at("roots").front();
    for (int index = 0; index < 56; ++index) {
        node = Json(node.at("children").front());
    }
    REQUIRE(node.at("sv_module") == "stage_0");
    REQUIRE_THROWS_AS(service.call("get_hierarchy", {{"max_depth", -1}}), std::invalid_argument);
}
TEST_CASE("Hierarchy child indexes preserve order and requested depth") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto root = service.call("get_hierarchy", {{"max_depth", 1}}).at("roots").front();
    REQUIRE(root.at("children").size() == 3);
    REQUIRE(root.at("children")[0].at("path") == "top.u_a");
    REQUIRE(root.at("children")[1].at("path") == "top.u_b");
    REQUIRE(root.at("children")[2].at("path") == "top.generated");
    for (const auto& child : root.at("children")) {
        REQUIRE(child.at("children").empty());
    }
    const auto depth = GENERATE(0, 1, 2);
    const auto generated =
        service.call("get_hierarchy", {{"root", "top.generated"}, {"max_depth", depth}})
            .at("roots")
            .front();
    if (depth == 0) {
        REQUIRE(generated.at("children").empty());
        return;
    }
    REQUIRE(generated.at("children").size() == 2);
    REQUIRE(generated.at("children")[0].at("path") == "top.generated[0]");
    REQUIRE(generated.at("children")[1].at("path") == "top.generated[1]");
    REQUIRE(generated.at("children")[0].at("children").size() == (depth == 1 ? 0 : 1));
}

TEST_CASE("Reload replaces hierarchy and exact instance indexes") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE(service.call("inspect_instance", {{"instance_path", "top.u_a"}})
                .at("instance")
                .at("sv_module") == "leaf");
    project.write("design.sv",
                  "module replacement; endmodule\nmodule top; replacement u(); endmodule\n");
    (void)service.call("project_load", project.arguments());
    REQUIRE(service.call("get_hierarchy", {}).at("roots").front().at("children").size() == 1);
    REQUIRE(service.call("inspect_instance", {{"instance_path", "top.u"}})
                .at("instance")
                .at("sv_module") == "replacement");
    REQUIRE_THROWS_AS(service.call("inspect_instance", {{"instance_path", "top.u_a"}}),
                      std::invalid_argument);
    REQUIRE_THROWS_AS(service.call("get_hierarchy", {{"root", "top.generated"}}),
                      std::invalid_argument);
}

TEST_CASE("Partial loading preserves local facts despite missing child implementations") {
    Project project;
    project.write("fragment.sv", R"sv(
module fragment #(parameter int WIDTH=7)(input logic [WIDTH-1:0] data);
  missing_child u(.data(data));
  logic [WIDTH-1:0] local_copy;
  assign local_copy = data;
endmodule
)sv");
    project.write("unselected.sv", "this file must never be parsed\n");
    SemanticService service;
    const Json args = {{"source_files", {project.path("fragment.sv").string()}},
                       {"top_module", "fragment"}};
    const auto loaded = service.call("project_load", args);
    REQUIRE(loaded.at("analysis_scope") == "fragment");
    REQUIRE(loaded.at("completeness") == "not_verified");
    REQUIRE(loaded.at("parameter_context") == "standalone_top");
    REQUIRE(loaded.at("source_file_count") == 1);
    REQUIRE(loaded.at("diagnostic_error_count").get<int>() > 0);
    REQUIRE(service.call("describe_symbol", {{"identifier", "fragment.local_copy"}}).at("width") ==
            7);
    REQUIRE(
        service.call("get_signal_writes", {{"signal", "fragment.local_copy"}}).at("total_count") ==
        1);
    REQUIRE(service.call("project_reload", {}).at("analysis_scope") == "fragment");
    REQUIRE(service.call("project_info", {}).at("metadata").at("dependency_resolution") ==
            "provided_files_only");
    project.write("child.sv", "module missing_child(input logic [6:0] data); endmodule\n");
    auto expanded = args;
    expanded["source_files"].push_back(project.path("child.sv").string());
    REQUIRE(service.call("project_load", expanded).at("diagnostic_error_count") == 0);
    REQUIRE(service.call("find_instance", {{"query", "fragment.u"}}).at("sv_module") ==
            "missing_child");
}

TEST_CASE("Partial loading supports ordered packages includes and build defines") {
    Project project;
    project.write("width.svh", "`define WIDTH 9\n");
    project.write(
        "types.sv",
        "`include \"width.svh\"\npackage types; typedef logic [`WIDTH-1:0] word_t; endpackage\n");
    project.write("fragment.sv", "module fragment(input types::word_t data); `ifdef EXTRA\nlogic "
                                 "present;\n`endif\nendmodule\n");
    SemanticService service;
    REQUIRE(service
                .call("project_load",
                      {{"source_files",
                        {project.path("types.sv").string(), project.path("fragment.sv").string()}},
                       {"top_module", "fragment"},
                       {"include_directories", {project.path("").string()}},
                       {"defines", {{"EXTRA", nullptr}}}})
                .at("diagnostic_error_count") == 0);
    REQUIRE(
        service.call("get_ports", {{"sv_module", "fragment"}}).at("items").front().at("width") ==
        9);
    REQUIRE(service.call("find_symbol", {{"name", "present"}}).at("match_count") == 1);
    REQUIRE(service.call("project_info", {}).at("summary").at("completeness") == "not_verified");
}

TEST_CASE("Invalid partial inputs leave the previous design active") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto previous = service.call("project_info", {});
    const auto sources = GENERATE(Json::array(), Json::array({"relative.sv"}),
                                  Json::array({"/missing/fragment.sv"}));
    REQUIRE_THROWS_AS(
        service.call("project_load", {{"source_files", sources}, {"top_module", "leaf"}}),
        std::invalid_argument);
    REQUIRE(service.call("project_info", {}) == previous);
}

TEST_CASE("A fragment top does not inherit unavailable parent parameter overrides") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE(service.call("get_instance_parameters", {{"instance_path", "top.u_a"}})
                .at("parameters")
                .at("items")
                .front()
                .at("integer_value") == 32);
    (void)service.call("project_load", {{"source_files", {project.path("design.sv").string()}},
                                        {"top_module", "leaf"},
                                        {"include_directories", nullptr},
                                        {"defines", nullptr}});
    REQUIRE(service.call("get_instance_parameters", {{"instance_path", "leaf"}})
                .at("parameters")
                .at("items")
                .front()
                .at("integer_value") == 8);
    REQUIRE(service.call("list_instances", {}).at("total_count") == 1);
    const auto active = service.call("project_info", {});
    std::filesystem::remove(project.path("design.sv"));
    REQUIRE_THROWS_AS(service.call("project_reload", {}), std::invalid_argument);
    REQUIRE(service.call("project_info", {}) == active);
    project.write("design.sv", hierarchy_rtl);
    REQUIRE(service.call("project_load", project.arguments()).at("analysis_scope") == "fragment");
}
TEST_CASE("Focused inspections preserve selected sections and identity") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto tool = GENERATE("inspect_module", "inspect_instance", "inspect_signal");
    Json args = {{"sv_module", "leaf"}, {"instance_path", "top.u_a"}, {"signal", "top.data"}};
    const auto complete = service.call(tool, args);
    for (const auto& [field, value] : complete.items()) {
        args["fields"] = Json::array({field});
        if (field == "definition" || field == "instance" || field == "symbol") {
            continue;
        }
        const auto focused = service.call(tool, args);
        REQUIRE(focused.size() == 2);
        REQUIRE(focused.at(field) == value);
    }
    args["fields"] = Json::array();
    REQUIRE(service.call(tool, args).size() == 1);
    args["fields"] = Json::array({"not_a_section"});
    REQUIRE_THROWS_AS(service.call(tool, args), std::invalid_argument);
    args["fields"] = Json::array({42});
    REQUIRE_THROWS(service.call(tool, args));
    args["fields"] = nullptr;
    REQUIRE_THROWS_AS(service.call(tool, args), std::invalid_argument);
}

TEST_CASE("Inspection defaults return signatures without extra sections") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto module = service.call("inspect_module", {{"sv_module", "leaf"}});
    REQUIRE(module.size() == 3);
    REQUIRE(module.contains("definition"));
    REQUIRE(module.contains("parameters"));
    REQUIRE(module.contains("ports"));
    const auto instance = service.call("inspect_instance", {{"instance_path", "top.u_a"}});
    REQUIRE(instance.size() == 3);
    REQUIRE(instance.contains("instance"));
    REQUIRE(instance.contains("parameters"));
    REQUIRE(instance.contains("connections"));
    REQUIRE(service.call("inspect_instance", {{"instance_path", "top"}, {"fields", {"children"}}})
                .at("children")
                .at("total_count") == 4);
}

TEST_CASE("Reference direction filters include compound accesses") {
    Project project;
    project.write("design.sv", "module top; int count; initial count += 1; endmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto kind = GENERATE("read", "write", "read_write");
    const auto result = service.call("get_references", {{"symbol", "top.count"}, {"kind", kind}});
    REQUIRE(result.at("total_count") == 1);
    REQUIRE(result.at("items").front().at("kind") == "read_write");
}

TEST_CASE("Read write reference filter combines access directions without duplicating sites") {
    Project project;
    project.write(
        "design.sv",
        "module top; int count; initial begin count = count + 1; count += 2; end endmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto result =
        service.call("get_references", {{"symbol", "top.count"}, {"kind", "read_write"}});
    REQUIRE(result.at("total_count") == 3);
    REQUIRE(result.at("items")[0].at("kind") == "write");
    REQUIRE(result.at("items")[1].at("kind") == "read");
    REQUIRE(result.at("items")[2].at("kind") == "read_write");
    REQUIRE(service.call("get_references", {{"symbol", "top.count"}, {"kind", "read"}})
                .at("total_count") == 2);
    REQUIRE(service.call("get_references", {{"symbol", "top.count"}, {"kind", "write"}})
                .at("total_count") == 2);
    REQUIRE(service.call("get_references", {{"symbol", "top.count"}, {"kind", "declaration"}})
                .at("total_count") == 1);
}

TEST_CASE("References accept qualified register names and stable identifiers") {
    Project project;
    project.write("design.sv", R"sv(
module cpu(input logic clk, input logic next_bank, output logic bank);
  logic bank_sel_ff;
  always_ff @(posedge clk) bank_sel_ff <= next_bank;
  assign bank = bank_sel_ff;
endmodule
)sv");
    auto arguments = project.arguments();
    arguments["top_module"] = "cpu";
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", arguments).at("diagnostic_error_count") == 0);
    const auto symbols = service.call("find_symbol", {{"name", "bank_sel_ff"}});
    REQUIRE(symbols.at("match_count") == 1);
    const auto& symbol = symbols.at("symbols").front();
    REQUIRE(symbol.at("qualified_name") == "cpu.bank_sel_ff");
    const auto by_name = service.call("get_references", {{"symbol", "cpu.bank_sel_ff"}});
    REQUIRE(by_name == service.call("get_references", {{"symbol", symbol.at("symbol_id")}}));
    REQUIRE(service.call("get_references", {{"symbol", "cpu.bank_sel_ff"}, {"kind", "read"}})
                .at("total_count") == 1);
    REQUIRE(service.call("get_references", {{"symbol", "cpu.bank_sel_ff"}, {"kind", "write"}})
                .at("total_count") == 1);
    REQUIRE(service.call("get_references", {{"symbol", "cpu.bank_sel_ff"}, {"kind", "read_write"}})
                .at("total_count") == 2);
}

TEST_CASE("Focused module inspections validate target kind before selecting sections") {
    Project project;
    project.write("design.sv", "package types; endpackage\nmodule top; logic data; endmodule\n");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto target = GENERATE("top.data", "types");
    const auto fields = GENERATE(Json::array(), Json::array({"declaration_count"}),
                                 Json::array({"diagnostic_count"}));
    REQUIRE_THROWS_AS(service.call("inspect_module", {{"sv_module", target}, {"fields", fields}}),
                      std::invalid_argument);
}

TEST_CASE("Focused signature filters apply before bounded pagination") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto tool = GENERATE("inspect_module", "inspect_instance");
    const auto result = service.call(tool, {{"sv_module", "leaf"},
                                            {"instance_path", "top.u_a"},
                                            {"fields", {"parameters"}},
                                            {"parameter_names", {"WIDTH"}},
                                            {"limit", 1}});
    REQUIRE(result.at("parameters").at("parameters").at("total_count") == 1);
    REQUIRE(result.at("parameters").at("parameters").at("items").front().at("integer_value") ==
            (std::string_view(tool) == "inspect_module" ? 8 : 32));
    const auto field = std::string_view(tool) == "inspect_module" ? "ports" : "connections";
    const auto ports = service.call(tool, {{"sv_module", "leaf"},
                                           {"instance_path", "top.u_a"},
                                           {"fields", Json::array({field})},
                                           {"port_names", {"o"}},
                                           {"limit", 1}});
    REQUIRE(ports.at(field).at("total_count") == 1);
    REQUIRE(ports.at(field).at("items").size() == 1);
    REQUIRE(ports.at(field).at("truncated") == false);
}

TEST_CASE("Large module signatures expose truncation and filter before the limit") {
    Project project;
    std::string rtl = "module top #(parameter int P0=0";
    for (int index = 1; index < 120; ++index) {
        rtl += ", parameter int P" + std::to_string(index) + "=" + std::to_string(index);
    }
    rtl += ")(input logic port0";
    for (int index = 1; index < 120; ++index) {
        rtl += ", input logic port" + std::to_string(index);
    }
    project.write("design.sv", rtl + "); endmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto result = service.call("inspect_module", {{"sv_module", "top"}});
    const auto& parameters = result.at("parameters").at("parameters");
    REQUIRE(parameters.at("total_count") == 120);
    REQUIRE(parameters.at("items").size() == 100);
    REQUIRE(parameters.at("truncated") == true);
    REQUIRE(result.at("ports").at("total_count") == 120);
    REQUIRE(result.at("ports").at("items").size() == 100);
    REQUIRE(result.at("ports").at("truncated") == true);
    const auto selected = service.call("inspect_module", {{"sv_module", "top"},
                                                          {"parameter_names", {"P119"}},
                                                          {"port_names", {"port119"}},
                                                          {"limit", 1}});
    REQUIRE(selected.at("parameters").at("parameters").at("items").front().at("name") == "P119");
    REQUIRE_FALSE(selected.at("parameters").at("parameters").at("truncated").get<bool>());
    REQUIRE(selected.at("ports").at("items").front().at("name") == "port119");
    REQUIRE_FALSE(selected.at("ports").at("truncated").get<bool>());
}

TEST_CASE("Focused inspections do not evaluate unrequested query sections") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE(service
                .call("inspect_instance", {{"instance_path", "top.u_a"},
                                           {"fields", {"children"}},
                                           {"parameter_names", 42},
                                           {"port_names", 42}})
                .size() == 2);
    REQUIRE(service
                .call("inspect_module", {{"sv_module", "leaf"},
                                         {"fields", {"declaration_count"}},
                                         {"parameter_names", 42},
                                         {"port_names", 42}})
                .size() == 2);
    REQUIRE(service
                .call("inspect_signal", {{"signal", "top.data"},
                                         {"fields", {"reference_count"}},
                                         {"kind", "invalid_unused_kind"}})
                .size() == 2);
}
} // namespace slang_mcp::test
