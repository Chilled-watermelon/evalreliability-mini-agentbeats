from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .cases import build_cases, manifest_payload
from .framework import LangGraphEvalRunner, framework_info, runtime_probe
from .reporting import build_summary, write_json, write_report, write_sha256s
from .storage import JsonLedger
from .tracing import TraceWriter


KNOWN_OUTPUTS = {
    "SHA256SUMS",
    "baseline_ledger.json",
    "case_manifest.json",
    "feasibility.json",
    "recovery_ledger.json",
    "report.md",
    "summary.json",
    "test-results.txt",
    "traces.jsonl",
}


def clean_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in KNOWN_OUTPUTS:
        path = output_dir / name
        if path.exists():
            path.unlink()


def _replay_check(runner: LangGraphEvalRunner, cases, ledger: JsonLedger) -> dict[str, Any]:
    before_terminal = ledger.terminal_count()
    before_side_effect = ledger.side_effect_count()
    replay_results = [runner.run_case(case) for case in cases]
    after_terminal = ledger.terminal_count()
    after_side_effect = ledger.side_effect_count()
    return {
        "replayed_case_count": len(replay_results),
        "replay_skipped_count": sum(result.replay_skipped for result in replay_results),
        "terminal_records_before": before_terminal,
        "terminal_records_after": after_terminal,
        "side_effect_records_before": before_side_effect,
        "side_effect_records_after": after_side_effect,
        "terminal_deduplicated": before_terminal == after_terminal,
        "side_effects_deduplicated": before_side_effect == after_side_effect,
    }


def run_experiment(output_dir: Path) -> dict[str, Any]:
    clean_output(output_dir)
    cases = build_cases()
    manifest = manifest_payload(cases)
    write_json(output_dir / "case_manifest.json", manifest)
    probe = runtime_probe()
    write_json(
        output_dir / "feasibility.json",
        {
            "status": "PASS",
            "framework": framework_info(),
            "probe": probe,
            "candidate_imports": {
                "LangGraph": {"module": "langgraph", "status": "PASS", "runtime_executed": True},
                "OpenAI Agents SDK": {"module": "agents", "status": "NOT_IMPORTABLE"},
                "AutoGen": {"modules": ["autogen", "autogen_agentchat"], "status": "NOT_IMPORTABLE"},
            },
            "constraints": {
                "new_install": False,
                "network": False,
                "account_or_key": False,
                "paid_api": False,
            },
        },
    )

    trace = TraceWriter(output_dir / "traces.jsonl")
    results = {}
    ledgers = {}
    runners = {}
    for mode in ("baseline", "recovery"):
        ledger = JsonLedger(output_dir / f"{mode}_ledger.json", mode)
        runner = LangGraphEvalRunner(mode, cases, ledger, trace)
        ledgers[mode] = ledger
        runners[mode] = runner
        results[mode] = [runner.run_case(case) for case in cases]

    replay_checks = {
        mode: _replay_check(runners[mode], cases, ledgers[mode])
        for mode in ("baseline", "recovery")
    }
    summary = build_summary(cases, results, ledgers, replay_checks)
    write_json(output_dir / "summary.json", summary)
    write_report(output_dir / "report.md", summary)
    return summary


def validate_outputs(output_dir: Path) -> None:
    missing = [name for name in KNOWN_OUTPUTS - {"SHA256SUMS"} if not (output_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"missing output files: {sorted(missing)}")

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    if not summary["comparison"]["same_case_plan"]:
        raise RuntimeError("baseline and recovery case plans differ")
    for mode in ("baseline", "recovery"):
        metrics = summary["modes"][mode]
        if metrics["case_count"] != summary["case_plan"]["total"]:
            raise RuntimeError(f"{mode} case count mismatch")
        replay = summary["replay_idempotency_check"][mode]
        if not replay["terminal_deduplicated"] or not replay["side_effects_deduplicated"]:
            raise RuntimeError(f"{mode} replay idempotency check failed")

    required_trace_fields = TraceWriter.REQUIRED_FIELDS | {"schema_version", "sequence", "timestamp_utc"}
    lines = (output_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    if not lines:
        raise RuntimeError("trace file is empty")
    for number, line in enumerate(lines, start=1):
        event = json.loads(line)
        missing_fields = required_trace_fields.difference(event)
        if missing_fields:
            raise RuntimeError(f"trace line {number} missing {sorted(missing_fields)}")


def run_tests(repo_root: Path, output_dir: Path) -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    (output_dir / "test-results.txt").write_text(combined, encoding="utf-8")
    print(combined, end="")
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic LangGraph reliability integration")
    parser.add_argument("--output", default="artifacts/live", help="output directory under repository root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = (repo_root / args.output).resolve()
    artifacts_root = (repo_root / "artifacts").resolve()
    if output_dir != artifacts_root and artifacts_root not in output_dir.parents:
        raise SystemExit("--output must be under artifacts/")

    summary = run_experiment(output_dir)
    test_returncode = run_tests(repo_root, output_dir)
    validate_outputs(output_dir)
    hashes = write_sha256s(output_dir)

    baseline = summary["modes"]["baseline"]
    recovery = summary["modes"]["recovery"]
    print(f"Framework: LangGraph {summary['framework']['version']}")
    print(f"Cases: {summary['case_plan']['total']} deterministic synthetic cases")
    print(f"Baseline: {baseline['success_count']}/{baseline['case_count']} success; recovered {baseline['recovered_case_count']}/{baseline['faulted_case_count']}")
    print(f"Recovery: {recovery['success_count']}/{recovery['case_count']} success; recovered {recovery['recovered_case_count']}/{recovery['faulted_case_count']}")
    print(f"Outputs: {output_dir}")
    print(f"Hashed files: {len(hashes)}")
    return test_returncode


if __name__ == "__main__":
    raise SystemExit(main())
