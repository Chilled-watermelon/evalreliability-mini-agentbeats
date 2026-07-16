from __future__ import annotations

import copy
import unittest

from agentbeats_adapter.adapter import build_subject_payload, validate_subject_payload
from agentbeats_adapter.protocol import validate_result_schema


class AgentBeatsAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.positive_payload = build_subject_payload("none")
        cls.positive_result = validate_subject_payload(cls.positive_payload)
        cls.negative_result = validate_subject_payload(build_subject_payload("details_array"))

    def test_positive_result_preserves_rc1_metrics(self) -> None:
        self.assertEqual(self.positive_result["status"], "PASS")
        self.assertEqual(self.positive_result["mode_results"]["baseline"]["success"], 3)
        self.assertEqual(self.positive_result["mode_results"]["recovery"]["success"], 12)
        self.assertEqual(
            self.positive_result["metrics"]["recovery_transition"]["valid_case_count"],
            9,
        )
        self.assertEqual(validate_result_schema(self.positive_result), [])

    def test_details_array_negative_control_returns_fail(self) -> None:
        self.assertEqual(self.negative_result["status"], "FAIL")
        self.assertEqual(
            self.negative_result["metrics"]["trace_schema"]["valid_event_count"],
            278,
        )
        self.assertEqual(
            self.negative_result["metrics"]["trace_schema"]["total_event_count"],
            279,
        )
        self.assertTrue(
            any("details must be an object" in item for item in self.negative_result["failures"])
        )

    def test_artifact_hash_tamper_returns_fail_without_exception(self) -> None:
        payload = copy.deepcopy(self.positive_payload)
        payload["file_sha256"]["traces.jsonl"] = "0" * 64
        result = validate_subject_payload(payload)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("subject artifact hash mismatch: traces.jsonl", result["failures"])

    def test_claim_boundary_is_machine_checked(self) -> None:
        result = copy.deepcopy(self.positive_result)
        result["claims"]["not_production_grade"] = False
        self.assertIn("claim boundary mismatch", validate_result_schema(result))


if __name__ == "__main__":
    unittest.main()
