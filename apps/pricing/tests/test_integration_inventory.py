"""Pricing with the real Inventory app: products and categories created, changed and deleted by
Inventory's own operations; the event Inventory records is handed to ``events.react`` as the outbox
relay will, from the outbox itself."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from live.errors import NotFound
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get

from apps.pricing import events
from apps.pricing.models import DiscountRule, PriceItem

from .conftest import A, TODAY, ctx_for

pytestmark = pytest.mark.django_db

WHEN = dt.datetime.combine(TODAY, dt.time(12), ZoneInfo("Europe/Madrid")).isoformat()


def run(name, data, ctx=None):
    op = get(name)
    return op(ctx or ctx_for("hub_admin"), op.input.model_validate(data))


def relay(name: str) -> None:
    """Hands the last ``name`` event of the outbox to the pricing app's reactions."""
    event = OutboxEvent.objects.filter(name=name).latest("created_at")
    events.react(A, event.name, event.payload)


def new_product(name="Shampoo", sku="SH-1", price=1500, **fields):
    return run("inventory.product.create", {"name": name, "sku": sku, "price": price, "tax_category_key": "product.generic", **fields})


def test_a_product_of_inventory_is_priced_by_its_sku_and_follows_its_catalog_price():
    product = new_product()
    run("pricing.price_list.create", {"code": "GEN", "name": "General", "is_default": True})
    run("pricing.price_item.add", {"price_list": "GEN", "product": "sh-1", "price": 1200})
    line = run("pricing.price.resolve", {"product": "Shampoo", "quantity": "2", "when": WHEN})
    assert (line.product_id, line.base_price, line.unit_price, line.line_amount) == (product.id, 1500, 1200, 2400)
    run("inventory.product.update", {"id": str(product.id), "price": 1700})
    # Inventory's change re-runs the prices live, and they read the new catalog price.
    assert "pricing.price_item.list" in live_registry.affected(["inventory.product.updated"])
    assert run("pricing.price_item.list", {"price_list": "GEN"}).rows[0].base_price == 1700
    assert run("pricing.price.resolve", {"product_id": str(product.id), "when": WHEN}).base_price == 1700


def test_a_product_sold_by_weight_in_steps_of_a_gram():
    product = new_product("Coffee", "CF", price=2400, unit="g", pricing_unit="kg")
    run("pricing.price_list.create", {"code": "GEN", "name": "General", "is_default": True})
    run("pricing.price_item.add", {"price_list": "GEN", "product_id": str(product.id), "price": 2000, "min_quantity": "500"})
    assert run("pricing.price.resolve", {"product_id": str(product.id), "quantity": "250", "when": WHEN}).line_amount == 600
    assert run("pricing.price.resolve", {"product_id": str(product.id), "quantity": "500", "when": WHEN}).line_amount == 1000


def test_a_product_deleted_in_inventory_leaves_no_price_and_its_rules_off():
    product = new_product()
    run("pricing.price_list.create", {"code": "VIP", "name": "VIP"})
    run("pricing.price_item.add", {"price_list": "VIP", "product": "SH-1", "price": 1200})
    run("pricing.rule.create", {"code": "SH", "name": "Shampoo", "rule_type": "percent", "percent": "10", "applies_to": "product", "product": "SH-1"})
    assert run("pricing.rule.list", {}).rows[0].target_deleted is False
    run("inventory.product.delete", {"id": str(product.id)})
    # Before the relay: hidden at reading, never priced, and its rule says its product is gone.
    [row] = run("pricing.rule.list", {}).rows
    assert (row.product_name, row.target_deleted, row.is_active) == ("Shampoo", True, True)
    assert run("pricing.price_item.list", {"price_list": "VIP"}).total == 0
    assert run("pricing.price_list.get", {"price_list": "VIP"}).item_count == 0
    with pytest.raises(NotFound):
        run("pricing.price.resolve", {"product_id": str(product.id), "when": WHEN})
    relay("inventory.product.deleted")
    assert not PriceItem.objects.exists()
    assert DiscountRule.objects.get(code="SH").is_active is False


def test_a_category_rule_follows_the_products_inventory_puts_in_it_and_its_deletion():
    product = new_product()
    run("inventory.category.create", {"name": "Hair care"})
    run("pricing.rule.create", {"code": "HAIR", "name": "Hair care", "rule_type": "percent", "percent": "20", "applies_to": "category", "category": "hair care"})
    assert run("pricing.price.resolve", {"product_id": str(product.id), "when": WHEN}).rule_code is None
    run("inventory.product_category.add", {"product": "SH-1", "category": "Hair care"})
    line = run("pricing.price.resolve", {"product_id": str(product.id), "when": WHEN})
    assert (line.rule_code, line.discount) == ("HAIR", 300)
    run("inventory.category.update", {"category": "Hair care", "name": "Hair"})
    assert run("pricing.rule.list", {}).rows[0].category_name == "Hair"
    run("inventory.category.delete", {"category": "Hair"})
    assert run("pricing.rule.list", {}).rows[0].target_deleted is True
    assert run("pricing.price.resolve", {"product_id": str(product.id), "when": WHEN}).rule_code is None
    relay("inventory.category.deleted")
    assert DiscountRule.objects.get(code="HAIR").is_active is False
