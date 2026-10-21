"""Price Lists hears Inventory, Customers and Services through the worker's outbox relay, end to end (PRICING-F14).

Each app's real operation deletes a product, a category or a customer group, or renames a service, and records its
event in the outbox; one tick of the worker's real loop (``base.worker.run`` → ``base.relay``) hands it to Price
Lists, whose reaction removes the product's prices and switches off its rules, switches off the category's rules,
leaves the group's lists without group and switches off its rules, or copies the service's new name — once: a
second tick, or the same event handed over again, changes nothing. What is deleted in hub B is forgotten in B only,
and the notices are heard in B only.
"""

import datetime as dt
import json
import threading
from zoneinfo import ZoneInfo

import psycopg
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.pricing.models import DiscountRule, PriceItem, PriceList
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import (
    A,
    B,
    TODAY,
    categorize,
    ctx_for,
    make_category,
    make_customer,
    make_group,
    make_item,
    make_list,
    make_product,
    make_rule,
    make_service,
)

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
NOON = dt.datetime.combine(TODAY, dt.time(12), ZoneInfo("Europe/Madrid")).isoformat()


def run(name: str, data: dict, scope=A):
    """Run the operation ``name`` as the owner of ``scope``: the other apps' own, with their permissions."""
    op = get(name)
    return op(ctx_for("hub_owner", scope=scope), op.input.model_validate(data))


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


def delivery_to_pricing(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Price Lists."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    row = EventDelivery.objects.get(event_id=event.id, app_label="pricing")
    return row.status, row.attempts


def notices(name: str) -> list[dict]:
    """The payloads of the ``name`` events in the outbox, oldest first."""
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")]


def pricing_notices() -> int:
    return OutboxEvent.objects.filter(name__startswith="pricing.").count()


def rule_active(code: str) -> bool:
    return DiscountRule.objects.get(code=code).is_active


# ── Inventory deletes a product ───────────────────────────────────────────────────────────────────


def test_a_product_deleted_in_inventory_leaves_every_list_and_switches_off_its_rules_through_the_relay(tick):
    shampoo, conditioner = make_product("Shampoo", "SH-1", price=1500), make_product("Conditioner", "CO-1")
    vip, retail = make_list("VIP"), make_list("RETAIL")
    one = make_item(vip, shampoo, price=1200)
    ten = make_item(vip, shampoo, price=1000, min_quantity="10")
    other_list = make_item(retail, shampoo, price=1400)
    kept = make_item(vip, conditioner, price=900)
    make_rule("SH10", applies_to="product", product=shampoo)
    make_rule("CO10", applies_to="product", product=conditioner)

    run("inventory.product.delete", {"id": str(shampoo.id)})
    # Inventory's command only records its event: the prices wait for the relay.
    assert PriceItem.objects.filter(product=shampoo).count() == 3

    tick()

    assert delivery_to_pricing("inventory.product.deleted") == ("delivered", 1)
    assert not PriceItem.objects.filter(product=shampoo).exists()
    assert list(PriceItem.objects.values_list("id", flat=True)) == [kept.id]
    assert rule_active("SH10") is False
    assert rule_active("CO10") is True
    removed = sorted(notices("pricing.price_item.removed"), key=lambda payload: payload["id"])
    assert removed == sorted(
        [
            {"id": str(one.id), "price_list_id": str(vip.id)},
            {"id": str(ten.id), "price_list_id": str(vip.id)},
            {"id": str(other_list.id), "price_list_id": str(retail.id)},
        ],
        key=lambda payload: payload["id"],
    )
    assert notices("pricing.rule.deactivated") == [{"id": str(DiscountRule.objects.get(code="SH10").id)}]
    # The list's detail (PRICING-F06) keeps only what is still sold.
    page = run("pricing.price_item.list", {"price_list_id": str(vip.id)})
    assert [row.id for row in page.rows] == [kept.id]


# ── Inventory deletes a category ──────────────────────────────────────────────────────────────────


def test_a_category_deleted_in_inventory_switches_off_its_rules_through_the_relay(tick):
    hair, nails = make_category("Hair care"), make_category("Nails")
    categorize(make_product("Shampoo", "SH-1"), hair)
    make_rule("HAIR10", applies_to="category", category=hair)
    make_rule("HAIROFF", applies_to="category", category=hair, is_active=False)
    make_rule("NAILS10", applies_to="category", category=nails)

    run("inventory.category.delete", {"id": str(hair.id)})
    assert rule_active("HAIR10") is True

    tick()

    assert delivery_to_pricing("inventory.category.deleted") == ("delivered", 1)
    assert rule_active("HAIR10") is False
    assert rule_active("HAIROFF") is False
    assert rule_active("NAILS10") is True
    # Only the rule that was on is switched off, once.
    assert notices("pricing.rule.deactivated") == [{"id": str(DiscountRule.objects.get(code="HAIR10").id)}]


# ── Customers deletes a group ─────────────────────────────────────────────────────────────────────


def test_a_group_deleted_in_customers_leaves_its_lists_without_group_and_its_rules_off_through_the_relay(tick):
    vip, staff = make_group("VIP"), make_group("Staff")
    lucia = make_customer("Lucía Pérez", groups=[vip])
    shampoo = make_product("Shampoo", "SH-1", price=1500)
    vip_list, staff_list = make_list("VIP", customer_group_id=vip.id), make_list("STAFF", customer_group_id=staff.id)
    make_item(vip_list, shampoo, price=1200)
    make_rule("VIP10", customer_group_id=vip.id)
    make_rule("STAFF10", customer_group_id=staff.id)
    asked = {"product_id": str(shampoo.id), "customer_id": str(lucia.id), "when": NOON}
    assert (run("pricing.price.resolve", asked).unit_price, run("pricing.price.resolve", asked).rule_code) == (
        1200,
        "VIP10",
    )

    run("customer.group.delete", {"id": str(vip.id)})

    tick()

    assert delivery_to_pricing("customer.group.deleted") == ("delivered", 1)
    vip_list.refresh_from_db()
    assert (vip_list.customer_group_id, vip_list.is_default, vip_list.is_active) == (None, False, True)
    assert PriceList.objects.get(code="STAFF").customer_group_id == staff.id
    # Never does a group's discount spread to everybody: its rule is off, not without group.
    assert rule_active("VIP10") is False
    assert DiscountRule.objects.get(code="VIP10").customer_group_id == vip.id
    assert rule_active("STAFF10") is True
    assert notices("pricing.price_list.updated") == [{"id": str(vip_list.id)}]
    assert notices("pricing.rule.deactivated") == [{"id": str(DiscountRule.objects.get(code="VIP10").id)}]
    # The group's former member pays the catalog's price, without discount (PRICING-F13).
    line = run("pricing.price.resolve", asked)
    assert (line.unit_price, line.price_list_id, line.discount, line.rule_code) == (1500, None, 0, None)


# ── Services renames a service ────────────────────────────────────────────────────────────────────


def test_a_service_renamed_in_services_is_renamed_in_its_prices_and_rules_through_the_relay(tick):
    haircut, colour = make_service("Haircut"), make_service("Colour")
    salon = make_list("SALON")
    cut_item = make_item(salon, None, service_id=haircut.id, service_name="Haircut")
    colour_item = make_item(salon, None, service_id=colour.id, service_name="Colour")
    make_rule("CUT10", applies_to="service", service_id=haircut.id, service_name="Haircut")

    run("service.service.update", {"id": str(haircut.id), "name": "Ladies' cut"})
    cut_item.refresh_from_db()
    assert cut_item.service_name == "Haircut"

    tick()

    assert delivery_to_pricing("service.service.updated") == ("delivered", 1)
    cut_item.refresh_from_db()
    colour_item.refresh_from_db()
    assert (cut_item.service_name, colour_item.service_name) == ("Ladies' cut", "Colour")
    rule = DiscountRule.objects.get(code="CUT10")
    assert rule.service_name == "Ladies' cut"
    assert notices("pricing.price_item.updated") == [{"service_id": str(haircut.id)}]
    assert notices("pricing.rule.updated") == [{"id": str(rule.id)}]


def test_a_service_changed_without_a_new_name_changes_nothing_in_price_lists(tick):
    haircut = make_service("Haircut")
    make_item(make_list("SALON"), None, service_id=haircut.id, service_name="Haircut")
    make_rule("CUT10", applies_to="service", service_id=haircut.id, service_name="Haircut")

    run("service.service.update", {"id": str(haircut.id), "price": 2000})
    tick()

    assert delivery_to_pricing("service.service.updated") == ("delivered", 1)
    assert pricing_notices() == 0


# ── Once ──────────────────────────────────────────────────────────────────────────────────────────


def test_a_second_tick_or_the_same_notices_handed_over_again_change_nothing(tick):
    shampoo = make_product("Shampoo", "SH-1")
    hair = make_category("Hair care")
    vip = make_group("VIP")
    haircut = make_service("Haircut")
    make_item(make_list("VIP", customer_group_id=vip.id), shampoo)
    make_item(make_list("SALON"), None, service_id=haircut.id, service_name="Haircut")
    make_rule("SH10", applies_to="product", product=shampoo)
    make_rule("HAIR10", applies_to="category", category=hair)
    make_rule("VIP10", customer_group_id=vip.id)
    make_rule("CUT10", applies_to="service", service_id=haircut.id, service_name="Haircut")
    run("inventory.product.delete", {"id": str(shampoo.id)})
    run("inventory.category.delete", {"id": str(hair.id)})
    run("customer.group.delete", {"id": str(vip.id)})
    run("service.service.update", {"id": str(haircut.id), "name": "Ladies' cut"})
    tick()
    reacted = pricing_notices()
    state = (
        sorted(PriceItem.objects.values_list("id", "service_name")),
        sorted(PriceList.objects.values_list("code", "customer_group_id", "is_active")),
        sorted(DiscountRule.objects.values_list("code", "is_active", "service_name")),
    )
    heard = ["inventory.product.deleted", "inventory.category.deleted", "customer.group.deleted", "service.service.updated"]
    assert reacted == 7  # 1 price removed, 3 rules off, 1 list without group, 1 price and 1 rule renamed

    tick()
    assert [delivery_to_pricing(name) for name in heard] == [("delivered", 1)] * 4

    # The same notices handed to Price Lists again, as if their delivery had been lost: the relay runs them once more.
    for name in heard:
        event = OutboxEvent.objects.filter(name=name).latest("id")
        EventDelivery.objects.filter(event_id=event.id, app_label="pricing").update(
            status=EventDelivery.Status.PENDING, delivered_at=None, next_attempt_at=timezone.now()
        )
    tick()

    assert [delivery_to_pricing(name) for name in heard] == [("delivered", 2)] * 4
    assert pricing_notices() == reacted
    assert (
        sorted(PriceItem.objects.values_list("id", "service_name")),
        sorted(PriceList.objects.values_list("code", "customer_group_id", "is_active")),
        sorted(DiscountRule.objects.values_list("code", "is_active", "service_name")),
    ) == state


# ── Two hubs, on committed data ───────────────────────────────────────────────────────────────────


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


def test_a_product_deleted_in_hub_b_leaves_b_lists_only_and_is_heard_in_b_only(listen, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    on_a, on_b = listen(A), listen(B)
    a_product, b_product = make_product("Shampoo A", "SH-A"), make_product("Shampoo B", "SH-B")
    a_item = make_item(make_list("ALIST"), a_product)
    b_item = make_item(make_list("BLIST"), b_product)

    run("inventory.product.delete", {"id": str(b_product.id)}, B)
    heard(on_b)  # the deletion's own notice
    one_tick()

    assert not PriceItem.objects.filter(id=b_item.id).exists()
    assert "pricing.price_item.removed" in heard(on_b)
    assert heard(on_a) == set()
    assert PriceItem.objects.filter(id=a_item.id).exists()
    reaction = OutboxEvent.objects.get(name="pricing.price_item.removed", payload__id=str(b_item.id))
    assert (reaction.scope_kind, reaction.scope_key) == (B.kind, B.key)
    # The positive control: a product deleted in hub A leaves A's list, heard in A.
    run("inventory.product.delete", {"id": str(a_product.id)}, A)
    heard(on_a)
    one_tick()
    assert not PriceItem.objects.filter(id=a_item.id).exists()
    assert "pricing.price_item.removed" in heard(on_a)
    assert heard(on_b) == set()
