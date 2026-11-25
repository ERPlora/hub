"""What changes an appointment that exists: moving it, editing it, cancelling it, deleting some and charging it."""

import datetime as dt
from typing import Annotated
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.appointment.schemas.appointments import AppointmentRefIn
from apps.appointment.schemas.fields import (
    A_MEMBER,
    AN_APPOINTMENT,
    BOOK_EVEN_IF_IT_OVERLAPS,
    D_CONFIRM_OVERLAP,
    D_START,
    MAX_BULK_DELETE,
    SAY_WHAT_TO_EDIT,
    T_APPOINTMENTS,
    In,
    Minutes,
    Note,
    Reason,
    Said,
    _text,
)
from apps.appointment.schemas.references import ForCustomer, OptionalServices

SAY_WHAT_CHANGES = _("Say what changes: the time, the length, the professional or the services.")


class RescheduleIn(AppointmentRefIn, ForCustomer):
    start: dt.datetime | None = Field(None, description=D_START)
    duration_minutes: Minutes | None = Field(
        None, description="The new length in minutes; empty keeps it."
    )
    staff_id: UUID | None = Field(
        None, description="The new professional's id; empty keeps the professional.", json_schema_extra=A_MEMBER
    )
    staff: Said | None = Field(None, description="The new professional's name.")
    services: OptionalServices = Field(
        None, description="The new services; empty keeps them."
    )
    reason: Reason = Field("", description="Why it moves (kept in its history).")
    confirm_overlap: bool = Field(False, title=BOOK_EVEN_IF_IT_OVERLAPS, description=D_CONFIRM_OVERLAP)

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
    staff_id: UUID | None = Field(None, description="The new professional's id.", json_schema_extra=A_MEMBER)
    staff: Said | None = Field(None, description="The new professional's name.")
    services: OptionalServices = Field(None, description="The new services.")
    confirm_overlap: bool = Field(False, title=BOOK_EVEN_IF_IT_OVERLAPS, description=D_CONFIRM_OVERLAP)

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
    ids: list[Annotated[UUID, Field(json_schema_extra=AN_APPOINTMENT)]] = Field(
        min_length=1,
        max_length=MAX_BULK_DELETE,
        title=T_APPOINTMENTS,
        description="The appointments to delete.",
    )


class ChargeOut(Schema):
    appointment_id: UUID
    order_id: UUID = Field(description="The check opened in the till (Sales).")
    label: str = Field(description="The check's title in the till's open checks.")


class BulkDeletedOut(Schema):
    deleted: list[UUID]
