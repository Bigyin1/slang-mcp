#include "support.hpp"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>

namespace slang_mcp::test {
namespace {
constexpr std::string_view type_rtl = R"sv(
module top;
  typedef struct packed {logic [7:0] data; logic valid;} word_t;
  typedef union packed {word_t word; logic [8:0] raw;} overlay_t;
  typedef struct {word_t payload; int count;} record_t;
  typedef union {int integer_value; real real_value;} choice_t;
  typedef union tagged {void Invalid; word_t Valid;} tagged_t;
  word_t word;
  overlay_t overlay;
  record_t record_value;
  choice_t choice;
  tagged_t tagged_value;
  word_t words[3:1][-2:0];
  logic signed [1:0][3:0] matrix[2];
  word_t dynamic_words[];
  int associative_words[string];
  word_t queued_words[$:7];
endmodule
)sv";

Json type_info(SemanticService& service, const std::string& name, int depth = 2) {
    return service.call("describe_symbol", {{"identifier", name}, {"type_depth", depth}})
        .at("type_info");
}
} // namespace

TEST_CASE("Packed structs and unions expose ordered fields and packed offsets") {
    Project project;
    project.write("design.sv", type_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto word = type_info(service, "top.word");
    REQUIRE(word.at("kind") == "packed_struct");
    REQUIRE(word.at("width") == 9);
    REQUIRE(word.at("total_bits") == 9);
    REQUIRE(word.at("field_count") == 2);
    REQUIRE(word.at("fields").at(0).at("name") == "data");
    REQUIRE(word.at("fields").at(0).at("bit_offset") == 1);
    REQUIRE(word.at("fields").at(0).at("type_info").at("width") == 8);
    REQUIRE(word.at("fields").at(1).at("bit_offset") == 0);
    const auto overlay = type_info(service, "top.overlay", 4);
    REQUIRE(overlay.at("kind") == "packed_union");
    REQUIRE(overlay.at("fields").at(0).at("bit_offset") == 0);
    REQUIRE(overlay.at("fields").at(1).at("bit_offset") == 0);
    REQUIRE(overlay.at("fields").at(0).at("type_info").at("fields").size() == 2);
    REQUIRE_FALSE(overlay.at("truncated").get<bool>());
}

TEST_CASE("Unpacked structs and unions do not invent packed layouts") {
    Project project;
    project.write("design.sv", type_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto record = type_info(service, "top.record_value");
    REQUIRE(record.at("kind") == "unpacked_struct");
    REQUIRE(record.at("width").is_null());
    REQUIRE(record.at("total_bits") == 41);
    REQUIRE(record.at("fields").front().at("bit_offset").is_null());
    const auto choice = type_info(service, "top.choice");
    REQUIRE(choice.at("kind") == "unpacked_union");
    REQUIRE(choice.at("fields").size() == 2);
    REQUIRE(choice.at("fields").front().at("bit_offset").is_null());
    REQUIRE(type_info(service, "top.tagged_value").at("tagged") == true);
}

TEST_CASE("Array descriptions distinguish dimensions and packed element width from total size") {
    Project project;
    project.write("design.sv", type_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto words = type_info(service, "top.words");
    REQUIRE(words.at("width") == 9);
    REQUIRE(words.at("total_bits") == 81);
    REQUIRE(words.at("dimensions").size() == 2);
    REQUIRE(words.at("dimensions").at(0).at("left") == 3);
    REQUIRE(words.at("dimensions").at(0).at("right") == 1);
    REQUIRE(words.at("dimensions").at(1).at("left") == -2);
    REQUIRE(words.at("element_type").at("kind") == "packed_struct");
    REQUIRE(words.at("element_type").at("fields").size() == 2);
    const auto matrix = type_info(service, "top.matrix");
    REQUIRE(matrix.at("width") == 8);
    REQUIRE(matrix.at("total_bits") == 16);
    REQUIRE(matrix.at("dimensions").size() == 3);
    REQUIRE(matrix.at("dimensions").at(0).at("kind") == "unpacked");
    REQUIRE(matrix.at("dimensions").at(1).at("kind") == "packed");
    REQUIRE(matrix.at("dimensions").at(1).at("is_signed") == true);
    REQUIRE(matrix.at("is_signed") == false);
}

TEST_CASE("Dynamic associative and queue dimensions describe types without runtime sizes") {
    Project project;
    project.write("design.sv", type_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto dynamic = type_info(service, "top.dynamic_words");
    REQUIRE(dynamic.at("width") == 9);
    REQUIRE(dynamic.at("total_bits").is_null());
    REQUIRE(dynamic.at("dimensions").front().at("kind") == "dynamic");
    REQUIRE(dynamic.at("dimensions").front().at("size").is_null());
    const auto associative = type_info(service, "top.associative_words");
    REQUIRE(associative.at("dimensions").front().at("kind") == "associative");
    REQUIRE(associative.at("dimensions").front().at("index_type") == "string");
    const auto queue = type_info(service, "top.queued_words");
    REQUIRE(queue.at("dimensions").front().at("kind") == "queue");
    REQUIRE(queue.at("dimensions").front().at("max_size") == 8);
    REQUIRE(queue.at("total_bits").is_null());
}

TEST_CASE("Type depth is validated and metadata reports omitted children") {
    Project project;
    project.write("design.sv", type_rtl);
    SemanticService service(SnapshotPolicy::Disabled);
    (void)service.call("project_load", project.arguments());
    const auto word = type_info(service, "top.word", 0);
    REQUIRE(word.at("field_count") == 2);
    REQUIRE(word.at("fields").empty());
    REQUIRE(word.at("truncated") == true);
    REQUIRE(type_info(service, "top.words", 0).at("element_type").is_null());
    const auto invalid = GENERATE(Json(-1), Json(9), Json(true), Json(1.5), Json("2"));
    REQUIRE_THROWS(
        service.call("describe_symbol", {{"identifier", "top.word"}, {"type_depth", invalid}}));
}

TEST_CASE("Type descriptions bound wide records and replace effective layouts on reload") {
    Project project;
    std::string source = "module top; typedef struct packed {";
    for (int index = 0; index < 200; ++index) {
        source += "logic field_" + std::to_string(index) + ";";
    }
    project.write("design.sv", source + "} wide_t; wide_t value; endmodule");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    const auto wide = type_info(service, "top.value", 8);
    REQUIRE(wide.at("field_count") == 200);
    REQUIRE(wide.at("fields").size() == 127);
    REQUIRE(wide.at("truncated") == true);
    project.write("design.sv", "module top; typedef struct packed {logic [2:0] replacement;} "
                               "wide_t; wide_t value; endmodule");
    (void)service.call("project_reload", {});
    const auto replacement = type_info(service, "top.value");
    REQUIRE(replacement.at("width") == 3);
    REQUIRE(replacement.at("field_count") == 1);
    REQUIRE(replacement.at("fields").front().at("name") == "replacement");
    REQUIRE_FALSE(replacement.at("truncated").get<bool>());
}

TEST_CASE("Type aliases type parameters and port widths retain effective dimensions") {
    Project project;
    project.write("design.sv", R"sv(
module leaf #(parameter int W=3, parameter type T=logic[W-1:0])(input T values[2]);
  typedef T alias_t;
  alias_t copy[2];
endmodule
module top;
  logic [6:0] words[2];
  leaf #(.W(7)) child(.values(words));
endmodule
)sv");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    REQUIRE(type_info(service, "top.child.copy").at("width") == 7);
    REQUIRE(type_info(service, "top.child.T").at("width") == 7);
    REQUIRE(type_info(service, "top.child.alias_t").at("width") == 7);
    const auto port = service.call("get_ports", {{"sv_module", "leaf"}}).at("items").front();
    REQUIRE(port.at("width") == 3);
    const auto description = service.call("describe_symbol", {{"identifier", "top.child.copy"}});
    REQUIRE(description.at("width") == description.at("type_info").at("width"));
}

TEST_CASE("Type descriptions bound dimension chains and tolerate erroneous RTL") {
    Project project;
    std::string source = "module top; logic many";
    for (int index = 0; index < 18; ++index) {
        source += "[2]";
    }
    project.write("design.sv", source + "; missing_type broken; endmodule");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") > 0);
    const auto many = type_info(service, "top.many", 8);
    REQUIRE(many.at("dimensions").size() == 16);
    REQUIRE(many.at("truncated") == true);
    REQUIRE(many.at("element_type").is_null());
    const auto broken = type_info(service, "top.broken");
    REQUIRE(broken.at("width").is_null());
    REQUIRE(broken.at("total_bits").is_null());
}

TEST_CASE("Nested member lvalues read their selectors and write their base aggregate") {
    Project project;
    const auto statement =
        GENERATE("entries[idx].data = source.data;", "entries[idx].data += source.data;",
                 "entries[idx].data++;", "entries[idx].data[0] = source.data[0];");
    project.write("design.sv", std::string(R"sv(
module top;
  typedef struct packed {logic [7:0] data; logic valid;} word_t;
  word_t entries[4], source;
  logic [1:0] idx;
  always_comb begin
)sv") + statement + "\nend\nendmodule\n");
    SemanticService service(SnapshotPolicy::Disabled);
    REQUIRE(service.call("project_load", project.arguments()).at("diagnostic_error_count") == 0);
    REQUIRE(service.call("get_references", {{"symbol", "top.idx"}, {"kind", "read"}})
                .at("total_count") == 1);
    REQUIRE(service.call("get_references", {{"symbol", "top.idx"}, {"kind", "write"}})
                .at("total_count") == 0);
    REQUIRE(service.call("get_references", {{"symbol", "top.entries"}, {"kind", "write"}})
                .at("total_count") == 1);
}
} // namespace slang_mcp::test
