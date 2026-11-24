"""Reactions to other apps' events (WORKBOOK PRICING-F14), run as the platform: a product deleted or restored, a
category or a customer group deleted, a service renamed."""

import uuid

import pytest
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.pricing.models import DiscountRule, PriceItem

from .conftest import HUB_DB, make_category, make_group, make_item, make_list, make_product, make_rule, make_service
from .test_services import events, refused, run

pytestmark = HUB_DB


def react(name, payload):
    from live.context import system_context

    from .conftest import A

    op = get(name)
    return op(system_context(A), op.input.model_validate(payload))


def test_a_deleted_product_leaves_no_price_and_switches_its_rules_off_once():
    product = make_product("Shampoo", "SH-1")
    other = make_product("Gel", "GE")
    item = make_item(make_list("VIP"), product)
    make_item(make_list("GEN"), other)
    rule = make_rule("PROD", applies_to="product", product=product)
    answer = react("pricing.catalog.forget_product", {"id": str(product.id), "sku": "SH-1", "name": "Shampoo"})
    assert (answer.items, answer.rules, answer.lists) == (1, 1, 0)
    assert list(PriceItem.objects.values_list("product_id", flat=True)) == [other.id]
    rule.refresh_from_db()
    assert rule.is_active is False
    assert events("pricing.price_item.removed")[0]["id"] == str(item.id)
    assert events("pricing.rule.deactivated") == [{"id": str(rule.id)}]
    again = react("pricing.catalog.forget_product", {"id": str(product.id)})
    assert (again.items, again.rules) == (0, 0)


def deleted(product, is_deleted: bool = True) -> None:
    """``product`` deleted in Inventory (or back, the same one, from the separate copy: INVENTORY-F34)."""
    type(product).objects.filter(pk=product.pk).update(is_deleted=is_deleted)


def test_a_restored_product_switches_back_on_only_the_rules_its_deletion_switched_off():
    product = make_product("Shampoo", "SH-1")
    other = make_product("Gel", "GE")
    gone = make_rule("PROD", applies_to="product", product=product)
    by_hand = make_rule("HAND", applies_to="product", product=product)
    touched = make_rule("EDIT", applies_to="product", product=product)
    make_rule("OTHER", applies_to="product", product=other)
    run("pricing.rule.deactivate", {"id": str(by_hand.id)})
    deleted(product)
    deleted(other)
    react("pricing.catalog.forget_product", {"id": str(product.id)})
    react("pricing.catalog.forget_product", {"id": str(other.id)})
    # Off since, the business renamed it: it stays as the business left it.
    run("pricing.rule.update", {"id": str(touched.id), "name": "Renamed"})
    OutboxEvent.objects.all().delete()
    deleted(product, False)

    answer = react("pricing.catalog.recall_product", {"id": str(product.id), "sku": "SH-1", "name": "Shampoo"})

    assert (answer.lists, answer.items, answer.rules) == (0, 0, 1)
    assert dict(DiscountRule.objects.values_list("code", "is_active")) == {
        "PROD": True,
        "HAND": False,
        "EDIT": False,
        "OTHER": False,
    }
    assert DiscountRule.objects.get(pk=gone.pk).updated_by == "system"
    assert events("pricing.rule.activated") == [{"id": str(gone.id)}]
    assert events("pricing.rule.deactivated") == []
    again = react("pricing.catalog.recall_product", {"id": str(product.id)})
    assert again.rules == 0 and len(events("pricing.rule.activated")) == 1


def test_a_product_deleted_again_or_a_group_gone_leaves_its_rules_off():
    product = make_product()
    group = make_group("VIP")
    plain = make_rule("PROD", applies_to="product", product=product)
    vip = make_rule("VIP", applies_to="product", product=product, customer_group_id=group.id)
    deleted(product)
    react("pricing.catalog.forget_product", {"id": str(product.id)})
    # The event of its restore reaches Tarifas after the product was deleted again: nothing to switch on.
    assert react("pricing.catalog.recall_product", {"id": str(product.id)}).rules == 0
    group.delete()
    deleted(product, False)

    # A rule of a group Customers deleted would apply to nobody: it stays off, the others come back.
    assert react("pricing.catalog.recall_product", {"id": str(product.id)}).rules == 1
    plain.refresh_from_db()
    vip.refresh_from_db()
    assert (plain.is_active, vip.is_active) == (True, False)


def test_a_deleted_category_switches_its_rules_off():
    category = make_category("Colour")
    rule = make_rule("CAT", applies_to="category", category=category)
    assert react("pricing.catalog.forget_category", {"id": str(category.id), "name": "Colour"}).rules == 1
    rule.refresh_from_db()
    assert rule.is_active is False


def test_a_deleted_group_leaves_its_lists_without_group_and_switches_its_rules_off():
    group_id = uuid.uuid7()
    price_list = make_list("VIP", customer_group_id=group_id)
    rule = make_rule("VIP", customer_group_id=group_id)
    answer = react("pricing.catalog.forget_group", {"id": str(group_id)})
    assert (answer.lists, answer.rules) == (1, 1)
    price_list.refresh_from_db()
    rule.refresh_from_db()
    assert (price_list.customer_group_id, rule.is_active, rule.customer_group_id) == (None, False, group_id)
    assert events("pricing.price_list.updated") == [{"id": str(price_list.id)}]


def test_a_renamed_service_is_renamed_in_its_prices_and_rules():
    haircut = make_service("Haircut")
    make_item(make_list("VIP"), None, service_id=haircut.id, service_name="Haircut")
    rule = make_rule("CUT", applies_to="service", service_id=haircut.id, service_name="Haircut")
    haircut.name = "Women's haircut"
    haircut.save()
    answer = react("pricing.catalog.refresh_service", {"id": str(haircut.id)})
    assert (answer.items, answer.rules) == (1, 1)
    assert PriceItem.objects.get().service_name == "Women's haircut"
    rule.refresh_from_db()
    assert rule.service_name == "Women's haircut"
    assert events("pricing.price_item.updated") == [{"service_id": str(haircut.id)}]
    assert events("pricing.rule.updated") == [{"id": str(rule.id)}]
    assert react("pricing.catalog.refresh_service", {"id": str(haircut.id)}).items == 0


@pytest.mark.parametrize("name", ["pricing.catalog.forget_product", "pricing.catalog.recall_product"])
def test_a_reaction_is_no_person_s(name):
    product = make_product()
    refused(PermissionDenied, name, {"id": str(product.id)})
