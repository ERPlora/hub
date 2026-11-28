"""The settings of the public page and the diary's rules it applies: what the owner changes and what she reads."""

import re
from typing import Annotated

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field
from pydantic import AfterValidator, StringConstraints

from apps.appointment.schemas.settings import AdvanceDays
from apps.online_booking.logo import LogoFieldsOut, LogoName
from apps.online_booking.schemas.fields import In, _text

#: The page's own texts.
MAX_TEXT = 2000

NOT_A_COLOUR = _("Write the colour as #RRGGBB (for example #6366f1).")

_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _colour(value: str) -> str:
    if not _COLOUR.match(value):
        raise ValueError(str(NOT_A_COLOUR))
    return value


Colour = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=7), AfterValidator(_colour)
]
Text = _text(MAX_TEXT)


class SettingsIn(In):
    """Only what is sent changes, all of it or nothing; the rules are the diary's (Citas)."""

    is_enabled: bool | None = Field(None, description="The public page takes bookings.")
    page_title: _text(120) | None = Field(
        None, description="The page's title; empty: its usual title, in the visitor's language."
    )
    welcome_message: Text | None = Field(
        None, description="The text at the top of the page."
    )
    primary_color: Colour | None = Field(
        None, description="The page's colour, as #RRGGBB."
    )
    logo: LogoName | None = Field(
        None, description="The logo, as online_booking.settings.upload_logo answered it; empty = no logo."
    )
    require_email: bool | None = Field(
        None, description="The customer must leave her email."
    )
    max_upcoming_per_customer: int | None = Field(
        None,
        ge=1,
        le=50,
        description="How many upcoming online bookings one mobile may hold at once (1 to 50).",
    )
    allow_staff_selection: bool | None = Field(
        None, description="The customer may choose the professional."
    )
    allow_notes: bool | None = Field(None, description="The customer may leave a note.")
    confirmation_message: Text | None = Field(
        None,
        description="What the customer reads once she has booked; empty = the page's own.",
    )
    cancellation_policy: Text | None = Field(
        None, description="The cancellation policy the customer reads."
    )
    min_booking_notice: int | None = Field(
        None,
        ge=0,
        le=10080,
        title=gettext_noop("Minimum booking notice (minutes)"),
        description="Diary rule: minutes ahead the customer must book.",
    )
    max_advance_booking: AdvanceDays | None = Field(
        None,
        title=gettext_noop("Book at most this far ahead (days)"),
        description="Diary rule: days ahead one may book; 0 = no limit.",
    )
    slot_interval: int | None = Field(
        None,
        ge=5,
        le=240,
        title=gettext_noop("Slot interval (minutes)"),
        description="Diary rule: minutes between free times.",
    )
    auto_confirm_online: bool | None = Field(
        None,
        title=gettext_noop("Confirm the customer's bookings automatically"),
        description="Diary rule: the customer's bookings are born confirmed (false: pending, to review).",
    )
    allow_customer_cancellation: bool | None = Field(
        None,
        title=gettext_noop("Let the customer cancel her booking"),
        description="Diary rule: the customer may cancel her booking.",
    )
    cancellation_notice_hours: int | None = Field(
        None,
        ge=0,
        le=720,
        title=gettext_noop("Minimum notice to cancel (hours)"),
        description="Diary rule: hours before the start she may still cancel.",
    )


class SettingsOut(LogoFieldsOut):
    is_enabled: bool
    page_title: str
    welcome_message: str
    primary_color: str
    require_email: bool
    max_upcoming_per_customer: int
    allow_staff_selection: bool
    allow_notes: bool
    confirmation_message: str
    cancellation_policy: str
    min_booking_notice: int
    max_advance_booking: int
    slot_interval: int
    auto_confirm_online: bool
    allow_customer_cancellation: bool
    cancellation_notice_hours: int
    timezone: str
