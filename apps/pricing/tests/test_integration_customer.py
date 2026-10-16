"""Pricing with the real Customers app: groups and cards made, changed and deleted by Customers' own
operations; the price of a line for a customer named by name or phone."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from live.models import OutboxEvent
from live.operations import get

from apps.pricing import events
from apps.pricing.models import DiscountRule, PriceList

from .conftest import A, TODAY, ctx_for, make_product

pytestmark = pytest.mark.django_db

WHEN = dt.datetime.combine(TODAY, dt.time(12), ZoneInfo("Europe/Madrid")).isoformat()


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


def relay(name: str) -> None:
    event = OutboxEvent.objects.filter(name=name).latest("created_at")
    events.react(A, event.name, event.payload)


@pytest.fixture
def vip_customer():
    run("customer.group.create", {"name": "VIP"})
    lucia = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "+34 600 111 222"})
    run("customer.customer.set_groups", {"id": str(lucia.id), "groups": ["VIP"]})
    return lucia


def test_the_vip_group_s_list_and_rule_price_its_members_named_by_phone(vip_customer):
    product = make_product("Shampoo", "SH-1", price=1500)
    run("pricing.price_list.create", {"code": "VIP", "name": "VIP members", "customer_group": "vip"})
    run("pricing.price_item.add", {"price_list": "VIP", "product": "SH-1", "price": 1200})
    run("pricing.rule.create", {"code": "VIP5", "name": "VIP 5", "rule_type": "percent", "percent": "5", "customer_group": "VIP"})
    line = run("pricing.price.resolve", {"product_id": str(product.id), "customer": "600111222", "when": WHEN})
    assert (line.price_list_code, line.unit_price, line.rule_code, line.discount) == ("VIP", 1200, "VIP5", 60)
    stranger = run("customer.customer.create", {"name": "Bea Gil"})
    plain = run("pricing.price.resolve", {"product_id": str(product.id), "customer_id": str(stranger.id), "when": WHEN})
    assert (plain.unit_price, plain.rule_code) == (1500, None)


def test_a_group_renamed_in_customers_is_named_again_and_one_deactivated_prices_nobody(vip_customer):
    product = make_product("Shampoo", "SH-1", price=1500)
    run("pricing.price_list.create", {"code": "VIP", "name": "VIP members", "customer_group": "VIP"})
    run("pricing.price_item.add", {"price_list": "VIP", "product": "SH-1", "price": 1200})
    run("customer.group.update", {"group": "VIP", "name": "Gold"})
    assert run("pricing.price_list.get", {"price_list": "VIP"}).customer_group_name == "Gold"
    run("customer.group.update", {"group": "Gold", "is_active": False})
    line = run("pricing.price.resolve", {"product_id": str(product.id), "customer_id": str(vip_customer.id), "when": WHEN})
    assert line.unit_price == 1500


def test_a_group_deleted_in_customers_prices_nobody_and_the_reaction_tidies_up(vip_customer):
    product = make_product("Shampoo", "SH-1", price=1500)
    run("pricing.price_list.create", {"code": "VIP", "name": "VIP members", "customer_group": "VIP"})
    run("pricing.price_item.add", {"price_list": "VIP", "product": "SH-1", "price": 1200})
    run("pricing.rule.create", {"code": "VIP5", "name": "VIP 5", "rule_type": "percent", "percent": "5", "customer_group": "VIP"})
    run("customer.group.delete", {"group": "VIP"})
    line = run("pricing.price.resolve", {"product_id": str(product.id), "customer_id": str(vip_customer.id), "when": WHEN})
    assert (line.unit_price, line.rule_id) == (1500, None)
    relay("customer.group.deleted")
    assert PriceList.objects.get(code="VIP").customer_group_id is None
    assert DiscountRule.objects.get(code="VIP5").is_active is False
