"""The input of a waitlist entry: the day and time the guest would like, and for whom."""

import datetime as dt

from apps.reservation.schemas.waitlist import WaitlistIn

from .conftest import errors


def test_a_waitlist_entry_says_for_whom():
    entry = {
        "guest_name": "Luis",
        "guest_phone": "600",
        "date": "2026-10-15",
        "preferred_time": "21:00",
        "party_size": 2,
    }
    assert WaitlistIn.model_validate(entry).preferred_time == dt.time(21)
    assert "__root__" in errors(WaitlistIn, {**entry, "guest_name": ""})
