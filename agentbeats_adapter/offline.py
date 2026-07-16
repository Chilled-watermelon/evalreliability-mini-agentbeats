from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from .a2a_support import send_message_for_data
from .protocol import validate_result_schema


def _stable_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, value: object) -> None:
    path.write_text(_stable_json(value), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_agent(url: str, process: subprocess.Popen[bytes] | None = None) -> None:
    deadline = time.monotonic() + 30
    card_url = f"{url.rstrip('/')}/.well-known/agent-card.json"
    with httpx.Client(trust_env=False) as client:
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                raise RuntimeError("A2A server stopped before becoming ready")
            try:
                if client.get(card_url, timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    raise RuntimeError("A2A server readiness timeout")


async def run_remote_assessment(green_url: str, subject_url: str, mutation: str) -> dict[str, Any]:
    request = {
        "participants": {"subject": subject_url},
        "config": {"mutation": mutation},
    }
    result = await send_message_for_data(_stable_json(request), green_url)
    errors = validate_result_schema(result)
    if errors:
        raise RuntimeError(f"result schema errors: {errors}")
    return result


def assert_positive(result: dict[str, Any]) -> None:
    if result["status"] != "PASS":
        raise RuntimeError(f"positive assessment failed: {result['failures']}")
    if result["mode_results"]["baseline"] != {
        "success": 3,
        "total": 12,
        "recovered": 0,
        "faulted": 9,
    }:
        raise RuntimeError("baseline result changed")
    if result["mode_results"]["recovery"] != {
        "success": 12,
        "total": 12,
        "recovered": 9,
        "faulted": 9,
    }:
        raise RuntimeError("recovery result changed")
    metrics = result["metrics"]
    expected = {
        "trace_schema": (279, 279),
        "recovery_transition": (9, 9),
        "success_path_negative_control": (6, 6),
        "baseline_fail_fast_transition": (9, 9),
        "replay_idempotency": (2, 2),
    }
    numerator_keys = {
        "trace_schema": "valid_event_count",
        "recovery_transition": "valid_case_count",
        "success_path_negative_control": "valid_path_count",
        "baseline_fail_fast_transition": "valid_case_count",
        "replay_idempotency": "valid_mode_count",
    }
    denominator_keys = {
        "trace_schema": "total_event_count",
        "recovery_transition": "total_case_count",
        "success_path_negative_control": "total_path_count",
        "baseline_fail_fast_transition": "total_case_count",
        "replay_idempotency": "total_mode_count",
    }
    for name, (numerator, denominator) in expected.items():
        if metrics[name][numerator_keys[name]] != numerator:
            raise RuntimeError(f"{name} numerator changed")
        if metrics[name][denominator_keys[name]] != denominator:
            raise RuntimeError(f"{name} denominator changed")


def assert_negative(result: dict[str, Any]) -> None:
    if result["status"] != "FAIL":
        raise RuntimeError("negative control did not fail")
    schema = result["metrics"]["trace_schema"]
    if (schema.get("valid_event_count"), schema.get("total_event_count")) != (278, 279):
        raise RuntimeError("negative control schema denominator changed")
    if not any("details must be an object" in failure for failure in result["failures"]):
        raise RuntimeError("negative control failure is not readable")


def write_assessment_set(
    output_dir: Path,
    positive_one: dict[str, Any],
    positive_two: dict[str, Any],
    negative: dict[str, Any],
    extra_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.iterdir():
        if path.is_file():
            path.unlink()
    assert_positive(positive_one)
    assert_positive(positive_two)
    assert_negative(negative)
    if positive_one != positive_two:
        raise RuntimeError("consecutive positive assessments are not byte-stable")

    _write_json(output_dir / "positive-run-1.json", positive_one)
    _write_json(output_dir / "positive-run-2.json", positive_two)
    _write_json(output_dir / "negative-details-array.json", negative)
    summary = {
        "status": "PASS",
        "positive_runs_identical": True,
        "positive_result_sha256": _sha256(output_dir / "positive-run-1.json"),
        "negative_status": negative["status"],
        "negative_trace_schema": negative["metrics"]["trace_schema"],
    }
    if extra_summary:
        summary.update(extra_summary)
    _write_json(output_dir / "assessment-summary.json", summary)
    names = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    checksums = "".join(f"{_sha256(output_dir / name)}  {name}\n" for name in names)
    (output_dir / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    return summary


async def run_local(output_dir: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    purple_port = _free_port()
    green_port = _free_port()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root)
    commands = [
        [
            sys.executable,
            "-m",
            "agentbeats_adapter.server",
            "--role",
            "purple",
            "--host",
            "127.0.0.1",
            "--port",
            str(purple_port),
        ],
        [
            sys.executable,
            "-m",
            "agentbeats_adapter.server",
            "--role",
            "green",
            "--host",
            "127.0.0.1",
            "--port",
            str(green_port),
        ],
    ]
    processes = [
        subprocess.Popen(
            command,
            cwd=repo_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for command in commands
    ]
    purple_url = f"http://127.0.0.1:{purple_port}/"
    green_url = f"http://127.0.0.1:{green_port}/"
    try:
        _wait_for_agent(purple_url, processes[0])
        _wait_for_agent(green_url, processes[1])
        positive_one = await run_remote_assessment(green_url, purple_url, "none")
        positive_two = await run_remote_assessment(green_url, purple_url, "none")
        negative = await run_remote_assessment(green_url, purple_url, "details_array")
        return write_assessment_set(output_dir, positive_one, positive_two, negative)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local AgentBeats A2A assessment")
    parser.add_argument("--output", default="artifacts/agentbeats/live")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = (repo_root / args.output).resolve()
    artifacts_root = (repo_root / "artifacts").resolve()
    if artifacts_root not in output_dir.parents:
        raise SystemExit("--output must be under artifacts/")
    summary = asyncio.run(run_local(output_dir))
    print("AgentBeats local A2A: PASS")
    print("Positive assessments: 2/2 identical")
    print("Negative details-array control: FAIL 278/279 as expected")
    print(f"Positive result SHA-256: {summary['positive_result_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
