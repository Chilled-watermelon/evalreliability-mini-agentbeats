from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION


class TraceWriter:
    REQUIRED_FIELDS = {
        "framework",
        "mode",
        "case_id",
        "fault",
        "graph_thread_id",
        "attempt",
        "state",
        "node",
        "elapsed_ms",
        "final_result",
        "details",
    }

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sequence = 0

    def write(self, **event: Any) -> None:
        missing = self.REQUIRED_FIELDS.difference(event)
        if missing:
            raise ValueError(f"trace event missing fields: {sorted(missing)}")
        self.sequence += 1
        # Wall-clock timing is intentionally excluded from deterministic release evidence.
        event["elapsed_ms"] = None
        payload = {
            "schema_version": SCHEMA_VERSION,
            "sequence": self.sequence,
            **event,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
