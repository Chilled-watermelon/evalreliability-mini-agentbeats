from __future__ import annotations

import json

from a2a.server.tasks import TaskUpdater
from a2a.types import DataPart, Message, Part, TaskState
from a2a.utils import get_message_text, new_agent_text_message
from pydantic import ValidationError

from .a2a_support import send_message_for_data
from .adapter import build_subject_payload, validate_subject_payload
from .protocol import AssessmentRequest, SubjectCommand, validate_result_schema


class PurpleAgent:
    """Deterministic subject: executes the unchanged RC1 experiment without an LLM."""

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        try:
            command = SubjectCommand.model_validate_json(get_message_text(message))
        except ValidationError:
            await updater.reject(new_agent_text_message("Invalid deterministic subject command"))
            return
        await updater.update_status(
            TaskState.working,
            new_agent_text_message("Running deterministic RC1 subject"),
        )
        payload = build_subject_payload(command.mutation)
        await updater.add_artifact(
            parts=[Part(root=DataPart(data=payload))],
            name="EvalReliabilitySubjectArtifacts",
        )


class GreenAgent:
    """Green evaluator: orchestrates the subject and runs the original RC1 validator."""

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        try:
            request = AssessmentRequest.model_validate_json(get_message_text(message))
        except ValidationError:
            await updater.reject(new_agent_text_message("Invalid AgentBeats assessment request"))
            return
        subject_url = request.participants.get("subject")
        if subject_url is None:
            await updater.reject(new_agent_text_message("Missing required participant role: subject"))
            return
        mutation = request.config.get("mutation", "none")
        try:
            command = SubjectCommand(mutation=mutation)
        except ValidationError:
            await updater.reject(new_agent_text_message("Unsupported deterministic assessment config"))
            return

        await updater.update_status(
            TaskState.working,
            new_agent_text_message("Validating deterministic recovery evidence"),
        )
        subject_payload = await send_message_for_data(
            command.model_dump_json(),
            str(subject_url),
        )
        result = validate_subject_payload(subject_payload)
        schema_errors = validate_result_schema(result)
        if schema_errors:
            raise RuntimeError("result schema validation failed")
        await updater.add_artifact(
            parts=[Part(root=DataPart(data=result))],
            name="EvalReliabilityAssessmentResult",
        )
