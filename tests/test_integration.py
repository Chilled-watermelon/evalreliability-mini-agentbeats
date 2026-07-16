from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evalreliability.cases import INTERRUPTION, TIMEOUT, TOOL_ERROR, build_cases
from evalreliability.cli import run_experiment, validate_outputs
from evalreliability.framework import framework_info, runtime_probe


class RealFrameworkIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls._temporary.name) / "artifacts"
        cls.summary = run_experiment(cls.output_dir)
        cls.baseline_ledger = json.loads((cls.output_dir / "baseline_ledger.json").read_text(encoding="utf-8"))
        cls.recovery_ledger = json.loads((cls.output_dir / "recovery_ledger.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._temporary.cleanup()

    def test_langgraph_runtime_probe_executes_compiled_graph(self):
        probe = runtime_probe()
        info = framework_info()
        self.assertEqual("PASS", probe["status"])
        self.assertEqual("CompiledStateGraph", probe["runtime_type"])
        self.assertEqual({"value": 12}, probe["output"])
        self.assertEqual("langgraph", info["distribution"])
        self.assertIn("github.com/langchain-ai/langgraph", info["source"])

    def test_manifest_has_twelve_cases_and_fixed_fault_plan(self):
        cases = build_cases()
        self.assertEqual(12, len(cases))
        self.assertEqual(3, sum(case.fault == "none" for case in cases))
        self.assertEqual(3, sum(case.fault == TIMEOUT for case in cases))
        self.assertEqual(3, sum(case.fault == TOOL_ERROR for case in cases))
        self.assertEqual(3, sum(case.fault == INTERRUPTION for case in cases))

    def test_baseline_and_recovery_use_same_case_plan(self):
        self.assertTrue(self.summary["comparison"]["same_case_plan"])
        self.assertEqual(12, self.summary["modes"]["baseline"]["case_count"])
        self.assertEqual(12, self.summary["modes"]["recovery"]["case_count"])

    def test_all_faults_fail_baseline_and_resume_in_recovery(self):
        baseline = self.summary["modes"]["baseline"]
        recovery = self.summary["modes"]["recovery"]
        self.assertEqual((3, 12), (baseline["success_count"], baseline["case_count"]))
        self.assertEqual((0, 9), (baseline["recovered_case_count"], baseline["faulted_case_count"]))
        self.assertEqual((12, 12), (recovery["success_count"], recovery["case_count"]))
        self.assertEqual((9, 9), (recovery["recovered_case_count"], recovery["faulted_case_count"]))

    def test_failed_nodes_are_reinvoked_by_langgraph_resume(self):
        for case_id in ("case-004", "case-005", "case-006"):
            self.assertEqual(2, self.recovery_ledger["runs"][case_id]["attempts"]["transform"])
        for case_id in ("case-007", "case-008", "case-009"):
            self.assertEqual(2, self.recovery_ledger["runs"][case_id]["attempts"]["fetch"])
        for case_id in ("case-010", "case-011", "case-012"):
            self.assertEqual(2, self.recovery_ledger["runs"][case_id]["attempts"]["commit"])

    def test_interruption_reuses_one_durable_side_effect(self):
        for case_id in ("case-010", "case-011", "case-012"):
            record = self.recovery_ledger["side_effects"][f"{case_id}:commit"]
            self.assertEqual(1, record["write_count"])
            self.assertEqual(1, record["reuse_count"])

    def test_replay_does_not_duplicate_terminal_or_side_effect(self):
        for mode in ("baseline", "recovery"):
            replay = self.summary["replay_idempotency_check"][mode]
            self.assertEqual(12, replay["terminal_records_before"])
            self.assertEqual(12, replay["terminal_records_after"])
            self.assertEqual(replay["side_effect_records_before"], replay["side_effect_records_after"])
            self.assertEqual(12, replay["replay_skipped_count"])

    def test_trace_contains_framework_resume_fault_and_tool_events(self):
        events = [json.loads(line) for line in (self.output_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines()]
        states = {event["state"] for event in events}
        self.assertTrue({"graph_invoked", "fault_injected", "graph_resume_scheduled", "side_effect_written", "side_effect_reused"}.issubset(states))
        self.assertTrue(all(event["framework"] == "LangGraph" for event in events))

    def test_output_validator_accepts_complete_artifacts(self):
        (self.output_dir / "test-results.txt").write_text("fixture tests passed\n", encoding="utf-8")
        validate_outputs(self.output_dir)


if __name__ == "__main__":
    unittest.main()
