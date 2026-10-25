"""Staff on the Home (PLAN-HUB round 2026-10-21; FIX-STAFF-SETUP-HOOKS): base's own query brings the old module's five
panels — the head count, who is away today, the requests waiting, today's time off and the people by role
(STAFF-F20, STAFF-F23) — each answered by Staff's own query as that person, only to whoever may read it: the team's
figures to whoever sees the team, the time off to whoever sees the time off. A change in hub B re-runs B's panels and
tells A nothing.

base and staff run for real: the panels come from StaffConfig through base's own query, and the figures from records,
roles and time off written through Staff's own operations.
"""

import datetime as dt
import json

import psycopg
import pytest
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from apps.staff.tests.conftest import A, B, ctx_for
from base.schemas import WidgetListIn

HEADCOUNT = "staff.headcount"
ON_LEAVE = "staff.on_leave_today"
PENDING = "staff.pending_time_off"
AWAY = "staff.time_off_today"
BY_ROLE = "staff.by_role"
ALL = [HEADCOUNT, ON_LEAVE, PENDING, AWAY, BY_ROLE]
TEAM = [HEADCOUNT, BY_ROLE]
TIME_OFF = [ON_LEAVE, PENDING, AWAY]
WAIT = 1.0
QUIET = 0.3


def run(name: str, data: dict, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


def panels(ctx) -> dict[str, dict]:
    widgets = get("base.widget.list")(ctx, WidgetListIn()).model_dump(mode="json")["widgets"]
    return {widget["key"]: widget for widget in widgets if widget["app"] == "staff"}


def answer(panel: dict, ctx) -> dict:
    """What a panel reads: its operation with its params, as the person (what the SPA's useLive asks)."""
    op = get(panel["operation"])
    return op(ctx, op.input.model_validate(panel["params"])).model_dump(mode="json")


def rows(panel: dict, ctx) -> list[dict]:
    """The rows base's `widgetView` reads: a page's `rows`, or the object itself as its only row."""
    result = answer(panel, ctx)
    return result["rows"] if isinstance(result.get("rows"), list) else [result]


def figure(panel: dict, ctx):
    """The value a KPI or a stat paints: its field of the first row; a field the query lacks fails here, never blank."""
    return rows(panel, ctx)[0][panel["map"]["value"]]


def bars(panel: dict, ctx) -> list[tuple[str, int]]:
    return [(row[panel["map"]["label"]], row[panel["map"]["value"]]) for row in rows(panel, ctx)]


def entries(panel: dict, ctx) -> list[tuple[str, str]]:
    return [(row[panel["map"]["title"]], row[panel["map"]["description"]]) for row in rows(panel, ctx)]


def member(first_name: str, last_name: str = "López", ctx=None, **fields) -> str:
    return str(run("staff.member.create", {"first_name": first_name, "last_name": last_name, **fields}, ctx).id)


def role(name: str, ctx=None) -> str:
    return str(run("staff.role.create", {"name": name}, ctx).id)


def time_off(member_id: str, start: dt.date, end: dt.date | None = None, *, approved: bool = True, ctx=None, **fields):
    created = run(
        "staff.time_off.create",
        {"member_id": member_id, "start_date": start.isoformat(), "end_date": (end or start).isoformat(), **fields},
        ctx,
    )
    if approved:
        run("staff.time_off.approve", {"id": str(created.id)}, ctx)
    return created


def today() -> dt.date:
    return timezone.localdate()


@pytest.mark.django_db
def test_an_owner_is_offered_the_five_panels_followed_live():
    offered = panels(ctx_for("hub_owner"))
    assert list(offered) == ALL
    assert {key: (panel["operation"], panel["default"], panel["live"], panel["kind"]) for key, panel in offered.items()} == {
        HEADCOUNT: ("staff.member.stats", True, True, "kpi"),
        ON_LEAVE: ("staff.member.stats", True, True, "stat"),
        PENDING: ("staff.member.stats", False, True, "kpi"),
        AWAY: ("staff.time_off.today", True, True, "timeline"),
        BY_ROLE: ("staff.role.list", False, True, "bar-list"),
    }
    # The picker groups them under the app's own name (never a literal category).
    assert {panel["category"] for panel in offered.values()} == {"Staff"}


@pytest.mark.django_db
def test_every_role_of_the_business_reads_the_five_as_in_staff():
    """STAFF-F20 and STAFF-F23 are for everyone: the employee sees the team and who is away, so the Home tells them
    the same figures."""
    for name in ("hub_admin", "hub_manager", "hub_employee"):
        assert list(panels(ctx_for(name))) == ALL, name


@pytest.mark.django_db
def test_whoever_may_not_see_the_time_off_gets_only_the_teams_panels():
    """The list of who is away is refused by hand too; its two counts are figures of the team that Personal already
    shows to whoever sees it (STAFF-F23), without a name or a reason."""
    team_only = ctx_for(permissions={"base.view_home", "staff.view"})
    assert list(panels(team_only)) == TEAM
    with pytest.raises(PermissionDenied):
        answer(panels(ctx_for())[AWAY], team_only)


@pytest.mark.django_db
def test_whoever_may_not_see_the_team_gets_only_the_time_off_panels():
    time_off_only = ctx_for(permissions={"base.view_home", "staff.view_time_off"})
    assert list(panels(time_off_only)) == TIME_OFF
    offered = panels(ctx_for())
    for key in TEAM:
        with pytest.raises(PermissionDenied):
            answer(offered[key], time_off_only)


@pytest.mark.django_db
def test_whoever_may_read_nothing_of_staff_gets_no_panel_and_is_refused_the_figures_by_hand():
    outsider = OperationContext(scope=A, actor="tester", permissions=frozenset({"base.view_home"}), language="en")
    assert panels(outsider) == {}
    offered = panels(ctx_for())
    assert list(offered) == ALL  # a loop over nothing would refuse nothing
    for panel in offered.values():
        with pytest.raises(PermissionDenied):
            answer(panel, outsider)


@pytest.mark.django_db
def test_the_head_count_is_the_active_people_without_the_ones_who_left():
    panel = panels(ctx_for())[HEADCOUNT]
    assert figure(panel, ctx_for()) == 0  # an empty team: a real zero, not «No data»
    ana, bea, carla = member("Ana"), member("Bea"), member("Carla")
    member("Dora", status="inactive")
    member("Eva", status="on_leave")
    assert figure(panel, ctx_for()) == 3
    run("staff.member.deactivate", {"id": bea})
    run("staff.member.terminate", {"id": carla, "termination_date": today().isoformat()})
    assert figure(panel, ctx_for()) == 1
    assert ana


@pytest.mark.django_db
def test_on_leave_today_counts_distinct_people_with_approved_time_off_covering_the_business_day():
    panel = panels(ctx_for())[ON_LEAVE]
    assert figure(panel, ctx_for()) == 0
    ana, bea, carla, dora = member("Ana"), member("Bea"), member("Carla"), member("Dora")
    day = today()
    # Ana: two part days today, one person.
    time_off(ana, day, is_full_day=False, start_time="09:00", end_time="11:00")
    time_off(ana, day, is_full_day=False, start_time="15:00", end_time="17:00")
    time_off(bea, day - dt.timedelta(days=2), day + dt.timedelta(days=2))  # a week covering today
    time_off(carla, day, approved=False)  # asked, not approved
    time_off(dora, day - dt.timedelta(days=1))  # yesterday only
    assert figure(panel, ctx_for()) == 2


@pytest.mark.django_db
def test_pending_time_off_counts_the_requests_waiting_for_an_answer():
    panel = panels(ctx_for())[PENDING]
    ana, bea = member("Ana"), member("Bea")
    day = today() + dt.timedelta(days=7)
    time_off(ana, day, approved=False)
    time_off(bea, day, approved=False)
    time_off(bea, day + dt.timedelta(days=7))  # approved
    assert figure(panel, ctx_for()) == 2
    rejected = time_off(ana, day + dt.timedelta(days=14), approved=False)
    run("staff.time_off.reject", {"id": str(rejected.id)})
    assert figure(panel, ctx_for()) == 2


@pytest.mark.django_db
def test_todays_time_off_lists_who_is_away_whole_days_first_then_by_name_with_the_type():
    panel = panels(ctx_for())[AWAY]
    assert rows(panel, ctx_for()) == []  # nobody away: «No data», never a made-up entry
    ana, bea, carla = member("Ana", "Ruiz"), member("Bea", "Sanz"), member("Carla", "Vidal")
    day = today()
    time_off(ana, day, leave_type="training", is_full_day=False, start_time="09:00", end_time="11:00")
    time_off(carla, day - dt.timedelta(days=1), day + dt.timedelta(days=1), leave_type="sick")
    time_off(bea, day)  # a vacation by default
    time_off(bea, day + dt.timedelta(days=1))  # tomorrow
    assert entries(panel, ctx_for()) == [
        ("Bea Sanz", "Vacation"),
        ("Carla Vidal", "Sick leave"),
        ("Ana Ruiz", "Training"),
    ]
    with translation.override("es"):
        assert [description for _, description in entries(panel, ctx_for())] == [
            "Vacaciones",
            "Baja por enfermedad",
            "Formación",
        ]


@pytest.mark.django_db
def test_staff_by_role_paints_the_active_people_of_each_role_the_biggest_first_ten_at_most():
    panel = panels(ctx_for())[BY_ROLE]
    assert rows(panel, ctx_for()) == []
    stylist, colourist, reception = role("Stylist"), role("Colourist"), role("Reception")
    for first_name in ("Ana", "Bea", "Carla"):
        member(first_name, role_id=colourist)
    member("Dora", role_id=stylist)
    member("Eva", role_id=stylist, status="inactive")  # only the active people count
    member("Fina", role_id=stylist, status="on_leave")
    assert bars(panel, ctx_for()) == [("Colourist", 3), ("Stylist", 1), ("Reception", 0)]
    for index in range(10):
        role(f"Role {index:02}")
    assert len(bars(panel, ctx_for())) == 10
    assert bars(panel, ctx_for())[:2] == [("Colourist", 3), ("Stylist", 1)]
    assert reception


@pytest.mark.django_db
def test_a_spanish_request_reads_the_panels_in_spanish(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    widgets = client.get("/api/home/widgets", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert widgets.status_code == 200
    ours = [widget for widget in widgets.json()["widgets"] if widget["app"] == "staff"]
    assert [(widget["title"], widget["category"]) for widget in ours] == [
        ("Plantilla activa", "Personal"),
        ("Ausentes hoy", "Personal"),
        ("Ausencias pendientes", "Personal"),
        ("Ausencias de hoy", "Personal"),
        ("Empleados por rol", "Personal"),
    ]


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
def test_a_record_a_role_and_an_approval_in_hub_b_re_run_the_panels_of_b_and_tell_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    in_b = ctx_for(scope=B)
    stylist = role("Stylist", in_b)
    assert panels(in_b)[BY_ROLE]["operation"] in affected(on_b)
    ana = member("Ana", ctx=in_b, role_id=stylist)
    assert {panels(in_b)[key]["operation"] for key in (HEADCOUNT, BY_ROLE)} <= affected(on_b)
    time_off(ana, today(), ctx=in_b)
    assert {panels(in_b)[key]["operation"] for key in TIME_OFF} <= affected(on_b)
    assert figure(panels(in_b)[ON_LEAVE], in_b) == 1
    assert received(on_a, timeout=QUIET) == []
