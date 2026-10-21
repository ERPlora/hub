"""Menus and the other apps through the worker's outbox relay, end to end (COMBO-F10, F11, F13).

The other app's real operation records its event in the outbox; one tick of the worker's real loop
(``base.worker.run`` → ``base.relay``) hands it to the reaction of each app that listens, as production runs it:
nothing is called by hand. A repeated delivery changes nothing, and what happens in hub B is heard in B only.

- COMBO-F10: Sales charges menus (``sale.sale.complete``) and Inventory lowers each dish picked, times the
  menus and the times it was picked, never the menu, and nothing for a service; a refund puts each dish back.
- COMBO-F11: Sales fires a check with a menu (``sale.order.fire``) and the kitchen gets each dish at its
  station under the menu's kitchen name, on the card and on paper; a menu short of a course never gets there.
- COMBO-F13: Inventory deletes a product (``inventory.product.delete``) and its choices leave every menu
  (``combo.option.drop_product``); until the tick they are marked «no longer in the catalogue» and never offered.
"""

import json
import threading
from decimal import Decimal

import psycopg
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.combo.models import ChoiceOption
from apps.inventory.models import Product, StockMovement
from apps.kitchen.models import Ticket
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import A, B, FOOD, ctx_for

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def run(name: str, data: dict, scope=A):
    """Run the operation ``name`` as an admin of ``scope``: Inventory's and Menus' own, with their permissions."""
    op = get(name)
    return op(ctx_for("hub_admin", scope=scope), op.input.model_validate(data))


def one_tick() -> None:
    """One tick of the worker's real loop."""
    stop = threading.Event()

    def wait(_seconds: float) -> bool:
        stop.set()
        return True

    now = timezone.now()
    assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0


@pytest.fixture
def tick(db, monkeypatch):
    """``one_tick`` without the SaaS (``register_apps``) and, inside the test's transaction, without releasing
    the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    return one_tick


def delivery_to(app: str, name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to ``app``."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    row = EventDelivery.objects.get(event_id=event.id, app_label=app)
    return row.status, row.attempts


def delivery_to_combo(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Menus."""
    return delivery_to("combo", name)


def product(name: str, sku: str, scope=A, *, price: int = 400, **more):
    """A product of Inventory, made by Inventory."""
    data = {"name": name, "sku": sku, "price": price, "tax_category_key": FOOD, **more}
    return run("inventory.product.create", data, scope)


def menu(name: str, *skus: str, scope=A):
    """A menu eaten in with a «Dessert» course offering ``skus``, made by Menus."""
    run("combo.combo.create", {"name": name, "price": 1350, "tax_category_key": FOOD}, scope)
    run("combo.group.create", {"combo": name, "name": "Dessert"}, scope)
    for sku in skus:
        run("combo.option.create", {"combo": name, "group": "Dessert", "product": sku}, scope)


def statuses(name: str, scope=A) -> list[tuple[str, str]]:
    """``(product name, status)`` of each choice of the menu ``name``, as its builder reads them."""
    detail = run("combo.combo.get", {"combo": name}, scope)
    return [(option.product_name, option.status) for group in detail.groups for option in group.options]


def dropped(product_id) -> list[dict]:
    """The ``combo.option.deleted`` notices that took a choice of ``product_id`` out of a menu."""
    return [
        event.payload
        for event in OutboxEvent.objects.filter(name="combo.option.deleted", payload__product_id=str(product_id))
        if event.payload.get("reason") == "product_deleted"
    ]


@pytest.fixture
def desserts(db):
    """Flan and cheesecake in Inventory, both on the menu of the day and on the kids' menu."""
    flan = product("Flan", "FLA")
    cake = product("Cheesecake", "CHC")
    menu("Menu of the day", "FLA", "CHC")
    menu("Kids' menu", "FLA", "CHC")
    return flan, cake


def test_combo_f13_a_product_deleted_in_inventory_leaves_every_menu_through_the_relay(tick, desserts):
    flan, cake = desserts

    run("inventory.product.delete", {"id": str(flan.id)})
    # Inventory's command only records its event: until the tick the choice stays, marked and never offered.
    assert statuses("Menu of the day") == [("Flan", "product_deleted"), ("Cheesecake", "offered")]
    sale = run("combo.combo.for_sale", {"search": "Menu of the day"})
    assert [o.product_name for g in sale.rows[0].groups for o in g.options] == ["Cheesecake"]

    tick()

    assert delivery_to_combo("inventory.product.deleted") == ("delivered", 1)
    assert statuses("Menu of the day") == [("Cheesecake", "offered")]
    assert statuses("Kids' menu") == [("Cheesecake", "offered")]
    assert not ChoiceOption.objects.filter(product_id=flan.id).exists()
    assert ChoiceOption.objects.filter(product_id=cake.id).count() == 2
    # One notice per choice that left, saying why: the builders open on either menu re-read it.
    assert len(dropped(flan.id)) == 2
    assert {payload["combo_id"] for payload in dropped(flan.id)} == {
        str(run("combo.combo.get", {"combo": name}).id) for name in ("Menu of the day", "Kids' menu")
    }


def test_combo_f13_a_second_tick_or_the_same_notice_handed_over_again_changes_nothing(tick, desserts):
    flan, cake = desserts
    run("inventory.product.delete", {"id": str(flan.id)})
    tick()
    notices = OutboxEvent.objects.filter(name="combo.option.deleted").count()

    tick()
    assert delivery_to_combo("inventory.product.deleted") == ("delivered", 1)

    # The same notice handed to Menus again, as if its delivery had been lost: the relay runs it once more.
    event = OutboxEvent.objects.filter(name="inventory.product.deleted").latest("id")
    EventDelivery.objects.filter(event_id=event.id, app_label="combo").update(
        status=EventDelivery.Status.PENDING, delivered_at=None, next_attempt_at=timezone.now()
    )
    tick()

    assert delivery_to_combo("inventory.product.deleted") == ("delivered", 2)
    assert OutboxEvent.objects.filter(name="combo.option.deleted").count() == notices
    assert statuses("Menu of the day") == [("Cheesecake", "offered")]
    assert ChoiceOption.objects.filter(product_id=cake.id).count() == 2


def test_combo_f13_a_product_on_no_menu_is_deleted_and_nothing_happens(tick, desserts):
    lonely = product("Brownie", "BRW")

    run("inventory.product.delete", {"id": str(lonely.id)})
    tick()

    assert delivery_to_combo("inventory.product.deleted") == ("delivered", 1)
    assert dropped(lonely.id) == []
    assert statuses("Menu of the day") == [("Flan", "offered"), ("Cheesecake", "offered")]


# ── COMBO-F10 and F11: a menu sold and fired, through Sales, Inventory and the kitchen ─────────────


def stock(sku: str) -> Decimal:
    return Product.objects.get(sku=sku, is_deleted=False).stock


@pytest.fixture
def till_menu(db):
    """«Menu of the day» (kitchen name «MENU»), 13,50 € eaten in: «Starters» (lentils or salad), «Mains» (hake,
    or steak +2,00 €), an optional «Coffee» course that takes the same coffee twice, and an optional «Service»
    of a service (the table service). Each product starts with 10 in stock. Returns the choices by SKU."""
    for name, sku, price in (
        ("Lentils", "LEN", 500),
        ("Salad", "SAL", 450),
        ("Hake", "HAK", 1400),
        ("Steak", "STK", 1800),
        ("Coffee", "COF", 150),
    ):
        product(name, sku, price=price, initial_stock="10")
    product("Table service", "TIP", price=100, product_type="service")
    run(
        "combo.combo.create",
        {"name": "Menu of the day", "kitchen_name": "MENU", "price": 1350, "tax_category_key": FOOD},
    )
    for group, minimum, maximum, repeat in (
        ("Starters", 1, 1, False),
        ("Mains", 1, 1, False),
        ("Coffee", 0, 2, True),
        ("Service", 0, 1, False),
    ):
        run(
            "combo.group.create",
            {"combo": "Menu of the day", "name": group, "min_choices": minimum, "max_choices": maximum, "allow_repeat": repeat},
        )
    options = {}
    for group, sku, delta in (
        ("Starters", "LEN", 0),
        ("Starters", "SAL", 0),
        ("Mains", "HAK", 0),
        ("Mains", "STK", 200),
        ("Coffee", "COF", 0),
        ("Service", "TIP", 0),
    ):
        created = run(
            "combo.option.create",
            {"combo": "Menu of the day", "group": group, "product": sku, "price_delta": delta},
        )
        options[sku] = str(created.id)
    return options


def picks(options: dict, *skus: str) -> list[dict]:
    """The choices of the menu, by SKU, as the till sends them: one entry per pick."""
    return [{"option_id": options[sku]} for sku in skus]


def charge(key: str, options: dict, *skus: str, quantity: str = "1", scope=A):
    """Sales charges ``quantity`` menus with ``skus`` picked, by card, as the till does."""
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": f"combo-relay-{key}",
            "payments": [{"method": "card"}],
            "combo_lines": [{"combo": "Menu of the day", "choices": picks(options, *skus), "quantity": quantity}],
        },
        scope,
    )


def test_combo_f10_three_menus_lower_three_portions_of_each_dish_through_the_relay(tick, till_menu):
    """inventory#69: the menu has no stock of its own; each dish picked moves, times the menus and the times
    it was picked (two coffees in each), and the service moves nothing."""
    sale = charge("f10-three", till_menu, "LEN", "STK", "COF", "COF", "TIP", quantity="3")
    (line,) = sale.lines
    # 13,50 + 2,00 of the steak, per menu: what Menus priced.
    assert line.unit_price == 1550
    # Sales' command only records its notice: the stock waits for the relay.
    assert (stock("LEN"), stock("STK"), stock("COF")) == (Decimal("10"), Decimal("10"), Decimal("10"))

    tick()

    assert delivery_to("inventory", "sale.sale.completed") == ("delivered", 1)
    assert (stock("LEN"), stock("STK"), stock("COF")) == (Decimal("7"), Decimal("7"), Decimal("4"))
    assert (stock("SAL"), stock("HAK")) == (Decimal("10"), Decimal("10"))
    assert not Product.objects.filter(name="Menu of the day").exists()
    assert not StockMovement.objects.filter(product__sku="TIP").exists()
    assert StockMovement.objects.filter(product__sku="COF", movement_type="sale").get().qty == Decimal("-6")

    tick()
    assert (stock("LEN"), stock("STK"), stock("COF")) == (Decimal("7"), Decimal("7"), Decimal("4"))


def test_combo_f10_refunding_one_of_three_menus_puts_one_portion_of_each_dish_back_through_the_relay(tick, till_menu):
    sale = charge("f10-refund", till_menu, "SAL", "HAK", "COF", quantity="3")
    tick()
    assert (stock("SAL"), stock("HAK"), stock("COF")) == (Decimal("7"), Decimal("7"), Decimal("7"))
    (line,) = sale.lines

    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "Cold",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 1350}],
            "lines": [{"line_id": str(line.id), "quantity": "1"}],
        },
    )
    tick()

    assert delivery_to("inventory", "sale.sale.refunded") == ("delivered", 1)
    assert (stock("SAL"), stock("HAK"), stock("COF")) == (Decimal("8"), Decimal("8"), Decimal("8"))
    tick()
    assert (stock("SAL"), stock("HAK"), stock("COF")) == (Decimal("8"), Decimal("8"), Decimal("8"))


def test_combo_f10_voiding_the_sale_gives_every_dish_back_through_the_relay(tick, till_menu):
    sale = charge("f10-void", till_menu, "LEN", "HAK", "COF", "COF", quantity="2")
    tick()
    assert (stock("LEN"), stock("HAK"), stock("COF")) == (Decimal("8"), Decimal("8"), Decimal("6"))

    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    tick()

    assert delivery_to("inventory", "sale.sale.voided") == ("delivered", 1)
    assert (stock("LEN"), stock("HAK"), stock("COF")) == (Decimal("10"), Decimal("10"), Decimal("10"))


def station(name: str, usage: str = "kitchen"):
    return run("kitchen.station.create", {"name": name, "printer_usage": usage})


def route(sku: str, station_name: str) -> None:
    run("kitchen.routing.set", {"product": sku, "station": station_name})


def kitchen_paper() -> dict[str, list[dict]]:
    """The items of each kitchen sheet sent to print, by printer function."""
    from apps.printing.models import PrintJob

    jobs = PrintJob.objects.filter(document_type="kitchen_order").order_by("created_at", "id")
    return {job.usage: job.document["items"] for job in jobs}


def test_combo_f11_a_menu_fired_reaches_each_station_under_its_kitchen_name_through_the_relay(tick, till_menu):
    """sales#522 and hub#1156: the kitchen gets the dishes the table chose, each at its own station, under the
    menu's kitchen name, on the card and on paper; the service is never cooked."""
    station("Cold")
    station("Grill")
    station("Bar", usage="bar")
    route("LEN", "Cold")
    route("STK", "Grill")
    route("COF", "Bar")
    order = run("sale.order.open", {"label": "Table 4"})
    (line,) = run(
        "sale.order.add_combo_line",
        {
            "order_id": str(order.id),
            "combo": "Menu of the day",
            "choices": picks(till_menu, "LEN", "STK", "COF", "COF", "TIP"),
            "quantity": "2",
            "notes": "No salt",
        },
    ).lines
    run("sale.order.fire", {"order_id": str(order.id)})
    # Sales' command only records its notice: the kitchen saves its ticket when the relay hands it over.
    assert not Ticket.objects.exists()

    tick()

    assert delivery_to("kitchen", "sale.order.fired") == ("delivered", 1)
    (ticket,) = run("kitchen.ticket.board", {}).cooking
    assert ticket.saved is True
    assert [(item.name, item.quantity, item.menu_name, item.station_name) for item in ticket.items] == [
        ("Lentils", Decimal("2"), "MENU", "Cold"),
        ("Steak", Decimal("2"), "MENU", "Grill"),
        ("Coffee", Decimal("4"), "MENU", "Bar"),
    ]
    assert {item.notes for item in ticket.items} == {"No salt"}
    assert {item.menu_line_id for item in ticket.items} == {line.id}
    ref = str(line.id)
    dish = {"notes": "No salt", "combo_ref": ref, "combo_name": "MENU"}
    assert kitchen_paper() == {
        "kitchen": [{"name": "Lentils", "quantity": 2.0, **dish}, {"name": "Steak", "quantity": 2.0, **dish}],
        "bar": [{"name": "Coffee", "quantity": 4.0, **dish}],
    }

    tick()
    assert Ticket.objects.count() == 1


def test_combo_f11_a_menu_short_of_a_required_course_never_reaches_the_kitchen(tick, till_menu):
    """sales#535: a menu without its main course is refused by Menus when it is ordered, so the check has
    nothing to fire and the kitchen never gets half a menu."""
    order = run("sale.order.open", {"label": "Table 4"})
    with pytest.raises(Conflict) as refused:
        run(
            "sale.order.add_combo_line",
            {"order_id": str(order.id), "combo": "Menu of the day", "choices": picks(till_menu, "LEN")},
        )
    assert refused.value.code == "combo.group_incomplete"
    with pytest.raises(Conflict) as nothing:
        run("sale.order.fire", {"order_id": str(order.id)})
    assert nothing.value.code == "sale.nothing_to_fire"

    tick()

    assert not Ticket.objects.exists()
    assert run("kitchen.ticket.board", {}).cooking == []


# ── Two hubs, on committed data ──────────────────────────────────────────────────────────────


@pytest.fixture
def listen(transactional_db, db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 0.5) -> set[str]:
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_combo_f13_a_product_deleted_in_hub_b_leaves_b_menus_and_is_heard_in_b_only(listen, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    on_a, on_b = listen(A), listen(B)
    product("Flan", "FLA-A", A)
    menu("Menu A", "FLA-A", scope=A)
    tart = product("Tart", "TRT-B", B)
    menu("Menu B", "TRT-B", scope=B)
    heard(on_a), heard(on_b)  # the creations' own notices

    run("inventory.product.delete", {"id": str(tart.id)}, B)
    heard(on_b)  # the deletion's own notice
    one_tick()

    assert statuses("Menu B", B) == []
    assert "combo.option.deleted" in heard(on_b)
    assert heard(on_a) == set()
    assert statuses("Menu A", A) == [("Flan", "offered")]
    (reaction,) = OutboxEvent.objects.filter(name="combo.option.deleted", payload__product_id=str(tart.id))
    assert (reaction.scope_kind, reaction.scope_key) == (B.kind, B.key)
