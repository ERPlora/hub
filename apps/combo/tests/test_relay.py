"""Menus and the other apps through the worker's outbox relay, end to end (COMBO-F13).

The other app's real operation records its event in the outbox; one tick of the worker's real loop
(``base.worker.run`` → ``base.relay``) hands it to the reaction of each app that listens, as production runs it:
nothing is called by hand. A repeated delivery changes nothing, and what happens in hub B is heard in B only.

- COMBO-F13: Inventory deletes a product (``inventory.product.delete``) and its choices leave every menu
  (``combo.option.drop_product``); until the tick they are marked «no longer in the catalogue» and never offered.
"""

import json
import threading

import psycopg
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.combo.models import ChoiceOption
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


def delivery_to_combo(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Menus."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    row = EventDelivery.objects.get(event_id=event.id, app_label="combo")
    return row.status, row.attempts


def product(name: str, sku: str, scope=A, **more):
    """A product of Inventory, made by Inventory."""
    data = {"name": name, "sku": sku, "price": 400, "tax_category_key": FOOD, **more}
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
