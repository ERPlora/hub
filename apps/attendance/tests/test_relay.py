"""The time clock hears Staff through the worker's outbox relay, end to end (ATTENDANCE-F13).

Staff's real operation terminates a person and records ``staff.member.terminated`` in the outbox; one tick of the
worker's real loop (``base.worker.run`` → ``base.relay``, ``worker_loop``) hands it to the time clock, and the person's
open day (and its running break) is closed with a correction of the system — once: a second tick, or the same event
handed over again, changes nothing. A person who leaves in hub B closes B's day only, and the notice is heard in B only.

The worker's real loop serves each business in its own database and releases its connections once it has served it:
what these tests write is committed.
"""


import pytest
from django.utils import timezone, translation
from live.models import OutboxEvent

from apps.attendance import events
from apps.attendance.models import Correction
from apps.flow.tests.test_relay import heard
from base.models import EventDelivery
from base.tenancy.context import use_hub

from .conftest import HUB_DB_COMMITTED, A, B, ctx_for, run

pytestmark = HUB_DB_COMMITTED

TERMINATED = "staff.member.terminated"


def delivery_to_attendance() -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest termination to the time clock."""
    event = OutboxEvent.objects.filter(name=TERMINATED).latest("id")
    row = EventDelivery.objects.get(event_id=event.id, app_label="attendance")
    return row.status, row.attempts


def day(record_id, scope=A):
    """The working day as a manager reads it, with its breaks."""
    return run("attendance.record.detail", {"id": str(record_id)}, ctx_for("hub_manager", scope=scope))


def in_now(scope=A) -> list[str]:
    """Who «Clocked in now» says is in."""
    return [row.member_name for row in run("attendance.presence.list", {}, ctx_for("hub_manager", scope=scope)).rows]


def notices(name: str) -> int:
    return OutboxEvent.objects.filter(name=name).count()


@pytest.fixture
def ana_on_a_break(person, clock):
    """Ana clocked in at 07:00 and on a break since 11:00; Bea clocked in at 08:00. It is 12:00."""
    clock("2026-10-06T07:00")
    ana, ana_ctx = person("Ana", "López")
    ana_day = run("attendance.record.clock_in", {}, ana_ctx)
    clock("2026-10-06T08:00")
    bea, bea_ctx = person("Bea", "Ruiz")
    bea_day = run("attendance.record.clock_in", {}, bea_ctx)
    clock("2026-10-06T11:00")
    run("attendance.break.start", {}, ana_ctx)
    clock("2026-10-06T12:00")
    return ana, ana_ctx, ana_day, bea_day


def test_a_person_terminated_in_staff_has_their_open_day_closed_through_the_relay(worker_loop, ana_on_a_break):
    ana, ana_ctx, ana_day, bea_day = ana_on_a_break

    run("staff.member.terminate", {"id": str(ana.id), "reason": "End of contract"}, ctx_for("hub_admin"))
    # Staff's command only records its event: the day waits for the relay.
    assert day(ana_day.id).status == "open"
    assert Correction.objects.count() == 0

    worker_loop()

    assert delivery_to_attendance() == ("delivered", 1)
    closed = day(ana_day.id)
    assert closed.status == "closed"
    assert closed.clock_out_at == timezone.now()
    # The running break ends with the day: 11:00 to 12:00.
    assert [(b.ended_at, b.seconds) for b in closed.breaks] == [(timezone.now(), 3600)]
    assert closed.break_seconds == 3600 and closed.worked_seconds == 4 * 3600
    # One correction of the system, with its reason in the reader's language.
    trail = run("attendance.correction.list", {"record_id": str(ana_day.id)}, ctx_for("hub_manager")).rows
    assert [(t.is_system, t.created_by_name, t.old_status, t.new_status) for t in trail] == [
        (True, "", "open", "closed")
    ]
    assert trail[0].reason == "Day closed when the person was terminated in Staff."
    with translation.override("es"):
        trail = run("attendance.correction.list", {"record_id": str(ana_day.id)}, ctx_for("hub_manager")).rows
    assert trail[0].reason == "Jornada cerrada al dar de baja a la persona en Personal."
    # Its notices, after the COMMIT of the reaction: the break ended and the day corrected.
    corrected = OutboxEvent.objects.get(name=events.RECORD_CORRECTED)
    assert corrected.payload["id"] == str(ana_day.id) and corrected.payload["member_id"] == str(ana.id)
    assert notices(events.BREAK_ENDED) == 1
    # Ana is out of «Clocked in now» and no longer clocks; Bea's day is untouched.
    assert in_now() == ["Bea Ruiz"]
    assert run("attendance.record.current", {}, ana_ctx).member is None
    assert day(bea_day.id).status == "open"
    # The day stays four years and keeps her name.
    assert day(ana_day.id).member_name == "Ana López"


def test_a_second_tick_or_the_same_notice_handed_over_again_changes_nothing(worker_loop, ana_on_a_break):
    ana, _ana_ctx, ana_day, _bea_day = ana_on_a_break
    run("staff.member.terminate", {"id": str(ana.id)}, ctx_for("hub_admin"))
    worker_loop()
    closed = day(ana_day.id)
    written = (notices(events.RECORD_CORRECTED), notices(events.BREAK_ENDED))

    worker_loop()
    assert delivery_to_attendance() == ("delivered", 1)

    # The same notice handed to the time clock again, as if its delivery had been lost: the relay runs it once more.
    event = OutboxEvent.objects.filter(name=TERMINATED).latest("id")
    EventDelivery.objects.filter(event_id=event.id, app_label="attendance").update(
        status=EventDelivery.Status.PENDING, delivered_at=None, next_attempt_at=timezone.now()
    )
    worker_loop()

    assert delivery_to_attendance() == ("delivered", 2)
    assert Correction.objects.count() == 1
    assert (notices(events.RECORD_CORRECTED), notices(events.BREAK_ENDED)) == written
    assert day(ana_day.id) == closed


def test_a_person_without_an_open_day_leaves_and_nothing_happens(worker_loop, person, clock):
    clock("2026-10-06T07:00")
    ana, ana_ctx = person("Ana", "López")
    ana_day = run("attendance.record.clock_in", {}, ana_ctx)
    clock("2026-10-06T15:00")
    run("attendance.record.clock_out", {}, ana_ctx)

    run("staff.member.terminate", {"id": str(ana.id)}, ctx_for("hub_admin"))
    worker_loop()

    assert delivery_to_attendance() == ("delivered", 1)
    assert Correction.objects.count() == 0
    assert day(ana_day.id).clock_out_at.isoformat() == "2026-10-06T15:00:00+00:00"


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────


def test_a_person_who_leaves_hub_b_has_b_day_closed_only_and_is_heard_in_b_only(listen, person, worker_loop, hub_b):
    on_a, on_b = listen(A), listen(B)
    ana, ana_ctx = person("Ana", "López", scope=A)
    a_day = run("attendance.record.clock_in", {}, ana_ctx)
    with use_hub(hub_b):
        bea, bea_ctx = person("Bea", "Ruiz", scope=B)
        b_day = run("attendance.record.clock_in", {}, bea_ctx)
    heard(on_a), heard(on_b)  # the clock-ins' own notices

    with use_hub(hub_b):
        run("staff.member.terminate", {"id": str(bea.id)}, ctx_for("hub_admin", scope=B))
    heard(on_b)  # the termination's own notice
    worker_loop()

    with use_hub(hub_b):
        assert day(b_day.id, B).status == "closed"
        reaction = OutboxEvent.objects.get(name=events.RECORD_CORRECTED, payload__id=str(b_day.id))
    assert events.RECORD_CORRECTED in heard(on_b)
    assert heard(on_a) == set()
    assert day(a_day.id, A).status == "open"
    assert (reaction.scope_kind, reaction.scope_key) == (B.kind, B.key)
    # The positive control: a person who leaves hub A has A's day closed, heard in A.
    run("staff.member.terminate", {"id": str(ana.id)}, ctx_for("hub_admin", scope=A))
    heard(on_a)
    worker_loop()
    assert day(a_day.id, A).status == "closed"
    assert events.RECORD_CORRECTED in heard(on_a)
    assert heard(on_b) == set()
