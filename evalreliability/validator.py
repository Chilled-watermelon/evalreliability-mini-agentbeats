from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .cases import INTERRUPTION, NO_FAULT
from .tracing import TraceWriter


ALLOWED_MODES = {"baseline", "recovery"}
ALLOWED_NODES = {None, "fetch", "transform", "commit"}
ALLOWED_STATES = {
    "case_started",
    "graph_invoked",
    "node_started",
    "node_completed",
    "fault_injected",
    "graph_resume_scheduled",
    "side_effect_written",
    "side_effect_reused",
    "case_succeeded",
    "case_failed",
    "replay_skipped",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _schema_errors(event: dict[str, Any], line_number: int, cases: dict[str, dict[str, Any]]) -> list[str]:
    required = TraceWriter.REQUIRED_FIELDS | {"schema_version", "sequence"}
    errors: list[str] = []
    missing = sorted(required.difference(event))
    if missing:
        errors.append(f"trace line {line_number}: missing fields {missing}")
        return errors

    unexpected = sorted(set(event).difference(required))
    if unexpected:
        errors.append(f"trace line {line_number}: unexpected fields {unexpected}")

    if event["schema_version"] != SCHEMA_VERSION:
        errors.append(f"trace line {line_number}: schema_version mismatch")
    if (
        not isinstance(event["sequence"], int)
        or isinstance(event["sequence"], bool)
        or event["sequence"] != line_number
    ):
        errors.append(f"trace line {line_number}: non-contiguous sequence")
    if event["framework"] != "LangGraph":
        errors.append(f"trace line {line_number}: framework is not LangGraph")
    mode = event["mode"]
    case_id = event["case_id"]
    state = event["state"]
    node = event["node"]
    if not isinstance(mode, str) or mode not in ALLOWED_MODES:
        errors.append(f"trace line {line_number}: invalid mode")
    if not isinstance(case_id, str) or case_id not in cases:
        errors.append(f"trace line {line_number}: unknown case_id")
    elif event["fault"] != cases[case_id]["fault"]:
        errors.append(f"trace line {line_number}: fault differs from case manifest")
    expected_thread = f"{mode}:{case_id}"
    if event["graph_thread_id"] != expected_thread:
        errors.append(f"trace line {line_number}: graph_thread_id mismatch")
    if not isinstance(event["attempt"], int) or isinstance(event["attempt"], bool) or event["attempt"] < 0:
        errors.append(f"trace line {line_number}: attempt must be a non-negative integer")
    if not isinstance(state, str) or state not in ALLOWED_STATES:
        errors.append(f"trace line {line_number}: invalid state")
    if node is not None and (not isinstance(node, str) or node not in ALLOWED_NODES):
        errors.append(f"trace line {line_number}: invalid node")
    if event["elapsed_ms"] is not None:
        errors.append(f"trace line {line_number}: wall-clock timing must be excluded from RC evidence")
    if event["final_result"] is not None and not isinstance(event["final_result"], str):
        errors.append(f"trace line {line_number}: final_result must be null or string")
    if not isinstance(event["details"], dict):
        errors.append(f"trace line {line_number}: details must be an object")
    return errors


def _ordered_steps(events: list[dict[str, Any]], expected: list[tuple[str, str | None]]) -> bool:
    cursor = 0
    for event in events:
        if cursor < len(expected) and (event.get("state"), event.get("node")) == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def _success_path_valid(
    events: list[dict[str, Any]],
    run: dict[str, Any],
    case: dict[str, Any],
) -> bool:
    states = [event.get("state") for event in events]
    graph_invocations = [event for event in events if event.get("state") == "graph_invoked"]
    expected_order = [
        ("case_started", None),
        ("graph_invoked", None),
        ("node_started", "fetch"),
        ("node_completed", "fetch"),
        ("node_started", "transform"),
        ("node_completed", "transform"),
        ("node_started", "commit"),
        ("side_effect_written", "commit"),
        ("node_completed", "commit"),
        ("case_succeeded", None),
        ("replay_skipped", None),
    ]
    terminal = run.get("terminal") or {}
    if len(graph_invocations) != 1:
        return False
    return all(
        (
            case["fault"] == NO_FAULT,
            "fault_injected" not in states,
            "graph_resume_scheduled" not in states,
            "case_failed" not in states,
            graph_invocations[0].get("details", {}).get("resume") is False,
            _ordered_steps(events, expected_order),
            run.get("graph_invocation_count") == 1,
            run.get("resume_count") == 0,
            run.get("attempts") == {"fetch": 1, "transform": 1, "commit": 1},
            terminal.get("success") is True,
            terminal.get("recovered") is False,
            terminal.get("final_result") == case["expected_result"],
        )
    )


def _recovery_transition_valid(
    events: list[dict[str, Any]],
    run: dict[str, Any],
    case: dict[str, Any],
) -> bool:
    fault_events = [
        (index, event)
        for index, event in enumerate(events)
        if event.get("state") == "fault_injected"
    ]
    schedules = [index for index, event in enumerate(events) if event.get("state") == "graph_resume_scheduled"]
    resumes = [
        index
        for index, event in enumerate(events)
        if event.get("state") == "graph_invoked" and event.get("details", {}).get("resume") is True
    ]
    retries = [
        index
        for index, event in enumerate(events)
        if event.get("state") == "node_started"
        and event.get("node") == case["fault_node"]
        and event.get("attempt") == 2
    ]
    successes = [index for index, event in enumerate(events) if event.get("state") == "case_succeeded"]
    if not (len(fault_events) == len(schedules) == len(resumes) == len(retries) == len(successes) == 1):
        return False

    fault_index, fault_event = fault_events[0]
    schedule_index = schedules[0]
    resume_index = resumes[0]
    retry_index = retries[0]
    success_index = successes[0]
    terminal = run.get("terminal") or {}
    common = all(
        (
            fault_event.get("fault") == case["fault"],
            fault_event.get("node") == case["fault_node"],
            fault_event.get("attempt") == case["trigger_attempt"],
            fault_event.get("details", {}).get("phase") == case["fault_phase"],
            fault_index < schedule_index < resume_index < retry_index < success_index,
            run.get("graph_invocation_count") == 2,
            run.get("resume_count") == 1,
            run.get("attempts", {}).get(case["fault_node"]) == 2,
            terminal.get("success") is True,
            terminal.get("recovered") is True,
            terminal.get("final_result") == case["expected_result"],
        )
    )
    if not common:
        return False

    if case["fault"] == INTERRUPTION:
        written = [index for index, event in enumerate(events) if event.get("state") == "side_effect_written"]
        reused = [index for index, event in enumerate(events) if event.get("state") == "side_effect_reused"]
        return (
            len(written) == 1
            and len(reused) == 1
            and written[0] < fault_index
            and retry_index < reused[0] < success_index
        )
    return not any(event.get("state") == "side_effect_reused" for event in events)


def _baseline_fail_fast_valid(
    events: list[dict[str, Any]],
    run: dict[str, Any],
    case: dict[str, Any],
) -> bool:
    states = [event.get("state") for event in events]
    terminal = run.get("terminal") or {}
    return all(
        (
            states.count("fault_injected") == 1,
            "graph_resume_scheduled" not in states,
            "case_succeeded" not in states,
            states.count("case_failed") == 1,
            run.get("graph_invocation_count") == 1,
            run.get("resume_count") == 0,
            terminal.get("success") is False,
            terminal.get("recovered") is False,
            terminal.get("failure") == case["fault"],
        )
    )


def _idempotency_valid(
    mode: str,
    events: list[dict[str, Any]],
    ledger: dict[str, Any],
    replay: dict[str, Any],
    cases: dict[str, dict[str, Any]],
) -> bool:
    terminal_count = sum(run.get("terminal") is not None for run in ledger["runs"].values())
    replay_skips = sum(
        event.get("state") == "replay_skipped" and event.get("mode") == mode
        for event in events
    )
    expected_side_effect_count = (
        len(cases)
        if mode == "recovery"
        else sum(
            case["fault"] == NO_FAULT or case["fault_phase"] == "after_side_effect"
            for case in cases.values()
        )
    )
    side_effect_shape_valid = True
    for key, record in ledger["side_effects"].items():
        case_id = key.split(":", 1)[0]
        expected_reuse = 1 if mode == "recovery" and cases[case_id]["fault"] == INTERRUPTION else 0
        if record.get("write_count") != 1 or record.get("reuse_count") != expected_reuse:
            side_effect_shape_valid = False

    return all(
        (
            replay.get("terminal_deduplicated") is True,
            replay.get("side_effects_deduplicated") is True,
            replay.get("terminal_records_before") == len(cases),
            replay.get("terminal_records_after") == len(cases),
            replay.get("side_effect_records_before") == expected_side_effect_count,
            replay.get("side_effect_records_after") == expected_side_effect_count,
            replay.get("replay_skipped_count") == len(cases),
            terminal_count == len(cases),
            len(ledger["side_effects"]) == expected_side_effect_count,
            replay_skips == len(cases),
            side_effect_shape_valid,
        )
    )


def build_validation_report(output_dir: Path) -> dict[str, Any]:
    manifest = _load_json(output_dir / "case_manifest.json")
    cases = {case["case_id"]: case for case in manifest["cases"]}
    events = _load_events(output_dir / "traces.jsonl")
    ledgers = {
        mode: _load_json(output_dir / f"{mode}_ledger.json")
        for mode in sorted(ALLOWED_MODES)
    }
    summary = _load_json(output_dir / "summary.json")

    schema_errors: list[str] = []
    valid_event_count = 0
    schema_validity: list[bool] = []
    for line_number, event in enumerate(events, start=1):
        errors = _schema_errors(event, line_number, cases)
        schema_errors.extend(errors)
        is_valid = not errors
        schema_validity.append(is_valid)
        valid_event_count += is_valid

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event, is_valid in zip(events, schema_validity, strict=True):
        if not is_valid:
            continue
        key = (event.get("mode"), event.get("case_id"))
        if isinstance(key[0], str) and isinstance(key[1], str) and key[0] in ALLOWED_MODES and key[1] in cases:
            grouped[key].append(event)

    normal_cases = [case for case in cases.values() if case["fault"] == NO_FAULT]
    success_path_results: dict[str, bool] = {}
    for mode in sorted(ALLOWED_MODES):
        for case in normal_cases:
            key = f"{mode}:{case['case_id']}"
            success_path_results[key] = _success_path_valid(
                grouped[(mode, case["case_id"])],
                ledgers[mode]["runs"].get(case["case_id"], {}),
                case,
            )

    faulted_cases = [case for case in cases.values() if case["fault"] != NO_FAULT]
    recovery_results = {
        case["case_id"]: _recovery_transition_valid(
            grouped[("recovery", case["case_id"])],
            ledgers["recovery"]["runs"].get(case["case_id"], {}),
            case,
        )
        for case in faulted_cases
    }
    baseline_results = {
        case["case_id"]: _baseline_fail_fast_valid(
            grouped[("baseline", case["case_id"])],
            ledgers["baseline"]["runs"].get(case["case_id"], {}),
            case,
        )
        for case in faulted_cases
    }
    idempotency_results = {
        mode: _idempotency_valid(
            mode,
            events,
            ledgers[mode],
            summary["replay_idempotency_check"][mode],
            cases,
        )
        for mode in sorted(ALLOWED_MODES)
    }

    valid_success_paths = sum(success_path_results.values())
    valid_recovery_cases = sum(recovery_results.values())
    valid_baseline_cases = sum(baseline_results.values())
    valid_idempotency_modes = sum(idempotency_results.values())
    failures = list(schema_errors)
    failures.extend(f"success path regression: {key}" for key, valid in success_path_results.items() if not valid)
    failures.extend(f"illegal recovery transition: {key}" for key, valid in recovery_results.items() if not valid)
    failures.extend(f"invalid baseline fail-fast transition: {key}" for key, valid in baseline_results.items() if not valid)
    failures.extend(f"replay idempotency failure: {key}" for key, valid in idempotency_results.items() if not valid)

    metrics = {
        "trace_schema": {
            "valid_event_count": valid_event_count,
            "total_event_count": len(events),
            "valid_rate": _rate(valid_event_count, len(events)),
        },
        "recovery_transition": {
            "valid_case_count": valid_recovery_cases,
            "total_case_count": len(recovery_results),
            "valid_rate": _rate(valid_recovery_cases, len(recovery_results)),
        },
        "success_path_negative_control": {
            "valid_path_count": valid_success_paths,
            "total_path_count": len(success_path_results),
            "valid_rate": _rate(valid_success_paths, len(success_path_results)),
            "zero_regression": valid_success_paths == len(success_path_results),
        },
        "baseline_fail_fast_transition": {
            "valid_case_count": valid_baseline_cases,
            "total_case_count": len(baseline_results),
            "valid_rate": _rate(valid_baseline_cases, len(baseline_results)),
        },
        "replay_idempotency": {
            "valid_mode_count": valid_idempotency_modes,
            "total_mode_count": len(idempotency_results),
            "valid_rate": _rate(valid_idempotency_modes, len(idempotency_results)),
            "terminal_and_side_effect_counts_preserved": all(idempotency_results.values()),
        },
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not failures else "FAIL",
        "metrics": metrics,
        "case_results": {
            "success_path_negative_control": success_path_results,
            "recovery_transition": recovery_results,
            "baseline_fail_fast_transition": baseline_results,
            "replay_idempotency": idempotency_results,
        },
        "definitions": {
            "trace_schema_valid_rate": "events satisfying required fields, types, manifest identity, contiguous sequence, and deterministic-field policy / all trace events",
            "recovery_transition_legal_rate": "faulted recovery cases with inject -> schedule -> resume -> retry -> success in legal order / all faulted recovery cases",
            "success_path_zero_regression": "no-fault mode/case paths with no fault or resume events and one successful graph execution / all no-fault paths",
            "replay_idempotency": "modes preserving terminal and side-effect counts with one replay skip per completed case / baseline and recovery modes",
        },
        "failures": sorted(failures),
    }


def assert_validation_pass(report: dict[str, Any]) -> None:
    if report["status"] != "PASS":
        raise RuntimeError(f"trace validation failed: {report['failures']}")
