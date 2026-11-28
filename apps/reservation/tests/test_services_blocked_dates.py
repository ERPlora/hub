"""Writes of the book's blocked dates (``reservation.blocked_date.*``)."""

import datetime as dt

from apps.reservation.models import BlockedDate

from .conftest import HUB_DB, events, refusal, run

pytestmark = HUB_DB


def test_a_date_is_blocked_whole_or_for_some_hours_once_and_unblocked():
    whole = run(
        "reservation.blocked_date.create", {"date": "2026-10-15", "reason": "Holiday"}
    )
    assert whole.is_full_day is True
    error = refusal(
        lambda: run("reservation.blocked_date.create", {"date": "2026-10-15"})
    )
    assert (error.code, error.message) == (
        "reservation.blocked_date_exists",
        "That date is already blocked at that time.",
    )
    hours = run(
        "reservation.blocked_date.create",
        {
            "date": "2026-10-16",
            "is_full_day": False,
            "blocked_from": "20:00",
            "blocked_until": "22:00",
        },
    )
    assert (hours.blocked_from, hours.blocked_until) == (dt.time(20), dt.time(22))
    run("reservation.blocked_date.delete", {"date": "2026-10-15"})
    assert BlockedDate.objects.get(pk=whole.id).is_deleted is True
    assert events() == [
        "reservation.blocked_date.created",
        "reservation.blocked_date.created",
        "reservation.blocked_date.deleted",
    ]
