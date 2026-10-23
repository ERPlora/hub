"""Sales on the Home (PLAN-HUB round 2026-10-21): base's ``base.widget.list`` offers Sales' four panels to whoever
may read them, each followed live and answered by its own query as that person (today's money and tickets after a
charge, the seven days, the last eight sales newest first), and a charge in hub B re-runs them on B's channel only.

base and sale run for real: the panels come from SaleConfig through base's own query, never a stand-in module.
"""

import json

import psycopg
import pytest
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for

from apps.sale.tests.conftest import A, B, ctx_for, run
from base.schemas import WidgetListIn

PANELS = ["sale.today", "sale.tickets_today", "sale.last_7_days", "sale.recent_activity"]
WAIT = 1.0
QUIET = 0.3


def sale_panels(ctx) -> dict[str, dict]:
    """The Sales panels of the Home's board for the person of ``ctx``, in their order, as the SPA receives them."""
    widgets = get("base.widget.list")(ctx, WidgetListIn()).model_dump(mode="json")["widgets"]
    return {widget["key"]: widget for widget in widgets if widget["app"] == "sale"}


def answer(panel: dict, ctx) -> dict:
    """What a panel reads: its operation with its params, as the person (what the SPA's useLive asks)."""
    op = get(panel["operation"])
    return op(ctx, op.input.model_validate(panel["params"])).model_dump(mode="json")


def charge(key: str, lines=({"product": "COF"},), **more):
    return run("sale.sale.complete", {"idempotency_key": key, "lines": list(lines), **more})


@pytest.fixture
def catalog(product):
    product("Coffee", "COF", 121, "product.generic")
    product("Steak", "STK", 1800, "restaurant.food")


@pytest.mark.django_db
def test_a_manager_is_offered_the_four_panels_followed_live():
    panels = sale_panels(ctx_for("hub_manager"))
    assert list(panels) == PANELS
    assert {key: (panel["operation"], panel["default"], panel["live"], panel["kind"]) for key, panel in panels.items()} == {
        "sale.today": ("sale.sale.today", True, True, "kpi"),
        "sale.tickets_today": ("sale.sale.today", True, True, "kpi"),
        "sale.last_7_days": ("sale.sale.last_7_days", False, True, "chart"),
        "sale.recent_activity": ("sale.sale.list", False, True, "timeline"),
    }
    # The picker groups them under the app's own name.
    assert {panel["category"] for panel in panels.values()} == {"Sales & POS"}


@pytest.mark.django_db
def test_an_employee_without_the_reports_permission_only_gets_the_recent_activity():
    """The figures are the reports' (``sale.view_reports``, the manager's); the employee reads the sales."""
    employee = ctx_for("hub_employee")
    assert employee.has("sale.view_sale") and not employee.has("sale.view_reports")
    assert list(sale_panels(employee)) == ["sale.recent_activity"]


@pytest.mark.django_db
def test_each_panel_paints_its_figure_from_its_own_query(catalog, customer):
    ana = customer("Ana López")
    first = charge("home-key-0001", customer_id=str(ana.id))
    second = charge("home-key-0002", lines=[{"product": "STK"}], payments=[{"method": "card"}])
    manager = ctx_for("hub_manager")
    panels = sale_panels(manager)

    today = answer(panels["sale.today"], manager)
    assert today[panels["sale.today"]["map"]["value"]] == 1921
    assert today[panels["sale.tickets_today"]["map"]["value"]] == 2

    chart = panels["sale.last_7_days"]["map"]
    days = answer(panels["sale.last_7_days"], manager)["rows"]
    assert len(days) == 7 and all(day[chart["label"]] for day in days)
    assert [day[chart["value"]] for day in days] == [0, 0, 0, 0, 0, 0, 1921]

    timeline = panels["sale.recent_activity"]["map"]
    rows = answer(panels["sale.recent_activity"], manager)["rows"]
    assert [(row[timeline["title"]], row[timeline["description"]]) for row in rows] == [
        (second.number, ""),
        (first.number, "Ana López"),
    ]
    assert all(row[timeline["time"]] for row in rows)


@pytest.mark.django_db
def test_the_recent_activity_is_the_last_eight_sales(catalog):
    sales = [charge(f"home-last-{n:04d}") for n in range(9)]
    employee = ctx_for("hub_employee")
    panel = sale_panels(employee)["sale.recent_activity"]
    rows = answer(panel, employee)["rows"]
    assert [row["id"] for row in rows] == [str(sale.id) for sale in reversed(sales[1:])]


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


# Transactional: the notice leaves after a real COMMIT. A flush between transactional tests empties Taxes'
# factory catalogue (seeded by its migrations): `factory_data` plants it again.
@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("factory_data")
def test_a_charge_in_hub_b_re_runs_the_panels_of_b_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    in_b = ctx_for(scope=B)
    order = run(
        "sale.order.open",
        {"label": "Table 4", "open_lines": [{"unit_price": 250, "tax_category_key": "product.generic"}]},
        in_b,
    )
    run(
        "sale.sale.complete",
        {"idempotency_key": "home-b-0001", "order_id": str(order.id), "payments": [{"method": "cash"}]},
        in_b,
    )
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    panels = sale_panels(ctx_for("hub_manager", scope=B))
    assert list(panels) == PANELS
    assert {panel["operation"] for panel in panels.values()} <= live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
