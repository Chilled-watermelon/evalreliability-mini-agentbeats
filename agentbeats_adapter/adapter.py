from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from evalreliability.cli import run_experiment
from evalreliability.validator import build_validation_report

from . import ADAPTER_SCHEMA, BASELINE_COMMIT, RESULT_SCHEMA
from .protocol import validate_result_schema


ARTIFACT_NAMES = {
    "baseline_ledger.json",
    "case_manifest.json",
    "recovery_ledger.json",
    "summary.json",
    "traces.jsonl",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mutate_details_array(output_dir: Path) -> None:
    trace_path = output_dir / "traces.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    for event in events:
        if event.get("state") == "graph_invoked":
            event["details"] = []
            break
    else:
        raise RuntimeError("negative control could not find graph_invoked event")
    stable = "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events)
    trace_path.write_text(stable, encoding="utf-8")


def build_subject_payload(mutation: str = "none") -> dict[str, Any]:
    if mutation not in {"none", "details_array"}:
        raise ValueError("unsupported deterministic mutation")
    with tempfile.TemporaryDirectory(prefix="evalrel-subject-") as directory:
        output_dir = Path(directory)
        run_experiment(output_dir)
        if mutation == "details_array":
            _mutate_details_array(output_dir)
        files = {
            name: (output_dir / name).read_text(encoding="utf-8")
            for name in sorted(ARTIFACT_NAMES)
        }
    return {
        "adapter_schema": ADAPTER_SCHEMA,
        "baseline_commit": BASELINE_COMMIT,
        "mutation": mutation,
        "files": files,
        "file_sha256": {name: _sha256_text(value) for name, value in files.items()},
    }


def _failure_result(failures: list[str]) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA,
        "adapter_schema": ADAPTER_SCHEMA,
        "baseline_commit": BASELINE_COMMIT,
        "benchmark": {
            "name": "EvalReliability-Mini v0.3 RC1 AgentBeats adapter",
            "framework": "LangGraph 1.1.6",
            "protocol": "A2A via the AgentBeats official template contract",
        },
        "status": "FAIL",
        "case_plan": {
            "total": 12,
            "fault_counts": {"none": 3, "timeout": 3, "tool_error": 3, "interruption": 3},
        },
        "mode_results": {
            "baseline": {"success": 0, "total": 12, "recovered": 0, "faulted": 9},
            "recovery": {"success": 0, "total": 12, "recovered": 0, "faulted": 9},
        },
        "metrics": {
            "trace_schema": {},
            "recovery_transition": {},
            "success_path_negative_control": {},
            "baseline_fail_fast_transition": {},
            "replay_idempotency": {},
        },
        "artifacts": {"sha256": {}},
        "claims": _claims(),
        "failures": sorted(failures),
    }


def _claims() -> dict[str, Any]:
    return {
        "no_llm": True,
        "local_deterministic_tools": True,
        "process_local_checkpoint": True,
        "deterministic_synthetic_cases": True,
        "research_portfolio_rc": True,
        "not_production_grade": True,
        "does_not_prove": [
            "distributed_reliability",
            "production_sla",
            "enterprise_auth",
            "real_llm_reliability",
            "multi_agent_reliability",
            "external_adoption",
        ],
    }


def validate_subject_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _failure_result(["subject payload must be an object"])
    if payload.get("adapter_schema") != ADAPTER_SCHEMA:
        return _failure_result(["subject adapter_schema mismatch"])
    if payload.get("baseline_commit") != BASELINE_COMMIT:
        return _failure_result(["subject baseline_commit mismatch"])
    files = payload.get("files")
    hashes = payload.get("file_sha256")
    if not isinstance(files, dict) or set(files) != ARTIFACT_NAMES:
        return _failure_result(["subject artifact set mismatch"])
    if not isinstance(hashes, dict) or set(hashes) != ARTIFACT_NAMES:
        return _failure_result(["subject artifact hash set mismatch"])
    for name in sorted(ARTIFACT_NAMES):
        value = files.get(name)
        if not isinstance(value, str):
            return _failure_result([f"subject artifact is not text: {name}"])
        if hashes.get(name) != _sha256_text(value):
            return _failure_result([f"subject artifact hash mismatch: {name}"])

    try:
        with tempfile.TemporaryDirectory(prefix="evalrel-green-") as directory:
            output_dir = Path(directory)
            for name, value in files.items():
                (output_dir / name).write_text(value, encoding="utf-8")
            report = build_validation_report(output_dir)
            manifest = json.loads(files["case_manifest.json"])
            summary = json.loads(files["summary.json"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return _failure_result([f"subject artifacts could not be validated: {type(error).__name__}"])

    result = {
        "schema_version": RESULT_SCHEMA,
        "adapter_schema": ADAPTER_SCHEMA,
        "baseline_commit": BASELINE_COMMIT,
        "benchmark": {
            "name": "EvalReliability-Mini v0.3 RC1 AgentBeats adapter",
            "framework": "LangGraph 1.1.6",
            "protocol": "A2A via the AgentBeats official template contract",
        },
        "status": report["status"],
        "case_plan": {
            "total": manifest["case_count"],
            "fault_counts": manifest["fault_counts"],
        },
        "mode_results": {
            mode: {
                "success": summary["modes"][mode]["success_count"],
                "total": summary["modes"][mode]["case_count"],
                "recovered": summary["modes"][mode]["recovered_case_count"],
                "faulted": summary["modes"][mode]["faulted_case_count"],
            }
            for mode in ("baseline", "recovery")
        },
        "metrics": report["metrics"],
        "artifacts": {"sha256": {name: hashes[name] for name in sorted(ARTIFACT_NAMES)}},
        "claims": _claims(),
        "failures": report["failures"],
    }
    schema_errors = validate_result_schema(result)
    if schema_errors:
        return _failure_result(schema_errors)
    return result
