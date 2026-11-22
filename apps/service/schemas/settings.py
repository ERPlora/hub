"""Schemas of the service settings: the defaults a new service takes and what the booking page shows."""

from datetime import datetime
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.service.schemas.fields import Buffer, Code, In, Minutes


class SettingsIn(In):
    """Only the fields sent change."""

    default_duration: Minutes | None = Field(
        None, description="Duration a new service takes, in minutes."
    )
    default_buffer_time: Buffer | None = Field(
        None, description="Buffer before and after a new service, in minutes."
    )
    default_tax_category_key: Code | None = Field(
        None,
        title=gettext_noop("Default tax category"),
        description="Key of the tax category a new service takes; null or empty removes it.",
    )
    show_prices: bool | None = Field(
        None, description="Whether the public booking page shows prices."
    )
    show_duration: bool | None = Field(
        None, description="Whether the public booking page shows durations."
    )
    allow_online_booking: bool | None = Field(
        None, description="Whether a new service may be booked online."
    )


class SettingsOut(Schema):
    default_duration: int
    default_buffer_time: int
    default_tax_category_id: UUID | None
    default_tax_category_key: str | None
    default_tax_category_name: str | None
    show_prices: bool
    show_duration: bool
    allow_online_booking: bool
    updated_at: datetime | None
