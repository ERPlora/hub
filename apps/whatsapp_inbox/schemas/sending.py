"""Schemas of sending a message: a text, or a template with its variables."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.whatsapp_inbox.schemas.fields import (
    A_CONVERSATION,
    A_SAMPLE,
    CONVERSATION,
    CONVERSATION_REFERENCE,
    TEMPLATE,
    WHICH_CONVERSATION,
    Reference,
    _blank,
    _text,
)

TEXT_OR_TEMPLATE = _("Write a message or choose a template.")


class TemplateSendIn(Schema):
    name: _text(512, 1) = Field(
        description="The template's name, as Meta has it (recordatorio_cita)."
    )
    language: _text(15) | None = Field(
        None, description="Its language (es, en); needed when it exists in several."
    )
    variables: list[_text(1024)] = Field(
        default_factory=list,
        max_length=20,
        description="The values of {{1}}, {{2}}… in order.",
    )
    header_sample: UUID | None = Field(
        None,
        title=gettext_noop("File"),
        description="For a template whose header is a photo, a video or a document: the id "
        "whatsapp_inbox.template_sample.upload answered for the file to send; without it, the template's own file.",
        json_schema_extra=A_SAMPLE,
    )


class SendIn(Schema):
    id: UUID | None = Field(
        None, title=CONVERSATION, description="The conversation's id.", json_schema_extra=A_CONVERSATION
    )
    to: _text(32) | None = Field(
        None,
        title=gettext_noop("Phone"),
        description="A number to write to (a template to somebody who has not written yet).",
    )
    conversation: Reference | None = Field(
        None, validate_default=True, description=CONVERSATION_REFERENCE
    )
    template: TemplateSendIn | None = Field(
        None,
        title=TEMPLATE,
        description="An approved template; the only way to write after the 24-hour window.",
    )
    text: _text(4096) | None = Field(
        None,
        validate_default=True,
        description="The message, within 24 hours of the customer's last message.",
    )
    client_message_id: UUID = Field(
        description="A key of the caller's own for THIS message (a new UUID per message, the same on a retry): "
        "sending again with it never sends twice.",
        json_schema_extra={"attempt_key": True},
    )

    @field_validator("conversation")
    @classmethod
    def _target(cls, value: str | None, info: ValidationInfo) -> str | None:
        if (
            info.data.get("id") is None
            and _blank(info.data.get("to"))
            and _blank(value)
        ):
            raise ValueError(WHICH_CONVERSATION)
        return value

    @field_validator("text")
    @classmethod
    def _one(cls, value: str | None, info: ValidationInfo) -> str | None:
        if _blank(value) == (info.data.get("template") is None):
            raise ValueError(TEXT_OR_TEMPLATE)
        return value or None
