"""Schemas of the table checks (``table.session.*``): naming one, the list, seating, closing, moving, joining and
splitting them, and the lines of their check of Sales."""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.table.schemas.fields import (
    A_CHECK,
    A_CUSTOMER,
    A_LINE,
    A_RESERVATION,
    A_SALES_CHECK,
    A_TABLE,
    CHECK,
    DESTINATION_TABLE,
    DESTINATION_ZONE,
    MAX_GUESTS,
    SAY_WHICH_TABLE,
    In,
    Page,
    PageIn,
    Said,
    _named,
    _text,
)

#: The lines of a check that move to the new one when it is split (Sales' own cap).
MAX_LINES = 500

SAY_WHICH_CHECK = _("Say which check: its id, or the number of its table.")
SAY_WHERE_TO = _("Say which table it goes to: its id, or its number.")
SAY_WHICH_TARGET = _(
    "Say which table or check it joins: an id, or the number of its table."
)

SessionStatus = Literal["open", "closed", "transferred", "merged", "parked"]
SessionSort = Literal[
    "opened_at",
    "-opened_at",
    "closed_at",
    "-closed_at",
    "table_number",
    "-table_number",
    "zone_name",
    "-zone_name",
    "guests_count",
    "-guests_count",
    "paid_total",
    "-paid_total",
    "status",
    "-status",
]


Notes = _text(2000)
Guests = Annotated[int, Field(ge=1, le=MAX_GUESTS)]


class SessionRefIn(In):
    id: UUID | None = Field(None, title=CHECK, description="The table check's id.", json_schema_extra=A_CHECK)
    table: Said | None = Field(
        None,
        description="The number of the table the check is open at, when its id is not known.",
    )
    zone: Said | None = Field(
        None, description="The table's zone, when the same number is in several zones."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.table, SAY_WHICH_CHECK)
        return self


class ByIdIn(In):
    """Deleting a closed check names it by its id alone."""

    id: UUID = Field(title=CHECK, description="The table check's id.", json_schema_extra=A_CHECK)


class SessionListIn(PageIn):
    search: str | None = Field(
        None, max_length=20, description="Part of the table's number."
    )
    table_number: str | None = Field(
        None,
        max_length=20,
        description="Part of the table's number (the column filter).",
    )
    status: SessionStatus | None = Field(
        None,
        description="open, closed, transferred, merged or parked; without it, every check.",
    )
    zone_id: UUID | None = Field(
        None, description="Only the checks of this zone's tables."
    )
    waiter_id: str | None = Field(
        None, max_length=64, description="Only the checks this person opened."
    )
    table_id: UUID | None = Field(None, description="Only the checks of this table.")
    opened_from: dt.date | None = Field(
        None, description="Opened on this business day or later."
    )
    opened_to: dt.date | None = Field(
        None, description="Opened on this business day or earlier."
    )
    sort: SessionSort = Field(
        "-opened_at", description="Order; a leading '-' reverses it."
    )


class SessionOut(Schema):
    id: UUID = Field(description="The table check's id.")
    table_id: UUID | None = Field(description="Its table (none when parked).")
    table_number: str | None = Field(description="Its table's number.")
    label: str = Field(
        description="Where the check is, in the reader's language: its table with its zone («5 (Terrace)»), or "
        "«Parked»."
    )
    zone_id: UUID | None = Field(description="Its table's zone.")
    zone_name: str | None = Field(description="Its zone's name.")
    order_id: UUID | None = Field(description="Its open check of Sales.")
    guests_count: int = Field(description="Guests.")
    status: SessionStatus = Field(
        description="open, closed, transferred, merged or parked."
    )
    waiter_id: str = Field(description="Who opened it (serves it).")
    waiter_name: str = Field(description="Their name.")
    opened_at: dt.datetime = Field(description="When it opened.")
    closed_at: dt.datetime | None = Field(description="When it ended.")
    notes: str = Field(description="Notes.")
    split_from_id: UUID | None = Field(description="The check it was split from.")
    transferred_from_id: UUID | None = Field(
        description="The check it was transferred from."
    )
    merged_into_id: UUID | None = Field(description="The check it was merged into.")
    paid_total: int | None = Field(
        description="What its check of Sales charged, in minor units of its currency (none yet: null).",
        json_schema_extra={"money": True},
    )
    currency: str | None = Field(
        description="ISO 4217 currency its check was charged in: its sales', never rewritten (none yet: null)."
    )
    currency_decimals: int | None = Field(
        description="The decimals of that currency as the server counts them (0 in JPY; none yet: null)."
    )
    customer_id: UUID | None = Field(description="The customer of the check, if any.")
    customer_name: str | None = Field(description="Their name.")


SessionPage = Page[SessionOut]


class SessionsOut(Schema):
    rows: list[SessionOut] = Field(description="The table checks.")


class SessionOpenIn(In):
    table_id: UUID | None = Field(None, description="The table to seat.", json_schema_extra=A_TABLE)
    table: Said | None = Field(
        None, description="The number of the table to seat, e.g. «4»."
    )
    zone: Said | None = Field(
        None, description="Its zone, when the same number is in several zones."
    )
    guests_count: Guests | None = Field(
        None,
        description="How many sit; empty = the reservation's guests, else the table's seats.",
    )
    notes: Notes = Field("", description="Notes of the check.")
    order_id: UUID | None = Field(
        None,
        description="An open check of Sales to bring to the table (e.g. a bar check); empty = a new one.",
        json_schema_extra=A_SALES_CHECK,
    )
    customer_id: UUID | None = Field(None, description="The customer of the check.", json_schema_extra=A_CUSTOMER)
    customer: Said | None = Field(
        None,
        title=gettext_noop("Customer"),
        description="The customer's name or phone, when the id is not known.",
    )
    reservation_id: UUID | None = Field(
        None,
        title=gettext_noop("Reservation"),
        description="The reservation whose party sits: only its hold of the table is spent; empty = every hold "
        "already showing the table Reserved.",
        json_schema_extra=A_RESERVATION,
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.table_id, self.table, SAY_WHICH_TABLE)
        return self


class SessionCloseIn(SessionRefIn):
    order_id: UUID | None = Field(
        None,
        description="The check of Sales the screen saw on it: a different one now refuses the close.",
        json_schema_extra=A_SALES_CHECK,
    )
    notes: Notes | None = Field(None, description="A note added to the check's notes.")


class SessionTransferIn(SessionRefIn):
    to_table_id: UUID | None = Field(
        None, title=DESTINATION_TABLE, description="The table it goes to.", json_schema_extra=A_TABLE
    )
    to_table: Said | None = Field(
        None, title=DESTINATION_TABLE, description="The number of the table it goes to."
    )
    to_zone: Said | None = Field(
        None,
        title=DESTINATION_ZONE,
        description="That table's zone, when its number repeats.",
    )

    @model_validator(mode="after")
    def _where(self):
        _named(self.to_table_id, self.to_table, SAY_WHERE_TO)
        return self


class SessionMergeIn(SessionRefIn):
    into_session_id: UUID | None = Field(
        None,
        title=gettext_noop("Into check"),
        description="The check that stays (another one of the same table too).",
        json_schema_extra=A_CHECK,
    )
    into_table_id: UUID | None = Field(
        None, title=DESTINATION_TABLE, description="The table whose check stays.", json_schema_extra=A_TABLE
    )
    into_table: Said | None = Field(
        None,
        title=DESTINATION_TABLE,
        description="The number of the table whose check stays.",
    )
    into_zone: Said | None = Field(
        None,
        title=DESTINATION_ZONE,
        description="That table's zone, when its number repeats.",
    )

    @model_validator(mode="after")
    def _where(self):
        if self.into_session_id is None:
            _named(self.into_table_id, self.into_table, SAY_WHICH_TARGET)
        return self


class SessionSplitIn(SessionRefIn):
    line_ids: list[Annotated[UUID, Field(json_schema_extra=A_LINE)]] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=gettext_noop("Lines to move"),
        description="The lines of its check of Sales that move to the new check; none = a blank one.",
    )
    guests_count: Guests = Field(1, description="Guests of the new check.")
    notes: Notes = Field("", description="Notes of the new check.")


class SessionGuestsIn(SessionRefIn):
    guests_count: Guests = Field(description="How many sit now.")


class SessionRestoreIn(In):
    id: UUID = Field(title=CHECK, description="The parked check.", json_schema_extra=A_CHECK)
    table_id: UUID | None = Field(None, description="The table it sits at.", json_schema_extra=A_TABLE)
    table: Said | None = Field(None, description="The number of the table it sits at.")
    zone: Said | None = Field(
        None, description="That table's zone, when its number repeats."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.table_id, self.table, SAY_WHICH_TABLE)
        return self


class SessionLinkOrderIn(SessionRefIn):
    order_id: UUID = Field(
        description="The open check of Sales that becomes the table's.", json_schema_extra=A_SALES_CHECK
    )


class ByOrderIn(In):
    order_id: UUID = Field(description="The check of Sales.")


class LineRefIn(In):
    id: UUID = Field(description="The line's id, in the check of Sales of a table check.")


class LineOut(Schema):
    id: UUID = Field(description="The line's id.")
    name: str = Field(description="Its name, as «Split check» lists it.")
    quantity: Decimal = Field(description="Quantity.")
    unit: str = Field(description="Unit of the quantity.")


class SplitOut(Schema):
    session: SessionOut = Field(description="The check that was split.")
    new_session: SessionOut = Field(description="The new check, at the same table.")


class ClosedOut(Schema):
    closed: int = Field(description="How many table checks were closed.")
