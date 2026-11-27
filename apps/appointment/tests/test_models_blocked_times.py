"""Models of the blocked times: what the database itself refuses, and what a row looks like.

The operations check before writing; these constraints are the last line when two writes race or a
second write path (the admin) skips the rules.
"""

from apps.appointment.models.blocked_times import BlockedTime

from .conftest import HUB_DB, MONDAY, at, make_block, refused

pytestmark = HUB_DB


def test_a_block_ends_after_it_starts():
    make_block(at(MONDAY, "10:00"), at(MONDAY, "11:00"))
    refused(lambda: make_block(at(MONDAY, "11:00"), at(MONDAY, "11:00")))
    refused(
        lambda: make_block(at(MONDAY, "11:00"), at(MONDAY, "12:00"), block_type="party")
    )
    assert BlockedTime.objects.count() == 1
