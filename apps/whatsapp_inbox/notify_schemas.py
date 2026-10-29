"""The input of ``whatsapp_inbox.message.notify`` (FLOW-F31): what an automation may send to a customer.

Kept apart from ``schemas.py`` and built from its pieces: the template is the inbox's own (``TemplateSendIn``)
and «a text or a template» is the same rule as sending from the inbox.
"""

from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.whatsapp_inbox.schemas import TEXT_OR_TEMPLATE, TemplateSendIn, _blank, _text


class NotifyIn(Schema):
    phone: _text(32) = Field(
        description="The customer's number, exactly in international format (+34600111222): only the conversation "
        "of that number in this business is written to, never a new one."
    )
    template: TemplateSendIn | None = Field(
        None,
        title=gettext_noop("Template"),
        description="An approved template, for when more than 24 hours have passed since the customer's last "
        "message (WhatsApp lets nothing else through then).",
    )
    text: _text(4096) = Field(
        "",
        validate_default=True,
        description="The message, sent as it is within 24 hours of the customer's last message.",
    )
    client_message_id: UUID | None = Field(
        None,
        description="A key of the caller's own for this message (the same on a retry): sending again with it never "
        "sends twice. Empty: a new message.",
    )

    @field_validator("text")
    @classmethod
    def _something(cls, value: str, info: ValidationInfo) -> str:
        if _blank(value) and info.data.get("template") is None:
            raise ValueError(TEXT_OR_TEMPLATE)
        return value
