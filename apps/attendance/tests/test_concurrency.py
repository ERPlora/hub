"""Two taps at the same instant (threads, real transactions): the second waits for the first one's lock on
the person, then decides on what it left. «Two clock-ins at once leave one open day» is the old module's
rule (its partial unique index); here the lock answers first and the index is the last guard."""

import threading

import pytest
from django.db import connection, transaction
from django.utils import timezone
from live.errors import Conflict

from apps.attendance.models import Break, Correction, Record
from apps.staff.models import Member
from apps.staff.tests.conftest import deleted_on_screen

from .conftest import ctx_for, make_member, run, utc

pytestmark = pytest.mark.django_db(transaction=True)

QUIET = 0.3


def _in_thread(target):
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    return thread, outcome


def _race(first, second):
    """Run ``first`` in a transaction kept open until ``second`` (another thread) is blocked on it.

    Returns the outcome of ``second``, which must have waited (a lock), never decided blind.
    """
    done, release = threading.Event(), threading.Event()

    def held():
        with transaction.atomic():
            result = first()
            done.set()
            release.wait(5)
        return result

    holder, held_outcome = _in_thread(held)
    assert done.wait(5)
    waiter, outcome = _in_thread(second)
    waiter.join(QUIET)
    waited = waiter.is_alive()
    release.set()
    holder.join(5)
    waiter.join(5)
    assert "result" in held_outcome, held_outcome
    assert waited, "the second call did not wait for the first one's lock"
    return outcome


def test_two_clock_ins_at_once_leave_one_open_day(person):
    _, ctx = person()
    outcome = _race(
        lambda: run("attendance.record.clock_in", {}, ctx),
        lambda: run("attendance.record.clock_in", {}, ctx),
    )
    assert isinstance(outcome.get("error"), Conflict), outcome
    assert outcome["error"].code == "attendance.already_clocked_in"
    assert Record.objects.filter(status="open").count() == 1


def test_two_break_starts_at_once_leave_one_break(person):
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    outcome = _race(
        lambda: run("attendance.break.start", {}, ctx),
        lambda: run("attendance.break.start", {}, ctx),
    )
    assert outcome["error"].code == "attendance.break_running"
    assert Break.objects.count() == 1


def test_a_manager_and_the_employee_clock_her_in_at_once(person, make_user):
    ana, ctx = person()
    manager = ctx_for("hub_manager", actor=make_user("boss", role="hub_manager"))
    outcome = _race(
        lambda: run("attendance.record.clock_in", {}, ctx),
        lambda: run("attendance.record.clock_in", {"member_id": str(ana.id)}, manager),
    )
    assert outcome["error"].code == "attendance.already_clocked_in"
    assert Record.objects.filter(member=ana, status="open").count() == 1


def test_a_clock_in_while_her_old_day_is_reopened_keeps_one_open_day(
    person, monkeypatch
):
    # A correction that reopens a day and a clock-in of the same person: one of them must lose.
    ana, ctx = person()
    old = Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-05T07:00"),
        clock_out_at=utc("2026-10-05T15:00"),
        status="closed",
        work_date=utc("2026-10-05T07:00").date(),
    )
    reopen = {
        "record_id": str(old.id),
        "clock_in_at": "2026-10-05T07:00:00Z",
        "clock_out_at": None,
        "reason": "Reopen",
    }
    monkeypatch.setattr(timezone, "now", lambda: utc("2026-10-05T16:00"))
    outcome = _race(
        lambda: run("attendance.record.correct", reopen),
        lambda: run("attendance.record.clock_in", {}, ctx),
    )
    assert outcome["error"].code == "attendance.already_clocked_in"
    assert Record.objects.filter(status="open").count() == 1
    assert Correction.objects.count() == 1


# ── The Hub admin's «Delete» of a person while their first day is clocked in ──────────────────────
#
# A clock-in holds the person's record and then writes the day, which protects the record. Django's delete
# page and its «Delete selected» check what protects a record before deleting it: the check ran before the
# clock-in committed, and the deletion then found the day (a 500). The admin locks the record before the
# check, so it waits for the clock-in and answers «Cannot delete», as for a person protected before.


@pytest.mark.parametrize("how", ["page", "list"])
def test_a_clock_in_while_the_hub_admin_deletes_the_person_leaves_them_protected(how):
    ana = make_member()
    writes_the_day = lambda sql: sql.lstrip().startswith('INSERT INTO "attendance_record"')  # noqa: E731
    with deleted_on_screen(ana, how, writes_the_day) as answers:
        record = run("attendance.record.clock_in", {"member_id": str(ana.id)})
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert (answer.status_code, str(answer.context["title"])) == (200, "Cannot delete staff member")
    assert len(answer.context["protected"]) == 1
    assert Member.objects.filter(pk=ana.pk).exists()
    assert Record.objects.filter(pk=record.id, member=ana).exists()
