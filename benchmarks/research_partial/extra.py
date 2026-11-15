"""Add reduced-source dependency omissions after the primary matrix completes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import cast

from benchmarks.dataset import read_object
from benchmarks.research_partial.archive import RAW, expand
from benchmarks.research_partial.measure import Scenario, exclude, measure, scenarios


def extra_scenarios(index: int) -> list[Scenario]:
    base = scenarios(index)[2]
    return [
        replace(base, name="reduced_missing_" + label, sources=exclude(base, filename))
        for label, filename in (("child", "cc_fifo.sv"), ("package", "cc_pkg.sv"))
    ]


async def main() -> None:
    output = expand(read_object(RAW))
    for index in (2, 3):
        for scenario in extra_scenarios(index):
            for repeat in range(3):
                cast("list[object]", output["runs"]).append(await measure(scenario, repeat))
                RAW.write_text(json.dumps(output, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
