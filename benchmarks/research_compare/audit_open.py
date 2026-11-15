"""Export the separate open-review experiment against its pre-run Git revision.

Usage: python -m benchmarks.research_compare.audit_open --revision COMMIT
       --runs PATH --output DIR [--metadata OPEN_REVIEW_DIRECTORY]
Only the five public per-run artifacts are exported; raw traces remain private.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.adapters.traces import object_dict
from benchmarks.research_compare.audit import ArtifactPackage, AuditRequest
from benchmarks.research_compare.audit import export as export_package
from benchmarks.research_compare.audit_freeze import (
    FROZEN_REVISION,
    Snapshot,
    frozen_plan,
    load_snapshot,
)
from benchmarks.research_compare.audit_integrity import workspace_audit
from benchmarks.research_compare.models import Case, Plan
from benchmarks.runner.storage import write_json

MAIN_DIRECTORY = Path(__file__).parent
SHARED_FILES = ("models.py", "prompts.py", "runner.py", "skill.md")
TASK_PATTERN = "cases/{case_id}/workspace/task.txt"


def export(request: AuditRequest, builders: Snapshot | None = None) -> dict[str, object]:
    """Anchor open inputs separately while retaining the original builder freeze."""
    return _export(
        request,
        load_snapshot(request.inputs.parent, request.revision),
        builders if builders is not None else load_snapshot(MAIN_DIRECTORY, FROZEN_REVISION),
    )


def _export(request: AuditRequest, snapshot: Snapshot, shared: Snapshot) -> dict[str, object]:
    checks = _input_checks(snapshot, shared, frozen_plan(snapshot))
    report = export_package(request, ArtifactPackage(shared, TASK_PATTERN), write_report=False)
    report["open_inputs"] = checks
    report["integrity_valid"] = report["integrity_valid"] and checks["valid"]
    write_json(request.output / "metrics.json", report)
    return report


def _input_checks(snapshot: Snapshot, shared: Snapshot, plan: Plan) -> dict[str, object]:
    checks = _shared_checks(snapshot, shared, plan.settings.skill)
    cases = [_case_checks(snapshot, case) for case in plan.cases]
    return {
        **checks,
        "valid": checks["valid"] and all(case["valid"] for case in cases),
        "cases": cases,
    }


def _shared_checks(snapshot: Snapshot, shared: Snapshot, skill: Path) -> dict[str, object]:
    declared = object_dict(snapshot.json("protocol.json").get("shared_files"))
    expected = {name: hashlib.sha256(shared.read(name)).hexdigest() for name in SHARED_FILES}
    return {
        "valid": declared == expected
        and skill.resolve() == (shared.root / shared.directory / "skill.md").resolve(),
        "shared_revision": shared.revision,
        "shared_files_match": declared == expected,
        "shared_declared_sha256": declared,
        "shared_frozen_sha256": expected,
        "skill_path_matches": skill.resolve()
        == (shared.root / shared.directory / "skill.md").resolve(),
    }


def _case_checks(snapshot: Snapshot, case: Case) -> dict[str, object]:
    files = _workspace_files(snapshot, case.id)
    checks = _case_inputs(snapshot, case, files)
    runtime = workspace_audit(case.workspace, files)
    return {
        "case_id": case.id,
        "valid": all(checks.values()) and runtime["valid"] is True,
        **checks,
        "runtime_source": runtime,
    }


def _case_inputs(snapshot: Snapshot, case: Case, files: dict[str, object]) -> dict[str, object]:
    inputs = object_dict(snapshot.json("inputs.json").get(case.id))
    return {
        "input_hashes_match": object_dict(inputs.get("files")) == files,
        "config_matches": inputs.get("config")
        == snapshot.json(f"cases/{case.id}/workspace/config.json"),
        "task_path_matches": case.task.resolve()
        == (snapshot.root / snapshot.directory / TASK_PATTERN.format(case_id=case.id)).resolve(),
    }


def _workspace_files(snapshot: Snapshot, case_id: str) -> dict[str, object]:
    prefix = str(snapshot.directory / f"cases/{case_id}/workspace") + "/"
    return {
        name.removeprefix(prefix): hashlib.sha256(content).hexdigest()
        for name, content in snapshot.files.items()
        if name.startswith(prefix)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True, help="Git commit frozen before the four runs")
    parser.add_argument("--metadata", type=Path, default=MAIN_DIRECTORY / "open_review")
    args = parser.parse_args()
    report = export(
        AuditRequest(
            args.runs,
            args.output,
            args.metadata / "inputs.json",
            args.metadata / "protocol.json",
            args.revision,
        )
    )
    print(
        json.dumps({key: report[key] for key in ("complete", "scheduled_runs", "finalized_runs")})
    )


if __name__ == "__main__":
    main()
