"""Free times, and whether one time is free."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.appointment.schemas.fields import D_START, MAX_SERVICES, In, Minutes, Said
from apps.appointment.schemas.references import ServiceRefIn

SAY_THE_LENGTH = _("Say the services or how many minutes it lasts.")


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
