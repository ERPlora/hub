"""Write operations of the attendance app: one transaction each, with its events in the outbox.

The cases come from the old module's batteries (clock_cycle against the kernel; data.pg: two clock-ins
in a row, the geofence, clock-out closing the running break, the correction guards and the overlap of
two days of a person, the review of forgotten days, the settings singleton) and the WORKBOOK. A refused command
leaves no trace: no row, no event.
"""

import json

import pytest
from live.errors import Conflict
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.attendance import events
from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, outbox, run

pytestmark = HUB_DB


# Live notifications: a write in one scope reaches that scope's channel only


def received(session, timeout=1.0, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@HUB_DB_COMMITTED
def test_clocking_in_in_b_notifies_b_only(listen, person, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        _, ctx_b = person(scope=B)
        run("attendance.record.clock_in", {}, ctx_b)
        noted_in_b = list(OutboxEvent.objects.values_list("scope_kind", "scope_key"))
    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.CLOCKED_IN]})
    ]
    assert received(on_a, timeout=0.3) == []
    # The notice leaves on the operation's channel whatever the event says: the event itself is B's, in B's database.
    assert noted_in_b == [(B.kind, B.key)]
    assert outbox() == []
    # Positive control: the same listener of A hears a command run in A.
    _, ctx_a = person("Bea", "Ruiz", scope=A)
    run("attendance.record.clock_in", {}, ctx_a)
    assert received(on_a, stop_after=1) == [
        (channel_for(A), {"events": [events.CLOCKED_IN]})
    ]


@HUB_DB_COMMITTED
def test_a_refused_command_notifies_nobody(listen, person):
    on_a = listen(A)
    _, ctx = person()
    with pytest.raises(Conflict):
        run("attendance.record.clock_out", {}, ctx)
    assert received(on_a, timeout=0.3) == []
