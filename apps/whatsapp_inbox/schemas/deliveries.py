"""Schemas of handing the messages to erplora.com and of resuming what was left halfway."""

from typing import Literal
from uuid import UUID

from ninja import Field, Schema


class ClaimDeliveryOut(Schema):
    claimed: bool = Field(description="Whether this delivery may go now (queued or sending, nobody else on it).")
    to: str = Field("", description="The number it goes to.")
    text: str | None = Field(None, description="The text, for a text message.")
    template: dict | None = Field(None, description="name, language and variables, for a template.")
    client_message_id: UUID | None = Field(None, description="Its Idempotency-Key.")


class RecordDeliveryIn(Schema):
    id: UUID = Field(description="The message handed to erplora.com.")
    kind: Literal["sent", "refused", "unreachable", "unknown"] = Field(description="How erplora.com answered.")
    wa_message_id: str = Field("", description="Meta's id, when it was sent.")
    code: str = Field("", description="erplora.com's code, when it refused.")
    message: str = Field("", description="erplora.com's reason, or what went wrong.")


class RecordOut(Schema):
    status: str | None = Field(description="The status now.")


class ResumeIn(Schema):
    pass


class ResumeOut(Schema):
    messages: int = Field(description="Messages handed to erplora.com again.")
    erasures: int = Field(description="Erasures asked to erplora.com again.")
    templates: int = Field(0, description="Templates handed to erplora.com again.")
    template_deletions: int = Field(0, description="Template deletions asked to erplora.com again.")
