from __future__ import annotations

import hashlib
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cases import NO_FAULT, ReplayCase, manifest_payload
from .framework import CaseResult, framework_info
from .storage import JsonLedger


CLAIM_BOUNDARY = (
    "Research/portfolio MVP using LangGraph with deterministic synthetic cases and local deterministic tools; "
    "not production-grade, not a distributed production system, not a real-SLA or real-model claim, and not "
    "evidence that general Agent reliability is solved."
)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def summarize_mode(results: list[CaseResult], ledger: JsonLedger) -> dict[str, Any]:
    faulted = [result for result in results if result.fault != NO_FAULT]
    latencies = [result.elapsed_ms for result in results]
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
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 6),
            "p50": round(_percentile(latencies, 0.50), 6),
            "p95": round(_percentile(latencies, 0.95), 6),
            "total": round(sum(latencies), 6),
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
        "schema_version": "0.2",
        "generated_at_utc": datetime.now(UTC).isoformat(),
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
    text = f"""# EvalReliability-Mini v0.2 Real-Framework Report

- Framework: LangGraph {summary['framework']['version']} (`StateGraph` + `InMemorySaver`)
- Cases: {summary['case_plan']['total']} deterministic synthetic replay cases; same case and fault plan in both modes
- Baseline: {baseline['success_count']}/{baseline['case_count']} success; recovery {baseline['recovered_case_count']}/{baseline['faulted_case_count']}
- Recovery: {recovery['success_count']}/{recovery['case_count']} success; recovery {recovery['recovered_case_count']}/{recovery['faulted_case_count']}
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
