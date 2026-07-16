from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


NO_FAULT = "none"
TIMEOUT = "timeout"
TOOL_ERROR = "tool_error"
INTERRUPTION = "interruption"


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    input_value: int
    fault: str
    fault_node: str | None
    fault_phase: str | None
    trigger_attempt: int
    expected_result: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _case(number: int, fault: str, node: str | None, phase: str | None) -> ReplayCase:
    case_id = f"case-{number:03d}"
    input_value = number * 2
    transformed = input_value * 3 + 1
    return ReplayCase(
        case_id=case_id,
        input_value=input_value,
        fault=fault,
        fault_node=node,
        fault_phase=phase,
        trigger_attempt=1,
        expected_result=f"receipt:{case_id}:{transformed}",
    )


def build_cases() -> list[ReplayCase]:
    cases: list[ReplayCase] = []
    cases.extend(_case(number, NO_FAULT, None, None) for number in range(1, 4))
    cases.extend(_case(number, TIMEOUT, "transform", "before_tool") for number in range(4, 7))
    cases.extend(_case(number, TOOL_ERROR, "fetch", "before_tool") for number in range(7, 10))
    cases.extend(_case(number, INTERRUPTION, "commit", "after_side_effect") for number in range(10, 13))
    return cases


def manifest_payload(cases: list[ReplayCase]) -> dict[str, object]:
    rows = [case.to_dict() for case in cases]
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    counts = {fault: sum(case.fault == fault for case in cases) for fault in (NO_FAULT, TIMEOUT, TOOL_ERROR, INTERRUPTION)}
    return {
        "schema_version": "0.2",
        "case_count": len(cases),
        "fault_counts": counts,
        "cases_sha256": hashlib.sha256(canonical).hexdigest(),
        "cases": rows,
    }
