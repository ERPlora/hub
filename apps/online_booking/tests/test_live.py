"""Live queries of the online booking app: which events re-run which query after the COMMIT.

The inbox follows the diary's appointments (a booking, a confirmation, a cancellation… of any appointment,
since it may be an online one) and Customers' merge and erasure (the names it shows). The settings follow
this app's and the diary's. The public reads are asked by the page at the moment: not followed.
"""

from live.live_registry import live_registry
from live.operations import get

from apps.appointment import events as appointment_events
from apps.online_booking import events

APPOINTMENTS = appointment_events.APPOINTMENT_EVENTS
CUSTOMER_GONE = ["customer.customer.merged", "customer.customer.erased"]


def online_booking_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("online_booking.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    inbox = [*APPOINTMENTS, *CUSTOMER_GONE, events.BOOKING_CREATED]
    assert online_booking_queries() == {
        "online_booking.booking.list": inbox,
        "online_booking.booking.get": inbox,
        "online_booking.settings.get": [
            events.SETTINGS_UPDATED,
            appointment_events.SETTINGS_UPDATED,
        ],
    }


def test_every_live_query_is_a_query_with_a_permission():
    for name in online_booking_queries():
        op = get(name)
        assert op.kind == "query" and op.permission, name


def test_the_public_reads_are_not_followed():
    assert not [name for name in online_booking_queries() if ".public." in name]
