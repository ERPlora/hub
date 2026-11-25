"""The rounds of a check of Sales: the one the till sends to the kitchen, and the reactions to Sales' events
(a round fired; a check charged, voided or merged), which read only what they need from the emitter's
payload and ignore the rest, never refuse it."""

from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import field_validator

from apps.kitchen.schemas.fields import (
    A_CHECK,
    A_CHECK_LINE,
    DISHES,
    OF_ORDER_TYPE,
    TICKET_TYPE,
    In,
    Label,
    OrderType,
    Priority,
    Reaction,
)
from apps.kitchen.schemas.tickets import TicketOut


class TicketSendIn(In):
    order_id: UUID = Field(
        description="The open check whose pending lines go to the kitchen.", json_schema_extra=A_CHECK
    )
    label: Label = Field(
        "",
        description="What the kitchen reads as the check's name (Table 4); empty: the check's title.",
    )
    channel: OrderType = Field(
        "dine_in",
        title=TICKET_TYPE,
        description="dine_in, takeaway or delivery.",
        json_schema_extra=OF_ORDER_TYPE,
    )
    priority: Literal["normal", "rush"] = Field(
        "normal", description="rush sends it urgent."
    )
    waiter: Label = Field(
        "",
        description="Who attends the check as the till names it («Atiende»); empty: who sends it.",
    )


_PRIORITIES = {"urgent": "rush", "rush": "rush", "vip": "vip"}
_CHANNELS = {"dine_in", "takeaway", "delivery"}


class ReceivedItemIn(Reaction):
    order_item_id: UUID = Field(description="The line of Sales sent.", json_schema_extra=A_CHECK_LINE)


class TicketReceiveIn(Reaction):
    """``sale.order.fired`` as Sales sends it (its WORKBOOK «Lo que avisa»)."""

    order_id: UUID = Field(description="The check the round was fired from.", json_schema_extra=A_CHECK)
    round_no: int = Field(ge=1, description="The round fired.")
    label: str = Field("", description="What the kitchen reads as the check's name.")
    # A closed list, so the card says each by its label: what Sales sends is read before (``_channel``, ``_priority``),
    # and anything else still becomes dine_in and normal, never a refusal.
    channel: OrderType = Field(
        "dine_in",
        title=TICKET_TYPE,
        description="dine_in, takeaway or delivery; anything else is dine_in.",
        json_schema_extra=OF_ORDER_TYPE,
    )
    priority: Priority = Field(
        "normal", description="urgent or rush (rush), vip; anything else is normal."
    )
    waiter: str = Field("", description="Who sent it.")
    items: list[ReceivedItemIn] = Field(
        default_factory=list, title=DISHES, description="The lines sent."
    )

    @field_validator("label", "waiter", mode="before")
    @classmethod
    def _short(cls, value):
        return (value or "")[:120] if isinstance(value, str) else ""

    @field_validator("channel", mode="before")
    @classmethod
    def _channel(cls, value):
        return value if value in _CHANNELS else "dine_in"

    @field_validator("priority", mode="before")
    @classmethod
    def _priority(cls, value):
        return _PRIORITIES.get(str(value or "").strip().lower(), "normal")


class ReceivedOut(Schema):
    ticket: TicketOut | None = Field(
        description="The ticket of the round; none when it had nothing to cook."
    )


class TicketSyncIn(Reaction):
    """A check Sales charged, voided or whose line it voided (``order_id``), or merged (``to_order_id``)."""

    order_id: UUID | None = Field(None, description="The check Sales changed.")
    from_order_id: UUID | None = Field(
        None,
        title=gettext_noop("From check"),
        description="The check absorbed by a merge.",
    )
    to_order_id: UUID | None = Field(
        None,
        title=gettext_noop("Into check"),
        description="The check that stays after a merge.",
    )


class SyncOut(Schema):
    received: int = Field(description="Rounds the kitchen saved.")
    changed: int = Field(description="Tickets whose state changed with what Sales did.")
