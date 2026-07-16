from __future__ import annotations

import importlib.metadata
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .cases import INTERRUPTION, NO_FAULT, TIMEOUT, TOOL_ERROR, ReplayCase
from .storage import JsonLedger
from .tracing import TraceWriter


FRAMEWORK_SOURCE = "https://github.com/langchain-ai/langgraph/tree/main/libs/langgraph"


class WorkflowState(TypedDict, total=False):
    case_id: str
    input_value: int
    fetched_value: int
    transformed_value: int
    receipt: str


class InjectedFault(RuntimeError):
    def __init__(self, kind: str, node: str, phase: str):
        super().__init__(f"deterministic {kind} injected at {node}:{phase}")
        self.kind = kind
        self.node = node
        self.phase = phase


@dataclass(frozen=True)
class CaseResult:
    mode: str
    case_id: str
    fault: str
    success: bool
    recovered: bool
    elapsed_ms: float
    final_result: str | None
    failure: str | None
    replay_skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def framework_info() -> dict[str, str]:
    distribution = importlib.metadata.distribution("langgraph")
    return {
        "name": "LangGraph",
        "distribution": distribution.metadata["Name"],
        "version": distribution.version,
        "source": FRAMEWORK_SOURCE,
        "state_graph_module": StateGraph.__module__,
        "checkpoint_class": InMemorySaver.__name__,
    }


def runtime_probe() -> dict[str, Any]:
    class ProbeState(TypedDict):
        value: int

    def add_seven(state: ProbeState) -> dict[str, int]:
        return {"value": state["value"] + 7}

    builder = StateGraph(ProbeState)
    builder.add_node("deterministic_tool", add_seven)
    builder.add_edge(START, "deterministic_tool")
    builder.add_edge("deterministic_tool", END)
    graph = builder.compile()
    result = graph.invoke({"value": 5})
    if result != {"value": 12}:
        raise RuntimeError(f"LangGraph runtime probe failed: {result}")
    return {
        "status": "PASS",
        "runtime_type": type(graph).__name__,
        "framework_module": StateGraph.__module__,
        "input": {"value": 5},
        "output": result,
        "node": "deterministic_tool",
    }


class DeterministicToolbox:
    def __init__(self, ledger: JsonLedger):
        self.ledger = ledger

    @staticmethod
    def fetch(input_value: int) -> int:
        return input_value

    @staticmethod
    def transform(fetched_value: int) -> int:
        return fetched_value * 3 + 1

    def commit(self, case_id: str, transformed_value: int) -> tuple[str, bool]:
        receipt = f"receipt:{case_id}:{transformed_value}"
        return self.ledger.record_side_effect(f"{case_id}:commit", receipt)


class LangGraphEvalRunner:
    def __init__(self, mode: str, cases: list[ReplayCase], ledger: JsonLedger, trace: TraceWriter):
        if mode not in {"baseline", "recovery"}:
            raise ValueError(f"unsupported mode: {mode}")
        self.mode = mode
        self.cases = {case.case_id: case for case in cases}
        self.ledger = ledger
        self.trace = trace
        self.tools = DeterministicToolbox(ledger)
        self.checkpointer = InMemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("fetch", self._fetch_node)
        builder.add_node("transform", self._transform_node)
        builder.add_node("commit", self._commit_node)
        builder.add_edge(START, "fetch")
        builder.add_edge("fetch", "transform")
        builder.add_edge("transform", "commit")
        builder.add_edge("commit", END)
        return builder.compile(checkpointer=self.checkpointer)

    def _thread_id(self, case: ReplayCase) -> str:
        return f"{self.mode}:{case.case_id}"

    def _event(
        self,
        case: ReplayCase,
        *,
        attempt: int,
        state: str,
        node: str | None,
        elapsed_ms: float,
        final_result: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.trace.write(
            framework="LangGraph",
            mode=self.mode,
            case_id=case.case_id,
            fault=case.fault,
            graph_thread_id=self._thread_id(case),
            attempt=attempt,
            state=state,
            node=node,
            elapsed_ms=round(elapsed_ms, 6),
            final_result=final_result,
            details=details or {},
        )

    def _case_from_state(self, state: WorkflowState) -> ReplayCase:
        return self.cases[str(state["case_id"])]

    @staticmethod
    def _fault_matches(case: ReplayCase, node: str, phase: str, attempt: int) -> bool:
        return (
            case.fault != NO_FAULT
            and case.fault_node == node
            and case.fault_phase == phase
            and case.trigger_attempt == attempt
        )

    def _before_tool(self, case: ReplayCase, node: str) -> tuple[int, int]:
        attempt = self.ledger.next_attempt(case.case_id, node)
        started = time.perf_counter_ns()
        self._event(
            case,
            attempt=attempt,
            state="node_started",
            node=node,
            elapsed_ms=0.0,
            final_result=None,
            details={"runtime": type(self.graph).__name__},
        )
        if self._fault_matches(case, node, "before_tool", attempt):
            self._event(
                case,
                attempt=attempt,
                state="fault_injected",
                node=node,
                elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000,
                final_result=None,
                details={"phase": "before_tool"},
            )
            raise InjectedFault(case.fault, node, "before_tool")
        return attempt, started

    def _fetch_node(self, state: WorkflowState) -> dict[str, int]:
        case = self._case_from_state(state)
        attempt, started = self._before_tool(case, "fetch")
        value = self.tools.fetch(int(state["input_value"]))
        self._event(
            case,
            attempt=attempt,
            state="node_completed",
            node="fetch",
            elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000,
            final_result=None,
            details={"tool": "deterministic_fetch"},
        )
        return {"fetched_value": value}

    def _transform_node(self, state: WorkflowState) -> dict[str, int]:
        case = self._case_from_state(state)
        attempt, started = self._before_tool(case, "transform")
        value = self.tools.transform(int(state["fetched_value"]))
        self._event(
            case,
            attempt=attempt,
            state="node_completed",
            node="transform",
            elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000,
            final_result=None,
            details={"tool": "deterministic_transform"},
        )
        return {"transformed_value": value}

    def _commit_node(self, state: WorkflowState) -> dict[str, str]:
        case = self._case_from_state(state)
        attempt, started = self._before_tool(case, "commit")
        receipt, reused = self.tools.commit(case.case_id, int(state["transformed_value"]))
        self._event(
            case,
            attempt=attempt,
            state="side_effect_reused" if reused else "side_effect_written",
            node="commit",
            elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000,
            final_result=receipt,
            details={"tool": "durable_commit", "idempotency_key": f"{case.case_id}:commit"},
        )
        if self._fault_matches(case, "commit", "after_side_effect", attempt):
            self._event(
                case,
                attempt=attempt,
                state="fault_injected",
                node="commit",
                elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000,
                final_result=None,
                details={"phase": "after_side_effect"},
            )
            raise InjectedFault(case.fault, "commit", "after_side_effect")
        self._event(
            case,
            attempt=attempt,
            state="node_completed",
            node="commit",
            elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000,
            final_result=receipt,
            details={"tool": "durable_commit", "side_effect_reused": reused},
        )
        return {"receipt": receipt}

    def _result_from_terminal(self, case: ReplayCase, terminal: dict[str, Any]) -> CaseResult:
        self._event(
            case,
            attempt=0,
            state="replay_skipped",
            node=None,
            elapsed_ms=0.0,
            final_result=terminal.get("final_result"),
            details={"reason": "terminal_already_recorded"},
        )
        return CaseResult(
            mode=self.mode,
            case_id=case.case_id,
            fault=case.fault,
            success=bool(terminal["success"]),
            recovered=bool(terminal["recovered"]),
            elapsed_ms=0.0,
            final_result=terminal.get("final_result"),
            failure=terminal.get("failure"),
            replay_skipped=True,
        )

    def run_case(self, case: ReplayCase) -> CaseResult:
        existing = self.ledger.terminal(case.case_id)
        if existing is not None:
            return self._result_from_terminal(case, existing)

        case_started = time.perf_counter_ns()
        config = {"configurable": {"thread_id": self._thread_id(case)}}
        initial_state: WorkflowState = {"case_id": case.case_id, "input_value": case.input_value}
        self._event(
            case,
            attempt=0,
            state="case_started",
            node=None,
            elapsed_ms=0.0,
            final_result=None,
            details={"framework_runtime": type(self.graph).__name__},
        )

        try:
            invocation = self.ledger.increment_graph_invocation(case.case_id)
            self._event(
                case,
                attempt=invocation,
                state="graph_invoked",
                node=None,
                elapsed_ms=0.0,
                final_result=None,
                details={"resume": False},
            )
            graph_result = self.graph.invoke(initial_state, config)
        except InjectedFault as fault:
            if self.mode != "recovery":
                return self._finish(
                    case,
                    case_started=case_started,
                    success=False,
                    final_result=None,
                    failure=fault.kind,
                )
            resume_count = self.ledger.increment_resume(case.case_id)
            self._event(
                case,
                attempt=resume_count,
                state="graph_resume_scheduled",
                node=fault.node,
                elapsed_ms=0.0,
                final_result=None,
                details={"fault": fault.kind, "checkpoint": "LangGraph InMemorySaver"},
            )
            invocation = self.ledger.increment_graph_invocation(case.case_id)
            self._event(
                case,
                attempt=invocation,
                state="graph_invoked",
                node=fault.node,
                elapsed_ms=0.0,
                final_result=None,
                details={"resume": True},
            )
            graph_result = self.graph.invoke(None, config)

        final_result = graph_result.get("receipt")
        success = final_result == case.expected_result
        return self._finish(
            case,
            case_started=case_started,
            success=success,
            final_result=final_result,
            failure=None if success else "result_mismatch",
        )

    def _finish(
        self,
        case: ReplayCase,
        *,
        case_started: int,
        success: bool,
        final_result: str | None,
        failure: str | None,
    ) -> CaseResult:
        elapsed_ms = (time.perf_counter_ns() - case_started) / 1_000_000
        snapshot = self.ledger.run_snapshot(case.case_id)
        recovered = case.fault != NO_FAULT and success and int(snapshot["resume_count"]) > 0
        terminal = {
            "success": success,
            "recovered": recovered,
            "elapsed_ms": None,
            "final_result": final_result,
            "failure": failure,
        }
        if not self.ledger.record_terminal(case.case_id, terminal):
            raise RuntimeError(f"duplicate terminal write was not prevented for {case.case_id}")
        self._event(
            case,
            attempt=0,
            state="case_succeeded" if success else "case_failed",
            node=None,
            elapsed_ms=elapsed_ms,
            final_result=final_result,
            details={"failure": failure, "recovered": recovered},
        )
        return CaseResult(
            mode=self.mode,
            case_id=case.case_id,
            fault=case.fault,
            success=success,
            recovered=recovered,
            elapsed_ms=round(elapsed_ms, 6),
            final_result=final_result,
            failure=failure,
        )
