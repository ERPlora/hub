"""Repeating appointments: their rule, a change from a date on, and the appointments they book."""

import datetime as dt
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.appointment.schemas.fields import (
    A_MEMBER,
    A_SERIES,
    D_DURATION,
    D_SERVICES,
    END_BEFORE_START,
    SAY_WHAT_TO_EDIT,
    T_SERIES,
    In,
    Minutes,
    Page,
    PageIn,
    Said,
    _text,
)
from apps.appointment.schemas.references import (
    SAY_WHICH_STAFF,
    CustomerOf,
    OptionalServices,
    Services,
    _named,
)
from base.weekdays import Weekday

Frequency = Literal["daily", "weekly", "biweekly", "monthly"]
RecurringSort = Literal[
    "customer_name",
    "-customer_name",
    "staff_name",
    "-staff_name",
    "start_date",
    "-start_date",
    "time",
    "-time",
]


class RecurringRule(In):
    start_date: dt.date = Field(description="From when it repeats (YYYY-MM-DD).")
    frequency: Frequency = Field(
        description="daily, weekly, biweekly (every two weeks) or monthly."
    )
    day_of_week: Weekday | None = Field(
        None, description="Weekly and biweekly: the weekday, Monday = 0; empty = the start date's."
    )
    time: dt.time = Field(
        description="The wall-clock time each appointment starts (HH:MM)."
    )
    duration_minutes: Minutes | None = Field(None, description=D_DURATION)
    end_date: dt.date | None = Field(
        None, description="Its last possible date (included); empty = no end."
    )
    max_occurrences: int | None = Field(
        None,
        ge=1,
        le=1000,
        description="How many appointments in all; empty = no limit.",
    )


class RecurringCreateIn(RecurringRule, CustomerOf):
    services: Services = Field(description=D_SERVICES)
    staff_id: UUID | None = Field(None, description="The professional's id.", json_schema_extra=A_MEMBER)
    staff: Said | None = Field(
        None, validate_default=True, description="The professional's name."
    )

    @field_validator("staff")
    @classmethod
    def _staff(cls, value, info: ValidationInfo):
        return _named(value, info, "staff_id", SAY_WHICH_STAFF)

    @field_validator("end_date")
    @classmethod
    def _end(cls, value, info: ValidationInfo):
        start = info.data.get("start_date")
        if value is not None and start is not None and value < start:
            raise ValueError(str(END_BEFORE_START))
        return value


#: A repeating appointment's id, named on the assistant's card as the series list titles one.
SeriesId = Annotated[
    UUID, Field(title=T_SERIES, description="The repeating appointment's id.", json_schema_extra=A_SERIES)
]


class RecurringRefIn(In):
    id: SeriesId


class RecurringGetIn(RecurringRefIn):
    from_date: dt.date | None = Field(
        None,
        description="An edit would apply from this date: how many appointments it reaches.",
    )


class RecurringUpdateIn(In):
    id: SeriesId
    from_date: dt.date = Field(
        title=gettext_noop("Applies from"),
        description="The occurrence from which the change applies (this and all following).",
    )
    frequency: Frequency | None = Field(None, description="The new repetition.")
    day_of_week: Weekday | None = Field(None, description="The new weekday, Monday = 0.")
    time: dt.time | None = Field(None, description="The new time.")
    duration_minutes: Minutes | None = Field(None, description="The new length.")
    staff_id: UUID | None = Field(
        None, description="The professional who takes it over.", json_schema_extra=A_MEMBER
    )
    staff: Said | None = Field(
        None, description="The professional who takes it over, by name."
    )
    services: OptionalServices = Field(None, description="The new services.")
    end_date: dt.date | None = Field(None, description="The new last date.")
    max_occurrences: int | None = Field(
        None, ge=1, le=1000, description="The new number of appointments."
    )

    @model_validator(mode="after")
    def _something(self):
        if not (self.model_fields_set - {"id", "from_date"}):
            raise ValueError(str(SAY_WHAT_TO_EDIT))
        return self


class MaterializeIn(In):
    id: SeriesId
    from_date: dt.date | None = Field(
        None,
        title=gettext_noop("Book from"),
        description="Book from this date (the next_from of a previous run).",
    )
    to_date: dt.date | None = Field(
        None,
        title=gettext_noop("Book up to"),
        description="Book up to this date (the to of a previous run).",
    )


class RecurringListIn(PageIn):
    search: _text(100) = Field(
        "",
        description="Text in the customer's, a service's or the professional's name.",
    )
    is_active: bool | None = Field(
        None, description="Only the active (true) or the paused (false) ones."
    )
    frequency: Frequency | None = Field(None, description="Only this repetition.")
    staff_id: UUID | None = Field(None, description="Only this professional's.")
    sort: RecurringSort = Field("customer_name", description="Order.")


class RecurringLineOut(Schema):
    service_id: UUID
    name: str


class RecurringOut(Schema):
    id: UUID
    customer_id: UUID
    customer_name: str
    staff_id: UUID | None
    staff_name: str
    services: list[RecurringLineOut]
    service_names: str
    frequency: Frequency
    day_of_week: int | None
    time: dt.time
    duration_minutes: int
    start_date: dt.date
    end_date: dt.date | None
    max_occurrences: int | None
    is_active: bool
    split_from_id: UUID | None
    created_at: dt.datetime


class RecurringDetailOut(RecurringOut):
    next_date: dt.date | None = Field(
        description="Its next date from today; empty when it has none left."
    )
    upcoming: int = Field(
        description="Appointments booked from the date asked on (today by default)."
    )
    charged: int = Field(
        description="Of those, how many are charged: an edit leaves them alone."
    )
    label: str = Field(
        description="How a person names it, as the series list titles one: its customer and how it repeats."
    )


class RecurringPage(Page[RecurringOut]):
    pass


class SkippedOut(Schema):
    occurrence_date: dt.date
    code: str
    message: str


class MaterializeOut(Schema):
    recurring: RecurringOut
    booked: int
    already_booked: int
    skipped: list[SkippedOut]
    next_from: dt.date | None = Field(
        description="Run again from this date to book the rest of the window."
    )
    to: dt.date = Field(description="The window's last date.")
    upcoming_date: dt.date | None = Field(
        description="Nothing to book yet: the series' next date beyond the window."
    )


class RecurringUpdatedOut(Schema):
    recurring: RecurringOut = Field(
        description="The series from the date on (a new one when it was split)."
    )
    moved: int
    cancelled: int = Field(
        description="Appointments that no longer fall on the pattern."
    )
    locked: int = Field(
        description="Appointments left alone: charged, in progress or completed."
    )
    skipped: list[SkippedOut] = Field(
        description="Appointments that did not fit and keep their time."
    )
    booked: int = Field(description="New dates booked.")


class RecurringDeletedOut(Schema):
    id: UUID
