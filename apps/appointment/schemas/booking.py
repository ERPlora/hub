"""Booking: one appointment, or the same one at several times."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field
from pydantic import ValidationInfo, field_validator, model_validator

from apps.appointment.schemas.fields import (
    A_MEMBER,
    BOOK_EVEN_IF_IT_OVERLAPS,
    D_CONFIRM_OVERLAP,
    D_DURATION,
    D_SERVICES,
    D_START,
    MAX_BATCH,
    Minutes,
    Note,
    Said,
    Source,
)
from apps.appointment.schemas.references import SAY_WHICH_STAFF, CustomerOf, Services, _named

PICK_A_SERVICE = _("Pick at least one service.")


class AppointmentCreateIn(CustomerOf):
    services: Services = Field(description=D_SERVICES)
    staff_id: UUID | None = Field(
        None, description="The professional's id (a staff member).", json_schema_extra=A_MEMBER
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
    confirm_overlap: bool = Field(False, title=BOOK_EVEN_IF_IT_OVERLAPS, description=D_CONFIRM_OVERLAP)

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
    staff_id: UUID | None = Field(None, description="The professional's id.", json_schema_extra=A_MEMBER)
    staff: Said | None = Field(
        None, validate_default=True, description="The professional's name."
    )
    starts: list[dt.datetime] = Field(
        title=gettext_noop("Dates and times"),
        min_length=1,
        max_length=MAX_BATCH,
        description="Every start to book (1 to 50), as in a single booking.",
    )
    duration_minutes: Minutes | None = Field(None, description=D_DURATION)
    notes: Note = Field(
        "", description="Notes the customer may see, on every appointment."
    )
    confirm_overlap: bool = Field(False, title=BOOK_EVEN_IF_IT_OVERLAPS, description=D_CONFIRM_OVERLAP)

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
