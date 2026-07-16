from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .cases import NO_FAULT, ReplayCase, manifest_payload
from .framework import CaseResult, framework_info
from .storage import JsonLedger


CLAIM_BOUNDARY = (
    "Research/portfolio RC using real LangGraph with deterministic synthetic cases, local deterministic tools, "
    "no LLM, and a process-local checkpoint; not production-grade and not evidence of distributed reliability, "
    "a production SLA, enterprise authentication, multi-Agent orchestration, real external adoption, or general "
    "Agent reliability."
)


def summarize_mode(results: list[CaseResult], ledger: JsonLedger) -> dict[str, Any]:
    faulted = [result for result in results if result.fault != NO_FAULT]
    successful = sum(result.success for result in results)
    recovered = sum(result.recovered for result in results)
    return {
        "case_count": len(results),
        "faulted_case_count": len(faulted),
        "success_count": successful,
        "success_rate": successful / len(results),
        "recovered_case_count": recovered,
        "recovery_rate": recovered / len(faulted),
        "terminal_record_count": ledger.terminal_count(),
        "side_effect_record_count": ledger.side_effect_count(),
        "suppressed_terminal_writes": ledger.suppressed_terminal_writes(),
        "timing": {
            "included_in_release_evidence": False,
            "reason": "Wall-clock timing is machine-dependent and excluded from deterministic RC evidence.",
        },
    }


def build_summary(
    cases: list[ReplayCase],
    results: dict[str, list[CaseResult]],
    ledgers: dict[str, JsonLedger],
    replay_checks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    manifest = manifest_payload(cases)
    mode_summaries = {mode: summarize_mode(results[mode], ledgers[mode]) for mode in ("baseline", "recovery")}
    return {
        "schema_version": SCHEMA_VERSION,
        "framework": framework_info(),
        "execution": {
            "model": "none",
            "tools": "local deterministic fetch/transform/commit",
            "network_or_external_service": False,
            "checkpoint_scope": "process-local LangGraph InMemorySaver",
            "durable_scope": "atomic local JSON terminal and side-effect ledger",
        },
        "case_plan": {
            "total": len(cases),
            **manifest["fault_counts"],
            "cases_sha256": manifest["cases_sha256"],
        },
        "comparison": {
            "same_case_plan": True,
            "success_rate_delta": round(mode_summaries["recovery"]["success_rate"] - mode_summaries["baseline"]["success_rate"], 6),
        },
        "modes": mode_summaries,
        "replay_idempotency_check": replay_checks,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_report(path: Path, summary: dict[str, Any]) -> None:
    baseline = summary["modes"]["baseline"]
    recovery = summary["modes"]["recovery"]
    baseline_replay = summary["replay_idempotency_check"]["baseline"]
    recovery_replay = summary["replay_idempotency_check"]["recovery"]
    verification = summary["verification"]
    text = f"""# EvalReliability-Mini v0.3 RC1 Verification Report

- Framework: LangGraph {summary['framework']['version']} (`StateGraph` + `InMemorySaver`)
- Cases: {summary['case_plan']['total']} deterministic synthetic replay cases; same case and fault plan in both modes
- Baseline: {baseline['success_count']}/{baseline['case_count']} success; recovery {baseline['recovered_case_count']}/{baseline['faulted_case_count']}
- Recovery: {recovery['success_count']}/{recovery['case_count']} success; recovery {recovery['recovered_case_count']}/{recovery['faulted_case_count']}
- Trace schema: {verification['trace_schema']['valid_event_count']}/{verification['trace_schema']['total_event_count']} valid
- Recovery transitions: {verification['recovery_transition']['valid_case_count']}/{verification['recovery_transition']['total_case_count']} legal
- Success-path negative controls: {verification['success_path_negative_control']['valid_path_count']}/{verification['success_path_negative_control']['total_path_count']} zero-regression
- Replay idempotency: {verification['replay_idempotency']['valid_mode_count']}/{verification['replay_idempotency']['total_mode_count']} modes preserve terminal and side-effect counts
- Baseline replay: terminal {baseline_replay['terminal_records_before']} -> {baseline_replay['terminal_records_after']}; side effects {baseline_replay['side_effect_records_before']} -> {baseline_replay['side_effect_records_after']}
- Recovery replay: terminal {recovery_replay['terminal_records_before']} -> {recovery_replay['terminal_records_after']}; side effects {recovery_replay['side_effect_records_before']} -> {recovery_replay['side_effect_records_after']}
- Model/API: no LLM; local deterministic tools; no network, account, key, paid API, or external service

## Claim boundary

{summary['claim_boundary']}
"""
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256s(output_dir: Path) -> dict[str, str]:
    hashes = {
        path.name: sha256_file(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    }
    lines = [f"{digest}  {name}" for name, digest in sorted(hashes.items())]
    (output_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hashes
