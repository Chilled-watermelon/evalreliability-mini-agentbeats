from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    InvalidRequestError,
    Message,
    Part,
    Role,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError


OFFICIAL_GREEN_TEMPLATE = "https://github.com/RDI-Foundation/green-agent-template"
OFFICIAL_PURPLE_TEMPLATE = "https://github.com/RDI-Foundation/agent-template"
TERMINAL_STATES = {
    TaskState.completed,
    TaskState.canceled,
    TaskState.failed,
    TaskState.rejected,
}


class RunnableAgent(Protocol):
    async def run(self, message: Message, updater: TaskUpdater) -> None: ...


class TemplateExecutor(AgentExecutor):
    """Executor behavior kept compatible with the official AgentBeats templates."""

    def __init__(self, factory: Callable[[], RunnableAgent]):
        self.factory = factory
        self.agents: dict[str, RunnableAgent] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        if not message:
            raise ServerError(error=InvalidRequestError(message="Missing message in request"))
        task = context.current_task
        if task and task.status.state in TERMINAL_STATES:
            raise ServerError(error=InvalidRequestError(message="Task already processed"))
        if not task:
            task = new_task(message)
            await event_queue.enqueue_event(task)

        context_id = task.context_id
        agent = self.agents.get(context_id)
        if not agent:
            agent = self.factory()
            self.agents[context_id] = agent
        updater = TaskUpdater(event_queue, task.id, context_id)
        await updater.start_work()
        try:
            await agent.run(message, updater)
            if not updater._terminal_state_reached:
                await updater.complete()
        except Exception as error:
            await updater.failed(
                new_agent_text_message(
                    f"Agent error: {type(error).__name__}",
                    context_id=context_id,
                    task_id=task.id,
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


def create_text_message(text: str, context_id: str | None = None) -> Message:
    return Message(
        kind="message",
        role=Role.user,
        parts=[Part(root=TextPart(kind="text", text=text))],
        message_id=uuid4().hex,
        context_id=context_id,
    )


def _data_from_parts(parts: list[Part]) -> dict[str, Any] | None:
    for part in parts:
        if isinstance(part.root, DataPart) and isinstance(part.root.data, dict):
            return dict(part.root.data)
    return None


async def send_message_for_data(message: str, base_url: str, timeout: int = 300) -> dict[str, Any]:
    """Send an official A2A message and return the first structured artifact."""

    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resolver = A2ACardResolver(httpx_client=client, base_url=base_url)
        card = await resolver.get_agent_card()
        a2a_client = ClientFactory(ClientConfig(httpx_client=client, streaming=False)).create(card)
        last_event = None
        async for event in a2a_client.send_message(create_text_message(message)):
            last_event = event

    if isinstance(last_event, Message):
        data = _data_from_parts(last_event.parts)
        if data is not None:
            return data
    elif isinstance(last_event, tuple):
        task, _update = last_event
        if task.status.state.value != "completed":
            raise RuntimeError("participant did not complete")
        for artifact in task.artifacts or []:
            data = _data_from_parts(artifact.parts)
            if data is not None:
                return data
    raise RuntimeError("participant returned no structured artifact")
