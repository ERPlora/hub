"""The business's wall clock: now, and a reservation's day and time as the instant and the stay they are. The
business's zone is the Hub's (``base.business.business_zone``).
"""

import datetime as dt

from django.utils import timezone

from apps.reservation import engine
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
