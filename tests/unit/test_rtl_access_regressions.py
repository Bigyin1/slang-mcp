"""Access classification across less trivial elaborated RTL constructs."""

from pathlib import Path

import pytest

from tests.rtl_support import load_rtl


def test_concatenation_lvalue_keeps_index_as_read(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module top;
  logic [7:0] a, b, source;
  int index;
  initial {a[index], b[2:0]} = source[3:0];
endmodule
""",
    )
    assert project.service.rtl.get_signal_writes("top.a").total_count == 1
    assert project.service.rtl.get_signal_writes("top.b").total_count == 1
    assert project.service.rtl.get_signal_reads("top.a").total_count == 0
    assert project.service.rtl.get_signal_writes("top.index").total_count == 0
    assert project.service.rtl.get_signal_reads("top.index").total_count == 1
    assert project.service.rtl.get_signal_reads("top.source").total_count == 1


@pytest.mark.parametrize("selection", ["index +: 4", "index -: 4", "7:4"])
def test_part_select_write_does_not_read_target(tmp_path: Path, selection: str) -> None:
    project = load_rtl(
        tmp_path,
        f"""
module top;
  logic [15:0] data;
  logic [3:0] source;
  int index;
  initial data[{selection}] = source;
endmodule
""",
    )
    assert project.service.rtl.get_signal_writes("top.data").total_count == 1
    assert project.service.rtl.get_signal_reads("top.data").total_count == 0
    assert project.service.rtl.get_signal_reads("top.source").total_count == 1
    assert project.service.rtl.get_signal_reads("top.index").total_count == int(
        "index" in selection
    )


def test_procedure_sets_deduplicate_sites_and_keep_branch_reads(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module top(input logic enable, a, b, output logic q);
  always_comb begin
    q = a;
    if (enable) q = a & b;
    else q = b;
  end
endmodule
""",
    )
    block = project.service.rtl.get_procedural_blocks("top").items[0]
    assert set(block.reads.items) == {"top.a", "top.b", "top.enable"}
    assert block.writes.items == ("top.q",)
    assert project.service.rtl.get_signal_writes("top.q").total_count == 3
    assert {item.block for item in project.service.rtl.get_signal_writes("top.q").items} == {
        block.block_id,
    }
    assert project.service.rtl.get_state_elements("top").total_count == 0


def test_case_selector_and_default_branch_accesses(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module top(input logic [1:0] sel, input logic a, b, output logic q);
  always_comb case (sel)
    0: q = a;
    1: q = b;
    default: q = 0;
  endcase
endmodule
""",
    )
    assert project.service.rtl.get_signal_reads("top.sel").total_count == 1
    assert project.service.rtl.get_signal_writes("top.q").total_count == 3
    assert {item.context for item in project.service.rtl.get_signal_writes("top.q").items} == {
        "blocking_assignment",
    }


def test_disabled_generate_has_no_accesses_or_instances(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module leaf; endmodule
module top(input logic a, b, output logic q);
  if (1) begin: enabled
    assign q = a;
    leaf child();
  end else begin: disabled
    assign q = b;
    leaf ghost();
  end
endmodule
""",
    )
    assert project.service.rtl.get_signal_reads("top.a").total_count == 1
    assert project.service.rtl.get_signal_reads("top.b").total_count == 0
    assert project.service.rtl.get_signal_writes("top.q").total_count == 1
    assert [item.path for item in project.service.rtl.list_instances("leaf").items] == [
        "top.enabled.child",
    ]
    assert project.service.rtl.get_signal_writes("top.q").items[0].scope == "top.enabled"


def test_initial_final_and_latch_are_not_always_ff_state(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module top(input logic enable, data);
  logic latch_q, initial_q, final_q;
  initial initial_q = 0;
  final final_q = data;
  always_latch if (enable) latch_q = data;
endmodule
""",
    )
    assert {block.kind for block in project.service.rtl.get_procedural_blocks("top").items} == {
        "Initial",
        "Final",
        "AlwaysLatch",
    }
    assert project.service.rtl.get_state_elements("top").total_count == 0
    assert project.service.rtl.get_signal_writes("top.latch_q").total_count == 1
    assert project.service.rtl.get_signal_reads("top.data").total_count == 2


def test_system_call_is_unknown_without_fabricated_load(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path,
        """
module top;
  logic data;
  initial $display("data=%b", data);
endmodule
""",
    )
    references = project.service.rtl.get_references("top.data", "unknown")
    assert references.total_count == 1
    assert references.items[0].context == "system_call"
    assert project.service.rtl.get_loads("top.data").total_count == 0
    assert project.service.rtl.get_drivers("top.data").total_count == 0


def test_reference_locations_point_to_each_use(tmp_path: Path) -> None:
    project = load_rtl(
        tmp_path, "module top;\nlogic a, q;\nassign q = a;\ninitial q = a;\nendmodule\n"
    )
    assert [
        (item.location.line, item.location.column)
        for item in project.service.rtl.get_signal_reads("top.a").items
    ] == [(3, 12), (4, 13)]
    assert {item.location.line for item in project.service.rtl.get_drivers("top.q").items} == {3, 4}
    assert all(
        Path(item.location.filename or "").resolve() == project.source_file.resolve()
        for item in project.service.rtl.get_references("top.a").items
    )
