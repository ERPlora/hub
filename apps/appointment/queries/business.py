"""The business's clock and settings."""

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.errors import InvalidPayload

from apps.appointment import engine
from apps.appointment.models import Settings
from base.business import business_zone

INVALID_LOCAL_TIME = _(
    "That time does not exist on the business's clock: the change of time skips it. Pick another one."
)


def now() -> dt.datetime:
    return timezone.now()


def today() -> dt.date:
    return engine.wall(now(), business_zone()).date()


def read_moment(value: dt.datetime, field: str) -> dt.datetime:
    """A time as sent (wall clock or instant) read on the business's clock; 422 on ``field`` if skipped."""
    try:
        return engine.aware(value.replace(second=0, microsecond=0), business_zone())
    except engine.NonexistentTime:
        message = str(INVALID_LOCAL_TIME)
        raise InvalidPayload(
            message, code="appointment.invalid_local_time", fields={field: message}
        ) from None


def current_settings() -> Settings:
    """The saved settings, or the factory ones (unsaved) while nobody saved them."""
    return Settings.objects.first() or Settings()


def rules_of(settings: Settings) -> engine.Rules:
    return engine.Rules(
        min_notice=settings.min_booking_notice,
        max_advance_days=settings.max_advance_booking,
        allow_overlap=settings.allow_overlapping,
        calendar_start_hour=settings.calendar_start_hour,
        calendar_end_hour=settings.calendar_end_hour,
        slot_interval=settings.slot_interval,
    )


def day_bounds(
    date_from: dt.date, date_to: dt.date | None
) -> tuple[dt.datetime, dt.datetime]:
    """The instants of the business days ``date_from`` … ``date_to`` (included)."""
    zone = business_zone()
    last = date_to or date_from
    return engine.midnight(date_from, zone), engine.midnight(
        last + dt.timedelta(days=1), zone
    )
