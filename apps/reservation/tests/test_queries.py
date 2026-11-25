"""The book's reads together: every list keeps its ties in its own direction, and every read needs its permission.
Each is a ``READ ONLY`` operation; the reads of one entity are tested in ``test_queries_<module>.py``."""

import datetime as dt

import pytest
from live.errors import PermissionDenied

from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import (
    HUB_DB,
    ctx_for,
    make_blocked,
    make_entry,
    make_reservation,
    make_slot,
    run,
)

pytestmark = HUB_DB

NOBODY = ctx_for(permissions=set())


def _tied_reservations():
    return [make_reservation(guest_name="Same").id for _ in range(4)]


def _tied_slots():
    return [make_slot(n, max_reservations=10).id for n in range(4)]


def _tied_blocked_dates():
    return [
        make_blocked(reason="Same", blocked_from=dt.time(9 + n), blocked_until=dt.time(10 + n)).id for n in range(4)
    ]


def _tied_waitlist():
    return [make_entry(guest_name="Same").id for _ in range(4)]


@pytest.mark.parametrize(
    ("operation", "tied", "column"),
    [
        ("reservation.reservation.list", _tied_reservations, "guest_name"),
        ("reservation.time_slot.list", _tied_slots, "max_reservations"),
        ("reservation.blocked_date.list", _tied_blocked_dates, "reason"),
        ("reservation.waitlist.list", _tied_waitlist, "guest_name"),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(operation, tied, column):
    """hub#768 (as in Customers): a descending list is the ascending one read backwards, ties
    included, and its pages neither repeat nor lose rows."""
    assert_reads_backwards(listed_with(run, operation, column), sorted(tied()))


def rows(result) -> list:
    return [row for row in result.rows]


def test_every_read_needs_its_permission():
    for name, data in (
        ("reservation.reservation.list", {}),
        ("reservation.availability.day", {}),
        ("reservation.availability.tables", {"date": "2026-10-15", "time": "21:00"}),
        ("reservation.time_slot.list", {}),
        ("reservation.blocked_date.list", {}),
        ("reservation.waitlist.list", {}),
        ("reservation.settings.get", {}),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, NOBODY)
