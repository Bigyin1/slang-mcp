#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>

namespace slang_mcp::test {
TEST_CASE("Project lifecycle and nested hierarchy") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    const auto summary = service.call("project_load", project.arguments());
    REQUIRE(summary.at("diagnostic_error_count") == 0);
    REQUIRE(summary.at("top_modules") == Json::array({"top"}));
    REQUIRE(service.call("project_info", {}).at("summary") == summary);
    REQUIRE(service.call("project_info", {})
                .at("slang_version")
                .get<std::string>()
                .starts_with("12.1."));
    REQUIRE(service.call("get_hierarchy", {}).at("roots").front().at("path") == "top");
    REQUIRE(service.call("describe_instance", {{"path", "top.u_b.u_c"}}).at("sv_module") == "leaf");
    REQUIRE(service.call("list_instances", {{"sv_module", "leaf"}}).at("total_count") == 4);
    REQUIRE(service.call("get_hierarchy", {{"root", "top.u_b"}, {"max_depth", 1}})
                .at("roots")
                .front()
                .at("path") == "top.u_b");
}

TEST_CASE("Declared defaults remain separate from effective instance parameters") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE(service.call("get_parameters", {{"target", "leaf"}})
                .at("parameters")
                .at("items")
                .front()
                .at("integer_value") == 8);
    REQUIRE(service.call("get_ports", {{"sv_module", "leaf"}}).at("items").front().at("width") ==
            8);
    REQUIRE(
        service
            .call("get_instance_parameters", {{"instance_path", "top.u_a"}, {"names", {"WIDTH"}}})
            .at("parameters")
            .at("items")
            .front()
            .at("integer_value") == 32);
    const auto facts = service.call(
        "list_instance_facts",
        {{"sv_module", "leaf"}, {"parameter_names", {"WIDTH"}}, {"port_names", {"i"}}});
    REQUIRE(facts.at("total_count") == 4);
    for (const auto& fact : facts.at("items")) {
        REQUIRE(fact.at("parameters").at("items").front().at("integer_value") == 32);
        REQUIRE(fact.at("connections").at("items").size() == 1);
    }
}

TEST_CASE("Failed reload preserves active compilation and semantic snapshots") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    const auto before = service.call("semantic_diff", {});
    std::filesystem::remove(project.path("design.sv"));
    REQUIRE_THROWS_AS(service.call("project_reload", {}), std::invalid_argument);
    REQUIRE(service.call("semantic_diff", {}) == before);
    REQUIRE(service.call("project_info", {}).at("summary").at("top_modules") ==
            Json::array({"top"}));
}

TEST_CASE("Successful reload reports effective parameter changes") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    project.write("design.sv", "module top #(parameter int WIDTH=19); endmodule\n");
    (void)service.call("project_reload", {});
    REQUIRE(service.call("semantic_diff", {}).at("status") == "compared");
    REQUIRE_FALSE(service.call("semantic_diff", {}).at("changes").at("items").empty());
    REQUIRE(service.call("get_instance_parameters", {{"instance_path", "top"}})
                .at("parameters")
                .at("items")
                .front()
                .at("integer_value") == 19);
}

TEST_CASE("Sessions without diff snapshots retain queries and atomic reload") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    REQUIRE_THROWS_AS(service.call("semantic_diff", {}), std::invalid_argument);
    REQUIRE(service.call("list_instances", {{"sv_module", "leaf"}}).at("total_count") == 4);
    project.write("design.sv", "module top #(parameter int WIDTH=19); endmodule\n");
    (void)service.call("project_reload", {});
    const auto parameters = service.call("get_instance_parameters", {{"instance_path", "top"}});
    REQUIRE(parameters.at("parameters").at("items").front().at("integer_value") == 19);
    std::filesystem::remove(project.path("design.sv"));
    REQUIRE_THROWS_AS(service.call("project_reload", {}), std::invalid_argument);
    REQUIRE(service.call("get_instance_parameters", {{"instance_path", "top"}}) == parameters);
    REQUIRE_THROWS_AS(service.call("semantic_diff", {}), std::invalid_argument);
}

TEST_CASE("Bounds and invalid inputs are explicit errors") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service;
    REQUIRE_THROWS_AS(service.call("project_info", {}), std::invalid_argument);
    (void)service.call("project_load", project.arguments());
    const auto limit = GENERATE(0, -1, 501);
    REQUIRE_THROWS_AS(service.call("list_instances", {{"limit", limit}}), std::invalid_argument);
    REQUIRE_THROWS_AS(
        service.call("trace_connectivity", {{"signal", "top.data"}, {"max_depth", 51}}),
        std::invalid_argument);
    REQUIRE_THROWS_AS(service.call("get_hierarchy", {{"root", "missing"}}), std::invalid_argument);
    REQUIRE_THROWS_AS(service.call("find_symbol", {{"name", ""}}), std::invalid_argument);
}

TEST_CASE("Source reads writes procedures and connectivity share compiler evidence") {
    Project project;
    project.write("design.sv", R"sv(
module child(input logic d, output logic q); assign q = d; endmodule
module top(input logic a,b,output logic q);
  logic c,d,state;
  child u_child(.d(a), .q(c));
  assign d=c;
  always_comb q=d;
  always_ff @(posedge a) state <= b;
endmodule
)sv");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE(service.call("get_signal_reads", {{"signal", "top.c"}}).at("total_count") == 1);
    REQUIRE(service.call("get_signal_writes", {{"signal", "top.q"}}).at("total_count") == 1);
    const auto trace = service.call(
        "trace_connectivity", {{"signal", "top.a"}, {"direction", "loads"}, {"max_depth", 5}});
    REQUIRE(std::ranges::any_of(trace.at("paths").at("items"), [](const auto& path) {
        return path.at("end") == "top.q" && path.at("hops").size() == 5;
    }));
    REQUIRE(service.call("get_state_elements", {{"sv_module", "top"}})
                .at("items")
                .front()
                .at("signal")
                .at("qualified_name") == "top.state");
    REQUIRE(service.call("inspect_signal", {{"signal", "top.q"}}).at("drivers").at("total_count") ==
            1);
    REQUIRE(
        service.call("inspect_module", {{"sv_module", "child"}}).at("ports").at("total_count") ==
        2);
    REQUIRE(service.call("inspect_instance", {{"instance_path", "top.u_child"}})
                .at("connections")
                .at("total_count") == 2);
}

TEST_CASE("Lvalue indices are reads and system calls remain unknown") {
    Project project;
    project.write("design.sv", R"sv(
module top;
  logic [7:0] a,b,source;
  int index;
  initial {a[index], b[2:0]} = source[3:0];
  initial $display("%b", a);
endmodule
)sv");
    SemanticService service;
    (void)service.call("project_load", project.arguments());
    REQUIRE(service.call("get_signal_writes", {{"signal", "top.a"}}).at("total_count") == 1);
    REQUIRE(service.call("get_signal_reads", {{"signal", "top.a"}}).at("total_count") == 0);
    REQUIRE(service.call("get_signal_writes", {{"signal", "top.index"}}).at("total_count") == 0);
    REQUIRE(service.call("get_signal_reads", {{"signal", "top.index"}}).at("total_count") == 1);
    REQUIRE(service.call("get_references", {{"symbol", "top.a"}, {"kind", "unknown"}})
                .at("total_count") == 1);
}

TEST_CASE("Error diagnostics are accepted and grouped") {
    Project project;
    project.write("design.sv", "module top; missing u(); endmodule\n");
    SemanticService service;
    REQUIRE(
        service.call("project_load", project.arguments()).at("diagnostic_error_count").get<int>() >
        0);
    REQUIRE(
        service.call("get_diagnostics", {{"severity", "error"}}).at("returned_count").get<int>() >
        0);
    REQUIRE(service.call("summarize_diagnostics_by_code", {}).at("total_count").get<int>() > 0);
    REQUIRE(service.call("get_diagnostics", {{"severity", "ERROR"}}) ==
            service.call("get_diagnostics", {{"severity", "error"}}));
    REQUIRE(service.call("summarize_diagnostics_by_code", {{"severity", "Error"}}) ==
            service.call("summarize_diagnostics_by_code", {{"severity", "error"}}));
}

TEST_CASE("Partial syntax errors and unresolved dependencies stay visible together") {
    Project project;
    project.write("design.sv", R"sv(
module top(input logic a, output logic y);
  missing_child u_child();
  assign y = a
endmodule
)sv");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(
        service
            .call("project_load_partial",
                  {{"source_files", {project.path("design.sv").string()}}, {"top_module", "top"}})
            .at("diagnostic_error_count") >= 2);
    const auto result = service.call("get_diagnostics", {{"severity", "error"}});
    REQUIRE(result.at("analysis").at("analysis_scope") == "fragment");
    REQUIRE(result.at("analysis").at("completeness") == "not_verified");
    REQUIRE(std::ranges::any_of(result.at("diagnostics"), [](const auto& item) {
        return item.at("code") == "UnknownModule" &&
               item.at("scope_hint") == "possible_missing_dependency";
    }));
    REQUIRE(std::ranges::any_of(result.at("diagnostics"), [](const auto& item) {
        return item.at("scope_hint") == "unclassified";
    }));
    const auto bounded = service.call("get_diagnostics", {{"severity", "error"}, {"limit", 1}});
    REQUIRE(bounded.at("returned_count") == 1);
    REQUIRE(bounded.at("total_count") == result.at("total_count"));
    REQUIRE(bounded.at("truncated") == true);
    REQUIRE(service.call("inspect_module", {{"sv_module", "top"}, {"fields", {"ports"}}})
                .at("ports")
                .at("total_count") == 2);
}

TEST_CASE("Type errors do not become expected fragment boundary errors") {
    Project project;
    project.write("design.sv", R"sv(
module top(input logic a, output logic y);
  assign y = a.no_field;
endmodule
)sv");
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call(
        "project_load_partial",
        {{"source_files", {project.path("design.sv").string()}}, {"top_module", "top"}});
    const auto result = service.call("get_diagnostics", {{"severity", "error"}});
    REQUIRE_FALSE(result.at("diagnostics").empty());
    for (const auto& diagnostic : result.at("diagnostics")) {
        REQUIRE(diagnostic.at("scope_hint") == "unclassified");
        REQUIRE(diagnostic.at("severity") == "error");
    }
    REQUIRE(service.call("inspect_module", {{"sv_module", "top"}, {"fields", {"ports"}}})
                .at("ports")
                .at("total_count") == 2);
}
} // namespace slang_mcp::test
