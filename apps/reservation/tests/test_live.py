"""Live queries of the reservation app: which events re-run which query after the COMMIT.

The book is live: a reservation taken, changed or moved through its states re-runs the day's list, its
figures and the occupancy of its slots; a table renamed or taken out of service re-runs the free tables and
the labels; a change of the business's hours re-runs the day; the waitlist, the slots, the blocked dates and
the rules follow their own events.
"""

import pytest
from live.live_registry import live_registry

from apps.reservation import events

#: A reservation row also paints its table («5 (Terrace)»).
BOOK = [*events.RESERVATION_EVENTS, *events.TABLE_EVENTS]
DAY = [
    *events.RESERVATION_EVENTS,
    *events.SLOT_EVENTS,
    *events.BLOCKED_EVENTS,
    *events.SCHEDULE_EVENTS,
]
TABLES = [*events.RESERVATION_EVENTS, *events.TABLE_EVENTS]


def reservation_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("reservation.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert reservation_queries() == {
        "reservation.reservation.list": BOOK,
        "reservation.reservation.get": BOOK,
        "reservation.availability.day": DAY,
        "reservation.availability.tables": TABLES,
        "reservation.time_slot.list": events.SLOT_EVENTS,
        "reservation.blocked_date.list": events.BLOCKED_EVENTS,
        "reservation.waitlist.list": events.WAITLIST_EVENTS,
        "reservation.settings.get": [events.SETTINGS_UPDATED],
    }


@pytest.mark.django_db
def test_every_live_query_is_one_of_this_apps_reads():
    from live.operations import get

    for name in reservation_queries():
        assert get(name).kind == "query", name
