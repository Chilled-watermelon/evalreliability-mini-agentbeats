from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, HttpUrl

from . import ADAPTER_SCHEMA, BASELINE_COMMIT, RESULT_SCHEMA


class AssessmentRequest(BaseModel):
    """AgentBeats assessment request, following the official Green Agent template."""

    model_config = ConfigDict(extra="forbid")
    participants: dict[str, HttpUrl]
    config: dict[str, Any]


class SubjectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["evaluate"] = "evaluate"
    mutation: Literal["none", "details_array"] = "none"


def validate_result_schema(result: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result must be an object"]

    expected_keys = {
        "schema_version",
        "adapter_schema",
        "baseline_commit",
        "benchmark",
        "status",
        "case_plan",
        "mode_results",
        "metrics",
        "artifacts",
        "claims",
        "failures",
    }
    if set(result) != expected_keys:
        errors.append("result keys differ from the fixed schema")
    if result.get("schema_version") != RESULT_SCHEMA:
        errors.append("result schema_version mismatch")
    if result.get("adapter_schema") != ADAPTER_SCHEMA:
        errors.append("adapter_schema mismatch")
    if result.get("baseline_commit") != BASELINE_COMMIT:
        errors.append("baseline_commit mismatch")
    if result.get("status") not in {"PASS", "FAIL"}:
        errors.append("status must be PASS or FAIL")

    case_plan = result.get("case_plan")
    if not isinstance(case_plan, dict) or case_plan.get("total") != 12:
        errors.append("case_plan must report 12 cases")
    elif case_plan.get("fault_counts") != {
        "none": 3,
        "timeout": 3,
        "tool_error": 3,
        "interruption": 3,
    }:
        errors.append("fault plan differs from the RC1 manifest")

    mode_results = result.get("mode_results")
    if not isinstance(mode_results, dict) or set(mode_results) != {"baseline", "recovery"}:
        errors.append("mode_results must contain baseline and recovery")

    metrics = result.get("metrics")
    required_metrics = {
        "trace_schema",
        "recovery_transition",
        "success_path_negative_control",
        "baseline_fail_fast_transition",
        "replay_idempotency",
    }
    if not isinstance(metrics, dict) or set(metrics) != required_metrics:
        errors.append("validator metrics differ from the fixed RC1 metric set")

    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("sha256"), dict):
        errors.append("artifacts.sha256 must be an object")

    claims = result.get("claims")
    expected_claims = {
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
    if claims != expected_claims:
        errors.append("claim boundary mismatch")
    if not isinstance(result.get("failures"), list):
        errors.append("failures must be an array")
    return errors
