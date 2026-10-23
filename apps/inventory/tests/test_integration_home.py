"""Inventory on the Home (PLAN-HUB round 2026-10-21; FIX-INVENTORY-SETUP-HOOKS): base's own queries bring «Your
catalog» to whoever may add products (pending with no active product, done with one, physical or a service, and
pending again when every product is turned off or deleted; INVENTORY-F28) and Inventory's four panels to whoever reads
the products, each answered by the Panel's own queries as that person (INVENTORY-F17); a product added in hub B re-runs
B's checklist and panels and tells A nothing.

base and inventory run for real: the step and the panels come from InventoryConfig through base's own queries.
"""

import json

import psycopg
import pytest
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for

from apps.inventory.schemas import ProductIn, ProductPatchIn, ProductRefIn
from apps.inventory.tests.conftest import A, B, ctx_for, ctx_with
from apps.tax.models import TaxCategory
from base.schemas import SetupStatusIn, WidgetListIn

STEP = "inventory.catalog"
PANELS = [
    "inventory.low_stock_count",
    "inventory.value",
    "inventory.in_stock",
    "inventory.low_stock_products",
]
TAX = "test.general"
WAIT = 1.0
QUIET = 0.3


@pytest.fixture
def general(db):
    return TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})[0]


def steps(ctx) -> dict[str, dict]:
    document = get("base.setup.status")(ctx, SetupStatusIn()).model_dump(mode="json")
    return {item["key"]: item for item in document["items"] if item["app"] == "inventory"}


def panels(ctx) -> dict[str, dict]:
    widgets = get("base.widget.list")(ctx, WidgetListIn()).model_dump(mode="json")["widgets"]
    return {widget["key"]: widget for widget in widgets if widget["app"] == "inventory"}


def answer(panel: dict, ctx) -> dict:
    """What a panel reads: its operation with its params, as the person (what the SPA's useLive asks)."""
    op = get(panel["operation"])
    return op(ctx, op.input.model_validate(panel["params"])).model_dump(mode="json")


def create(name: str, sku: str, scope=A, **fields):
    data = ProductIn(name=name, sku=sku, price=100, tax_category_key=TAX, **fields)
    return get("inventory.product.create")(ctx_for(scope=scope), data)


def turn_off(product) -> None:
    get("inventory.product.update")(ctx_for(), ProductPatchIn(id=product.id, is_active=False))


def state(ctx=None) -> str:
    return steps(ctx or ctx_for())[STEP]["state"]


@pytest.mark.django_db
def test_a_hub_without_products_has_your_catalog_pending_and_it_leads_to_the_products(general):
    item = steps(ctx_for("hub_manager"))[STEP]
    assert {key: item[key] for key in ("state", "level", "required", "actionable", "route", "order", "icon")} == {
        "state": "pending",
        "level": "functional",
        "required": True,
        "actionable": True,
        "route": "/inventory/products",
        "order": 30,
        "icon": "ion:cube-outline",
    }
    assert (item["title"], item["description"]) == (
        "Your catalog",
        "Add at least one product so there is something to sell.",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("product_type", ["physical", "service"])
def test_one_active_product_physical_or_a_service_ticks_it(general, product_type):
    create("Haircut" if product_type == "service" else "Coffee", "ONE", product_type=product_type)
    assert state() == "done"


@pytest.mark.django_db
def test_turning_off_or_deleting_every_product_sends_it_back_to_pending(general):
    coffee = create("Coffee", "COF")
    tea = create("Tea", "TEA")
    turn_off(coffee)
    assert state() == "done"  # one active product is still something to sell
    turn_off(tea)
    assert state() == "pending"
    get("inventory.product.update")(ctx_for(), ProductPatchIn(id=tea.id, is_active=True))
    assert state() == "done"
    get("inventory.product.delete")(ctx_for(), ProductRefIn(id=tea.id))
    assert state() == "pending"


@pytest.mark.django_db
def test_whoever_may_not_add_products_is_not_told_about_the_step(general):
    employee = ctx_for("hub_employee")
    assert employee.has("inventory.view_product") and not employee.has("inventory.add_product")
    assert STEP not in steps(employee)


@pytest.mark.django_db
def test_a_manager_is_offered_the_four_panels_followed_live(general):
    offered = panels(ctx_for("hub_manager"))
    assert list(offered) == PANELS
    assert {key: (panel["operation"], panel["default"], panel["live"], panel["kind"]) for key, panel in offered.items()} == {
        "inventory.low_stock_count": ("inventory.stock.get_summary", True, True, "kpi"),
        "inventory.value": ("inventory.stock.get_summary", True, True, "kpi"),
        "inventory.in_stock": ("inventory.stock.get_summary", False, True, "stat"),
        "inventory.low_stock_products": ("inventory.product.list_low_stock", True, True, "bar-list"),
    }
    # The picker groups them under the app's own name (gh:inventory#126).
    assert {panel["category"] for panel in offered.values()} == {"Inventory"}


@pytest.mark.django_db
def test_an_employee_reads_the_panels_as_the_inventory_panel(general):
    # INVENTORY-F17's actors include the employee: the Home shows them what Inventory → Panel already shows them.
    assert list(panels(ctx_for("hub_employee"))) == PANELS


@pytest.mark.django_db
def test_whoever_may_not_read_the_products_gets_no_panel_and_is_refused_the_figures_by_hand(general):
    """Hiding a panel is not the gate: the live stream runs the panel's own query as the person, so the queries
    refuse whoever may not read the products."""
    outsider = ctx_with("base.view_home", "inventory.view_category")
    assert panels(outsider) == {}
    offered = panels(ctx_for())
    assert list(offered) == PANELS  # a loop over nothing would refuse nothing
    for panel in offered.values():
        with pytest.raises(PermissionDenied):
            answer(panel, outsider)


@pytest.mark.django_db
def test_each_panel_paints_its_figure_from_its_own_query(general):
    # Coffee: 3 left at cost 1.50 (450 cents of stock), under its threshold of 5. Milk: 1.5 litres at 0.80, under
    # 2. Beans: 40 at 2.00, above 10. Haircut: a service, no stock. Old: turned off, never counted.
    create("Coffee", "COF", cost=150, initial_stock="3", low_stock_threshold="5", track_stock=True)
    create("Milk", "MLK", cost=80, initial_stock="1.5", low_stock_threshold="2", unit="l", track_stock=True)
    create("Beans", "BNS", cost=200, initial_stock="40", low_stock_threshold="10", track_stock=True)
    create("Haircut", "CUT", product_type="service")
    old = create("Old", "OLD", cost=999, initial_stock="1", low_stock_threshold="5", track_stock=True)
    turn_off(old)
    manager = ctx_for("hub_manager")
    offered = panels(manager)

    summary = answer(offered["inventory.value"], manager)
    figure = {key: summary[offered[key]["map"]["value"]] for key in PANELS[:3]}
    assert figure == {
        "inventory.low_stock_count": 2,
        "inventory.value": 450 + 120 + 8000,
        "inventory.in_stock": 3,
    }

    bars = offered["inventory.low_stock_products"]
    rows = answer(bars, manager)["rows"]
    assert [(row[bars["map"]["label"]], row[bars["map"]["value"]]) for row in rows] == [
        ("Milk", "1.500"),
        ("Coffee", "3.000"),
    ]


@pytest.mark.django_db
def test_the_lowest_stock_panel_shows_five_the_one_with_less_first(general):
    for n in range(7):
        create(f"Item {n}", f"IT{n}", initial_stock=str(n), low_stock_threshold="10", track_stock=True)
    bars = panels(ctx_for())["inventory.low_stock_products"]
    rows = answer(bars, ctx_for())["rows"]
    assert [row["name"] for row in rows] == ["Item 0", "Item 1", "Item 2", "Item 3", "Item 4"]


@pytest.mark.django_db
def test_a_spanish_request_reads_the_step_and_the_panels_in_spanish(general, client, make_user):
    """gh:hub#868: the old checklist said «Your catalog» in English although the module carried its Spanish."""
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    setup = client.get("/api/home/setup", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert setup.status_code == 200
    (item,) = [item for item in setup.json()["items"] if item["key"] == STEP]
    assert (item["title"], item["description"]) == (
        "Tu catálogo",
        "Añade al menos un producto para que haya algo que vender.",
    )
    widgets = client.get("/api/home/widgets", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert widgets.status_code == 200
    ours = [widget for widget in widgets.json()["widgets"] if widget["app"] == "inventory"]
    assert [(widget["title"], widget["category"]) for widget in ours] == [
        ("Productos con stock bajo", "Inventario"),
        ("Valor de existencias (a coste)", "Inventario"),
        ("Productos en stock", "Inventario"),
        ("Productos con menos stock", "Inventario"),
    ]


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


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_a_product_added_in_hub_b_re_runs_the_step_and_the_panels_of_b_and_tells_a_nothing(listen):
    TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})
    on_a, on_b = listen(A), listen(B)
    create("Coffee", "COF", scope=B)
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    affected = live_registry.affected(events)
    assert "base.setup.status" in affected
    assert {panel["operation"] for panel in panels(ctx_for(scope=B)).values()} <= affected
    assert steps(ctx_for(scope=B))[STEP]["state"] == "done"
    assert received(on_a, timeout=QUIET) == []
