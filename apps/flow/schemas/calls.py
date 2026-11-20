"""Schemas of a run's «Call another system» step (``flow.run.claim_call``, ``flow.run.record_call``): the call
about to go out and how it ended."""

from typing import Any, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.flow.schemas.fields import In


class RecordCallIn(In):
    """How a call of a run ended (``apps.flow.http.Reply``), its secrets already hidden."""

    id: UUID = Field(description="The run's id.")
    kind: Literal["ok", "status", "blocked", "invalid", "failed", "timeout"] = Field(
        title=gettext_noop("How it ended"), description="How it ended."
    )
    status: int | None = Field(None, description="The HTTP status it answered.")
    body: Any = Field(None, title=gettext_noop("Body"), description="What it answered: data for JSON, text otherwise.")
    truncated: bool = Field(False, title=gettext_noop("Truncated"), description="Whether the answer was cut at 1 MiB.")
    detail: str = Field(
        "", max_length=2000, title=gettext_noop("Technical text"), description="What went wrong, technically."
    )


class ClaimCallOut(Schema):
    """A call a run is about to make, for the process that makes it (never a route: it carries the opened
    secrets, which only travel in memory)."""

    claimed: bool
    method: str = ""
    url: str = ""
    headers: dict[str, str] = {}
    body: str = ""
    timeout: int = 10
    masks: list[str] = []
