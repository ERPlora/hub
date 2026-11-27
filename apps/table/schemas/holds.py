"""Schemas of the holds of a table (``table.hold.*``): set aside by hand or for a reservation, and the inputs of the
reactions to the events of Reservations and Customers, which read only what they need from the payload."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, field_validator, model_validator

from apps.table.schemas.fields import (
    A_TABLE,
    MAX_GUESTS,
    SAY_WHICH_TABLE,
    In,
    Said,
    _named,
    _text,
)

HOLD_ENDS_BEFORE = _("A hold has to end after it starts.")
MOMENT_WITHOUT_ZONE = _("Give the moment with its time zone.")

HoldSource = Literal["manual", "reservation"]
HoldStatus = Literal["held", "consumed", "released", "expired"]


class Reaction(Schema):
    """The input of a reaction to another app's event: what it needs, the rest of the payload ignored."""

    model_config = ConfigDict(extra="ignore")


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError(str(MOMENT_WITHOUT_ZONE))
    return value


class HoldPlaceIn(In):
    table_id: UUID | None = Field(None, description="The table to hold.", json_schema_extra=A_TABLE)
    table: Said | None = Field(None, description="The number of the table to hold.")
    zone: Said | None = Field(
        None, description="Its zone, when the same number is in several zones."
    )
    source_ref: _text(100, 1) = Field(
        description="A reference of this hold: asking again with it changes the same hold."
    )
    held_from: dt.datetime = Field(description="When it starts, with its time zone.")
    held_until: dt.datetime = Field(description="When it ends, with its time zone.")
    party_size: int = Field(
        0, ge=0, le=MAX_GUESTS, description="Guests expected (0 = not said)."
    )
    label: _text(200) = Field(
        "", description="The name painted on the table, e.g. Pedro."
    )

    @field_validator("held_from", "held_until")
    @classmethod
    def _zoned(cls, value):
        return _aware(value)

    @model_validator(mode="after")
    def _window(self):
        _named(self.table_id, self.table, SAY_WHICH_TABLE)
        if self.held_until <= self.held_from:
            raise ValueError(str(HOLD_ENDS_BEFORE))
        return self


class HoldByReservationIn(In):
    reservation_id: UUID = Field(description="The reservation of Reservations whose hold of a table is wanted.")


class HoldReleaseIn(In):
    source: HoldSource = Field(
        "manual", description="Who held it: manual (by hand) or reservation."
    )
    source_ref: _text(100, 1) = Field(description="The hold's reference.")


class HoldOut(Schema):
    id: UUID = Field(description="The hold's id.")
    table_id: UUID = Field(description="The table held.")
    source: HoldSource = Field(description="manual or reservation.")
    source_ref: str = Field(description="Its reference.")
    held_from: dt.datetime = Field(description="When it starts.")
    held_until: dt.datetime = Field(description="When it ends.")
    party_size: int = Field(description="Guests expected.")
    label: str = Field(description="The name painted.")
    status: HoldStatus = Field(description="held, consumed, released or expired.")


class ExpiredOut(Schema):
    expired: int = Field(description="How many holds expired.")


class HoldsChangedOut(Schema):
    changed: int = Field(description="How many holds changed.")


class ReservationStatusIn(Reaction):
    """``reservation.reservation.status_changed``: the reservation with its table and its window."""

    id: str = Field(description="The reservation's id.")
    status: str = Field(
        description="Its new status: confirmed, seated, completed, cancelled, no_show…"
    )
    table_id: UUID | None = Field(None, description="Its table, if it has one.")
    date: dt.date | None = Field(None, description="Its day (the business's).")
    time: dt.time | None = Field(
        None, description="Its time (the business's wall clock)."
    )
    duration_minutes: int | None = Field(
        None, ge=1, le=24 * 60, description="How long it lasts (120 if not said)."
    )
    party_size: int | None = Field(None, ge=0, le=MAX_GUESTS, description="Its guests.")
    guest_name: str = Field(
        "",
        max_length=200,
        title=gettext_noop("Guest's name"),
        description="The name on the reservation.",
    )
    customer_id: UUID | None = Field(None, description="Its customer's card, if any.")


class ReservationUpdatedIn(ReservationStatusIn):
    """``reservation.reservation.updated``: the fields that changed. ``table_id`` sent empty = the
    reservation lost its table; not sent = unchanged."""

    status: str = Field("", description="Its status, if it changed.")


class CustomerErasedIn(Reaction):
    """``customer.customer.erased``: the card whose personal data was erased."""

    id: UUID | None = Field(None, description="The erased customer's card.")
