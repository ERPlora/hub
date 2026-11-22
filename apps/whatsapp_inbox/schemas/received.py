"""Schemas of what erplora.com hands the inbox from WhatsApp: a message received and a status of one sent."""

from datetime import datetime
from urllib.parse import urlsplit
from typing import Annotated, Literal
from uuid import UUID

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import StringConstraints, field_validator

from apps.whatsapp_inbox.schemas.fields import _text

NOT_ERPLORA = _("An attachment must come from erplora.com over https.")

#: An international number as WhatsApp gives it (``34600111222``) or E.164 (``+34600111222``).
INTERNATIONAL = r"^\+?[1-9]\d{6,14}$"


def _from_erplora(url: str) -> str:
    """An attachment's URL is erplora.com's own, over https (the local SaaS's origin in development)."""
    saas = urlsplit(str(getattr(settings, "SAAS_URL", "") or ""))
    given = urlsplit(url)
    secure = given.scheme == "https" or (settings.DEBUG and given.scheme == saas.scheme)
    if not secure or not saas.netloc or (given.scheme, given.netloc) != (saas.scheme, saas.netloc):
        raise ValueError(NOT_ERPLORA)
    return url


class ReceiveMediaIn(Schema):
    url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000, pattern=r"^https?://\S+$")] = Field(
        description="Where erplora.com serves the attachment: its own origin, over https."
    )
    mime_type: _text(120) = Field("", description="Its MIME type.")
    filename: _text(255) = Field("", description="Its file name (documents).")
    caption: _text(4096) = Field(
        "", description="The caption the customer wrote with it."
    )

    @field_validator("url")
    @classmethod
    def _erplora(cls, value: str) -> str:
        return _from_erplora(value)


class ReceiveReplyIn(Schema):
    id: _text(256) = Field("", description="The id of the option the customer tapped (a quick reply's payload, a button's or a list row's id).")
    title: _text(1024) = Field("", description="Its text, as she saw it.")


class ReceiveIn(Schema):
    wa_message_id: _text(255, 1) = Field(
        description="WhatsApp's id of the message (wamid…)."
    )
    from_: Annotated[str, StringConstraints(strip_whitespace=True, pattern=INTERNATIONAL)] = Field(
        alias="from", description="The customer's international number as WhatsApp gives it (34600111222), with or without +."
    )
    contact_name: _text(200) = Field(
        "", description="The name of the customer's WhatsApp profile."
    )
    direction: Literal["inbound", "outbound"] = Field(
        "inbound",
        description="inbound (the customer) or outbound (the owner's reply from the phone app).",
    )
    source: Literal["live", "history"] = Field(
        "live", description="live, or history brought by connecting the number."
    )
    type: _text(32) = Field("text", description="Meta's message type.")
    text: _text(65536) = Field(
        "", description="The text, or the caption lifted out of Meta's object."
    )
    media: ReceiveMediaIn | None = Field(
        None, description="The attachment, kept by erplora.com."
    )
    reply_to: _text(255) = Field(
        "", description="WhatsApp's id of the message this one answers."
    )
    reply: ReceiveReplyIn | None = Field(
        None, description="The option she tapped, for a button or interactive reply; read from Meta's object when missing."
    )
    sent_at: datetime | None = Field(
        None, description="When it was said (Meta's time); now when missing."
    )
    payload: dict = Field(
        default_factory=dict, description="Meta's own message object, verbatim."
    )


class ReceiveOut(Schema):
    id: UUID = Field(description="The message's id.")
    conversation_id: UUID = Field(description="Its conversation.")
    created: bool = Field(
        description="False when this message was already here (a repeated delivery)."
    )


class StatusErrorIn(Schema):
    code: _text(64) = Field("", description="Meta's error code (131047…).")
    message: _text(500) = Field("", description="Meta's reason.")


class StatusIn(Schema):
    wa_message_id: _text(255, 1) = Field(
        description="WhatsApp's id of a message the Hub sent."
    )
    client_message_id: UUID | None = Field(
        None, description="The Hub's key of the message (the Idempotency-Key it was sent with): matches a status that arrives before erplora.com's answer."
    )
    status: Literal["sent", "delivered", "read", "failed"] = Field(
        description="What Meta reported."
    )
    error: StatusErrorIn | None = Field(
        None, description="Why it was not delivered, for failed."
    )
    status_at: datetime | None = Field(None, description="When Meta reported it.")


class StatusOut(Schema):
    updated: bool = Field(
        description="Whether the message changed (an unknown id or an older status changes nothing)."
    )
    status: str | None = Field(description="The message's status now.")
