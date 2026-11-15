#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>

namespace slang_mcp::test {
TEST_CASE("Preprocessing preserves ordered packages includes and defines") {
    Project project;
    project.write("defs.svh", "`define WIDTH 13\n");
    project.write(
        "types.sv",
        "`include \"defs.svh\"\npackage types; typedef logic [`WIDTH-1:0] word_t; endpackage\n");
    project.write(
        "design.sv",
        "module top; types::word_t data; `ifdef EXTRA\nlogic added;\n`endif\nendmodule\n");
    project.write("includes.f", project.path("").string());
    auto args = project.arguments({"types.sv", "design.sv"});
    args["include_directory_lists"] = {project.path("includes.f").string()};
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
    const auto loaded = service.call("project_load_partial", args);
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
    REQUIRE(service.call("project_load_partial", expanded).at("diagnostic_error_count") == 0);
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
                .call("project_load_partial",
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
        service.call("project_load_partial", {{"source_files", sources}, {"top_module", "leaf"}}),
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
    (void)service.call("project_load_partial",
                       {{"source_files", {project.path("design.sv").string()}},
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
    REQUIRE_FALSE(service.call("project_load", project.arguments()).contains("analysis_scope"));
}
} // namespace slang_mcp::test
