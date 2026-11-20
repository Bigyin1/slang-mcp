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
    REQUIRE(service.call("get_hierarchy", {}).at("items").front().at("path") == "top");
    REQUIRE(service.call("describe_instance", {{"path", "top.u_b.u_c"}}).at("sv_module") == "leaf");
    REQUIRE(service.call("list_instances", {{"sv_module", "leaf"}}).at("total_count") == 4);
    REQUIRE(service.call("get_hierarchy", {{"root", "top.u_b"}, {"max_depth", 1}})
                .at("items")
                .front()
                .at("path") == "top.u_b");
}

TEST_CASE("Project configuration pages preserve the supplied values") {
    Project project;
    project.write("top.sv", "module top; endmodule\n");
    project.write("empty.sv", "// Empty compilation source.\n");
    const auto root = project.path("top.sv").parent_path();
    const auto other = project.path("empty.sv").string();
    std::filesystem::create_directory(root / "headers");
    const Json sources = {other, project.path("top.sv").string(), other};
    const Json includes = {(root / "headers").string(), root.string()};
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load",
                       {{"top_module", "top"},
                        {"source_files", sources},
                        {"include_directories", includes},
                        {"defines", {{"FLAG", nullptr}, {"EMPTY", ""}, {"RHS", "2"}}}});
    REQUIRE(service.call("project_info", {{"section", "source_files"}}).at("items") == sources);
    REQUIRE(service.call("project_info", {{"section", "include_directories"}}).at("items") ==
            includes);
    REQUIRE(service.call("project_info", {{"section", "defines"}}).at("items") ==
            Json::array({"EMPTY=", "FLAG", "RHS=2"}));
}

TEST_CASE("Project info validates configuration page arguments") {
    Project project;
    project.write("design.sv", hierarchy_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto invalid = GENERATE(
        R"({"limit":1})", R"({"cursor":"page"})", R"({"section":"unknown"})", R"({"section":null})",
        R"({"section":"source_files","limit":0})", R"({"section":"source_files","limit":501})",
        R"({"section":"source_files","limit":1.5})", R"({"section":"source_files","cursor":null})");
    REQUIRE_THROWS_AS(service.call("project_info", Json::parse(invalid)), std::invalid_argument);
}

TEST_CASE("File diagnostics accept physical paths even with a line directive") {
    Project project;
    project.write("design.sv", "module top;\n`line 40 \"virtual.sv\" 0\n"
                               "`include \"absent.svh\"\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    auto args = project.arguments();
    (void)service.call("project_load", args);
    const auto path = project.path("design.sv").string();
    const Json filter = {{"file", path}, {"code", "CouldNotOpenIncludeFile"}};
    const auto response = service.call("get_diagnostics", filter);
    REQUIRE(response.at("total_count") == 1);
    const auto& diagnostic = response.at("diagnostics").front();
    REQUIRE(diagnostic.at("scope_hint") == "possible_missing_dependency");
    REQUIRE(diagnostic.at("severity") == "error");
    REQUIRE(diagnostic.at("location").at("line") == 40);
    REQUIRE(service.call("get_diagnostics", {{"file", diagnostic.at("location").at("filename")}})
                .at("diagnostics") == response.at("diagnostics"));
    args["top_module"] = "missing";
    try {
        (void)service.call("project_load", args);
        FAIL("expected compilation failure");
    } catch (const CompilationError& error) {
        auto failed_filter = filter;
        failed_filter["attempt_id"] = error.attempt_id;
        REQUIRE(service.call("get_diagnostics", failed_filter).at("diagnostics") ==
                response.at("diagnostics"));
    }
}

TEST_CASE("File context reports which header actually won include search") {
    Project project;
    project.write("design.sv", "module top;\n`include \"width.svh\"\nendmodule\n");
    const auto first = project.path("first");
    const auto second = project.path("second");
    std::filesystem::create_directory(first);
    std::filesystem::create_directory(second);
    project.write("first/width.svh", "localparam int W = 8;\n");
    project.write("second/width.svh", "localparam int W = 16;\n");
    auto args = project.arguments();
    SemanticService service(SnapshotPolicy::Disabled);
    const Json query = {{"file", project.path("design.sv").string()}};
    const auto reverse = GENERATE(false, true);
    args["include_directories"] =
        reverse ? Json{second.string(), first.string()} : Json{first.string(), second.string()};
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    const auto context = service.call("project_info", query);
    REQUIRE(context.at("is_source") == true);
    REQUIRE(context.at("is_included") == false);
    REQUIRE(context.at("items").front().at("resolved_file") ==
            std::filesystem::canonical((reverse ? second : first) / "width.svh").string());
    REQUIRE(service.call("get_parameters", {{"target", "top"}})
                .at("parameters")
                .at("items")
                .front()
                .at("integer_value") == (reverse ? 16 : 8));
    const auto outside = service.call(
        "project_info", {{"file", ((reverse ? first : second) / "width.svh").string()}});
    REQUIRE(outside.at("is_source") == false);
    REQUIRE(outside.at("is_included") == false);
    REQUIRE(outside.at("items").empty());
}

TEST_CASE("File context keeps repeated includes, skips inactive directives and pages occurrences") {
    Project project;
    project.write("design.sv", "module top;\n`include \"shared.svh\"\n"
                               "`include \"shared.svh\"\n`ifdef NEVER_DEFINED\n"
                               "`include \"inactive.svh\"\n`endif\n"
                               "`include \"absent.svh\"\nendmodule\n");
    project.write("shared.svh", "`pragma once\nlocalparam int W = 8;\n");
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto file = project.path("shared.svh").string();
    const auto first = service.call("project_info", {{"file", file}, {"limit", 1}});
    REQUIRE(first.at("is_source") == false);
    REQUIRE(first.at("is_included") == true);
    REQUIRE(first.at("total_count") == 2);
    REQUIRE(first.at("items").front().at("directive").at("line") == 2);
    const Json next = {{"file", file}, {"cursor", first.at("next_cursor")}};
    REQUIRE(service.call("project_info", next).at("items").front().at("directive").at("line") == 3);
    const auto source =
        service.call("project_info", {{"file", project.path("design.sv").string()}});
    REQUIRE(source.at("total_count") == 3);
    REQUIRE(source.at("items").back().at("requested") == "absent.svh");
    REQUIRE(source.at("items").back().at("resolved_file").is_null());
    project.write("design.sv", "module top; endmodule\n");
    REQUIRE(service.call("project_info", next).at("total_count") == 2);
    (void)service.call("project_load", project.arguments());
    REQUIRE_THROWS_AS(service.call("project_info", next), std::invalid_argument);
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
    REQUIRE(service
                .call("project_load", {{"source_files", {project.path("design.sv").string()}},
                                       {"top_module", "top"}})
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
    (void)service.call("project_load", {{"source_files", {project.path("design.sv").string()}},
                                        {"top_module", "top"}});
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
TEST_CASE("Compilation units control macro and unit declaration sharing") {
    Project project;
    const auto single_unit = GENERATE(true, false);
    SECTION("Macro lifetime") {
        project.write("first.sv", "`define SHARED_WIDTH 7\n");
        project.write("second.sv", "module top; logic [`SHARED_WIDTH-1:0] data; endmodule\n");
    }
    SECTION("Unit declaration lifetime") {
        project.write("first.sv", "typedef logic [6:0] shared_t;\n");
        project.write("second.sv", "module top; shared_t data; endmodule\n");
    }
    SemanticService service;
    auto arguments = project.arguments({"first.sv", "second.sv"});
    arguments["single_unit"] = single_unit;
    const auto summary = service.call("project_load", arguments);
    REQUIRE((summary.at("diagnostic_error_count") == 0) == single_unit);
    REQUIRE(summary.at("single_unit") == single_unit);
    REQUIRE(service.call("project_info", {}).at("single_unit") == single_unit);
    REQUIRE(service.call("get_diagnostics", {}).at("analysis").at("single_unit") == single_unit);
    REQUIRE(service.call("project_reload", {}).at("single_unit") == single_unit);
}

TEST_CASE("Packages includes and predefined macros work in separate units") {
    Project project;
    std::filesystem::create_directory(project.path("includes"));
    project.write("includes/common.svh", "typedef logic [`WIDTH-1:0] word_t;\n");
    project.write("first.sv", "`include \"common.svh\"\npackage shared; parameter int N=7; "
                              "endpackage\nmodule child(input word_t a); endmodule\n");
    project.write("second.sv",
                  "`include \"common.svh\"\nmodule top; word_t a; child u(a); initial a "
                  "= shared::N; endmodule\n");
    SemanticService service;
    auto arguments = project.arguments({"first.sv", "second.sv"});
    arguments["single_unit"] = false;
    arguments["include_directories"] = {project.path("includes").string()};
    arguments["defines"] = {{"WIDTH", "7"}};
    REQUIRE(service.call("project_load", arguments).at("diagnostic_error_count") == 0);
    REQUIRE(service.call("get_ports", {{"sv_module", "child"}}).at("items").front().at("width") ==
            7);
}

TEST_CASE("Single unit defaults preserve ordered source preprocessing") {
    Project project;
    project.write("first.sv", "`define WIDTH 7\n");
    project.write("second.sv", "module top(input logic [`WIDTH-1:0] a); endmodule\n");
    SemanticService service;
    REQUIRE(service.call("project_load", project.arguments({"first.sv", "second.sv"}))
                .at("single_unit") == true);
    REQUIRE(service.call("get_ports", {{"sv_module", "top"}}).at("items").front().at("width") == 7);
    REQUIRE(service.call("project_load", project.arguments({"second.sv", "first.sv"}))
                .at("diagnostic_error_count") > 0);
}

TEST_CASE("Invalid compilation unit modes preserve the active project") {
    Project project;
    project.write("design.sv", "module top; endmodule\n");
    SemanticService service;
    auto arguments = project.arguments();
    arguments["single_unit"] = false;
    const auto summary = service.call("project_load", arguments);
    const auto invalid =
        GENERATE(Json(nullptr), Json(0), Json(1), Json("false"), Json::array(), Json::object());
    arguments["single_unit"] = invalid;
    REQUIRE_THROWS_AS(service.call("project_load", arguments), std::invalid_argument);
    REQUIRE(service.call("project_info", {}).at("summary") == summary);
    REQUIRE(service.call("project_reload", {}).at("single_unit") == false);
}

} // namespace slang_mcp::test
