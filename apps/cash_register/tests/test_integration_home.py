"""Cash register on the Home (PLAN-HUB round 2026-10-21; FIX-CASH_REGISTER-SETUP-HOOKS): base's own queries bring
«Your cash drawer» to whoever manages the drawer's settings (pending on the factory values, done once the business
saved them, even as they came; CASH_REGISTER-F01) and the drawer's two panels (CASH_REGISTER-F12): the open session's
expected cash, only to whoever may see it on a blind count (F07, gh:cash_register#24 and #84), and the differences of
the last eight closed sessions, each answered by the drawer's own query as that person. A save in hub B re-runs B's
checklist and panels and tells A nothing.

base, sale and cash_register run for real: the step and the panels come from CashRegisterConfig through base's own
queries, and the figures from sessions opened, charged and closed through their own operations.
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

from apps.cash_register.tests.conftest import A, B, charge, ctx_for, open_session, run
from base.schemas import SetupStatusIn, WidgetListIn

STEP = "cash_register.drawer"
EXPECTED = "cash_register.current_session"
RECENT = "cash_register.recent_sessions"
WAIT = 1.0
QUIET = 0.3


def steps(ctx) -> dict[str, dict]:
    document = get("base.setup.status")(ctx, SetupStatusIn()).model_dump(mode="json")
    return {item["key"]: item for item in document["items"] if item["app"] == "cash_register"}


def panels(ctx) -> dict[str, dict]:
    widgets = get("base.widget.list")(ctx, WidgetListIn()).model_dump(mode="json")["widgets"]
    return {widget["key"]: widget for widget in widgets if widget["app"] == "cash_register"}


def answer(panel: dict, ctx) -> dict:
    """What a panel reads: its operation with its params, as the person (what the SPA's useLive asks)."""
    op = get(panel["operation"])
    return op(ctx, op.input.model_validate(panel["params"])).model_dump(mode="json")


def figure(panel: dict, ctx):
    """The value a KPI paints: its field of the first row (base's `widgetView`); ``None`` = «No data»."""
    rows = answer(panel, ctx)["rows"]
    return rows[0][panel["map"]["value"]] if rows else None


def bars(panel: dict, ctx) -> list[tuple[str, int | None]]:
    return [(row[panel["map"]["label"]], row[panel["map"]["value"]]) for row in answer(panel, ctx)["rows"]]


def state(ctx=None) -> str:
    return steps(ctx or ctx_for())[STEP]["state"]


def close(counted: int | None, ctx=None):
    return run("cash_register.session.close", {"closing_balance": counted}, ctx)


@pytest.mark.django_db
def test_a_drawer_on_its_factory_values_has_your_cash_drawer_pending_and_it_leads_to_its_settings():
    item = steps(ctx_for())[STEP]
    assert {key: item[key] for key in ("state", "level", "required", "actionable", "route", "order", "icon")} == {
        "state": "pending",
        "level": "recommended",
        "required": False,
        "actionable": True,
        "route": "/cash_register/settings",
        "order": 90,
        "icon": "ion:cash-outline",
    }
    assert (item["title"], item["description"]) == (
        "Your cash drawer",
        "Decide how the till opens and closes: the opening float, the closing count and the POS screen that stays "
        "locked until the drawer is open.",
    )


@pytest.mark.django_db
def test_saving_the_settings_ticks_it_even_with_the_factory_values():
    run("cash_register.settings.update", {})
    assert state() == "done"


@pytest.mark.django_db
def test_saving_a_change_ticks_it_and_it_stays_done():
    run("cash_register.settings.update", {"require_blind_count": True})
    assert state() == "done"
    run("cash_register.settings.update", {"require_blind_count": False})
    assert state() == "done"  # a decision taken stays taken: back to the factory values is still the business's


@pytest.mark.django_db
def test_opening_a_session_on_the_factory_values_is_no_decision():
    open_session()
    assert state() == "pending"


@pytest.mark.django_db
def test_whoever_may_not_manage_the_settings_is_not_told_about_the_step():
    manager = ctx_for("hub_manager")
    assert manager.has("cash_register.view_session") and not manager.has("cash_register.manage_settings")
    assert STEP not in steps(manager)
    assert STEP not in steps(ctx_for("hub_employee"))


@pytest.mark.django_db
def test_a_manager_is_offered_both_panels_followed_live():
    offered = panels(ctx_for("hub_manager"))
    assert list(offered) == [EXPECTED, RECENT]
    assert {key: (panel["operation"], panel["default"], panel["live"], panel["kind"]) for key, panel in offered.items()} == {
        EXPECTED: ("cash_register.session.list", True, True, "kpi"),
        RECENT: ("cash_register.session.list", False, True, "bar-list"),
    }
    # The picker groups them under the app's own name (gh:cash_register#123).
    assert {panel["category"] for panel in offered.values()} == {"Cash register"}


@pytest.mark.django_db
def test_an_employee_never_gets_the_expected_cash_panel_but_reads_the_discrepancies():
    """F07: the employee counts blind, so the Home never shows them what the drawer should hold
    (gh:cash_register#24: the old dashboard's widget leaked it); the differences of closed sessions are theirs to see,
    as in Cash register."""
    employee = ctx_for("hub_employee")
    assert not employee.has("cash_register.view_expected_totals")
    assert list(panels(employee)) == [RECENT]


@pytest.mark.django_db
def test_on_a_blind_count_the_expected_panels_query_tells_the_employee_nothing():
    """Hiding a panel is not the gate: the live stream runs the panel's own query as the person, so on a blind count
    the query itself hides the open session's expected from whoever may not see it (gh:cash_register#84)."""
    run("cash_register.settings.update", {"require_blind_count": True})
    open_session(10000)
    panel = panels(ctx_for("hub_manager"))[EXPECTED]
    assert figure(panel, ctx_for("hub_manager")) == 10000
    assert figure(panel, ctx_for("hub_employee")) is None


@pytest.mark.django_db
def test_whoever_may_not_read_the_sessions_gets_no_panel_and_is_refused_the_figures_by_hand():
    outsider = OperationContext(scope=A, actor="tester", permissions=frozenset({"base.view_home"}), language="en")
    assert panels(outsider) == {}
    offered = panels(ctx_for())
    assert list(offered) == [EXPECTED, RECENT]  # a loop over nothing would refuse nothing
    for panel in offered.values():
        with pytest.raises(PermissionDenied):
            answer(panel, outsider)


@pytest.mark.django_db
def test_the_expected_panel_paints_the_open_sessions_expected_cash_and_follows_it(coffee):
    panel = panels(ctx_for())[EXPECTED]
    assert figure(panel, ctx_for()) is None  # no session open: «No data», never a made-up 0
    open_session(10000)
    assert figure(panel, ctx_for()) == 10000
    charge()  # a 1.50 € coffee paid in cash
    assert figure(panel, ctx_for()) == 10150
    run("cash_register.movement.add", {"type": "out", "amount": 500, "description": "Supplier"})
    assert figure(panel, ctx_for()) == 9650
    close(9650)
    assert figure(panel, ctx_for()) is None


@pytest.mark.django_db
def test_the_discrepancies_panel_shows_the_last_eight_closed_the_latest_first():
    differences = [-40, 550, 0, -1200, 75, -5, 300, -999, 20]
    numbers = []
    for difference in differences:
        session = open_session(10000)
        numbers.append(session.number)
        close(10000 + difference)
    open_session(10000)  # the open one has no difference yet: never a bar
    panel = panels(ctx_for())[RECENT]
    assert bars(panel, ctx_for()) == list(zip(numbers[::-1], differences[::-1], strict=True))[:8]


@pytest.mark.django_db
def test_a_spanish_request_reads_the_step_and_the_panels_in_spanish(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    setup = client.get("/api/home/setup", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert setup.status_code == 200
    (item,) = [item for item in setup.json()["items"] if item["key"] == STEP]
    assert (item["title"], item["description"]) == (
        "Tu caja",
        "Decide cómo se abre y se cierra la caja: el fondo inicial, el arqueo de cierre y la pantalla del TPV que "
        "queda bloqueada hasta abrirla.",
    )
    widgets = client.get("/api/home/widgets", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert widgets.status_code == 200
    ours = [widget for widget in widgets.json()["widgets"] if widget["app"] == "cash_register"]
    assert [(widget["title"], widget["category"]) for widget in ours] == [
        ("Caja (sesión actual)", "Caja"),
        ("Descuadres recientes", "Caja"),
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
def test_a_save_and_a_session_in_hub_b_re_run_the_step_and_the_panels_of_b_and_tell_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    run("cash_register.settings.update", {}, ctx_for(scope=B))
    assert "base.setup.status" in affected(on_b)
    assert steps(ctx_for(scope=B))[STEP]["state"] == "done"
    run("cash_register.session.open", {"opening_balance": 10000}, ctx_for(scope=B))
    assert {panel["operation"] for panel in panels(ctx_for(scope=B)).values()} <= affected(on_b)
    assert received(on_a, timeout=QUIET) == []
