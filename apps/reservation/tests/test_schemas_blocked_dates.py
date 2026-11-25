"""The input of a blocked date: the whole day by default, or some hours with both ends in order."""

from apps.reservation.schemas.blocked_dates import BlockedDateIn

from .conftest import errors


def test_a_blocked_window_needs_both_ends_in_order():
    assert BlockedDateIn.model_validate({"date": "2026-10-15"}).is_full_day is True
    assert set(errors(BlockedDateIn, {"date": "2026-10-15", "is_full_day": False})) == {
        "blocked_from",
        "blocked_until",
    }
    assert "blocked_until" in errors(
        BlockedDateIn,
        {
            "date": "2026-10-15",
            "is_full_day": False,
            "blocked_from": "22:00",
            "blocked_until": "21:00",
        },
    )
