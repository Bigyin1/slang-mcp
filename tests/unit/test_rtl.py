"""Real Slang tests for RTL access, signatures and instance queries."""

from pathlib import Path

import pytest

from slang_mcp.errors import AmbiguousSymbolError, SignatureUnavailableError
from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService

RTL = """
module leaf #(parameter WIDTH=32, parameter type T=logic)
 (input logic [WIDTH-1:0] d, output logic [WIDTH-1:0] q);
 localparam DOUBLE=2*WIDTH;
 assign q=d;
endmodule
module top(input logic clk, input logic a, b, output logic q);
 logic c, d;
 logic [63:0] wide;
 assign c=a & b;
 always_comb d=c;
 always_ff @(posedge clk) q <= d;
 always @(a) begin c = a; end
 leaf #(.WIDTH(64)) u_leaf(.d(64'(a & b)), .q(wide));
 leaf u_pos(32'b0, );
 for (genvar i=0; i<2; i++) begin: gen
   leaf #(.WIDTH(1)) u_gen(.d(a), .q());
 end
endmodule
"""


@pytest.fixture
def rtl_service(tmp_path: Path) -> SemanticService:
    (tmp_path / "design.sv").write_text(RTL, encoding="utf-8")
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {
                    "rtl": ProjectConfig("rtl", (tmp_path / "design.sv",), top_modules=("top",)),
                }
            )
        )
    )
    service.project_load("rtl")
    return service


def test_accesses(rtl_service: SemanticService) -> None:
    assert rtl_service.rtl.get_signal_reads("top.a").total_count >= 4
    assert rtl_service.rtl.get_signal_writes("top.q").total_count == 1
    assert rtl_service.rtl.get_signal_writes("top.q").items[0].context == "nonblocking_assignment"
    assert rtl_service.rtl.get_drivers("top.c").total_count == 2
    assert rtl_service.rtl.get_loads("top.d").total_count == 1
    assert rtl_service.rtl.get_references("top.c", kind="declaration").total_count == 1


def test_procedures(rtl_service: SemanticService) -> None:
    assert {item.kind for item in rtl_service.rtl.get_procedural_blocks("top").items} == {
        "AlwaysFF",
        "AlwaysComb",
        "Always",
    }
    assert rtl_service.rtl.get_state_elements("top").items[0].signal.qualified_name == "top.q"


def test_parameters(rtl_service: SemanticService) -> None:
    assert rtl_service.rtl.get_parameters("leaf").value_kind == "declared_default"
    assert rtl_service.rtl.get_parameters("leaf").parameters.items[0].value == "32"
    assert rtl_service.rtl.get_instance_parameters("top.u_leaf").parameters.items[0].value == "64"
    assert rtl_service.rtl.get_parameters("top.u_leaf").value_kind == "effective"
    assert rtl_service.rtl.get_ports("leaf").items[0].width == 32
    assert rtl_service.rtl.get_parameters("leaf").parameters.items[1].value == "logic"
    rtl_service.project_reload()
    assert rtl_service.semantic_diff().changes.total_count == 0


def test_connections(rtl_service: SemanticService) -> None:
    assert rtl_service.rtl.get_instance_connections("top.u_leaf").items[0].kind == "expression"
    assert rtl_service.rtl.get_instance_connections("top.u_leaf").items[0].symbols == (
        "top.a",
        "top.b",
    )
    assert rtl_service.rtl.get_instance_connections("top.u_leaf").items[1].symbols == ("top.wide",)
    assert rtl_service.rtl.get_instance_connections("top.u_pos").items[1].kind == "unconnected"


def test_instance_query_name_filters(rtl_service: SemanticService) -> None:
    parameters = rtl_service.rtl.get_instance_parameters(
        "top.u_leaf", names=["MISSING", "WIDTH"]
    ).parameters
    connections = rtl_service.rtl.get_instance_connections("top.u_leaf", ports=["q", "d"])

    assert [(item.name, item.value) for item in parameters.items] == [("WIDTH", "64")]
    assert parameters.total_count == 1
    assert [item.port.name for item in connections.items] == ["d", "q"]
    assert connections.total_count == 2
    assert rtl_service.rtl.get_instance_connections(
        "top.u_leaf", limit=1, ports=["d", "q"]
    ).truncated
    assert rtl_service.rtl.get_instance_connections("top.u_leaf", ports=["missing"]).items == ()


def test_instances(rtl_service: SemanticService) -> None:
    assert rtl_service.rtl.list_instances(sv_module="leaf").total_count == 4
    assert rtl_service.rtl.find_instance("top.gen[1].u_gen").sv_module == "leaf"
    assert rtl_service.rtl.find_instance("u_leaf").path == "top.u_leaf"
    with pytest.raises(AmbiguousSymbolError):
        rtl_service.rtl.find_instance("u_gen")
    with pytest.raises(AmbiguousSymbolError):
        rtl_service.rtl.get_references("d")


def test_bounded_inspections(rtl_service: SemanticService) -> None:
    assert rtl_service.rtl.list_instances(limit=1).truncated
    assert rtl_service.inspection.inspect_signal("top.a", 1).reads.truncated
    assert rtl_service.inspection.inspect_module("leaf").ports.items[0].width == 32
    assert rtl_service.inspection.inspect_instance("top.u_leaf").connections.total_count == 2
    with pytest.raises(ValueError, match="limit"):
        rtl_service.rtl.get_signal_reads("top.a", 0)


def test_scoped_symbols(rtl_service: SemanticService) -> None:
    assert {item.name for item in rtl_service.rtl.list_symbols("leaf", "port").items} == {"d", "q"}
    assert rtl_service.rtl.get_references("module:leaf", "instantiation").total_count == 4
    assert rtl_service.inspection.inspect_instance("top").children.total_count == 4
    assert (
        rtl_service.describe_symbol(
            rtl_service.rtl.list_symbols("leaf", "port").items[0].symbol_id
        ).width
        == 32
    )


def _source_service(tmp_path: Path, source: str) -> SemanticService:
    (tmp_path / "edges.sv").write_text(source, encoding="utf-8")
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {
                    "edges": ProjectConfig("edges", (tmp_path / "edges.sv",), top_modules=("top",)),
                }
            )
        )
    )
    service.project_load("edges")
    return service


def test_selects_and_compound_assignments(tmp_path: Path) -> None:
    service = _source_service(
        tmp_path,
        """
module top;
 logic [7:0] data;
 int idx; logic value;
 initial begin data[idx] = value; data[3:0] += 1; idx++; idx--; end
endmodule
""",
    )
    assert service.rtl.get_signal_writes("top.idx").total_count == 2
    assert service.rtl.get_signal_reads("top.idx").total_count == 3
    assert service.rtl.get_signal_writes("top.data").total_count == 2
    assert service.rtl.get_signal_reads("top.value").total_count == 1


def test_task_argument_directions(tmp_path: Path) -> None:
    service = _source_service(
        tmp_path,
        """
module top;
 logic a,b;
 task automatic transfer(input logic x, output logic y); y=x; endtask
 initial transfer(a,b);
endmodule
""",
    )
    assert service.rtl.get_signal_reads("top.a").total_count == 1
    assert service.rtl.get_signal_writes("top.b").total_count == 1
    assert service.rtl.get_signal_reads("top.b").total_count == 0


def test_wildcard_and_interface_connections(tmp_path: Path) -> None:
    service = _source_service(
        tmp_path,
        """
interface bus; logic v; modport sink(input v); endinterface
module consumer(input logic clk, bus.sink link); endmodule
module top; logic clk; bus link(); consumer child(.*); endmodule
""",
    )
    assert service.rtl.get_instance_connections("top.child").items[0].symbols == ("top.clk",)
    assert service.rtl.get_instance_connections("top.child").items[1].kind == "interface"
    assert service.rtl.get_ports("consumer").items[1].modport == "sink"


def test_unpacked_ports(tmp_path: Path) -> None:
    service = _source_service(
        tmp_path,
        """
module top(input logic [7:0] data[0:3]); endmodule
""",
    )
    assert service.rtl.get_ports("top").items[0].width == 8
    assert service.rtl.get_ports("top").items[0].unpacked_dimensions


def test_nested_definition_does_not_prevent_loading(tmp_path: Path) -> None:
    service = _source_service(
        tmp_path, "module top; module nested; endmodule nested child(); endmodule"
    )
    assert service.rtl.find_instance("top.child").sv_module == "nested"
    with pytest.raises(SignatureUnavailableError):
        service.rtl.get_ports("nested")
    service.project_reload()
    assert service.semantic_diff().changes.total_count == 0
