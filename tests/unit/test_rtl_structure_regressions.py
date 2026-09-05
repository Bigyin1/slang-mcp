"""Specializations, instance arrays and bounded semantic responses."""

from pathlib import Path

from tests.rtl_support import load_rtl


def test_dependent_defaults_and_type_overrides_are_independent(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module leaf #(parameter W=4, parameter type T=logic [W-1:0])
 (input T d, output T q);
 localparam BITS=$bits(T);
 assign q=d;
endmodule
module top;
 leaf #(.W(9)) wide('0, );
 leaf #(.W(9), .T(bit [2:0])) typed('0, );
endmodule
""",
    )
    assert project.service.rtl.get_ports("leaf").items[0].width == 4
    assert project.service.rtl.get_instance_connections("top.wide").items[0].port.width == 9
    assert project.service.rtl.get_instance_connections("top.typed").items[0].port.width == 3
    assert {
        item.name: item.value
        for item in project.service.rtl.get_instance_parameters("top.typed").parameters.items
    } == {"W": "9", "T": "bit[2:0]", "BITS": "3"}
    assert project.service.rtl.get_parameters("leaf").parameters.items[0].value == "4"


def test_nested_generate_filters_and_effective_values(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module leaf #(parameter W=1); endmodule
module top;
 for (genvar row=0; row<2; row++) begin: rows
   for (genvar col=0; col<3; col++) begin: cols
     leaf #(.W(row*3+col+1)) worker();
   end
 end
endmodule
""",
    )
    result = project.service.rtl.list_instances("leaf", "worker", "top.rows[1].", 2)
    assert result.total_count == 3
    assert result.truncated
    assert [item.path for item in result.items] == [
        "top.rows[1].cols[0].worker",
        "top.rows[1].cols[1].worker",
    ]
    assert {item.parent for item in result.items} == {"top"}
    assert project.service.inspection.inspect_instance("top").children.total_count == 6
    assert (
        project.service.rtl.get_instance_parameters("top.rows[1].cols[2].worker")
        .parameters.items[0]
        .value
        == "6"
    )


def test_instance_array_retains_each_occurrence(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module leaf(input logic a, output logic q); assign q=a; endmodule
module top;
 logic [3:0] data, result;
 leaf lanes[3:0](data, result);
endmodule
""",
    )
    assert {item.path for item in project.service.rtl.list_instances("leaf").items} == {
        "top.lanes[0]",
        "top.lanes[1]",
        "top.lanes[2]",
        "top.lanes[3]",
    }
    assert project.service.rtl.get_instance_connections("top.lanes[2]").items[0].port.width == 1
    assert project.service.rtl.get_drivers("top.result").total_count == 4
    assert project.service.rtl.get_loads("top.data").total_count == 4


def test_multidimensional_port_width_excludes_unpacked_dimensions(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module top(input logic signed [1:0][3:0] values[2:0][0:4]); endmodule
""",
    )
    port = project.service.rtl.get_ports("top").items[0]
    assert port.width == 8
    assert port.unpacked_dimensions == ("[2:0]", "[0:4]")
    assert "signed" in port.type


def test_qualified_port_and_variable_ids_share_access_sites(tmp_path: Path) -> None:
    project = load_rtl(tmp_path, "module top(input logic a, output logic q); assign q=a; endmodule")
    assert project.service.rtl.get_signal_reads("top.a").total_count == 1
    assert project.service.rtl.get_signal_reads("port:top.a").items[0].location == (
        project.service.rtl.get_signal_reads("variable:top.a").items[0].location
    )
    assert (
        project.service.rtl.get_signal_reads("port:top.a").items[0].symbol.symbol_id == "port:top.a"
    )
    assert project.service.rtl.get_signal_reads("variable:top.a").items[0].symbol.symbol_id == (
        "variable:top.a"
    )


def test_large_procedure_keeps_full_state_count_after_read_write_set_cap(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        "module top(input logic clk, d);\n"
        + "\n".join(f"logic q{i};" for i in range(503))
        + "\nalways_ff @(posedge clk) begin\n"
        + "\n".join(f"q{i} <= d;" for i in range(503))
        + "\nend\nendmodule",
    )
    block = project.service.rtl.get_procedural_blocks("top").items[0]
    assert block.writes.total_count == 503
    assert len(block.writes.items) == 500
    assert block.writes.truncated
    assert project.service.rtl.get_state_elements("top", limit=2).total_count == 503
    assert len(project.service.rtl.get_state_elements("top", limit=2).items) == 2
    assert project.service.rtl.get_signal_reads("top.d", limit=500).total_count == 503
    assert project.service.rtl.get_signal_reads("top.d", limit=500).truncated


def test_connections_bound_unique_symbols_without_changing_total(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        "module leaf(input logic d); endmodule\nmodule top;\n"
        + "\n".join(f"logic s{i};" for i in range(503))
        + "\nleaf child(.d("
        + " ^ ".join(f"s{i}" for i in range(503))
        + "));\nendmodule",
    )
    connection = project.service.rtl.get_instance_connections("top.child").items[0]
    assert connection.kind == "expression"
    assert connection.symbol_count == 503
    assert connection.symbols_truncated
    assert len(connection.symbols) == 500
    assert len(connection.expression or "") <= 1000
    assert project.service.rtl.get_signal_reads("top.s502").total_count == 1


def test_uninstantiated_module_is_inspectable_but_not_an_active_instance(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module unused #(parameter W=8)(input logic clk, d, output logic q);
 always_ff @(posedge clk) q <= d;
endmodule
module top; endmodule
""",
    )
    assert [item.path for item in project.service.rtl.list_instances().items] == ["top"]
    assert project.service.rtl.list_instances("unused").total_count == 0
    assert project.service.rtl.get_procedural_blocks("unused").total_count == 0
    assert project.service.rtl.get_state_elements("unused").total_count == 0
    assert project.service.rtl.get_references("module:unused", "instantiation").total_count == 0
    assert project.service.rtl.get_ports("unused").total_count == 3
    assert project.service.rtl.get_parameters("unused").parameters.items[0].value == "8"
