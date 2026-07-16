from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION


def _empty_state(mode: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "runs": {},
        "side_effects": {},
        "suppressed_terminal_writes": 0,
    }


class JsonLedger:
    """Atomic local ledger for attempts, terminal records, and tool side effects."""

    def __init__(self, path: Path, mode: str):
        self.path = path
        self.mode = mode
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = _empty_state(mode)
        self.reload()

    def reload(self) -> None:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                self.state = json.load(handle)
            if self.state.get("mode") != self.mode:
                raise ValueError(f"ledger mode mismatch: {self.state.get('mode')} != {self.mode}")
        else:
            self._save()

    def _save(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def _run(self, case_id: str) -> dict[str, Any]:
        runs = self.state["runs"]
        if case_id not in runs:
            runs[case_id] = {
                "attempts": {},
                "graph_invocation_count": 0,
                "resume_count": 0,
                "terminal": None,
            }
            self._save()
        return runs[case_id]

    def next_attempt(self, case_id: str, node: str) -> int:
        run = self._run(case_id)
        run["attempts"][node] = int(run["attempts"].get(node, 0)) + 1
        self._save()
        return int(run["attempts"][node])

    def increment_graph_invocation(self, case_id: str) -> int:
        run = self._run(case_id)
        run["graph_invocation_count"] = int(run["graph_invocation_count"]) + 1
        self._save()
        return int(run["graph_invocation_count"])

    def increment_resume(self, case_id: str) -> int:
        run = self._run(case_id)
        run["resume_count"] = int(run["resume_count"]) + 1
        self._save()
        return int(run["resume_count"])

    def record_side_effect(self, key: str, value: str) -> tuple[str, bool]:
        side_effects = self.state["side_effects"]
        if key in side_effects:
            existing = side_effects[key]
            if existing["value"] != value:
                raise ValueError(f"idempotency key collision for {key}")
            existing["reuse_count"] = int(existing.get("reuse_count", 0)) + 1
            self._save()
            return str(existing["value"]), True
        side_effects[key] = {"value": value, "write_count": 1, "reuse_count": 0}
        self._save()
        return value, False

    def terminal(self, case_id: str) -> dict[str, Any] | None:
        terminal = self._run(case_id)["terminal"]
        return json.loads(json.dumps(terminal)) if terminal is not None else None

    def record_terminal(self, case_id: str, record: dict[str, Any]) -> bool:
        run = self._run(case_id)
        if run["terminal"] is not None:
            self.state["suppressed_terminal_writes"] += 1
            self._save()
            return False
        run["terminal"] = record
        self._save()
        return True

    def run_snapshot(self, case_id: str) -> dict[str, Any]:
        return json.loads(json.dumps(self._run(case_id)))

    def terminal_count(self) -> int:
        return sum(run["terminal"] is not None for run in self.state["runs"].values())

    def side_effect_count(self) -> int:
        return len(self.state["side_effects"])

    def suppressed_terminal_writes(self) -> int:
        return int(self.state["suppressed_terminal_writes"])
