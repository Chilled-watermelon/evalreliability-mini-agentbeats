from __future__ import annotations

import argparse

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .a2a_support import OFFICIAL_GREEN_TEMPLATE, OFFICIAL_PURPLE_TEMPLATE, TemplateExecutor
from .agents import GreenAgent, PurpleAgent


def _card(role: str, url: str) -> AgentCard:
    if role == "green":
        skill = AgentSkill(
            id="evalreliability_assessment",
            name="Deterministic Agent Recovery Assessment",
            description="Validates RC1 traces, recovery transitions, success controls, and replay idempotency.",
            tags=["agent-evaluation", "reliability", "deterministic", "no-llm"],
            examples=["Assess the deterministic subject using the fixed 12-case plan."],
        )
        name = "EvalReliability Green Evaluator"
        description = f"AgentBeats-compatible Green Agent derived from {OFFICIAL_GREEN_TEMPLATE}."
    else:
        skill = AgentSkill(
            id="evalreliability_subject",
            name="Deterministic LangGraph Recovery Subject",
            description="Runs the fixed RC1 LangGraph workflow and returns raw machine artifacts.",
            tags=["langgraph", "deterministic", "no-llm"],
            examples=["Run the fixed RC1 evaluation without external services."],
        )
        name = "EvalReliability Purple Subject"
        description = f"AgentBeats-compatible Purple Agent derived from {OFFICIAL_PURPLE_TEMPLATE}."
    return AgentCard(
        name=name,
        description=description,
        url=url,
        version="0.3.0-rc1",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AgentBeats A2A adapter")
    parser.add_argument("--role", choices=("green", "purple"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9009)
    parser.add_argument("--card-url")
    args = parser.parse_args()

    factory = GreenAgent if args.role == "green" else PurpleAgent
    url = args.card_url or f"http://{args.host}:{args.port}/"
    handler = DefaultRequestHandler(
        agent_executor=TemplateExecutor(factory),
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(agent_card=_card(args.role, url), http_handler=handler)
    uvicorn.run(app.build(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
