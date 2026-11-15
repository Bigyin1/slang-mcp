"""Export public research artifacts and audit a frozen schedule.

Usage: python -m benchmarks.research_compare.audit --runs PATH --output DIR
Incomplete snapshots are explicitly marked; only finished runs are exported.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit_content import content_audit
from benchmarks.research_compare.audit_freeze import (
    FROZEN_REVISION,
    ArtifactSource,
    Snapshot,
    artifact_audit,
    frozen_plan,
    load_snapshot,
    snapshot_audit,
)
from benchmarks.research_compare.audit_integrity import binary_audit, digest, workspace_audit
from benchmarks.research_compare.audit_metrics import group_summaries, paired_metrics, run_metrics
from benchmarks.research_compare.audit_tools import tool_audit
from benchmarks.research_compare.models import Plan, Run
from benchmarks.runner.storage import write_json

PUBLIC_ARTIFACTS = (
    "answer.txt",
    "prompt.txt",
    "invocation.json",
    "result.json",
    "public_trace.jsonl",
)


@dataclass(frozen=True)
class AuditRequest:
    runs: Path
    output: Path
    inputs: Path
    protocol: Path
    revision: str = FROZEN_REVISION


@dataclass(frozen=True)
class ArtifactPackage:
    """A separately frozen task corpus reusing the original prompt builders."""

    builders: Snapshot
    task_pattern: str


@dataclass(frozen=True)
class Evidence:
    request: AuditRequest
    plan: Plan
    inputs: dict[str, object]
    protocol: dict[str, object]
    snapshot: Snapshot
    artifacts: ArtifactPackage | None = None


def _read(path: Path) -> dict[str, object]:
    return object_dict(json.loads(path.read_text()))


def export(
    request: AuditRequest,
    artifacts: ArtifactPackage | None = None,
    *,
    write_report: bool = True,
) -> dict[str, object]:
    """Export public files; allow a caller to finish checks before publishing metrics."""
    if (
        request.inputs.name != "inputs.json"
        or request.protocol.resolve() != request.inputs.with_name("protocol.json").resolve()
    ):
        raise ValueError("inputs.json and protocol.json must belong to the same frozen package")
    evidence = _load_evidence(request, artifacts)
    request.output.mkdir(parents=True)
    report = _report(evidence, [_run(run, evidence) for run in evidence.plan.runs])
    if write_report:
        write_json(request.output / "metrics.json", report)
    return report


def _load_evidence(request: AuditRequest, artifacts: ArtifactPackage | None) -> Evidence:
    snapshot = load_snapshot(request.inputs.parent, request.revision)
    return Evidence(
        request,
        frozen_plan(snapshot),
        snapshot.json("inputs.json"),
        snapshot.json("protocol.json"),
        snapshot,
        artifacts,
    )


def _run(run: Run, evidence: Evidence) -> dict[str, object]:
    source = evidence.request.runs / run.case_id / run.arm / f"rep_{run.repetition}"
    if not (source / "result.json").exists():
        return {
            **asdict(run),
            "status": "pending",
            "metrics": run_metrics({}),
            "tools": tool_audit(None, source / "workspace"),
            "workspace": {"valid": None},
        }
    result = _read(source / "result.json")
    tools = tool_audit(source / "public_trace.jsonl", source / "workspace")
    _copy_artifacts(source, evidence.request.output / run.id)
    return {
        **asdict(run),
        "status": result.get("status"),
        "metrics": run_metrics(result),
        "tools": tools,
        "workspace": workspace_audit(
            source / "workspace",
            object_dict(object_dict(evidence.inputs[run.case_id]).get("files")),
        ),
        "identity_matches": all(result.get(key) == value for key, value in asdict(run).items()),
        "artifacts": _artifact_checks(evidence, run, source),
        "content": content_audit(source, result),
        "missing_artifacts": [name for name in PUBLIC_ARTIFACTS if not (source / name).is_file()],
    }


def _copy_artifacts(source: Path, output: Path) -> None:
    output.mkdir()
    for name in PUBLIC_ARTIFACTS:
        if (source / name).is_file():
            shutil.copyfile(source / name, output / name)


def _artifact_checks(evidence: Evidence, run: Run, source: Path) -> dict[str, object]:
    if evidence.artifacts is None:
        return artifact_audit(evidence.snapshot, evidence.plan, run, source)
    return artifact_audit(
        ArtifactSource(
            evidence.artifacts.builders,
            evidence.snapshot.read(
                evidence.artifacts.task_pattern.format(case_id=run.case_id)
            ).decode(),
        ),
        evidence.plan,
        run,
        source,
    )


def _freeze_checks(evidence: Evidence) -> dict[str, object]:
    frozen = snapshot_audit(evidence.snapshot)
    if evidence.artifacts is None:
        return frozen
    builders = snapshot_audit(evidence.artifacts.builders)
    return {**frozen, "valid": frozen["valid"] and builders["valid"], "builders": builders}


def _report(evidence: Evidence, rows: list[dict[str, object]]) -> dict[str, object]:
    missing = [row["id"] for row in rows if row["status"] == "pending"]
    frozen = _freeze_checks(evidence)
    binary = binary_audit(evidence.plan.settings.binary, evidence.protocol.get("server_sha256"))
    return {
        "complete": not missing and len(rows) == evidence.protocol.get("total_runs"),
        "artifacts_complete": not missing and all(not row.get("missing_artifacts") for row in rows),
        "scheduled_runs": len(rows),
        "finalized_runs": len(rows) - len(missing),
        "expected_protocol_runs": evidence.protocol.get("total_runs"),
        "pending_runs": missing,
        "binary": binary,
        "freeze": frozen,
        "integrity_valid": frozen["valid"]
        and binary["valid"]
        and digest(evidence.request.runs / "manifest.json")
        == object_dict(evidence.protocol.get("files")).get("manifest.json")
        and all(_run_valid(row) for row in rows),
        "manifest_sha256": digest(evidence.request.runs / "manifest.json"),
        "frozen_manifest_sha256": object_dict(evidence.protocol.get("files")).get("manifest.json"),
        "manifest_matches": digest(evidence.request.runs / "manifest.json")
        == object_dict(evidence.protocol.get("files")).get("manifest.json"),
        "inputs_sha256": digest(evidence.request.inputs),
        "definitions": {
            "raw_total_tokens": "input_tokens + output_tokens; cache/reasoning subsets not added",
            "input_minus_cached_tokens": "input_tokens - cached_input_tokens; not monetary cost",
            "difference_mcp_minus_text": "Treatment minus baseline within one case/repetition",
            "sum": "Null if any scheduled observation is missing; no imputation",
            "duration_seconds": "CLI process monotonic wait duration, including model/tool time",
            "commands": "Completed commands retained for human protocol review; no regex verdict",
            "complete": "Every scheduled attempt finalized; failures remain included",
            "artifacts_complete": "Every finalized attempt has all five public artifacts",
            "integrity_valid": (
                "Frozen files, runtime metadata and public artifact consistency checks pass; "
                "this does not attest provider-reported truth"
            ),
        },
        "runs": rows,
        "pairs": paired_metrics(rows),
        "summaries": group_summaries(rows, _groups(evidence.protocol)),
    }


def _run_valid(row: dict[str, object]) -> bool:
    artifacts = object_dict(row.get("artifacts"))
    return all(
        (
            row.get("identity_matches") is True,
            not row.get("missing_artifacts"),
            object_dict(row.get("workspace")).get("valid") is True,
            object_dict(row.get("content")).get("valid") is True,
            all(
                object_dict(artifacts.get(name)).get("valid") is True
                for name in ("prompt", "invocation")
            ),
        )
    )


def _groups(protocol: dict[str, object]) -> dict[str, list[str]]:
    return {
        name: [str(case) for case in cases]
        for name, key in (
            ("real_rtl", "real_rtl_cases"),
            ("synthetic_controls", "synthetic_controls"),
        )
        if isinstance(cases := protocol.get(key), list)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=Path(__file__).with_name("inputs.json"))
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).with_name("protocol.json"),
        help="Must be protocol.json beside --inputs; committed bytes are authoritative",
    )
    parser.add_argument("--revision", default=FROZEN_REVISION)
    args = parser.parse_args()
    report = export(AuditRequest(args.runs, args.output, args.inputs, args.protocol, args.revision))
    print(
        json.dumps({key: report[key] for key in ("complete", "scheduled_runs", "finalized_runs")})
    )


if __name__ == "__main__":
    main()
