"""Input and output schemas of the appointment app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A customer is
named by her id or, as a person says it, by her name, phone or email; a service and a professional by
their id or their name; an appointment by its id or its number (``APT-…``). A time without a zone is a
wall-clock time of the business («2026-10-19 10:00»); one with a zone is converted to it. Money is in
cents. Every input refuses a field it does not declare; an edit changes only what it sends.
"""

import datetime as dt
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import (
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

T = TypeVar("T")

#: A booking lasts at most a day.
MAX_MINUTES = 1440
#: Services in one appointment, times in one batch, appointments in one bulk delete.
MAX_SERVICES = 10
MAX_BATCH = 50
MAX_BULK_DELETE = 100
#: The longest range the agenda reads at once (two months: a week view and its neighbours).
MAX_RANGE_DAYS = 62

SAY_WHICH_CUSTOMER = _("Say which customer: her id, or her name, phone or email.")
SAY_WHICH_STAFF = _("Say which professional: their id, or their name.")
SAY_WHICH_SERVICE = _("Say which service: its id, or its name.")
SAY_WHICH_APPOINTMENT = _("Say which appointment: its id, or its number.")
PICK_A_SERVICE = _("Pick at least one service.")
SAY_WHAT_CHANGES = _(
    "Say what changes: the time, the length, the professional or the services."
)
SAY_WHAT_TO_EDIT = _("Say what to change.")
SAY_THE_LENGTH = _("Say the services or how many minutes it lasts.")
END_BEFORE_START = _("The end cannot be before the start.")
RANGE_TOO_LONG = _("Ask for at most 62 days at once.")
CALENDAR_UPSIDE_DOWN = _("The calendar has to end after it starts.")

Status = Literal[
    "pending", "confirmed", "in_progress", "completed", "cancelled", "no_show"
]
Source = Literal["counter", "phone", "online", "whatsapp"]
Frequency = Literal["daily", "weekly", "biweekly", "monthly"]
BlockType = Literal["holiday", "vacation", "break", "maintenance", "other"]
HistoryAction = Literal[
    "created",
    "confirmed",
    "started",
    "completed",
    "cancelled",
    "no_show",
    "rescheduled",
    "staff_changed",
    "service_changed",
    "unassigned",
    "charged",
    "uncharged",
    "deleted",
]
AppointmentSort = Literal[
    "start",
    "-start",
    "number",
    "-number",
    "customer_name",
    "-customer_name",
    "staff_name",
    "-staff_name",
    "status",
    "-status",
]
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


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Said = _text(200, 1)
Note = _text(2000)
Reason = _text(500)
Minutes = Annotated[int, Field(ge=1, le=MAX_MINUTES)]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class PageIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


def _named(value, info: ValidationInfo, id_field: str, message) -> object:
    """The name is required when the id is not given (and the id itself is valid)."""
    if value is None and id_field in info.data and info.data[id_field] is None:
        raise ValueError(str(message))
    return value


# ── References ───────────────────────────────────────────────────────────────────────────────


class ServiceRefIn(In):
    service_id: UUID | None = Field(None, description="The service's id.")
    service: Said | None = Field(
        None,
        validate_default=True,
        description="The service's name, when its id is not known (e.g. Haircut).",
    )

    @field_validator("service")
    @classmethod
    def _service(cls, value, info: ValidationInfo):
        return _named(value, info, "service_id", SAY_WHICH_SERVICE)


class CustomerOf(In):
    customer_id: UUID | None = Field(None, description="The customer's card id.")
    customer: Said | None = Field(
        None,
        validate_default=True,
        description="The customer as a person says it: her full name, her phone or her email.",
    )

    @field_validator("customer")
    @classmethod
    def _customer(cls, value, info: ValidationInfo):
        return _named(value, info, "customer_id", SAY_WHICH_CUSTOMER)


class StaffOf(In):
    staff_id: UUID | None = Field(
        None, description="The professional's id (a staff member)."
    )
    staff: Said | None = Field(
        None,
        validate_default=True,
        description="The professional's name, when the id is not known (e.g. Ana).",
    )

    @field_validator("staff")
    @classmethod
    def _staff(cls, value, info: ValidationInfo):
        return _named(value, info, "staff_id", SAY_WHICH_STAFF)


class AppointmentRefIn(In):
    id: UUID | None = Field(None, description="The appointment's id.")
    number: _text(24, 1) | None = Field(
        None,
        validate_default=True,
        description="The appointment's number (APT-YYYYMMDD-NNNN), when the id is not known.",
    )

    @field_validator("number")
    @classmethod
    def _number(cls, value, info: ValidationInfo):
        return _named(value, info, "id", SAY_WHICH_APPOINTMENT)


Services = Annotated[
    list[ServiceRefIn],
    Field(min_length=1, max_length=MAX_SERVICES),
]
OptionalServices = Annotated[
    list[ServiceRefIn] | None,
    Field(min_length=1, max_length=MAX_SERVICES),
]

D_START = "When it starts: the business's wall-clock date and time (2026-10-19 10:00), or an instant with its zone."
D_DURATION = "How many minutes it lasts; empty = the sum of its services (each the professional's own length if set)."
D_SERVICES = (
    "The services, in order (e.g. a cut then a colour), each by its id or its name."
)
D_CONFIRM_OVERLAP = "True only after the person saw the overlapping appointments and chose to book anyway (front desk only)."


# ── Appointments: writes ───────────────────────────────────────────────────────────────────────


class AppointmentCreateIn(CustomerOf):
    services: Services = Field(description=D_SERVICES)
    staff_id: UUID | None = Field(
        None, description="The professional's id (a staff member)."
    )
    staff: Said | None = Field(
        None, validate_default=True, description="The professional's name (e.g. Ana)."
    )
    start: dt.datetime = Field(description=D_START)
    duration_minutes: Minutes | None = Field(None, description=D_DURATION)
    notes: Note = Field(
        "", description="Notes the customer may see (e.g. bring the colour reference)."
    )
    internal_notes: Note = Field(
        "", description="Notes for the team only (allergies, the colour formula)."
    )
    source: Source = Field(
        "counter",
        description="How it was booked: counter or phone (the team), online or whatsapp (the customer herself).",
    )
    confirm_overlap: bool = Field(False, description=D_CONFIRM_OVERLAP)

    @field_validator("staff")
    @classmethod
    def _staff(cls, value, info: ValidationInfo):
        return _named(value, info, "staff_id", SAY_WHICH_STAFF)

    @field_validator("services", mode="before")
    @classmethod
    def _some_service(cls, value):
        if isinstance(value, list) and not value:
            raise ValueError(str(PICK_A_SERVICE))
        return value


class BulkCreateIn(CustomerOf):
    services: Services = Field(description=D_SERVICES)
    staff_id: UUID | None = Field(None, description="The professional's id.")
    staff: Said | None = Field(
        None, validate_default=True, description="The professional's name."
    )
    starts: list[dt.datetime] = Field(
        min_length=1,
        max_length=MAX_BATCH,
        description="Every start to book (1 to 50), as in a single booking.",
    )
    duration_minutes: Minutes | None = Field(None, description=D_DURATION)
    notes: Note = Field(
        "", description="Notes the customer may see, on every appointment."
    )
    confirm_overlap: bool = Field(False, description=D_CONFIRM_OVERLAP)

    @field_validator("staff")
    @classmethod
    def _staff(cls, value, info: ValidationInfo):
        return _named(value, info, "staff_id", SAY_WHICH_STAFF)

    @model_validator(mode="before")
    @classmethod
    def _no_single_start(cls, data):
        # The single-booking form's `start: None` may travel along; it means nothing here.
        if isinstance(data, dict) and data.get("start", "") is None:
            data = {key: value for key, value in data.items() if key != "start"}
        return data


class ForCustomer(In):
    on_behalf_of_customer: bool = Field(
        False,
        description="True when the customer herself asks (WhatsApp, online): her ownership and the policy apply.",
    )
    customer_id: UUID | None = Field(
        None, description="The customer asking (with on_behalf_of_customer)."
    )
    customer: Said | None = Field(
        None,
        validate_default=True,
        description="The customer asking, by name, phone or email.",
    )

    @field_validator("customer")
    @classmethod
    def _asking(cls, value, info: ValidationInfo):
        if (
            info.data.get("on_behalf_of_customer")
            and info.data.get("customer_id") is None
            and value is None
        ):
            raise ValueError(str(SAY_WHICH_CUSTOMER))
        return value


class RescheduleIn(AppointmentRefIn, ForCustomer):
    start: dt.datetime | None = Field(None, description=D_START)
    duration_minutes: Minutes | None = Field(
        None, description="The new length in minutes; empty keeps it."
    )
    staff_id: UUID | None = Field(
        None, description="The new professional's id; empty keeps the professional."
    )
    staff: Said | None = Field(None, description="The new professional's name.")
    services: OptionalServices = Field(
        None, description="The new services; empty keeps them."
    )
    reason: Reason = Field("", description="Why it moves (kept in its history).")
    confirm_overlap: bool = Field(False, description=D_CONFIRM_OVERLAP)

    @model_validator(mode="after")
    def _something(self):
        if not (
            {"start", "duration_minutes", "staff_id", "staff", "services"}
            & self.model_fields_set
        ):
            raise ValueError(str(SAY_WHAT_CHANGES))
        return self


class UpdateIn(AppointmentRefIn):
    notes: Note | None = Field(
        None, description="Notes the customer may see; empty clears them."
    )
    internal_notes: Note | None = Field(
        None, description="Notes for the team; empty clears them."
    )
    customer_phone: _text(30) | None = Field(
        None,
        description="The customer's phone on this appointment (saved as +34600111222); empty clears it.",
    )
    customer_email: _text(254) | None = Field(
        None, description="The customer's email on this appointment."
    )
    start: dt.datetime | None = Field(None, description=D_START)
    duration_minutes: Minutes | None = Field(
        None, description="The new length in minutes."
    )
    staff_id: UUID | None = Field(None, description="The new professional's id.")
    staff: Said | None = Field(None, description="The new professional's name.")
    services: OptionalServices = Field(None, description="The new services.")
    confirm_overlap: bool = Field(False, description=D_CONFIRM_OVERLAP)

    @model_validator(mode="after")
    def _something(self):
        if not (self.model_fields_set - {"id", "number", "confirm_overlap"}):
            raise ValueError(str(SAY_WHAT_TO_EDIT))
        return self


class CancelIn(AppointmentRefIn, ForCustomer):
    reason: Reason = Field(
        "", description="Why it is cancelled (optional; kept in its history)."
    )


class BulkDeleteIn(In):
    ids: list[UUID] = Field(
        min_length=1,
        max_length=MAX_BULK_DELETE,
        description="The appointments to delete.",
    )


# ── Appointments: reads ────────────────────────────────────────────────────────────────────────


class DateRange(In):
    date_from: dt.date = Field(description="First business day (YYYY-MM-DD).")
    date_to: dt.date | None = Field(
        None,
        validate_default=True,
        description="Last business day (included; at most 62 days on); empty = the first.",
    )

    @field_validator("date_to")
    @classmethod
    def _range(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("date_from")
        if value is None or start is None:
            return value
        if value < start:
            raise ValueError(str(END_BEFORE_START))
        if (value - start).days > MAX_RANGE_DAYS:
            raise ValueError(str(RANGE_TOO_LONG))
        return value


class AppointmentListIn(DateRange):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(0, ge=0, description="How many rows to skip.")
    staff_id: UUID | None = Field(
        None, description="Only this professional's appointments."
    )
    staff: Said | None = Field(
        None, description="Only this professional's appointments, by name."
    )
    unassigned: bool | None = Field(
        None, description="True: only the appointments without a professional."
    )
    customer_id: UUID | None = Field(
        None, description="Only this customer's appointments."
    )
    status: Status | None = Field(None, description="Only this status.")
    search: _text(100) = Field(
        "", description="Text in the number, the customer's name or a service."
    )
    sort: AppointmentSort = Field(
        "start",
        description="Order: start (default), number, customer, professional, status.",
    )


class HistoryIn(AppointmentRefIn):
    limit: int = Field(
        100, ge=1, le=100, description="How many lines to return (1 to 100)."
    )
    offset: int = Field(0, ge=0, description="How many lines to skip.")


class ForCustomerIn(CustomerOf):
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="How many appointments, the newest first (1 to 100).",
    )
    offset: int = Field(0, ge=0, description="How many to skip.")


class CountForServiceIn(ServiceRefIn):
    pass


class NoIn(In):
    pass


class ServicesByScalar(In):
    """The services as query-string scalars (a GET): ids, or names as a person says them."""

    service_ids: list[UUID] | None = Field(
        None, max_length=MAX_SERVICES, description="The services' ids, in order."
    )
    services: list[Said] | None = Field(
        None, max_length=MAX_SERVICES, description="The services' names, in order (e.g. Haircut)."
    )
    duration_minutes: Minutes | None = Field(
        None, description="The length when no services are said."
    )

    @model_validator(mode="after")
    def _length(self):
        if not self.service_ids and not self.services and self.duration_minutes is None:
            raise ValueError(str(SAY_THE_LENGTH))
        return self

    def service_refs(self) -> list[ServiceRefIn]:
        return [ServiceRefIn(service_id=service_id) for service_id in self.service_ids or []] + [
            ServiceRefIn(service=name) for name in self.services or []
        ]


class SlotsIn(ServicesByScalar):
    date: dt.date = Field(description="The business day (YYYY-MM-DD).")
    staff_id: UUID | None = Field(
        None, description="Only this professional; empty = every one who can do it."
    )
    staff: Said | None = Field(None, description="Only this professional, by name.")
    exclude_id: UUID | None = Field(
        None, description="An appointment being moved: its own time does not count."
    )
    for_customer: bool = Field(
        False,
        description="True when the customer books: the minimum notice applies and nothing overlaps.",
    )


class CheckIn(ServicesByScalar):
    start: dt.datetime = Field(description=D_START)
    staff_id: UUID | None = Field(
        None, description="The professional's id; empty = the business alone."
    )
    staff: Said | None = Field(None, description="The professional's name.")
    exclude_id: UUID | None = Field(
        None, description="An appointment being moved: its own time does not count."
    )
    for_customer: bool = Field(False, description="True when the customer books.")


# ── Outputs ────────────────────────────────────────────────────────────────────────────────────


class LineOut(Schema):
    service_id: UUID
    name: str = Field(description="The service's name when it was booked.")
    price: int = Field(description="Its price when it was booked, in cents.")
    duration_minutes: int


class AppointmentRow(Schema):
    """An appointment as the agenda lists it: no contact and no notes."""

    id: UUID
    number: str
    customer_id: UUID
    customer_name: str = Field(description="Empty when the customer's data was erased.")
    staff_id: UUID | None = Field(
        description="Empty = unassigned (its professional left)."
    )
    staff_name: str
    start: dt.datetime = Field(description="On the business's clock.")
    end: dt.datetime
    duration_minutes: int
    status: Status
    source: Source
    services: list[LineOut]
    service_names: str = Field(description="The services' names, joined.")
    total: int = Field(description="The sum of its services' prices, in cents.")
    booked_by_customer: bool
    sale_id: UUID | None = Field(
        description="The sale that charged it; empty = not charged."
    )
    order_id: UUID | None = Field(
        description="The check open in the till (Sales) to charge it; empty = none. Charging again goes back to it."
    )
    recurring_id: UUID | None
    occurrence_date: dt.date | None


class AppointmentOut(AppointmentRow):
    customer_phone: str
    customer_email: str
    notes: str
    internal_notes: str
    cancelled_at: dt.datetime | None
    cancellation_reason: str
    cancelled_by_customer: bool
    charged_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    start_date_label: str = Field(
        description="Its day ready to say, in the caller's language on the business's clock (e.g. martes, 5 de "
        "marzo de 2030)."
    )
    start_time_label: str = Field(description="Its hour ready to say, 24-hour on the business's clock (e.g. 10:30).")


class AppointmentPage(Page[AppointmentRow]):
    timezone: str = Field(
        description="The business's time zone: every time is on its clock."
    )


class AppointmentsOut(Schema):
    rows: list[AppointmentOut]


class HistoryOut(Schema):
    id: UUID
    action: HistoryAction
    at: dt.datetime
    actor: str = Field(description="Who did it (empty for the platform).")
    by_customer: bool
    reason: str
    old_value: dict
    new_value: dict


class HistoryPage(Page[HistoryOut]):
    pass


class VisitOut(AppointmentRow):
    notes: str
    internal_notes: str


class VisitPage(Page[VisitOut]):
    pass


class CountOut(Schema):
    count: int
    earliest: dt.datetime | None = Field(
        description="The first one's start; empty when there is none."
    )


class NoticesIn(In):
    since: dt.datetime | None = Field(
        None, description="Only what happened from this instant on; empty = the last 24 hours."
    )
    limit: int = Field(20, ge=1, le=50, description="How many notices, the newest first (1 to 50).")


class NoticeOut(Schema):
    kind: Literal["booked", "cancelled"] = Field(
        description="booked: the customer booked it herself; cancelled: she cancelled it herself."
    )
    at: dt.datetime = Field(description="When she did it.")
    id: UUID
    number: str
    customer_name: str = Field(description="Empty once the customer's data was erased.")
    service_names: str
    staff_name: str
    start: dt.datetime
    start_date_label: str = Field(description="Its day ready to say, in the caller's language.")
    start_time_label: str = Field(description="Its hour ready to say, 24-hour on the business's clock.")


class NoticesOut(Schema):
    rows: list[NoticeOut] = Field(description="The notices, the newest first.")


class LaneOut(Schema):
    staff_id: UUID
    name: str
    color: str
    takes_bookings: bool = Field(
        description="False: no longer bookable (kept while it has appointments)."
    )


class LanesIn(DateRange):
    pass


class LanesOut(Schema):
    rows: list[LaneOut]
    unassigned: int = Field(
        description="Appointments without a professional in the range."
    )
    own_staff_id: UUID | None = Field(
        description="The caller's own staff record, if linked."
    )
    sees_everyone: bool = Field(
        description="False: the caller sees their own agenda only."
    )
    timezone: str


class SlotOut(Schema):
    start: dt.datetime
    end: dt.datetime
    within_notice: bool = Field(
        description="Inside the minimum notice: only the front desk is offered it."
    )
    staff_ids: list[UUID] = Field(description="The professionals free at that time.")


class SlotsOut(Schema):
    date: dt.date
    timezone: str
    duration_minutes: int
    slots: list[SlotOut]


class ConflictOut(Schema):
    id: UUID
    number: str
    customer_name: str
    start: dt.datetime
    end: dt.datetime


class CheckOut(Schema):
    available: bool
    code: str | None = Field(
        description="Why not: invalid_start, in_past, too_soon, too_far, outside_schedule, outside_staff_hours, "
        "blocked or overlap."
    )
    message: str
    conflicts: list[ConflictOut] = Field(
        description="The professional's appointments it overlaps."
    )


class ChargeOut(Schema):
    appointment_id: UUID
    order_id: UUID = Field(description="The check opened in the till (Sales).")
    label: str = Field(description="The check's title in the till's open checks.")


class DeletedOut(Schema):
    id: UUID


class BulkDeletedOut(Schema):
    deleted: list[UUID]


# ── Blocked time ───────────────────────────────────────────────────────────────────────────────


class BlockedTimeCreateIn(In):
    title: _text(200, 1) = Field(description="What it is (e.g. Training, Holiday).")
    block_type: BlockType = Field(
        "other", description="holiday, vacation, break, maintenance or other."
    )
    start: dt.datetime = Field(description=D_START)
    end: dt.datetime = Field(description="When it ends (a whole day: its last day).")
    all_day: bool = Field(
        False, description="True: whole days, from the start's day to the end's day."
    )
    staff_id: UUID | None = Field(
        None, description="Only this professional; empty = the whole business."
    )
    staff: Said | None = Field(None, description="Only this professional, by name.")
    reason: Reason = Field("", description="Why (optional).")

    @model_validator(mode="after")
    def _order(self):
        if self.end < self.start or (not self.all_day and self.end == self.start):
            raise ValueError(str(END_BEFORE_START))
        return self

    @field_validator("end")
    @classmethod
    def _end(cls, value, info: ValidationInfo):
        start = info.data.get("start")
        if start is not None and value < start:
            raise ValueError(str(END_BEFORE_START))
        return value


class BlockedTimeRefIn(In):
    id: UUID = Field(description="The blocked period's id.")


class BlockedTimeListIn(DateRange):
    limit: int = Field(100, ge=1, le=100, description="How many rows (1 to 100).")
    offset: int = Field(0, ge=0, description="How many rows to skip.")
    staff_id: UUID | None = Field(
        None, description="This professional's blocks and the whole business's."
    )


class BlockedTimeOut(Schema):
    id: UUID
    title: str
    block_type: BlockType
    start: dt.datetime
    end: dt.datetime
    all_day: bool
    staff_id: UUID | None
    staff_name: str
    reason: str


class BlockedTimePage(Page[BlockedTimeOut]):
    pass


# ── Series ─────────────────────────────────────────────────────────────────────────────────────


class RecurringRule(In):
    start_date: dt.date = Field(description="From when it repeats (YYYY-MM-DD).")
    frequency: Frequency = Field(
        description="daily, weekly, biweekly (every two weeks) or monthly."
    )
    day_of_week: int | None = Field(
        None,
        ge=0,
        le=6,
        description="Weekly and biweekly: the weekday, Monday = 0; empty = the start date's.",
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
    staff_id: UUID | None = Field(None, description="The professional's id.")
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


class RecurringRefIn(In):
    id: UUID = Field(description="The repeating appointment's id.")


class RecurringGetIn(RecurringRefIn):
    from_date: dt.date | None = Field(
        None,
        description="An edit would apply from this date: how many appointments it reaches.",
    )


class RecurringUpdateIn(In):
    id: UUID = Field(description="The repeating appointment's id.")
    from_date: dt.date = Field(
        description="The occurrence from which the change applies (this and all following)."
    )
    frequency: Frequency | None = Field(None, description="The new repetition.")
    day_of_week: int | None = Field(
        None, ge=0, le=6, description="The new weekday, Monday = 0."
    )
    time: dt.time | None = Field(None, description="The new time.")
    duration_minutes: Minutes | None = Field(None, description="The new length.")
    staff_id: UUID | None = Field(
        None, description="The professional who takes it over."
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
    id: UUID = Field(description="The repeating appointment's id.")
    from_date: dt.date | None = Field(
        None, description="Book from this date (the next_from of a previous run)."
    )
    to_date: dt.date | None = Field(
        None, description="Book up to this date (the to of a previous run)."
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


# ── Settings ───────────────────────────────────────────────────────────────────────────────────


class SettingsIn(In):
    default_duration: Minutes | None = Field(
        None, description="Minutes of a booking with no service length."
    )
    min_booking_notice: int | None = Field(
        None,
        ge=0,
        le=10080,
        description="Minutes ahead the customer must book (the front desk books for now).",
    )
    max_advance_booking: int | None = Field(
        None,
        ge=0,
        le=365,
        description="Days ahead one may book (up to a year); 0 = no limit (a series then books 90 days).",
    )
    allow_overlapping: bool | None = Field(
        None,
        description="True: the front desk is warned and may book anyway; false: a hard block.",
    )
    allow_customer_cancellation: bool | None = Field(
        None, description="The customer may cancel her appointment."
    )
    cancellation_notice_hours: int | None = Field(
        None, ge=0, le=720, description="Hours before the start she may still cancel."
    )
    calendar_start_hour: int | None = Field(
        None, ge=0, le=23, description="The calendar starts at this hour."
    )
    calendar_end_hour: int | None = Field(
        None, ge=1, le=24, description="The calendar ends at this hour."
    )
    slot_interval: int | None = Field(
        None, ge=5, le=240, description="Minutes between free times."
    )
    auto_confirm_online: bool | None = Field(
        None,
        description="The customer's own bookings are born confirmed (false: pending, to review).",
    )

    @model_validator(mode="after")
    def _window(self):
        start, end = self.calendar_start_hour, self.calendar_end_hour
        if start is not None and end is not None and end <= start:
            raise ValueError(str(CALENDAR_UPSIDE_DOWN))
        return self


class SettingsOut(Schema):
    default_duration: int
    min_booking_notice: int
    max_advance_booking: int
    allow_overlapping: bool
    allow_customer_cancellation: bool
    cancellation_notice_hours: int
    calendar_start_hour: int
    calendar_end_hour: int
    slot_interval: int
    auto_confirm_online: bool
    timezone: str


# ── Reactions to other apps' events (their payloads) ───────────────────────────────────────────


class Payload(Schema):
    """Another app's event payload: what this app reads of it (the rest is ignored)."""

    model_config = ConfigDict(extra="ignore")


class MergedIn(Payload):
    id: UUID = Field(description="The customer's card that stays.")
    absorbed_id: UUID = Field(description="The card merged into it.")


class CustomerEventIn(Payload):
    id: UUID = Field(description="The customer's card.")


class MemberEventIn(Payload):
    id: UUID = Field(description="The professional.")


class SaleFromAppointmentIn(Payload):
    sale_id: UUID
    appointment_id: UUID


class SaleVoidedIn(Payload):
    sale_id: UUID


class OrderVoidedIn(Payload):
    order_id: UUID


class ReactionOut(Schema):
    changed: int = Field(description="How many rows the reaction changed.")
