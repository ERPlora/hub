"""The business's clock and the book's rules. The business's zone is the Hub's (``base.business.business_zone``)."""

import datetime as dt

from django.utils import timezone

from apps.reservation import engine
from apps.reservation.models import Settings
from base.business import business_zone


def business_now() -> dt.datetime:
    """Now on the business's wall clock (naive), what a reservation's day and time compare with (its
    ``fold`` says which pass of a repeated hour it is)."""
    return timezone.localtime(timezone.now(), business_zone()).replace(tzinfo=None)


def starts_at(day: dt.date, at: dt.time) -> dt.datetime:
    """The instant (UTC) ``day`` at ``at`` on the business's wall clock is."""
    return engine.instant(dt.datetime.combine(day, at), business_zone())


def window_of(day: dt.date, at: dt.time, minutes: int) -> engine.Window:
    """A stay from ``day`` at ``at`` on the business's wall clock, ``minutes`` of real time long."""
    return engine.Window.of(day, at, minutes, business_zone())


def wall_clock(moment: dt.datetime) -> dt.datetime:
    """An instant on the business's wall clock (naive)."""
    return engine.wall(moment, business_zone())


def current_settings() -> Settings:
    """The book's rules; the factory ones (unsaved) while nobody saved them."""
    return Settings.objects.first() or Settings()


def rules_of(settings: Settings) -> engine.Rules:
    return engine.Rules(
        min_party_size=settings.min_party_size,
        max_party_size=settings.max_party_size,
        min_advance_hours=settings.min_advance_hours,
        max_advance_days=settings.max_advance_days,
        require_phone=settings.require_phone,
        require_email=settings.require_email,
    )
