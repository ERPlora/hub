"""Time clock on the Home (PLAN-HUB round 2026-10-21; FIX-ATTENDANCE-SETUP-HOOKS): base's own query brings the old
module's one panel, «Clocked in now» (ATTENDANCE-F11), answered by attendance's own count as that person, only to
whoever sees the whole team, never to an employee. It counts what «Clocked in now» lists in Records: an open day (on a
break too), never a closed one, a forgotten one, one waiting for review or a terminated person's. A clocking in hub B
re-runs B's panel and tells A nothing.

base, staff and attendance run for real: the panel comes from AttendanceConfig through base's own query, and the days
are clocked through attendance's own operations.
"""

import json

import psycopg
import pytest
from django.db import connections
from live.context import OperationContext
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from apps.attendance.models import Record
from apps.staff.models import Member
from base.schemas import WidgetListIn

from .conftest import A, B, ctx_for, make_member, run

CLOCKED_IN_NOW = "attendance.clocked_in_now"
WAIT = 1.0
QUIET = 0.3


def panels(ctx) -> dict[str, dict]:
    widgets = get("base.widget.list")(ctx, WidgetListIn()).model_dump(mode="json")["widgets"]
    return {widget["key"]: widget for widget in widgets if widget["app"] == "attendance"}


def answer(panel: dict, ctx) -> dict:
    """What a panel reads: its operation with its params, as the person (what the SPA's useLive asks)."""
    op = get(panel["operation"])
    return op(ctx, op.input.model_validate(panel["params"])).model_dump(mode="json")


def figure(panel: dict, ctx):
    """The value a KPI paints (base's `widgetView`): the field of its first row, the object itself when it has no
    `rows`; a field the query lacks fails here, never blank."""
    result = answer(panel, ctx)
    first = result["rows"][0] if isinstance(result.get("rows"), list) else result
    return first[panel["map"]["value"]]


def clock_in(member: Member, ctx=None):
    return run("attendance.record.clock_in", {"member_id": str(member.id)}, ctx)


@pytest.mark.django_db
def test_an_owner_is_offered_the_old_modules_one_panel_followed_live():
    offered = panels(ctx_for("hub_owner"))
    assert list(offered) == [CLOCKED_IN_NOW]
    panel = offered[CLOCKED_IN_NOW]
    assert (panel["operation"], panel["default"], panel["live"], panel["kind"], panel["size"]) == (
        "attendance.presence.count",
        True,
        True,
        "kpi",
        "sm",
    )
    assert (panel["title"], panel["icon"]) == ("Clocked in now", "ion:time-outline")
    # The picker groups it under the app's own name (never a literal category).
    assert panel["category"] == "Time clock"
    # It follows the events attendance emits today, never the old module's (`attendance.clocked_in`…).
    assert set(panel["refresh_on"]) == set(live_registry.subscribable["attendance.presence.count"])
    assert {"attendance.record.clocked_in", "attendance.record.clocked_out", "attendance.record.corrected"} <= set(
        panel["refresh_on"]
    )
    assert not {"attendance.clocked_in", "attendance.clocked_out"} & set(panel["refresh_on"])


@pytest.mark.django_db
def test_whoever_sees_the_whole_team_reads_it_and_an_employee_never():
    for name in ("hub_owner", "hub_admin", "hub_manager"):
        assert list(panels(ctx_for(name))) == [CLOCKED_IN_NOW], name
    assert panels(ctx_for("hub_employee")) == {}


@pytest.mark.django_db
def test_whoever_may_not_see_the_team_gets_no_panel_and_is_refused_the_figure_by_hand():
    clocker = OperationContext(
        scope=A, actor="tester", permissions=frozenset({"base.view_home", "attendance.clock"}), language="en"
    )
    assert panels(clocker) == {}
    panel = panels(ctx_for())[CLOCKED_IN_NOW]  # a refusal of nothing would refuse nothing
    with pytest.raises(PermissionDenied):
        answer(panel, clocker)


@pytest.mark.django_db
def test_it_counts_who_is_in_now_as_records_lists_them(clock):
    clock("2026-10-06T10:30")  # 12:30 in Madrid
    panel = panels(ctx_for())[CLOCKED_IN_NOW]
    assert figure(panel, ctx_for()) == 0  # nobody in: a real zero, not «No data»
    ana, bea = make_member("Ana"), make_member("Bea", "Ruiz")
    carlos, dani = make_member("Carlos", "Gil"), make_member("Dani", "Paz")
    clock_in(ana)
    clock_in(bea)
    run("attendance.break.start", {"member_id": str(bea.id)})  # on a break is still in
    clock_in(carlos)
    run("attendance.record.clock_out", {"member_id": str(carlos.id)})  # gone home
    clock_in(dani)
    assert figure(panel, ctx_for()) == 3
    # A day waiting for review does not count: nobody knows whether that person is still in.
    Record.objects.filter(member=dani).update(status=Record.Status.NEEDS_REVIEW)
    assert figure(panel, ctx_for()) == 2
    # Nor does a terminated person's (their open day is closed by ATTENDANCE-F13 afterwards).
    Member.objects.filter(pk=ana.pk).update(status=Member.Status.TERMINATED)
    assert figure(panel, ctx_for()) == 1
    assert figure(panel, ctx_for()) == run("attendance.presence.list", {}, ctx_for()).total


@pytest.mark.django_db
def test_a_forgotten_day_stops_counting_before_the_review_marks_it(clock):
    clock("2026-10-06T07:00")
    ana, bea = make_member("Ana"), make_member("Bea", "Ruiz")
    clock_in(ana)
    clock("2026-10-06T12:00")
    clock_in(bea)
    panel = panels(ctx_for())[CLOCKED_IN_NOW]
    assert figure(panel, ctx_for()) == 2
    clock("2026-10-06T19:30")  # Ana's day is 12 h 30 min open (Settings: 12 h), still open in the table
    assert Record.objects.get(member=ana).status == Record.Status.OPEN
    assert figure(panel, ctx_for()) == 1


@pytest.mark.django_db
def test_a_spanish_request_reads_the_panel_in_spanish(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    widgets = client.get("/api/home/widgets", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert widgets.status_code == 200
    ours = [widget for widget in widgets.json()["widgets"] if widget["app"] == "attendance"]
    assert [(widget["title"], widget["category"]) for widget in ours] == [("Fichados ahora", "Control horario")]


@pytest.fixture
def listen(django_db_setup):
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    sessions = []

    def open_listener(scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_listener
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


def affected(session) -> set[str]:
    return live_registry.affected({event for _, payload in received(session) for event in payload["events"]})


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_clocking_in_and_out_in_hub_b_re_runs_the_panel_of_b_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    in_b = ctx_for(scope=B)
    ana = make_member("Ana")
    panel = panels(in_b)[CLOCKED_IN_NOW]
    clock_in(ana, in_b)
    assert panel["operation"] in affected(on_b)
    assert figure(panel, in_b) == 1
    run("attendance.record.clock_out", {"member_id": str(ana.id)}, in_b)
    assert panel["operation"] in affected(on_b)
    assert figure(panel, in_b) == 0
    assert received(on_a, timeout=QUIET) == []
