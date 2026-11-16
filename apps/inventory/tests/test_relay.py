"""Inventory hears Sales through the worker's outbox relay, end to end (INVENTORY-F18, F21, F22, F23, F24).

The real Sales operations charge, void and refund (with the real Menus app for a menu); one tick of the
worker's real loop (``base.worker.run``) hands each event to Inventory, whose reaction moves the stock as the
system, once: a second tick changes nothing. The threshold crossing is recorded by that reaction, in its own
transaction, so it exists exactly when its movement does; a crossing in hub B is heard in B only.
"""

import json
from decimal import Decimal

import psycopg
import pytest
from django.db import connections
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from apps.inventory import events
from apps.inventory.models import Product, SaleStock, StockMovement
from base.models import EventDelivery
from base.tenancy.context import use_hub

from .conftest import A, B, HUB_DB_COMMITTED

#: The worker's real loop releases a business's connections once it has served it: what the test writes is committed.
pytestmark = HUB_DB_COMMITTED

GENERIC = "product.generic"
FOOD = "restaurant.food"


def owner(scope: Scope = A) -> OperationContext:
    """An owner of ``scope``: every permission the apps declare."""
    permissions = frozenset(p for config in all_live_app_configs() for p in config.permissions)
    return OperationContext(scope=scope, actor="tester", permissions=permissions, language="en")


def run(name: str, data: dict, ctx: OperationContext | None = None):
    op = get(name)
    return op(ctx or owner(), op.input.model_validate(data))


def make(name: str, sku: str, stock: str = "10", scope: Scope = A, **fields) -> Product:
    created = run(
        "inventory.product.create",
        {"name": name, "sku": sku, "price": 500, "tax_category_key": GENERIC, "initial_stock": stock, **fields},
        system_context(scope),
    )
    return Product.objects.get(pk=created.id)


def charge(key: str, *lines: tuple[str, str], scope: Scope = A, **source):
    data = {"idempotency_key": key, "payments": [{"method": "card"}], **source}
    if lines:
        data["lines"] = [{"product": sku, "quantity": quantity} for sku, quantity in lines]
    return run("sale.sale.complete", data, owner(scope))


def stock(sku: str) -> Decimal:
    return Product.objects.get(sku=sku, is_deleted=False).stock


def ledger(sku: str, kind: str) -> list[tuple[Decimal, str]]:
    rows = StockMovement.objects.filter(product__sku=sku, movement_type=kind).order_by("created_at", "id")
    return [(row.qty, row.reference) for row in rows]


def delivery(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the newest ``name`` event's delivery to Inventory."""
    event = OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()
    row = EventDelivery.objects.get(event_id=event.id, app_label="inventory")
    return row.status, row.attempts


def crossings() -> list[tuple[str, str, str, str, str]]:
    """``(sku, crossing, before, after, movement)`` of every threshold crossing, oldest first."""
    rows = OutboxEvent.objects.filter(name=events.STOCK_THRESHOLD_CROSSED).order_by("created_at", "id")
    return [
        (p["sku"], p["crossing"], p["previous_quantity"], p["current_quantity"], p["movement_type"])
        for p in (row.payload for row in rows)
    ]


@pytest.fixture
def tick(worker_loop, factory_data):
    """One tick of the worker's real loop over every business in its own database, as Automations' tests run it, with
    the factory data a sale needs planted again in business A."""
    return worker_loop


@pytest.fixture
def menu(db):
    """«Menu of the day» of Menus: «Starters» (lentils), «Mains» (hake) and an optional «Dessert» (flan)."""
    for name, sku in (("Lentils", "LEN"), ("Hake", "HAK"), ("Flan", "FLA")):
        make(name, sku, tax_category_key=FOOD)
    setup = system_context(A)
    run("combo.combo.create", {"name": "Menu of the day", "price": 1350, "tax_category_key": FOOD}, setup)
    for group, sku, minimum in (("Starters", "LEN", 1), ("Mains", "HAK", 1), ("Dessert", "FLA", 0)):
        run("combo.group.create", {"combo": "Menu of the day", "name": group, "min_choices": minimum}, setup)
        run("combo.option.create", {"combo": "Menu of the day", "group": group, "product": sku}, setup)


def menus(quantity: str, *dishes: str) -> dict:
    return {
        "combo_lines": [
            {"combo": "Menu of the day", "choices": [{"product": sku} for sku in dishes], "quantity": quantity}
        ]
    }


# ── INVENTORY-F21: a paid sale lowers the stock ─────────────────────────────────────────────────────


def test_inventory_f21_a_paid_sale_lowers_each_line_once_with_the_sale_as_reference(tick):
    make("Shampoo", "SHA")
    make("Wax", "WAX", track_stock=False)
    sale = charge("inv-relay-f21-1", ("SHA", "2"), ("SHA", "1"), ("WAX", "4"))
    assert stock("SHA") == Decimal("10")  # nothing moves until the relay hands the sale over

    tick()

    assert delivery("sale.sale.completed") == ("delivered", 1)
    assert stock("SHA") == Decimal("7")
    # One movement per line of the ticket; an article without stock control moves nothing.
    assert ledger("SHA", "sale") == [(Decimal("-2"), str(sale.id)), (Decimal("-1"), str(sale.id))]
    assert (stock("WAX"), ledger("WAX", "sale")) == (Decimal("10"), [])
    tick()
    assert stock("SHA") == Decimal("7")
    assert StockMovement.objects.filter(movement_type="sale").count() == 2


def test_inventory_f21_without_selling_without_stock_an_article_that_does_not_reach_is_not_lowered(tick):
    make("Shampoo", "SHA", stock="1")
    charge("inv-relay-f21-2", ("SHA", "3"))

    tick()

    assert delivery("sale.sale.completed") == ("delivered", 1)
    assert (stock("SHA"), ledger("SHA", "sale"), crossings()) == (Decimal("1"), [], [])
    # The sale is noted as unmoved, so its void gives nothing back.
    assert SaleStock.objects.get().state == SaleStock.State.UNMOVED


# ── INVENTORY-F16: the ledger reads a sale by the number on its paper ──────────────────────────────

ISSUER = {
    "legal_name": "Peluquería Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}


def ledger_rows(search: str) -> list[tuple[str, str]]:
    page = run("inventory.movement.list", {"search": search})
    return [(row.movement_type, row.reference_label) for row in page.rows]


def test_inventory_f16_a_sale_and_its_void_read_and_are_found_by_its_ticket_number(tick):
    run("invoice.issuer.update", ISSUER)
    make("Shampoo", "SHA")
    sale = charge("inv-relay-f16-1", ("SHA", "2"))
    assert sale.invoice_number  # Invoicing numbered its ticket in the charge
    tick()
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    tick()

    assert ledger_rows(sale.invoice_number) == [("void", sale.invoice_number), ("sale", sale.invoice_number)]
    assert ledger_rows(sale.number) == ledger_rows(sale.invoice_number)


def test_inventory_f16_without_a_fiscal_document_a_sale_reads_as_its_own_number(tick):
    make("Shampoo", "SHA")
    sale = charge("inv-relay-f16-2", ("SHA", "1"))
    assert sale.invoice_number == ""  # no issuer yet: the ticket is pending
    tick()

    assert ledger_rows(sale.number) == [("sale", sale.number)]


# ── INVENTORY-F22: a menu lowers its dishes, never itself ───────────────────────────────────────────


def test_inventory_f22_three_menus_lower_three_of_each_dish_picked(tick, menu):
    sale = charge("inv-relay-f22-1", **menus("3", "LEN", "HAK"))

    tick()

    assert delivery("sale.sale.completed") == ("delivered", 1)
    assert (stock("LEN"), stock("HAK"), stock("FLA")) == (Decimal("7"), Decimal("7"), Decimal("10"))
    assert ledger("LEN", "sale") == [(Decimal("-3"), str(sale.id))]
    # The menu is no product of Inventory: no movement names it.
    assert StockMovement.objects.filter(movement_type="sale").count() == 2


# ── INVENTORY-F23: a voided sale gives back what it took, once ──────────────────────────────────────


def test_inventory_f23_a_void_restores_exactly_what_the_sale_took_once(tick, menu):
    make("Shampoo", "SHA", stock="1")
    sale = charge("inv-relay-f23-1", ("SHA", "1"), ("SHA", "5"), **menus("2", "LEN", "HAK"))
    tick()
    # The second line did not reach (5 over 0 left): it was never lowered, so it is never given back.
    assert (stock("SHA"), stock("LEN")) == (Decimal("0"), Decimal("8"))

    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    tick()

    assert delivery("sale.sale.voided") == ("delivered", 1)
    assert (stock("SHA"), stock("LEN"), stock("HAK")) == (Decimal("1"), Decimal("10"), Decimal("10"))
    assert ledger("SHA", "void") == [(Decimal("1"), str(sale.id))]
    tick()
    assert StockMovement.objects.filter(movement_type="void").count() == 3


# ── INVENTORY-F24: a refund puts its returned units back, once ──────────────────────────────────────


def refund(sale, quantity: str, reason: str):
    return run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": reason,
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 500 * int(quantity)}],
            "lines": [{"line_id": str(sale.lines[0].id), "quantity": quantity}],
        },
    )


def test_inventory_f24_a_refund_returns_its_units_once_and_never_more_than_the_sale_took(tick):
    make("Shampoo", "SHA")
    sale = charge("inv-relay-f24-1", ("SHA", "4"))
    tick()
    refund(sale, "2", "Two bottles back")

    tick()

    assert delivery("sale.sale.refunded") == ("delivered", 1)
    assert stock("SHA") == Decimal("8")
    movement = StockMovement.objects.get(movement_type="refund")
    assert (movement.qty, movement.reference, movement.reason, movement.actor) == (
        Decimal("2"),
        str(sale.id),
        "Two bottles back",
        "system",
    )
    tick()
    assert stock("SHA") == Decimal("8")

    # The rest comes back with a second refund; the ledger then says nothing is out.
    refund(sale, "2", "The other two")
    tick()
    assert stock("SHA") == Decimal("10")
    assert [qty for qty, _ in ledger("SHA", "refund")] == [Decimal("2"), Decimal("2")]


# ── INVENTORY-F18: the threshold crossing, said by the reaction that moved the stock ────────────────


def test_inventory_f18_a_sale_crosses_below_once_and_the_void_says_recovered(tick):
    make("Shampoo", "SHA", stock="7", low_stock_threshold="5")
    first = charge("inv-relay-f18-1", ("SHA", "3"))
    tick()
    assert crossings() == [("SHA", "below", "7.000", "4.000", "sale")]
    payload = OutboxEvent.objects.get(name=events.STOCK_THRESHOLD_CROSSED).payload
    assert (payload["name"], payload["low_stock_threshold"], payload["reference"]) == ("Shampoo", "5.000", str(first.id))

    # Still below: no second notice.
    charge("inv-relay-f18-2", ("SHA", "1"))
    tick()
    assert len(crossings()) == 1

    # The void lifts it over the threshold again: «recovered», which arms the next one.
    run("sale.sale.void", {"sale_id": str(first.id), "reason": "Wrong table"})
    tick()
    assert crossings()[1:] == [("SHA", "recovered", "3.000", "6.000", "void")]
    charge("inv-relay-f18-3", ("SHA", "2"))
    tick()
    assert crossings()[2:] == [("SHA", "below", "6.000", "4.000", "sale")]


def test_inventory_f18_the_same_article_loose_and_inside_a_menu_crosses_once_on_the_total(tick, menu):
    run("inventory.product.update", {"product": "LEN", "low_stock_threshold": "8"}, system_context(A))
    charge("inv-relay-f18-4", ("LEN", "1"), **menus("1", "LEN", "HAK"))

    tick()

    assert ledger("LEN", "sale")[0][0] + ledger("LEN", "sale")[1][0] == Decimal("-2")
    assert crossings() == [("LEN", "below", "10.000", "8.000", "sale")]


def test_inventory_f18_the_crossing_and_its_movement_are_written_together_or_not_at_all(tick, monkeypatch):
    make("Shampoo", "SHA", stock="6", low_stock_threshold="5")
    charge("inv-relay-f18-5", ("SHA", "2"))
    real_save = SaleStock.save

    def fail(self, *args, **kwargs):
        if self.state == SaleStock.State.MOVED:
            raise RuntimeError("the sale's note could not be saved")
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(SaleStock, "save", fail)
    tick()

    # The reaction failed after it moved the stock and recorded the crossing: all of it is undone, and the
    # delivery waits for its next attempt.
    assert delivery("sale.sale.completed") == ("pending", 1)
    assert (stock("SHA"), ledger("SHA", "sale"), crossings()) == (Decimal("6"), [], [])
    assert not OutboxEvent.objects.filter(name=events.STOCK_CHANGED, payload__movement_type="sale").exists()


# ── Two hubs: a crossing in B is heard in B only ────────────────────────────────────────────────────


@pytest.fixture
def listen():
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    sessions = []

    def open_session(scope: Scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 0.5) -> set[str]:
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_inventory_f18_a_crossing_in_hub_b_is_heard_in_b_only(tick, hub_b, factory_data_b, listen):
    with use_hub(hub_b):
        make("Shampoo", "SHA", stock="6", low_stock_threshold="5", scope=B)
        on_a, on_b = listen(A), listen(B)
        charge("inv-relay-f18-b", ("SHA", "2"), scope=B)
    heard(on_b)  # the charge's own notice

    tick()

    with use_hub(hub_b):
        assert crossings() == [("SHA", "below", "6.000", "4.000", "sale")]
        assert OutboxEvent.objects.get(name=events.STOCK_THRESHOLD_CROSSED).scope_key == B.key
    assert events.STOCK_CHANGED in heard(on_b)
    assert heard(on_a) == set()
