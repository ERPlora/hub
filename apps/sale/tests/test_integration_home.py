"""Sales on the Home: base's ``base.widget.list`` offers Sales' four panels to whoever may read them, each followed live
and answered by its own query as that person (today's money and tickets after a charge, the seven days, the last eight
sales newest first), and a charge in hub B re-runs them on B's channel only.

base and sale run for real: the panels come from SaleConfig through base's own query, never a stand-in module.
"""

import dataclasses
import json

import psycopg
import pytest
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for

from apps.sale.tests.conftest import HUB_DB, A, B, ctx_for, run
from base.schemas.home import WidgetListIn
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

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


@HUB_DB
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


@HUB_DB
def test_an_employee_is_offered_the_four_panels_too():
    """The figures open to whoever reads the sales: an employee's count her own sales (test_queries_figures)."""
    employee = ctx_for("hub_employee")
    assert not employee.has("base.view_business_totals")
    assert list(sale_panels(employee)) == PANELS


@HUB_DB
def test_whoever_does_not_read_the_sales_is_offered_none_and_refused_them_by_hand():
    """Hiding a panel is not the gate: the live stream runs the panel's own query as the person, so each query
    refuses whoever does not read the sales, even with the business totals."""
    outsider = dataclasses.replace(ctx_for("hub_employee"), permissions=frozenset({"base.view_home", "base.view_business_totals"}))
    assert sale_panels(outsider) == {}
    panels = sale_panels(ctx_for("hub_manager"))
    for key in PANELS:
        with pytest.raises(PermissionDenied):
            answer(panels[key], outsider)


@HUB_DB
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


@HUB_DB
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
# factory catalogue (seeded by its migrations): `factory_data` and `factory_data_b` plant it again.
@pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("factory_data", "factory_data_b")
def test_a_charge_in_hub_b_re_runs_the_panels_of_b_and_tells_a_nothing(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    in_b = ctx_for(scope=B)
    with use_hub(hub_b):
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
        panels = sale_panels(ctx_for("hub_manager", scope=B))
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert list(panels) == PANELS
    assert {panel["operation"] for panel in panels.values()} <= live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
