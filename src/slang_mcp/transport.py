"""Shared MCP serialization and controlled error boundary."""

import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from slang_mcp.errors import SlangMcpError

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


def safe(call: Callable[[], T]) -> T:
    try:
        return call()
    except (SlangMcpError, ValueError) as error:
        raise ToolError(str(error)) from error
    except Exception as error:
        _LOGGER.exception("unexpected MCP tool failure")
        raise ToolError("internal semantic server failure") from error


def model_dict(model: Any) -> dict[str, Any]:
    return asdict(model)
