"""Compiler-backed source-level connectivity route tests."""

from pathlib import Path

import pytest

from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService

RTL = """
module child(input logic d, output logic q);
  assign q = d;
endmodule
module passthrough(inout wire link);
endmodule
module top(input logic a, b, output logic q);
  logic c, d, cycle_a, cycle_b;
  wire link;
  child u_child(.d(a), .q(c));
  assign d = c;
  always_comb q = d;
  always_ff @(posedge a) cycle_a <= cycle_b;
  always_comb cycle_b = cycle_a;
  child expression(.d(a & b), .q());
  child open(.d(a), .q());
  passthrough u_io(.link(link));
endmodule
"""


@pytest.fixture
def connectivity_service(tmp_path: Path) -> SemanticService:
    source = tmp_path / "connectivity.sv"
    source.write_text(RTL, encoding="utf-8")
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {"connectivity": ProjectConfig("connectivity", (source,), top_modules=("top",))}
            )
        )
    )
    service.project_load("connectivity")
    return service


def test_load_routes_follow_port_and_assignment_edges(
    connectivity_service: SemanticService,
) -> None:
    trace = connectivity_service.rtl.trace_connectivity("top.a", "loads", 5, 100)

    route = next(path for path in trace.paths.items if path.end == "top.q")
    assert [(hop.source, hop.target, hop.kind) for hop in route.hops] == [
        ("top.a", "top.u_child.d", "port_binding"),
        ("top.u_child.d", "top.u_child.q", "continuous_assignment"),
        ("top.u_child.q", "top.c", "port_binding"),
        ("top.c", "top.d", "continuous_assignment"),
        ("top.d", "top.q", "procedural_assignment"),
    ]
    assert route.stop_reason == "max_depth"
    assert route.hops[0].formal_port == "d"
    assert route.hops[-1].operation == "blocking_assignment"


def test_driver_and_both_routes_reverse_and_merge_edges(
    connectivity_service: SemanticService,
) -> None:
    drivers = connectivity_service.rtl.trace_connectivity("top.q", "drivers", 5, 100)
    route = next(path for path in drivers.paths.items if path.end == "top.a")
    assert [(hop.source, hop.target) for hop in route.hops] == [
        ("top.q", "top.d"),
        ("top.d", "top.c"),
        ("top.c", "top.u_child.q"),
        ("top.u_child.q", "top.u_child.d"),
        ("top.u_child.d", "top.a"),
    ]
    both = connectivity_service.rtl.trace_connectivity("top.c", "both", 1, 100)
    assert {(path.end, path.stop_reason) for path in both.paths.items} == {
        ("top.d", "max_depth"),
        ("top.u_child.q", "max_depth"),
    }


def test_inout_cycle_and_disconnected_routes(connectivity_service: SemanticService) -> None:
    inout = connectivity_service.rtl.trace_connectivity("top.link", "loads", 2, 100)
    assert inout.paths.items[0].hops[0].target == "top.u_io.link"
    assert inout.paths.items[0].stop_reason == "cycle"

    cycle = connectivity_service.rtl.trace_connectivity("top.cycle_a", "loads", 4, 100)
    assert cycle.paths.items[0].stop_reason == "cycle"
    assert cycle.paths.items[0].end == "top.cycle_a"

    disconnected = connectivity_service.rtl.trace_connectivity("top.b", "loads", 4, 100)
    assert disconnected.paths.items[0].stop_reason == "no_edges"


def test_trace_excludes_expression_actuals_and_obeys_budgets(
    connectivity_service: SemanticService,
) -> None:
    trace = connectivity_service.rtl.trace_connectivity("top.a", "loads", 5, 1)
    assert trace.paths.truncated
    assert trace.edges_considered == 1
    assert all(
        "top.expression" not in hop.target for path in trace.paths.items for hop in path.hops
    )

    with pytest.raises(ValueError, match="direction"):
        connectivity_service.rtl.trace_connectivity("top.a", "sideways", 5, 100)
    with pytest.raises(ValueError, match="max_depth"):
        connectivity_service.rtl.trace_connectivity("top.a", "loads", 51, 100)


def test_declaration_and_compound_assignment_dependencies(tmp_path: Path) -> None:
    source = tmp_path / "assignment_kinds.sv"
    source.write_text(
        """
module top;
  logic a; logic b; logic initialized = a; logic result;
  initial begin result = initialized; result += b; end
endmodule
""",
        encoding="utf-8",
    )
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {"kinds": ProjectConfig("kinds", (source,), top_modules=("top",))}
            )
        )
    )
    service.project_load("kinds")

    initialized = service.rtl.trace_connectivity("top.a", "loads", 1, 100)
    assert initialized.paths.items[0].hops[0].operation == "declaration_assignment"
    compound = service.rtl.trace_connectivity("top.b", "loads", 1, 100)
    assert compound.paths.items[0].hops[0].operation == "compound_blocking_assignment"


def test_multilevel_fanout_routes_are_deterministic_and_reversible(  # pylint: disable=too-many-locals
    tmp_path: Path,
) -> None:
    source = tmp_path / "multilevel.sv"
    source.write_text(
        """
module leaf(input logic a, b, output logic y);
  logic mixed;
  assign mixed = a ^ b;
  always_comb y = mixed;
endmodule
module wrapper(input logic d, f, output logic q);
  logic staged;
  leaf u_leaf(.a(d), .b(f), .y(staged));
  assign q = staged;
endmodule
module top(input logic src, side, output logic sink, tap);
  logic left_out, right_out, merged, feedback;
  wrapper u_left(.d(src), .f(side), .q(left_out));
  wrapper u_right(.d(src), .f(left_out), .q(right_out));
  assign merged = left_out | right_out;
  always_comb feedback = merged;
  wrapper u_final(.d(feedback), .f(src), .q(sink));
  always_ff @(posedge src) tap <= feedback;
endmodule
""",
        encoding="utf-8",
    )
    service = SemanticService(
        ProjectManager(
            StaticProjectProvider(
                {"multilevel": ProjectConfig("multilevel", (source,), top_modules=("top",))}
            )
        )
    )
    service.project_load("multilevel")

    first = service.rtl.trace_connectivity("top.src", "loads", 20, 100)
    second = service.rtl.trace_connectivity("top.src", "loads", 20, 100)
    route = next(
        path
        for path in first.paths.items
        if path.end == "top.sink" and path.hops[0].target == "top.u_left.d"
    )

    assert first == second
    assert first.edges_considered > len(route.hops)
    assert [(hop.source, hop.target) for hop in route.hops] == [
        ("top.src", "top.u_left.d"),
        ("top.u_left.d", "top.u_left.u_leaf.a"),
        ("top.u_left.u_leaf.a", "top.u_left.u_leaf.mixed"),
        ("top.u_left.u_leaf.mixed", "top.u_left.u_leaf.y"),
        ("top.u_left.u_leaf.y", "top.u_left.staged"),
        ("top.u_left.staged", "top.u_left.q"),
        ("top.u_left.q", "top.left_out"),
        ("top.left_out", "top.merged"),
        ("top.merged", "top.feedback"),
        ("top.feedback", "top.u_final.d"),
        ("top.u_final.d", "top.u_final.u_leaf.a"),
        ("top.u_final.u_leaf.a", "top.u_final.u_leaf.mixed"),
        ("top.u_final.u_leaf.mixed", "top.u_final.u_leaf.y"),
        ("top.u_final.u_leaf.y", "top.u_final.staged"),
        ("top.u_final.staged", "top.u_final.q"),
        ("top.u_final.q", "top.sink"),
    ]
    assert route.hops[8].operation == "blocking_assignment"

    drivers = service.rtl.trace_connectivity("top.sink", "drivers", 20, 100)
    reverse = next(
        path
        for path in drivers.paths.items
        if path.end == "top.src" and any(hop.target == "top.feedback" for hop in path.hops)
    )
    assert [(hop.source, hop.target) for hop in reverse.hops] == [
        (hop.target, hop.source) for hop in reversed(route.hops)
    ]

    both = service.rtl.trace_connectivity("top.merged", "both", 1, 100)
    assert [(path.end, path.stop_reason) for path in both.paths.items] == [
        ("top.feedback", "max_depth"),
        ("top.left_out", "max_depth"),
        ("top.right_out", "max_depth"),
    ]
