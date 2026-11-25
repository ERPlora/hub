"""Who is clocked in now and how many (attendance.presence.list and .count): closed, forgotten and terminated days
do not count, and only whoever sees the team reads them."""

import pytest
from live.errors import PermissionDenied

from apps.attendance.schemas import PresenceCountOut, PresencePage
from apps.staff.models import Member

from .conftest import HUB_DB, NOW, ctx_for, day, make_member, run, utc

pytestmark = HUB_DB


# attendance.presence.list: who is in now (ATTENDANCE-F11)


def test_who_is_in_now_leaves_out_closed_and_forgotten_days(person, clock):
    clock(NOW)
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    carlos, _ = person("Carlos", "Gil")
    dani, _ = person("Dani", "Paz")
    day(ana, "2026-10-06T07:00")
    day(bea, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])
    day(carlos, "2026-10-06T06:00", "2026-10-06T09:00")
    day(dani, "2026-10-04T07:00", status="needs_review")
    page = run("attendance.presence.list", {}, ctx_for("hub_manager"))
    assert isinstance(page, PresencePage)
    assert page.total == 2
    assert [(p.member_name, p.break_started_at) for p in page.rows] == [
        ("Ana López", None),
        ("Bea Ruiz", utc("2026-10-06T10:00")),
    ]
    assert [
        p.member_name
        for p in run(
            "attendance.presence.list", {"search": "bea"}, ctx_for("hub_manager")
        ).rows
    ] == ["Bea Ruiz"]


def test_only_who_sees_the_team_sees_who_is_in(person):
    _, ctx = person()
    with pytest.raises(PermissionDenied):
        run("attendance.presence.list", {}, ctx)


# attendance.presence.count: how many are in now (the Home's «Clocked in now», ATTENDANCE-F11)


def test_how_many_are_in_now_counts_what_the_list_shows(person, clock):
    # The old battery's «presence.count counts only open days»: the count is the list's total, whatever its page.
    clock(NOW)
    assert run("attendance.presence.count", {}, ctx_for("hub_manager")) == PresenceCountOut(count=0)
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    carlos, _ = person("Carlos", "Gil")
    dani, _ = person("Dani", "Paz")
    gone = make_member("Eva", "Sanz", status=Member.Status.TERMINATED)
    day(ana, "2026-10-06T07:00")
    day(bea, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])  # on a break: in
    day(carlos, "2026-10-06T06:00", "2026-10-06T09:00")  # closed
    day(dani, "2026-10-04T07:00", status="needs_review")
    day(gone, "2026-10-06T08:00")
    day(make_member("Fina", "Vidal"), "2026-10-05T20:00")  # 14 h 30 min open: forgotten
    count = run("attendance.presence.count", {}, ctx_for("hub_manager"))
    assert isinstance(count, PresenceCountOut)
    assert count.count == 2
    assert count.count == run("attendance.presence.list", {"limit": 1}, ctx_for("hub_manager")).total


def test_only_who_sees_the_team_counts_who_is_in(person):
    _, ctx = person()
    with pytest.raises(PermissionDenied):
        run("attendance.presence.count", {}, ctx)


def test_who_is_in_leaves_out_forgotten_days_and_terminated_records(person, clock):
    clock("2026-10-06T20:00")
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    day(ana, "2026-10-06T07:00")  # 13 h: forgotten
    day(bea, "2026-10-06T12:00")
    day(gone, "2026-10-06T15:00")
    assert [p.member_name for p in run("attendance.presence.list", {}, ctx_for("hub_manager")).rows] == ["Bea Ruiz"]
