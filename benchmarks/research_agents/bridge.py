"""Persistent JSON-lines frontend to a real MCP process for native workload pilots."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class Bridge:
    """Enforce catalog/call parity and retain controller-side wire evidence."""

    session: ClientSession
    log: Path
    allowed: frozenset[str]

    async def dispatch(self, request: dict[str, object]) -> dict[str, object]:
        """Handle one tools/list or tools/call request against the live session."""
        if request.get("method") == "tools/list":
            catalog = (await self.session.list_tools()).model_dump(mode="json", by_alias=True)
            if self.allowed:
                catalog["tools"] = [
                    tool for tool in catalog["tools"] if tool["name"] in self.allowed
                ]
            return cast("dict[str, object]", catalog)
        if request.get("method") != "tools/call":
            raise ValueError("Supported methods: tools/list, tools/call")
        name = str(request["name"])
        if self.allowed and name not in self.allowed:
            raise ValueError(f"Tool excluded by treatment: {name}")
        result = await self.session.call_tool(
            name, cast("dict[str, object]", request.get("arguments", {}))
        )
        return cast("dict[str, object]", result.model_dump(mode="json", by_alias=True))

    async def checked_dispatch(self, request: dict[str, object]) -> dict[str, object]:
        """Return a visible error for rejected or malformed tool requests."""
        try:
            return await self.dispatch(request)
        except (ValueError, KeyError) as error:
            return {"bridge_error": str(error)}

    def record(
        self, request: dict[str, object], response: dict[str, object], started: float
    ) -> None:
        """Append complete wire evidence and publish the same response."""
        with self.log.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "request": request,
                        "response": response,
                        "seconds": time.perf_counter() - started,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
        print(json.dumps(response, separators=(",", ":")), flush=True)

    async def run(self) -> None:
        """Process request lines until standard-input EOF."""
        print('{"bridge_ready":true}', flush=True)
        while line := await asyncio.to_thread(sys.stdin.readline):
            started = time.perf_counter()
            request = json.loads(line)
            response = await self.checked_dispatch(request)
            self.record(request, response, started)


async def serve(binary: Path, log: Path, allowed: frozenset[str]) -> None:
    """Keep one initialized compiler session alive until standard-input EOF."""
    # Pylint cannot follow the SDK async context-manager tuple assignment.
    # pylint: disable=used-before-assignment
    async with (
        stdio_client(StdioServerParameters(command=str(binary), args=[])) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        await Bridge(session, log, allowed).run()
    # pylint: enable=used-before-assignment


def main() -> None:
    """Start a session without loading projects or injecting oracle information."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--allow", action="append", default=[])
    options = parser.parse_args()
    asyncio.run(serve(options.binary.resolve(), options.log.resolve(), frozenset(options.allow)))


if __name__ == "__main__":
    main()
