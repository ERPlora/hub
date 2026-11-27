"""The report of the team's tips, by person and by clocked working day (TIP-F13), and an employee's own tips of today and
of the week (TIP-F14): active tips only, by payment method; a business never reads another's."""

import dataclasses
import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, PermissionDenied

from apps.attendance.models import Record
from apps.tip.models import Tip
from base import activation
from base.business import business_zone
from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.context import use_hub

from .conftest import CARD, HUB_DB, B, add_tip, as_user, charge, ctx_for, member, open_session, run, with_cash

pytestmark = HUB_DB


@pytest.fixture
def today():
    """The business day the test runs on, on the business's clock."""
    return timezone.localdate(timezone=business_zone())


def figures(row) -> tuple[int, int, int, int, int]:
    return (row.card, row.cash, row.other, row.total, row.count)


def report(ctx=None, **params):
    return run("tip.report.get", params, ctx)


def move(tip, days: int) -> None:
    """``tip`` recorded ``days`` days earlier than it was."""
    Tip.objects.filter(pk=tip.id).update(created_at=timezone.now() - dt.timedelta(days=days))


@pytest.fixture
def team(coffee):
    """Bea with a card tip of 100 and a cash one of 200, Ana with a card one of 300, 500 in cash to the pool, a
    «Bizum» tip of 50 for Ana, and a card tip of 900 for Bea voided."""
    open_session()
    bea, ana = member("Bea"), member("Ana")
    bizum = run("sale.payment_method.create", {"name": "Bizum", "type": "other"})
    of_bea, of_ana = (str(charge(payments=CARD, staff_id=str(person.id)).id) for person in (bea, ana))
    tips = {
        "bea_card": add_tip(100, "card", sale_id=of_bea),
        "bea_cash": add_tip(200, "cash", sale_id=of_bea),
        "ana_card": add_tip(300, "card", sale_id=of_ana),
        "pool": run("tip.tip.add", {"amount": 500, "pool": True}),
        "ana_bizum": add_tip(50, sale_id=of_ana, method_id=str(bizum.id), method=None),
        "voided": add_tip(900, "card", sale_id=of_bea),
    }
    run("tip.tip.void", {"id": str(tips["voided"].id), "reason": "wrong sale"})
    return {"bea": bea, "ana": ana, "tips": tips}


def test_by_person_each_one_s_active_tips_by_payment_method_and_the_unassigned_last(team):
    shown = report()
    assert [(row.member_id, row.member_name) for row in shown.rows] == [
        (team["ana"].id, "Ana Ruiz"),
        (team["bea"].id, "Bea Ruiz"),
        (None, ""),
    ]
    assert [figures(row) for row in shown.rows] == [(300, 0, 50, 350, 2), (100, 200, 0, 300, 2), (0, 500, 0, 500, 1)]
    assert figures(shown.totals) == (400, 700, 50, 1150, 5)
    assert (shown.by, shown.shifts_available) == ("person", True)


def test_the_period_is_today_unless_said_and_counts_business_days(team, today):
    move(team["tips"]["ana_card"], 1)
    move(team["tips"]["pool"], 3)
    shown = report()
    assert (shown.date_from, shown.date_to) == (today, today)
    assert figures(shown.totals) == (100, 200, 50, 350, 3)
    yesterday = (today - dt.timedelta(days=1)).isoformat()
    assert figures(report(date_from=yesterday, date_to=yesterday).totals) == (300, 0, 0, 300, 1)
    assert figures(report(date_from=(today - dt.timedelta(days=6)).isoformat()).totals) == (400, 700, 50, 1150, 5)


def test_by_shift_each_clocked_working_day_with_the_tips_of_its_person_while_it_ran(team):
    shift = run("attendance.record.clock_in", {"member_id": str(team["bea"].id)})
    during = add_tip(70, "card", sale_id=str(charge(payments=CARD, staff_id=str(team["bea"].id)).id))
    of_another = add_tip(20, "cash", sale_id=str(charge(payments=CARD, staff_id=str(team["ana"].id)).id))
    run("attendance.record.clock_out", {"member_id": str(team["bea"].id)})
    after = add_tip(30, "card", sale_id=str(charge(payments=CARD, staff_id=str(team["bea"].id)).id))
    shown = report(by="shift")
    assert (shown.by, shown.shifts_available) == ("shift", True)
    first, outside = shown.rows
    assert (first.shift_id, first.member_id, first.member_name) == (shift.id, team["bea"].id, "Bea Ruiz")
    assert (first.clock_in_at, first.clock_out_at is not None) == (shift.clock_in_at, True)
    assert figures(first) == (during.amount, 0, 0, 70, 1)
    assert (outside.shift_id, outside.member_id) == (None, None)
    assert figures(outside) == (400 + after.amount, 700 + of_another.amount, 50, 1200, 7)
    assert figures(shown.totals) == (500, 720, 50, 1270, 8)


def test_by_shift_a_working_day_still_open_runs_until_now_and_one_without_tips_is_listed(team):
    run("attendance.record.clock_in", {"member_id": str(team["ana"].id)})
    add_tip(40, "cash", sale_id=str(charge(payments=CARD, staff_id=str(team["ana"].id)).id))
    run("attendance.record.clock_in", {"member_id": str(team["bea"].id)})
    rows = report(by="shift").rows
    assert [(row.member_name, row.clock_out_at, figures(row)) for row in rows[:2]] == [
        ("Ana Ruiz", None, (0, 40, 0, 40, 1)),
        ("Bea Ruiz", None, (0, 0, 0, 0, 0)),
    ]


def test_by_shift_a_working_day_clocked_in_the_evening_before_keeps_its_tips_after_midnight(team, today):
    """A bar that closes past midnight: tonight's tips are of the working day clocked in yesterday evening, and one
    that ended before today began is not listed."""
    midnight = dt.datetime.combine(today, dt.time.min, tzinfo=business_zone())
    over, still = (run("attendance.record.clock_in", {"member_id": str(team[name].id)}) for name in ("ana", "bea"))
    yesterday = {"work_date": today - dt.timedelta(days=1), "clock_in_at": midnight - dt.timedelta(hours=4)}
    Record.objects.filter(pk=over.id).update(
        **yesterday, clock_out_at=midnight - dt.timedelta(hours=1), status=Record.Status.CLOSED
    )
    Record.objects.filter(pk=still.id).update(**yesterday)
    rows = report(by="shift").rows
    assert [(row.member_name, row.shift_id, figures(row)) for row in rows[:-1]] == [
        ("Bea Ruiz", still.id, (100, 200, 0, 300, 2))
    ]


def test_by_shift_without_time_clock_says_so_and_still_gives_the_totals(team, monkeypatch):
    monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"attendance"}))
    shown = report(by="shift")
    assert (shown.shifts_available, shown.rows) == (False, [])
    assert figures(shown.totals) == (400, 700, 50, 1150, 5)
    assert report().shifts_available is True


def test_only_whoever_manages_tips_reads_the_report(team):
    with pytest.raises(PermissionDenied):
        report(ctx_for("hub_employee"))
    assert figures(report(ctx_for("hub_manager")).totals) == (400, 700, 50, 1150, 5)


def test_a_business_never_reads_the_tips_of_another_in_its_report(team, hub_b):
    with use_hub(hub_b):
        in_b = ctx_for(scope=B)
        assert report(in_b).rows == []
        with_cash(in_b)
        run("cash_register.settings.update", {"enable_cash_register": False}, in_b)
        run("tip.tip.add", {"amount": 700, "pool": True}, in_b)
        assert figures(report(in_b).totals) == (0, 700, 0, 700, 1)
    assert figures(report().totals) == (400, 700, 50, 1150, 5)


# My tips


@pytest.fixture
def bea_signed_in(team, make_user):
    """Bea's own user, an employee, linked to her record of the team."""
    user = make_user("bea", role="hub_employee")
    run("staff.member.update", {"id": str(team["bea"].id), "user_id": str(user.person.pk)})
    return as_user(user)


def mine(ctx):
    return run("tip.report.mine", {}, ctx)


def test_my_tips_of_today_and_of_the_week_by_payment_method_and_only_mine(bea_signed_in, team, today):
    shown = mine(bea_signed_in)
    week_from = today - dt.timedelta(days=today.weekday())
    assert (shown.member_name, shown.today, shown.week_from) == ("Bea Ruiz", today, week_from)
    assert figures(shown.day) == (100, 200, 0, 300, 2)
    assert figures(shown.week) == (100, 200, 0, 300, 2)


def test_my_tips_of_the_week_start_on_monday(bea_signed_in, team, today):
    move(team["tips"]["bea_cash"], today.weekday())
    move(team["tips"]["bea_card"], today.weekday() + 1)
    shown = mine(bea_signed_in)
    on_monday_too = today.weekday() == 0
    assert figures(shown.day) == ((0, 200, 0, 200, 1) if on_monday_too else (0, 0, 0, 0, 0))
    assert figures(shown.week) == (0, 200, 0, 200, 1)


def test_without_a_record_of_the_team_there_are_no_tips_of_mine(team, make_user):
    with pytest.raises(Conflict) as refused:
        mine(as_user(make_user("eva", role="hub_employee")))
    assert refused.value.code == "tip.member_not_linked"
    assert str(refused.value) == "Your user is not linked to any staff record: ask a manager to link it in Staff."


def test_an_employee_reads_their_own_tips_but_not_the_report(bea_signed_in):
    assert mine(bea_signed_in).day.total == 300
    with pytest.raises(PermissionDenied):
        report(bea_signed_in)


def test_my_tips_in_one_business_are_never_those_of_another(bea_signed_in, team, hub_b):
    user = bea_signed_in.actor
    Membership.objects.create(user=user, host=B.key, role="hub_employee")
    with use_hub(hub_b):
        in_b = dataclasses.replace(ctx_for("hub_employee", scope=B), actor=user)
        person = ensure_hub_user(user)
        bea_in_b = run(
            "staff.member.create", {"first_name": "Bea", "last_name": "B", "user_id": str(person.pk)}, ctx_for(scope=B)
        )
        assert figures(mine(in_b).day) == (0, 0, 0, 0, 0)
        assert mine(in_b).member_name == "Bea B"
        assert bea_in_b.id != team["bea"].id
    assert figures(mine(bea_signed_in).day) == (100, 200, 0, 300, 2)
