"""Schemas of the book's rules: changing them and reading them."""

from ninja import Field, Schema

from apps.reservation.schemas.fields import Guests, In, Minutes


class SettingsIn(In):
    min_party_size: Guests | None = Field(
        None, description="The fewest guests a reservation takes."
    )
    max_party_size: Guests | None = Field(
        None, description="The most guests a reservation takes."
    )
    min_advance_hours: int | None = Field(
        None,
        ge=0,
        le=720,
        description="Hours of notice a guest booking herself (online, WhatsApp) must give.",
    )
    max_advance_days: int | None = Field(
        None, ge=0, le=365, description="How many days ahead a guest booking herself (online, WhatsApp) may book; the staff are not bound."
    )
    default_duration_minutes: Minutes | None = Field(
        None, description="How long a reservation keeps its table."
    )
    auto_confirm: bool | None = Field(
        None, description="True: every new reservation is born confirmed."
    )
    require_phone: bool | None = Field(
        None, description="True: every reservation needs a phone."
    )
    require_email: bool | None = Field(
        None, description="True: every reservation needs an email."
    )
    no_show_window_minutes: int | None = Field(
        None,
        ge=0,
        le=1440,
        description="Minutes after its time an unconfirmed reservation is released.",
    )


class SettingsOut(Schema):
    min_party_size: int = Field(description="The fewest guests a reservation takes.")
    max_party_size: int = Field(description="The most guests a reservation takes.")
    min_advance_hours: int = Field(
        description="Hours of notice for the guest booking herself."
    )
    max_advance_days: int = Field(description="How many days ahead a guest booking herself (online, WhatsApp) may book; the staff are not bound.")
    default_duration_minutes: int = Field(
        description="How long a reservation keeps its table."
    )
    auto_confirm: bool = Field(description="Every new reservation is born confirmed.")
    require_phone: bool = Field(description="Every reservation needs a phone.")
    require_email: bool = Field(description="Every reservation needs an email.")
    no_show_window_minutes: int = Field(
        description="Minutes after its time an unconfirmed reservation is released."
    )
    timezone: str = Field(
        description="The business's time zone."
    )
