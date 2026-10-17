"""The Hub admin's «Delete» of a staff record and the writes on that person, at once: real sessions in
threads, real row locks.

A write on a schedule or a time off locks the person's record and then the row. Django's deletion of the
record deletes its schedules (their days first) and its time off and then the record, so it held the row
the write went for while it waited for the record the write held: Postgres killed one of the two (a 500).
The admin enters through the record (``lock_members``), so it waits for the write and then deletes what
the write left.
"""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

import pytest
from django.contrib import admin
from django.db import connection, transaction
from django.test import RequestFactory
from live.errors import OperationError
from live.operations import get

from apps.staff.models import Member, Schedule, ScheduleDay, TimeOff

from .conftest import ctx_for, make_member, make_schedule, make_time_off

pytestmark = pytest.mark.django_db(transaction=True)

#: How long the deletion runs on its own before the write goes on: long enough to reach the record.
IN_FLIGHT = 0.5
ADMIN_DELETIONS = ["delete_model", "delete_queryset"]
WEEK = [{"weekday": 1, "start_time": "10:00", "end_time": "14:00"}]


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


def admin_delete(member: Member, how: str) -> None:
    """The Hub admin's «Delete» of ``member``: its page (``delete_model``) or the list's «Delete selected»
    action (``delete_queryset``), as the staff run them."""
    model_admin = admin.site._registry[Member]
    request = RequestFactory().post("/admin/")
    if how == "delete_queryset":
        model_admin.delete_queryset(request, Member.objects.filter(pk=member.pk))
    else:
        model_admin.delete_model(request, Member.objects.get(pk=member.pk))


@contextmanager
def admin_deleting(member: Member, how: str, after: Callable[[str], bool]):
    """The Hub admin's «Delete» of ``member`` started in another session right before the first statement
    of this one for which ``after`` holds, and left to run a moment before this one goes on."""
    deletions: list = []

    def deletion():
        try:
            with transaction.atomic():
                admin_delete(member, how)
            deletions.append("ok")
        except Exception as error:  # a deadlock, reported to the test
            deletions.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        if thread.ident is None and after(sql):
            thread.start()
            time.sleep(IN_FLIGHT)
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "the deletion never started"


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


def attempt(call):
    """What ``call`` answers: its result, or the error it is refused with (a 500 is raised as it comes)."""
    try:
        return call()
    except OperationError as error:
        return error


def locks(table: str) -> Callable[[str], bool]:
    return lambda sql: f'FROM "{table}"' in sql and "FOR UPDATE" in sql


def updates(table: str) -> Callable[[str], bool]:
    return lambda sql: sql.lstrip().startswith(f'UPDATE "{table}"')


def schedule(ana: Member) -> Schedule:
    return make_schedule(ana, is_default=True)


def time_off(ana: Member) -> TimeOff:
    return make_time_off(ana, "2026-11-02")


def approved_time_off(ana: Member) -> TimeOff:
    return make_time_off(ana, "2026-11-02", status=TimeOff.Status.APPROVED)


#: What is written about Ana while the admin deletes her: the row it needs, the call, and its first
#: statement on that row once her record is held.
WRITTEN_ABOUT_A_PERSON = {
    "editing her schedule": (
        schedule,
        lambda row: run("staff.schedule.update", {"id": str(row.id), "name": "Winter", "days": WEEK}),
        locks("staff_schedule"),
    ),
    "switching her schedule off": (
        schedule,
        lambda row: run("staff.schedule.set_active", {"id": str(row.id), "is_active": False}),
        locks("staff_schedule"),
    ),
    "deleting her schedule": (
        schedule,
        lambda row: run("staff.schedule.delete", {"id": str(row.id)}),
        locks("staff_schedule"),
    ),
    "giving her a new usual schedule": (
        schedule,
        lambda row: run(
            "staff.schedule.create", {"member_id": str(row.member_id), "is_default": True, "days": WEEK}
        ),
        updates("staff_schedule"),
    ),
    "approving her time off": (
        time_off,
        lambda row: run("staff.time_off.approve", {"id": str(row.id)}),
        locks("staff_timeoff"),
    ),
    "rejecting her time off": (
        time_off,
        lambda row: run("staff.time_off.reject", {"id": str(row.id)}),
        locks("staff_timeoff"),
    ),
    "cancelling her time off": (
        approved_time_off,
        lambda row: run("staff.time_off.cancel", {"id": str(row.id)}),
        locks("staff_timeoff"),
    ),
}


@pytest.mark.parametrize("how", ADMIN_DELETIONS)
@pytest.mark.parametrize("written", sorted(WRITTEN_ABOUT_A_PERSON))
def test_a_write_on_a_person_while_the_hub_admin_deletes_them_never_waits_in_a_circle(written, how):
    setup, call, after = WRITTEN_ABOUT_A_PERSON[written]
    ana = make_member()
    row = setup(ana)
    with admin_deleting(ana, how, after) as deletions:
        outcome = attempt(lambda: call(row))
    # The deletion waited for the write, which went through, and then took her and all that was hers.
    assert deleted(deletions) == ["ok"]
    assert not isinstance(outcome, OperationError), outcome
    assert not Member.objects.filter(pk=ana.pk).exists()
    assert not (Schedule.objects.exists() or ScheduleDay.objects.exists() or TimeOff.objects.exists())

