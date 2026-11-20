"""Schemas of a run's «Ask the assistant» step (``flow.run.claim_assistant``,
``flow.run.assistant_round``, ``flow.run.record_assistant``): a round of the model's calls and how the step ended."""

from typing import Any
from uuid import UUID

from ninja import Field, Schema

from apps.flow.schemas.fields import In


class ToolCallIn(In):
    call_id: str = Field(max_length=200, description="The call's id, as the model gave it.")
    name: str = Field(max_length=200, description="The tool's name, as the gateway names it (`task__task__create`).")
    arguments: str = Field("{}", max_length=200_000, description="Its data, as JSON text.")


class AssistantRoundIn(In):
    id: UUID = Field(description="The run whose «Ask the assistant» step is thinking.")
    text: str = Field("", max_length=200_000, description="What the model said with its calls.")
    calls: list[ToolCallIn] = Field(min_length=1, max_length=64, description="The reads and actions it asked for.")
    continuation: str | None = Field(None, max_length=4096, description="What the gateway gave with the calls.")


class RecordAssistantIn(In):
    id: UUID = Field(description="The run whose «Ask the assistant» step ended.")
    text: str = Field("", max_length=200_000, description="What the assistant answered.")
    failure: str = Field("", max_length=96, description="Why it did not answer: the gateway's code; empty when it did.")


class ClaimAssistantOut(Schema):
    claimed: bool
    messages: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    instructions: str = ""
    continuation: str | None = None


class AssistantRoundOut(Schema):
    go_on: bool
    messages: list[dict[str, Any]] = []
    continuation: str | None = None
