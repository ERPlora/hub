"""Schemas of a card's activity: the notes, the entries of other apps and the list of them."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import field_validator

from apps.customer.models import Activity
from apps.customer.schemas.fields import OWN_KIND, CustomerOfIn, Page, PageIn, _decimals, _text
from apps.customer.schemas.health import NOT_FOR_HEALTH_DATA
from base.relay import by_platform


class NoteIn(CustomerOfIn):
    content: _text(5000, 1) = Field(title=gettext_noop("Note"), description="The note.")
    title: _text(200) = Field(
        "", description="A title of the caller's own; empty: the history titles it by its kind, in the reader's language."
    )
    author_name: _text(200) = Field(
        "",
        title=gettext_noop("Author"),
        description="The author's name, when it is not the person signed in.",
    )


def _own_kinds() -> set[str]:
    return set(Activity.Kind.values)


class ActivityIn(CustomerOfIn):
    kind: str = Field(
        max_length=40,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$",
        description="The caller's key for the entry, e.g. appointment.visit.",
    )
    title: _text(200, 1) = Field(
        description="The entry's title, in the caller's words."
    )
    text: _text(5000) = Field("", description=f"Details of the entry. {NOT_FOR_HEALTH_DATA}")
    data: dict[str, Any] = Field(
        {}, description="Data of the caller's own about the entry."
    )
    related_id: _text(64) = Field(
        "", description="The id of what the entry is about in the calling app."
    )
    related_type: _text(40) = Field(
        "", description="The type of what the entry is about, e.g. appointment."
    )

    @field_validator("kind")
    @classmethod
    def _not_ours(cls, value: str) -> str:
        if value in _own_kinds():
            raise ValueError(OWN_KIND)
        return value


class ActivityListIn(CustomerOfIn, PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the entries."
    )


class ActivityRow(Schema):
    id: UUID = Field(description="The entry's id.")
    customer_id: UUID = Field(description="The customer's id.")
    kind: str = Field(
        description="The entry's key: note_added, purchase_recorded, consent_granted… or another app's."
    )
    title: str = Field(description="Its title, when the writer gave one.")
    text: str = Field(description="The note, the words shown or the reason.")
    data: dict[str, Any] = Field(
        description="Its data: amounts, channel, the merged card…"
    )
    currency_decimals: int | None = Field(
        description="The decimals of the currency its data carries, as the server counts them (2 in EUR, 0 in "
        "JPY); empty when it carries none."
    )
    related_id: str = Field(description="The id of what it is about.")
    related_type: str = Field(description="The type of what it is about.")
    actor: str = Field(description="Who did it: a person's name, an API key's or the platform's own mark.")
    by_platform: bool = Field(description="No person did it: the platform (the system, an automation, a recovery).")
    created_at: datetime = Field(description="When.")

    @staticmethod
    def resolve_currency_decimals(entry: Activity) -> int | None:
        return _decimals((entry.data or {}).get("currency"))

    @staticmethod
    def resolve_by_platform(entry: Activity) -> bool:
        return by_platform(entry.actor)


ActivityPage = Page[ActivityRow]
