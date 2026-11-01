"""System › Resources reads ``base.plan.usage`` (BASE-F40; PLAN-HUB §66): every figure of the business against what its plan
really gives, with two real hubs so one never sees the other's. What was not measured yet comes as nothing, never as a
zero; the notices' thresholds live here, so the bell and the screen say the same.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import override
from live.context import OperationContext, Scope
from live.operations import AI, get

from base import meter
from base.models import Membership
from base.permissions import permissions_for
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from control.models import Hub, HubActivityDaily, HubUsageDaily, HubVisit

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)

NOW = dt.datetime(2026, 3, 15, 12, 0, tzinfo=dt.UTC)
TODAY = NOW.date()
YESTERDAY = TODAY - dt.timedelta(days=1)
MEASURED_AT = dt.datetime(2026, 3, 15, 0, 15, tzinfo=dt.UTC)

FREE = {"slug": "free", "max_users": 1, "max_devices": 1, "max_db_connections": 1, "statement_timeout_seconds": 5}
STARTER = {"slug": "starter", "max_users": 3, "max_devices": 2, "max_db_connections": 3, "statement_timeout_seconds": 15}
STANDARD = {"slug": "standard", "max_users": 8, "max_devices": 4, "max_db_connections": 6, "statement_timeout_seconds": 15}
PRO = {"slug": "pro", "max_users": 20, "max_devices": 8, "max_db_connections": 12, "statement_timeout_seconds": 15}

pytestmark = [HUB_DB, pytest.mark.usefixtures("no_test_fallback")]


@pytest.fixture(autouse=True)
def the_clock_and_a_clean_meter(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)
    monkeypatch.setattr(meter, "_recording", False)
    monkeypatch.setattr(meter, "_activity", {})
    monkeypatch.setattr(meter, "_seen", {})


def admin_of(hub, role="hub_owner", username="olga") -> OperationContext:
    user, _ = get_user_model().objects.get_or_create(username=f"saas:{username}-{hub.slug}")
    with use_hub(hub):
        Membership.objects.get_or_create(user=user, host=hub.slug, defaults={"role": role})
        permissions = permissions_for(user, Scope("host", hub.slug))
    return OperationContext(scope=Scope("host", hub.slug), actor=user, permissions=permissions, language="en")


def usage_of(hub, **kwargs):
    ctx = admin_of(hub, **kwargs)
    op = get("base.plan.usage")
    with use_hub(hub):
        return op(ctx, op.input()).model_dump(mode="json")


def on_plan(hub, plan, **more) -> None:
    Hub.objects.filter(pk=hub.pk).update(state={"plan": {**plan, **more}})


def measured(hub, day=YESTERDAY, *, s3=0, db=0, people=0, month=0) -> None:
    HubUsageDaily.objects.create(
        hub=hub, day=day, s3_bytes=s3, db_bytes=db, active_users_1d=people, active_users_30d=month, measured_at=MEASURED_AT
    )


def did(hub, day=TODAY, *, requests=0, peak=0, busy=0) -> None:
    HubActivityDaily.objects.create(hub=hub, day=day, requests=requests, peak_connections=peak, busy_requests=busy)


def seen(hub, person, moment=NOW, day=TODAY) -> None:
    HubVisit.objects.create(host=hub.slug, day=day, saas_user_id=person, last_seen_at=moment)


# ── Files ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("used", "limit", "status", "percent"),
    [
        (0, 100, "within", 0),
        (79, 100, "within", 79),
        (7999, 10000, "within", 79),
        (80, 100, "near", 80),
        (99, 100, "near", 99),
        (100, 100, "full", 100),
        (150, 100, "full", 150),
    ],
)
def test_the_files_against_the_plan_s_space_say_how_full_they_are(hub_a, used, limit, status, percent):
    on_plan(hub_a, STARTER, max_storage_bytes=limit)
    measured(hub_a, s3=used)

    assert usage_of(hub_a)["files"] == {
        "bytes": used,
        "day": YESTERDAY.isoformat(),
        "limit": limit,
        "percent": percent,
        "status": status,
    }


def test_a_plan_with_no_space_limit_has_no_status(hub_a):
    on_plan(hub_a, STARTER, max_storage_bytes=0)
    measured(hub_a, s3=999)

    files = usage_of(hub_a)["files"]

    assert (files["bytes"], files["limit"], files["percent"], files["status"]) == (999, None, None, None)


def test_before_the_first_night_the_files_have_no_figure_never_a_zero(hub_a):
    on_plan(hub_a, STARTER, max_storage_bytes=100)

    assert usage_of(hub_a)["files"] == {"bytes": None, "day": None, "limit": 100, "percent": None, "status": None}


def test_the_files_come_from_the_last_night_measured(hub_a):
    on_plan(hub_a, STARTER, max_storage_bytes=100)
    measured(hub_a, TODAY - dt.timedelta(days=3), s3=10)
    measured(hub_a, TODAY - dt.timedelta(days=2), s3=20)

    files = usage_of(hub_a)["files"]

    assert (files["bytes"], files["day"]) == (20, (TODAY - dt.timedelta(days=2)).isoformat())


# ── Connections ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_connections_are_today_s_highest_against_what_it_really_has(hub_a):
    on_plan(hub_a, STARTER)
    did(hub_a, YESTERDAY, peak=3)
    did(hub_a, TODAY, peak=2)

    connections = usage_of(hub_a)["connections"]

    assert (connections["peak_today"], connections["limit"]) == (2, 3)


@pytest.mark.parametrize(
    ("plan", "limit", "helps"), [(FREE, 1, True), (STARTER, 3, True), (STANDARD, 6, False), (PRO, 6, False)]
)
def test_the_limit_is_the_effective_one_and_a_bigger_plan_helps_only_below_it(hub_a, plan, limit, helps):
    on_plan(hub_a, plan)

    connections = usage_of(hub_a)["connections"]

    assert (connections["limit"], connections["bigger_plan_gives_more"]) == (limit, helps)


def test_the_limit_follows_what_pgbouncer_gives_here(hub_a, settings):
    settings.PGBOUNCER_MAX_DB_CONNECTIONS = 3
    on_plan(hub_a, STANDARD)

    connections = usage_of(hub_a)["connections"]

    assert (connections["limit"], connections["bigger_plan_gives_more"]) == (3, False)


@pytest.mark.parametrize("row", [None, 0], ids=["no row today", "no transaction today"])
def test_with_no_measure_today_the_peak_says_nothing_never_a_zero(hub_a, row):
    on_plan(hub_a, STARTER)
    did(hub_a, YESTERDAY, peak=3)
    if row is not None:
        did(hub_a, TODAY, requests=2, peak=row)

    assert usage_of(hub_a)["connections"]["peak_today"] is None


def test_the_requests_with_no_room_are_those_of_the_last_7_days(hub_a):
    on_plan(hub_a, STARTER)
    did(hub_a, TODAY - dt.timedelta(days=7), busy=100)
    did(hub_a, TODAY - dt.timedelta(days=6), busy=4)
    did(hub_a, TODAY, busy=1)

    connections = usage_of(hub_a)["connections"]

    assert (connections["busy_last_7_days"], connections["busy_since"]) == (5, None)
    assert connections["status"] == "near"


def test_counted_for_less_than_7_days_it_says_since_when(hub_a):
    on_plan(hub_a, STARTER)
    did(hub_a, TODAY - dt.timedelta(days=5), busy=0)

    connections = usage_of(hub_a)["connections"]

    assert connections["busy_last_7_days"] == 0
    assert connections["busy_since"] == (TODAY - dt.timedelta(days=5)).isoformat()
    assert connections["status"] == "within"


def test_counted_for_exactly_7_days_it_says_no_since(hub_a):
    on_plan(hub_a, STARTER)
    did(hub_a, TODAY - dt.timedelta(days=6))

    assert usage_of(hub_a)["connections"]["busy_since"] is None


def test_reaching_the_top_for_a_moment_is_within_the_limit(hub_a):
    """A Free plan's first operation of the day is its 100 %: only running out of room says anything."""
    on_plan(hub_a, FREE)
    did(hub_a, TODAY, peak=1)

    assert usage_of(hub_a)["connections"]["status"] == "within"


def test_never_counted_it_has_no_figure_never_a_zero(hub_a):
    on_plan(hub_a, STARTER)

    connections = usage_of(hub_a)["connections"]

    assert (connections["peak_today"], connections["busy_last_7_days"], connections["busy_since"]) == (None, None, None)
    assert connections["status"] == "within"


# ── Requests ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_requests_are_those_of_the_natural_month_in_utc(hub_a):
    did(hub_a, dt.date(2026, 2, 28), requests=1000)
    did(hub_a, dt.date(2026, 3, 1), requests=7)
    did(hub_a, TODAY, requests=5)

    assert usage_of(hub_a)["requests"] == {"this_month": 12, "since": None}


def test_counted_since_after_day_1_it_says_since_when(hub_a):
    did(hub_a, dt.date(2026, 3, 9), requests=3)

    assert usage_of(hub_a)["requests"] == {"this_month": 3, "since": "2026-03-09"}


def test_a_quiet_month_of_a_hub_counted_before_is_a_true_zero(hub_a):
    did(hub_a, dt.date(2026, 2, 3), requests=3)

    assert usage_of(hub_a)["requests"] == {"this_month": 0, "since": None}


def test_never_counted_the_requests_have_no_figure(hub_a):
    assert usage_of(hub_a)["requests"] == {"this_month": None, "since": None}


# ── What this process has not written yet ─────────────────────────────────────────────────────────────────────────────


def test_a_reading_adds_what_the_process_has_not_written_yet(hub_a, monkeypatch):
    on_plan(hub_a, STARTER)
    did(hub_a, TODAY, requests=10, peak=1, busy=1)
    seen(hub_a, "ana")
    monkeypatch.setattr(meter, "_recording", True)
    meter.count_request(hub_a.pk)
    meter.count_busy(hub_a.pk)
    meter.note_peak(hub_a.pk, 2)
    meter.note_seen(hub_a.slug, "ana")
    meter.note_seen(hub_a.slug, "leo")
    monkeypatch.setattr(meter, "_recording", False)

    usage = usage_of(hub_a)

    assert usage["requests"]["this_month"] == 11
    assert usage["connections"]["peak_today"] == 2
    assert usage["connections"]["busy_last_7_days"] == 2
    assert usage["activity"]["active_now"] == 2


def test_the_first_minute_of_a_hub_is_counted_since_today(hub_a, monkeypatch):
    on_plan(hub_a, STARTER)
    monkeypatch.setattr(meter, "_recording", True)
    meter.count_request(hub_a.pk)
    monkeypatch.setattr(meter, "_recording", False)

    usage = usage_of(hub_a)

    assert usage["requests"] == {"this_month": 1, "since": TODAY.isoformat()}
    assert (usage["connections"]["busy_last_7_days"], usage["connections"]["busy_since"]) == (0, TODAY.isoformat())


# ── People ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_active_now_is_who_had_activity_in_the_last_5_minutes_here(hub_a, hub_b):
    seen(hub_a, "ana", NOW - dt.timedelta(minutes=4, seconds=59))
    seen(hub_a, "leo", NOW - dt.timedelta(minutes=5, seconds=1))
    seen(hub_b, "bea")
    HubVisit.objects.create(host=hub_a.slug, day=TODAY, saas_user_id="logged-in-before-it-was-noted")

    assert usage_of(hub_a)["activity"]["active_now"] == 1


def test_active_now_looks_at_yesterday_s_visit_around_midnight(hub_a, monkeypatch):
    midnight = dt.datetime(2026, 3, 15, 0, 1, tzinfo=dt.UTC)
    monkeypatch.setattr(timezone, "now", lambda: midnight)
    seen(hub_a, "ana", midnight - dt.timedelta(minutes=2), day=YESTERDAY)
    seen(hub_a, "leo", midnight - dt.timedelta(minutes=2), day=YESTERDAY)
    seen(hub_a, "leo", midnight, day=TODAY)

    assert usage_of(hub_a)["activity"]["active_now"] == 2


def test_the_people_of_the_last_night_and_its_30_days(hub_a):
    measured(hub_a, YESTERDAY, people=2, month=7)

    activity = usage_of(hub_a)["activity"]

    assert (activity["last_day"], activity["last_30_days"]) == (2, 7)
    assert (activity["last_day_date"], activity["last_day_is_yesterday"]) == (YESTERDAY.isoformat(), True)


def test_a_last_night_older_than_yesterday_says_its_date(hub_a):
    day = TODAY - dt.timedelta(days=3)
    measured(hub_a, day, people=2, month=7)

    activity = usage_of(hub_a)["activity"]

    assert (activity["last_day_date"], activity["last_day_is_yesterday"]) == (day.isoformat(), False)


def test_before_the_first_night_the_people_measured_have_no_figure(hub_a):
    activity = usage_of(hub_a)["activity"]

    assert activity == {
        "active_now": 0,
        "last_day": None,
        "last_day_date": None,
        "last_day_is_yesterday": False,
        "last_30_days": None,
    }


# ── A business never sees another's ───────────────────────────────────────────────────────────────────────────────────


def test_a_hub_never_sees_the_figures_of_another(hub_a, hub_b):
    on_plan(hub_a, STARTER, max_storage_bytes=1000)
    on_plan(hub_b, STANDARD, max_storage_bytes=2000)
    measured(hub_a, s3=100, db=11, people=1, month=2)
    measured(hub_b, s3=900, db=22, people=3, month=4)
    did(hub_a, TODAY, requests=5, peak=1, busy=0)
    did(hub_b, TODAY, requests=50, peak=4, busy=9)
    seen(hub_a, "ana")
    seen(hub_b, "bea")
    seen(hub_b, "leo")

    a, b = usage_of(hub_a), usage_of(hub_b)

    assert (a["files"]["bytes"], a["files"]["limit"], a["database"]["bytes"]) == (100, 1000, 11)
    assert (b["files"]["bytes"], b["files"]["limit"], b["database"]["bytes"]) == (900, 2000, 22)
    assert (a["requests"]["this_month"], a["connections"]["peak_today"], a["connections"]["busy_last_7_days"]) == (5, 1, 0)
    assert (b["requests"]["this_month"], b["connections"]["peak_today"], b["connections"]["busy_last_7_days"]) == (50, 4, 9)
    assert (a["activity"]["active_now"], a["activity"]["last_day"], a["activity"]["last_30_days"]) == (1, 1, 2)
    assert (b["activity"]["active_now"], b["activity"]["last_day"], b["activity"]["last_30_days"]) == (2, 3, 4)


# ── What the hub does not know ────────────────────────────────────────────────────────────────────────────────────────


def test_without_the_plan_the_figures_have_no_limit_status_or_notice(hub_a):
    measured(hub_a, s3=900)
    did(hub_a, TODAY, requests=5, peak=1, busy=9)

    usage = usage_of(hub_a)

    assert usage["known"] is False
    assert (usage["files"]["bytes"], usage["files"]["limit"], usage["files"]["status"]) == (900, None, None)
    assert usage["files"]["percent"] is None
    assert usage["connections"]["peak_today"] == 1
    assert usage["connections"]["busy_last_7_days"] == 9
    assert (usage["connections"]["limit"], usage["connections"]["status"]) == (None, None)
    assert usage["connections"]["bigger_plan_gives_more"] is False


def test_a_demo_says_so_and_carries_no_figure(hub_a):
    Hub.objects.filter(pk=hub_a.pk).update(is_demo=True)
    measured(hub_a, s3=900, people=4, month=4)
    did(hub_a, TODAY, requests=5, peak=1, busy=9)
    seen(hub_a, "ana")

    usage = usage_of(hub_a)

    assert usage["demo"] is True
    assert usage["files"] == {"bytes": None, "day": None, "limit": None, "percent": None, "status": None}
    assert usage["requests"] == {"this_month": None, "since": None}
    assert usage["connections"] == {
        "peak_today": None,
        "limit": None,
        "busy_last_7_days": None,
        "busy_since": None,
        "status": None,
        "bigger_plan_gives_more": False,
    }
    assert usage["activity"]["active_now"] is None
    assert usage["activity"]["last_day"] is None


def test_a_business_is_no_demo(hub_a):
    assert usage_of(hub_a)["demo"] is False


# ── The bell ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def bell_of(hub, role="hub_owner", language="en"):
    ctx = admin_of(hub, role=role, username=f"bell-{role}")
    op = get("base.bell.counters")
    with use_hub(hub), override(language):
        answer = op(OperationContext(scope=ctx.scope, actor=ctx.actor, permissions=ctx.permissions, language=language), op.input())
    return [row for row in answer.model_dump(mode="json")["counters"] if row["key"] == "base.plan_limits"]


def test_without_a_notice_the_bell_has_no_row(hub_a):
    on_plan(hub_a, STARTER, max_storage_bytes=100)
    measured(hub_a, s3=79)
    did(hub_a, TODAY, peak=3, busy=0)

    assert bell_of(hub_a) == []


def test_each_notice_adds_one_and_the_row_opens_resources(hub_a):
    on_plan(hub_a, STARTER, max_storage_bytes=100)
    measured(hub_a, s3=80)

    assert bell_of(hub_a) == [
        {
            "key": "base.plan_limits",
            "app": "base",
            "count": 1,
            "route": "/system#resources",
            "label": "Plan limits",
            "icon": "ion:speedometer-outline",
        }
    ]

    did(hub_a, TODAY, busy=1)
    assert bell_of(hub_a)[0]["count"] == 2


def test_full_files_alone_are_one_notice(hub_a):
    on_plan(hub_a, STARTER, max_storage_bytes=100)
    measured(hub_a, s3=100)

    assert bell_of(hub_a)[0]["count"] == 1


def test_the_connections_alone_are_one_notice_also_on_a_plan_that_cannot_grow(hub_a):
    on_plan(hub_a, PRO)
    did(hub_a, TODAY, busy=3)

    assert bell_of(hub_a)[0]["count"] == 1


def test_the_row_is_said_in_the_person_s_language(hub_a):
    on_plan(hub_a, STARTER, max_storage_bytes=100)
    measured(hub_a, s3=100)

    assert bell_of(hub_a, language="es")[0]["label"] == "Límites del plan"


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_only_who_runs_the_business_gets_the_row(hub_a, role):
    on_plan(hub_a, STARTER, max_storage_bytes=100)
    measured(hub_a, s3=100)

    assert bell_of(hub_a, role=role) == []


def test_without_the_plan_or_in_a_demo_there_is_no_row(hub_a):
    measured(hub_a, s3=100)
    did(hub_a, TODAY, busy=3)
    assert bell_of(hub_a) == []

    on_plan(hub_a, STARTER, max_storage_bytes=100)
    Hub.objects.filter(pk=hub_a.pk).update(is_demo=True)
    assert bell_of(hub_a) == []


def test_the_bell_of_a_hub_hears_only_its_own_notices(hub_a, hub_b):
    on_plan(hub_a, STARTER, max_storage_bytes=100)
    on_plan(hub_b, STARTER, max_storage_bytes=100)
    measured(hub_b, s3=100)
    did(hub_b, TODAY, busy=3)

    assert bell_of(hub_a) == []
    assert bell_of(hub_b)[0]["count"] == 2


# ── The assistant ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_who_runs_the_business_can_ask_the_assistant_the_same():
    op = get("base.plan.usage")

    assert isinstance(op.ai, AI)
    assert "¿cuánto espacio me queda?" in op.ai.asks["es"]
    assert "¿cuántas peticiones llevamos este mes?" in op.ai.asks["es"]
    assert "how much space do I have left?" in op.ai.asks["en"]
    assert "how many requests have we had this month?" in op.ai.asks["en"]


def test_the_assistant_is_no_longer_told_the_connections_are_not_measured():
    from live.assistant import description

    assert "not measured" not in description(get("base.system.status"))
