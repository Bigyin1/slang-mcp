"""Bounded subprocesses with process-group cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Command:
    argv: list[str]
    cwd: Path
    environment: dict[str, str]
    timeout: float


@dataclass(frozen=True)
class Completion:
    returncode: int
    duration: float
    timed_out: bool


def terminate(process: subprocess.Popen[bytes]) -> None:
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def execute(command: Command, output: Path) -> Completion:
    with (
        (output / "trace.jsonl").open("wb") as stdout,
        (output / "stderr.txt").open("wb") as stderr,
        subprocess.Popen(
            command.argv,
            cwd=command.cwd,
            env=command.environment,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        ) as process,
    ):
        return _wait(process, command.timeout)


def _wait(process: subprocess.Popen[bytes], timeout: float) -> Completion:
    started = time.monotonic()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        terminate(process)
    return Completion(process.returncode, time.monotonic() - started, timed_out)
