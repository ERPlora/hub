"""A blocked period ends after it starts and has a title."""

from apps.appointment.schemas.blocked_times import BlockedTimeCreateIn

from .schema_checks import MONDAY, errors


def test_a_block_ends_after_it_starts_and_has_a_title():
    good = {"title": "Training", "start": f"{MONDAY}T12:00", "end": f"{MONDAY}T13:00"}
    assert not errors(BlockedTimeCreateIn, **good)
    assert "end" in errors(BlockedTimeCreateIn, **{**good, "end": f"{MONDAY}T11:00"})
    assert "title" in errors(BlockedTimeCreateIn, **{**good, "title": " "})
    # A whole day may end the same day it starts.
    assert not errors(
        BlockedTimeCreateIn, **{**good, "end": f"{MONDAY}T12:00", "all_day": True}
    )
