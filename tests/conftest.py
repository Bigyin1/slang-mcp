"""Shared real-compilation fixtures."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from slang_mcp.models import ProjectConfig
from slang_mcp.project import ProjectManager
from slang_mcp.providers import StaticProjectProvider
from slang_mcp.services import SemanticService


@dataclass(frozen=True)
class FixtureProject:
    config: ProjectConfig
    design_file: Path


def project_load_arguments(project: FixtureProject) -> dict[str, object]:
    """Write simple absolute-path lists for the public MCP load contract."""
    root = project.design_file.parent
    sources = root / "sources.f"
    includes = root / "includes.f"
    sources.write_text(
        "\n".join(str(path) for path in project.config.source_files) + "\n", encoding="utf-8"
    )
    includes.write_text(
        "\n".join(str(path) for path in project.config.include_directories) + "\n",
        encoding="utf-8",
    )
    return {
        "source_file_lists": [str(sources)],
        "include_directory_lists": [str(includes)],
        "defines": dict(project.config.defines),
        "top_module": "top",
    }


@pytest.fixture
def fixture_project(tmp_path: Path) -> FixtureProject:
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    (include_dir / "defs.svh").write_text("`define DEFAULT_WIDTH 8\n", encoding="utf-8")
    package_file = tmp_path / "types_pkg.sv"
    package_file.write_text(
        """
`include "defs.svh"
package types_pkg;
  parameter int PKG_WIDTH = `DEFAULT_WIDTH;
  typedef logic [PKG_WIDTH-1:0] word_t;
  function automatic int double(input int value);
    return value * 2;
  endfunction
  class packet;
    word_t payload;
  endclass
endpackage
""",
        encoding="utf-8",
    )
    design_file = tmp_path / "design.sv"
    design_file.write_text(_design_text(), encoding="utf-8")
    config = ProjectConfig(
        logical_module="demo",
        source_files=(package_file, design_file),
        include_directories=(include_dir,),
        defines={"ADD_EXTRA": None, "BUILD_ID": "7"},
        top_modules=("top",),
        metadata={"fixture": "unit"},
    )
    return FixtureProject(config, design_file)


@pytest.fixture
def service(fixture_project: FixtureProject) -> SemanticService:
    provider = StaticProjectProvider({"demo": fixture_project.config})
    return SemanticService(ProjectManager(provider))


def _design_text(extra_signal: str = "") -> str:
    return f"""
interface bus_if;
  logic valid;
endinterface

module leaf #(
  parameter int WIDTH = 8
) (
  input logic [WIDTH-1:0] i,
  output logic [WIDTH-1:0] o
);
  logic state;
  wire ready;
  typedef logic [WIDTH-1:0] local_word_t;
  function automatic int identity(input int value);
    return value;
  endfunction
  task automatic clear;
    state = 1'b0;
  endtask
  assign o = i;
endmodule

module branch(input logic [31:0] data);
  leaf #(.WIDTH(32)) u_c(.i(data), .o());
endmodule

module top #(parameter bit ENABLE = 1'b1);
  import types_pkg::*;
  word_t package_word;
  logic [31:0] data;
  {extra_signal}
  leaf #(.WIDTH(32)) u_a(.i(data), .o());
  branch u_b(.data(data));
  for (genvar index = 0; index < 2; index++) begin : generated
    leaf #(.WIDTH(32)) u_generated(.i(data), .o());
  end
  if (ENABLE) begin : enabled
    leaf #(.WIDTH(32)) u_conditional(.i(data), .o());
  end
`ifdef ADD_EXTRA
  leaf #(.WIDTH(32)) u_extra(.i(data), .o());
`endif
endmodule
"""


def replacement_design() -> str:
    return _design_text("logic reloaded_signal;")
