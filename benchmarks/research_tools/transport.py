"""Record SDK calls without external model inference."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from mcp import ClientSession


@dataclass
class Recorder:
    """Retain both compact wire metrics and structured native answers."""

    session: ClientSession
    records: list[dict[str, object]] = field(default_factory=list)

    async def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        started = time.perf_counter()
        result = await self.session.call_tool(name, arguments)
        self.records.append(
            {
                "tool": name,
                "arguments": arguments,
                "seconds": time.perf_counter() - started,
                "response_bytes": len(
                    json.dumps(
                        result.model_dump(mode="json", by_alias=True), separators=(",", ":")
                    ).encode()
                ),
                "is_error": result.is_error,
                "answer": result.structured_content or {},
                "content": [item.model_dump(mode="json") for item in result.content]
                if result.is_error
                else [],
            }
        )
        return cast("dict[str, object]", result.structured_content or {})

    def save(self, destination: Path) -> None:
        destination.write_text(json.dumps(self.records, separators=(",", ":")) + "\n")
