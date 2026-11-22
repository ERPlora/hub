"""The daily auto-close: the cut-off a forgotten open session should have closed at."""

import datetime as dt

from django.utils import timezone

from apps.cash_register.models import Session, Settings
from base.business import business_zone


def last_cut_off(now: dt.datetime, at: dt.time) -> dt.datetime:
    """The latest moment at ``at`` (business time) not after ``now``: today's, or yesterday's before it."""
    local = timezone.localtime(now, business_zone())
    zone = local.tzinfo
    cut = dt.datetime.combine(local.date(), at, tzinfo=zone)
    if cut > local:
        cut = dt.datetime.combine(local.date() - dt.timedelta(days=1), at, tzinfo=zone)
    return cut


def auto_close_due_at(
    session: Session, settings: Settings, now: dt.datetime
) -> dt.datetime | None:
    """The cut-off an open session should have closed at, when the daily auto-close is due for it."""
    if not (settings.auto_close_enabled and session.is_open):
        return None
    cut = last_cut_off(now, settings.auto_close_time)
    return cut if session.opened_at < cut else None
