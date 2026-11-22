"""What every schema of the WhatsApp inbox shares: text fields, pages, a conversation's reference, the card's marks."""

from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints, ValidationInfo, field_validator

from base.schemas.assistant import names

T = TypeVar("T")

WHICH_CONVERSATION = _(
    "Say which conversation: its id, its number or the customer's name."
)


def _text(max_length: int, min_length: int = 0) -> Any:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


Reference = _text(200)

CONVERSATION_REFERENCE = (
    "The conversation's number (any format: +34 600 111 222, 600111222) or the name of the customer or "
    "of their WhatsApp profile, when the id is not known."
)

# The assistant's card names a template header's file by this read (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: by the name it was chosen with, as the template's sheet shows it. Whoever sends reads it.
A_SAMPLE = names("whatsapp_inbox.template_sample.detail")
# The same for the record a write acts on: a conversation as the inbox calls it, a message and a note by their text (a
# message without one by its caption or its file name, as the inbox's list says it), a template by its name and its
# language, as its sheet says it; a customer card by Customers' own read (the inbox requires Customers).
A_CONVERSATION = names("whatsapp_inbox.conversation.detail", name=("display_name",))
A_MESSAGE = names("whatsapp_inbox.message.get", name=("body", "media_caption", "media_filename", "template_name"))
A_NOTE = names("whatsapp_inbox.note.get", name=("text",))
A_TEMPLATE = names("whatsapp_inbox.template.get", name=("label",))
A_CUSTOMER = names("customer.customer.detail")
CONVERSATION = gettext_noop("Conversation")
MESSAGE = gettext_noop("Message")
NOTE = gettext_noop("Note")
TEMPLATE = gettext_noop("Template")


# ── Pages: every list is paginated, limit ≤ 100 ─────────────────────────────────────────────────


class PageIn(Schema):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return, at most 100."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped.")


# ── References ──────────────────────────────────────────────────────────────────────────────────


class ConversationRefIn(Schema):
    """A conversation by its ``id`` or by its number or customer's name (``conversation``); the id wins."""

    id: UUID | None = Field(
        None, title=CONVERSATION, description="The conversation's id.", json_schema_extra=A_CONVERSATION
    )
    conversation: Reference | None = Field(
        None, validate_default=True, description=CONVERSATION_REFERENCE
    )

    @field_validator("conversation")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("id") is None and _blank(value):
            raise ValueError(WHICH_CONVERSATION)
        return value


class ConversationPageIn(ConversationRefIn, PageIn):
    pass
