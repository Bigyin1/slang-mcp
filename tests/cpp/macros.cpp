#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>
#include <catch2/matchers/catch_matchers.hpp>

namespace slang_mcp::test {
namespace {
Json expand(SemanticService& service, const Project& project, int line, int column = 1) {
    return service.call(
        "expand_macro",
        {{"file", project.path("design.sv").string()}, {"line", line}, {"column", column}});
}

std::string compact(const Json& result) {
    auto text = result.at("expanded_text").get<std::string>();
    std::erase_if(text, [](char value) {
        return value == ' ' || value == '\t' || value == '\r' || value == '\n';
    });
    return text;
}
} // namespace

TEST_CASE("Macro expansion reports macro-created modules and pasted signal names") {
    Project project;
    project.write("design.sv", "`define DECL(n,w) logic [(w)-1:0] n``_ff;\n"
                               "`define WRAP(n) module n; `DECL(bank_sel,2) endmodule\n"
                               "`WRAP(cpu)\n");
    auto args = project.arguments();
    args["top_module"] = "cpu";
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    const auto result = expand(service, project, 3);
    REQUIRE(result.at("name") == "WRAP");
    REQUIRE(result.at("invocation").at("line") == 3);
    REQUIRE(result.at("definition").at("line") == 2);
    REQUIRE(compact(result) == "modulecpu;logic[(2)-1:0]bank_sel_ff;endmodule");
    REQUIRE_FALSE(result.at("truncated").get<bool>());
    REQUIRE(result.at("total_bytes") == result.at("expanded_text").get<std::string>().size());
    REQUIRE(service.call("describe_symbol", {{"identifier", "cpu.bank_sel_ff"}}).at("width") == 2);
    const auto described = service.call(
        "describe_symbol", {{"identifier", "cpu.bank_sel_ff"}, {"include_origin", true}});
    const auto& origin = described.at("origin");
    REQUIRE(origin.at("complete") == true);
    REQUIRE(origin.at("invocation").at("line") == 3);
    REQUIRE(origin.at("invocation").at("column") == 1);
    REQUIRE(origin.at("macros").size() == 2);
    REQUIRE(origin.at("macros").at(0).at("name") == "WRAP");
    REQUIRE(origin.at("macros").at(0).at("definition").at("line") == 2);
    REQUIRE(origin.at("macros").at(1).at("name") == "DECL");
    REQUIRE(origin.at("macros").at(1).at("definition").at("line") == 1);
}

TEST_CASE("Macro expansion uses active definitions from includes and redefinitions") {
    Project project;
    project.write("defs.svh", "`define VALUE 4\n");
    project.write("design.sv", "`include \"defs.svh\"\nmodule top;\n"
                               "localparam int A=`VALUE;\n`undef VALUE\n`define VALUE 9\n"
                               "localparam int B=`VALUE;\nendmodule\n");
    auto args = project.arguments();
    args["include_directories"] = {project.path("").string()};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    const auto first = expand(service, project, 3, 18);
    REQUIRE(compact(first) == "4");
    REQUIRE(first.at("definition").at("filename").get<std::string>().ends_with("defs.svh"));
    const auto second = expand(service, project, 6, 18);
    REQUIRE(compact(second) == "9");
    REQUIRE(second.at("definition").at("line") == 5);
}

TEST_CASE("Macro expansion respects compilation-unit boundaries") {
    Project project;
    project.write("defs.sv", "`define WIDTH 4\n");
    project.write("design.sv", "`ifndef WIDTH\n`define WIDTH 9\n`endif\n"
                               "module top; localparam int N=`WIDTH; endmodule\n");
    auto args = project.arguments({"defs.sv", "design.sv"});
    const auto single_unit = GENERATE(true, false);
    args["single_unit"] = single_unit;
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    REQUIRE(compact(expand(service, project, 4, 30)) == (single_unit ? "4" : "9"));
}

TEST_CASE("Configured and empty macros have real recorded expansions") {
    Project project;
    project.write("design.sv", "module top;\nlocalparam int N=`FLAG;\n`EMPTY\nendmodule\n");
    auto args = project.arguments();
    args["defines"] = {{"FLAG", nullptr}, {"EMPTY", ""}};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    REQUIRE(compact(expand(service, project, 2, 18)) == "1");
    const auto empty = expand(service, project, 3);
    REQUIRE(empty.at("expanded_text") == "");
    REQUIRE(empty.at("total_bytes") == 0);
    REQUIRE_FALSE(empty.at("truncated").get<bool>());
}

TEST_CASE("Inactive and intrinsic calls are not guessed from macro definitions") {
    Project project;
    project.write("design.sv", "`define VALUE 4\nmodule top;\n`ifdef ABSENT\n"
                               "localparam int N=`VALUE;\n`endif\n"
                               "localparam int LINE=`__LINE__;\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    REQUIRE_THROWS_AS(expand(service, project, 4, 18), std::invalid_argument);
    REQUIRE_THROWS_AS(expand(service, project, 6, 21), std::invalid_argument);
    REQUIRE_THROWS_AS(expand(service, project, 1, 9), std::invalid_argument);
}

TEST_CASE("Macro preprocessing errors do not masquerade as empty successful expansions") {
    Project project;
    project.write("design.sv", "`define ADD(a,b) a+b\nmodule top;\n"
                               "localparam int N=`ADD(1);\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") != 0);
    REQUIRE_THROWS_AS(expand(service, project, 3, 18), std::invalid_argument);
}

TEST_CASE("Include filename macros expose the consumed filename token") {
    Project project;
    project.write("body.svh", "logic included_signal;\n");
    project.write("design.sv",
                  "`define FILE \"body.svh\"\nmodule top;\n`include `FILE\nendmodule\n");
    auto args = project.arguments();
    args["include_directories"] = {project.path("").string()};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    REQUIRE(compact(expand(service, project, 3, 10)) == "\"body.svh\"");
}

TEST_CASE("Macro-generated directives fail explicitly instead of omitting included declarations") {
    Project project;
    project.write("body.svh", "logic included_signal;\n");
    project.write("design.sv",
                  "`define BODY `include \"body.svh\"\nmodule top;\n`BODY\nendmodule\n");
    auto args = project.arguments();
    args["include_directories"] = {project.path("").string()};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    REQUIRE_THROWS_WITH(expand(service, project, 3),
                        "macro-generated preprocessing directives are not supported");
}

TEST_CASE("Macro output remains inspectable with missing design dependencies") {
    Project project;
    project.write("design.sv",
                  "`define WRAP module top; logic local_flag; missing_child u(); endmodule\n"
                  "`WRAP\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") != 0);
    const auto result = expand(service, project, 2);
    REQUIRE(compact(result) == "moduletop;logiclocal_flag;missing_childu();endmodule");
    REQUIRE(service.call("find_symbol", {{"name", "local_flag"}}).at("match_count") == 1);
}

TEST_CASE("Parser recovery does not invent tokens in macro output") {
    Project project;
    project.write("design.sv", "`define BAD logic ;\nmodule top;\n`BAD\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") != 0);
    REQUIRE(compact(expand(service, project, 3)) == "logic;");
}

TEST_CASE("Macro coordinates use physical lines and byte columns") {
    Project project;
    project.write("design.sv", "`define VALUE 7\r\n`line 500 \"virtual.sv\" 0\r\n"
                               "module top; localparam int N=`VALUE; endmodule\r\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto result = expand(service, project, 3, 30);
    REQUIRE(compact(result) == "7");
    REQUIRE(result.at("invocation").at("line") == 3);
    REQUIRE(result.at("invocation").at("filename").get<std::string>().ends_with("design.sv"));
    REQUIRE_THROWS_AS(expand(service, project, 500, 29), std::invalid_argument);
}

TEST_CASE("Macro columns count UTF-8 bytes and tabs rather than display characters") {
    Project project;
    const std::string prefix = "\t/*ж*/ localparam int N=";
    project.write("design.sv", "`define VALUE 7\nmodule top;\n" + prefix + "`VALUE;\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto result = expand(service, project, 3, static_cast<int>(prefix.size() + 1));
    REQUIRE(compact(result) == "7");
    REQUIRE(result.at("invocation").at("column") == prefix.size() + 1);
}

TEST_CASE("Multiline declarations and macro stringification use expanded tokens") {
    Project project;
    project.write("design.sv", "`define TEXT(x) `\"x`\"\n"
                               "`define DECL(n) \\\n"
                               "logic n``_a; \\\n"
                               "logic n``_b;\nmodule top;\n`DECL(data)\n"
                               "localparam string NAME=`TEXT(data);\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    REQUIRE(compact(expand(service, project, 6)) == "logicdata_a;logicdata_b;");
    REQUIRE(compact(expand(service, project, 7, 24)) == "\"data\"");
}

TEST_CASE("Macro invocations in included files use their recorded context") {
    Project project;
    project.write("defs.svh", "`define DECL(n) logic n;\n");
    project.write("body.svh", "`DECL(included_signal)\n");
    project.write("unloaded.svh", "`DECL(unloaded_signal)\n");
    project.write("design.sv",
                  "`include \"defs.svh\"\nmodule top;\n`include \"body.svh\"\nendmodule\n");
    auto args = project.arguments();
    args["include_directories"] = {project.path("").string()};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    const auto result = service.call(
        "expand_macro", {{"file", project.path("body.svh").string()}, {"line", 1}, {"column", 1}});
    REQUIRE(compact(result) == "logicincluded_signal;");
    REQUIRE(result.at("invocation").at("filename").get<std::string>().ends_with("body.svh"));
    REQUIRE_THROWS_AS(
        service.call("expand_macro",
                     {{"file", project.path("unloaded.svh").string()}, {"line", 1}, {"column", 1}}),
        std::invalid_argument);
}

TEST_CASE("Repeated includes with different macro state are reported as ambiguous") {
    Project project;
    project.write("body.svh", "logic [`WIDTH-1:0] `NAME;\n");
    project.write("design.sv",
                  "`define WIDTH 3\n`define NAME first\nmodule top;\n"
                  "`include \"body.svh\"\n`undef WIDTH\n`undef NAME\n"
                  "`define WIDTH 7\n`define NAME second\n`include \"body.svh\"\nendmodule\n");
    auto args = project.arguments();
    args["include_directories"] = {project.path("").string()};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    REQUIRE_THROWS_WITH(
        service.call("expand_macro",
                     {{"file", project.path("body.svh").string()}, {"line", 1}, {"column", 8}}),
        "macro invocation has multiple preprocessing contexts; query an unambiguous source "
        "invocation");
}

TEST_CASE("Symbol origin keeps the active definition and the physical include occurrence") {
    Project project;
    project.write("body.svh", "`DECL(`NAME)\n");
    project.write("design.sv",
                  "`define DECL(n) logic [2:0] n``_ff;\n`define NAME first\nmodule top;\n"
                  "`include \"body.svh\"\n`undef NAME\n`undef DECL\n"
                  "`define DECL(n) logic [6:0] n``_ff;\n`define NAME second\n"
                  "`include \"body.svh\"\nendmodule\n");
    auto args = project.arguments();
    args["include_directories"] = {project.path("").string()};
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", args).at("diagnostic_error_count") == 0);
    const auto first =
        service.call("describe_symbol", {{"identifier", "top.first_ff"}, {"include_origin", true}});
    const auto second = service.call("describe_symbol",
                                     {{"identifier", "top.second_ff"}, {"include_origin", true}});
    REQUIRE(first.at("width") == 3);
    REQUIRE(second.at("width") == 7);
    REQUIRE(first.at("origin").at("include_sites").at(0).at("line") == 4);
    REQUIRE(second.at("origin").at("include_sites").at(0).at("line") == 9);
    REQUIRE(first.at("origin").at("macros").at(0).at("definition").at("line") == 1);
    REQUIRE(second.at("origin").at("macros").at(0).at("definition").at("line") == 7);
}

TEST_CASE("Macro expansion reads the active snapshot and refreshes only after a successful load") {
    Project project;
    project.write("design.sv", "`define VALUE 4\nmodule top; localparam int N=`VALUE; endmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    project.write("design.sv",
                  "`define VALUE 9\nmodule broken; localparam int N=`VALUE; endmodule\n");
    REQUIRE(compact(expand(service, project, 2, 30)) == "4");
    REQUIRE_THROWS(service.call("project_load", project.arguments()));
    REQUIRE(compact(expand(service, project, 2, 30)) == "4");
    project.write("design.sv", "`define VALUE 9\nmodule top; localparam int N=`VALUE; endmodule\n");
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    REQUIRE(compact(expand(service, project, 2, 30)) == "9");
}

TEST_CASE("Macro query coordinates and byte bounds reject invalid arguments") {
    Project project;
    project.write("design.sv", "`define VALUE 4\nmodule top; localparam int N=`VALUE; endmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE_THROWS_AS(expand(service, project, 2, 30), std::invalid_argument);
    (void)service.call("project_load", project.arguments());
    const auto key = GENERATE("line", "column", "max_bytes");
    const auto value = GENERATE(Json(0), Json(-1), Json(1.5), Json("1"), Json(nullptr));
    Json args = {{"file", project.path("design.sv").string()}, {"line", 2}, {"column", 30}};
    args[key] = value;
    REQUIRE_THROWS_AS(service.call("expand_macro", args), std::invalid_argument);
}

TEST_CASE("Macro query requires a loaded absolute path and a macro name position") {
    Project project;
    project.write("design.sv", "`define VALUE 4\nmodule top; localparam int N=`VALUE; endmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    REQUIRE_THROWS_AS(
        service.call("expand_macro", {{"file", "design.sv"}, {"line", 2}, {"column", 30}}),
        std::invalid_argument);
    REQUIRE_THROWS_AS(expand(service, project, 2, 29), std::invalid_argument);
    REQUIRE_THROWS_AS(service.call("expand_macro", {{"file", project.path("design.sv").string()},
                                                    {"line", 2},
                                                    {"column", 30},
                                                    {"max_bytes", 65537}}),
                      std::invalid_argument);
    REQUIRE(compact(expand(service, project, 2, 31)) == "4");
}

TEST_CASE("Macro replies enforce UTF-8-safe byte bounds") {
    Project project;
    project.write("design.sv", "`define TEXT \"жжж\"\nmodule top;\n"
                               "localparam string N=`TEXT;\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto full = expand(service, project, 3, 21);
    const auto limit = GENERATE(1, 2, 3, 4, 5);
    const auto result = service.call("expand_macro", {{"file", project.path("design.sv").string()},
                                                      {"line", 3},
                                                      {"column", 21},
                                                      {"max_bytes", limit}});
    REQUIRE(result.at("expanded_text").get<std::string>().size() <=
            static_cast<std::size_t>(limit));
    REQUIRE(result.at("total_bytes") == full.at("total_bytes"));
    REQUIRE(result.at("truncated") == true);
    REQUIRE_NOTHROW(result.dump());
    REQUIRE(full.at("expanded_text")
                .get<std::string>()
                .starts_with(result.at("expanded_text").get<std::string>()));
}
} // namespace slang_mcp::test
