"""The pricing app's models: defaults, the constraints the database keeps, and what a deletion in
another app takes with it (WORKBOOK «Para quien lo mantiene»)."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.pricing.models import DiscountRule, PriceItem, PriceList

from .conftest import make_category, make_group, make_item, make_list, make_product, make_rule

pytestmark = pytest.mark.django_db


def refused(make):
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


# Price lists


def test_keys_are_uuid7():
    for row in (make_list(), make_rule()):
        assert isinstance(row.pk, uuid.UUID) and row.pk.version == 7, row


def test_a_list_is_born_active_in_euros_following_the_business_tax_and_not_general():
    price_list = make_list("WHOLESALE", "Wholesale")
    assert (price_list.currency, price_list.tax_included, price_list.is_active, price_list.is_default) == (
        "EUR",
        None,
        True,
        False,
    )
    assert (price_list.customer_group_id, price_list.valid_from, price_list.valid_until) == (None, None, None)
    assert str(price_list) == "WHOLESALE — Wholesale"


def test_a_code_is_unique_whatever_its_case_also_against_an_inactive_list():
    make_list("VIP", is_active=False)
    refused(lambda: make_list("vip"))


def test_there_is_one_general_list_at_most():
    make_list("GENERAL", is_default=True)
    make_list("OTHER")
    refused(lambda: make_list("SECOND", is_default=True))


def test_the_general_list_is_for_everybody_and_active():
    refused(lambda: make_list("G1", is_default=True, customer_group_id=make_group().id))
    refused(lambda: make_list("G2", is_default=True, is_active=False))


def test_a_list_does_not_end_before_it_starts():
    make_list("SAME", valid_from=dt.date(2026, 7, 1), valid_until=dt.date(2026, 7, 1))
    refused(lambda: make_list("BACK", valid_from=dt.date(2026, 7, 2), valid_until=dt.date(2026, 7, 1)))


# Prices


def test_a_price_is_for_a_product_or_a_service_never_both_nor_none():
    price_list = make_list()
    product = make_product()
    make_item(price_list, product)
    make_item(price_list, service_id=uuid.uuid7(), service_name="Haircut")
    refused(lambda: make_item(price_list, product, service_id=uuid.uuid7(), min_quantity="5"))
    refused(lambda: make_item(price_list, None))


def test_one_price_per_list_article_and_minimum_quantity():
    price_list, other = make_list("A"), make_list("B")
    product = make_product()
    service_id = uuid.uuid7()
    make_item(price_list, product, min_quantity="1")
    make_item(price_list, product, min_quantity="10")
    make_item(other, product, min_quantity="1")
    refused(lambda: make_item(price_list, product, min_quantity="1.000"))
    make_item(price_list, service_id=service_id, service_name="Haircut")
    refused(lambda: make_item(price_list, service_id=service_id, service_name="Haircut"))


def test_a_minimum_quantity_is_more_than_zero_and_a_price_never_negative():
    price_list = make_list()
    refused(lambda: make_item(price_list, make_product("Gel"), min_quantity="0"))
    refused(lambda: make_item(price_list, make_product("Wax"), price=-1))


def test_a_price_keeps_three_decimals_of_quantity_and_cents():
    item = make_item(make_list(), make_product(), price=1250, min_quantity="0.5")
    item.refresh_from_db()
    assert (item.price, item.min_quantity) == (1250, Decimal("0.500"))


def test_a_list_takes_its_prices_with_it():
    price_list = make_list()
    make_item(price_list, make_product())
    price_list.delete()
    assert not PriceItem.objects.exists()


# Rules


def test_a_rule_is_born_active_for_everything_with_priority_100():
    rule = make_rule("TEN")
    assert (rule.applies_to, rule.priority, rule.is_active, rule.tiers) == ("all", 100, True, [])
    assert str(rule) == "TEN — Rule TEN"


def test_a_rule_code_is_unique_whatever_its_case():
    make_rule("TEN")
    refused(lambda: make_rule("ten"))


def test_a_rule_carries_the_value_of_its_type():
    make_rule("FIX", "fixed", amount=50)
    make_rule("BOGO", "buy_x_get_y", buy_quantity=2, get_quantity=1)
    make_rule("TIER", "tiered", tiers=[{"min_quantity": "3", "percent": "10"}])
    refused(lambda: make_rule("P0", "percent", percent=None))
    refused(lambda: make_rule("P1", "percent", percent=Decimal("100.01")))
    refused(lambda: make_rule("F0", "fixed"))
    refused(lambda: make_rule("B0", "buy_x_get_y", buy_quantity=2))
    refused(lambda: make_rule("T0", "tiered"))


def test_a_rule_names_its_target_as_its_scope_says():
    product, category = make_product(), make_category()
    make_rule("CAT", applies_to="category", category=category)
    make_rule("PROD", applies_to="product", product=product)
    make_rule("SERV", applies_to="service", service_id=uuid.uuid7(), service_name="Haircut")
    refused(lambda: make_rule("C0", applies_to="category"))
    refused(lambda: make_rule("P0", applies_to="product"))
    refused(lambda: make_rule("S0", applies_to="service"))
    refused(lambda: make_rule("ALL", applies_to="all", product=product))


def test_a_rule_does_not_end_before_it_starts():
    refused(lambda: make_rule("BACK", valid_from=dt.date(2026, 7, 2), valid_until=dt.date(2026, 7, 1)))


# What another app's deletion takes with it


def test_a_deleted_customer_group_changes_nothing_here_by_itself():
    # Customers deletes a group for real: the id stays (the reaction tidies up, test_events.py), and no
    # deletion of Customers ever reads these tables.
    group = make_group("VIP")
    group_id = group.id
    price_list = make_list("VIP", customer_group_id=group_id)
    rule = make_rule("VIP10", customer_group_id=group_id)
    group.delete()
    price_list.refresh_from_db()
    rule.refresh_from_db()
    assert (price_list.customer_group_id, rule.customer_group_id, rule.is_active) == (group_id, group_id, True)


def test_a_product_row_deleted_in_the_admin_takes_its_prices_and_its_rules():
    product = make_product()
    make_item(make_list(), product)
    make_rule("PROD", applies_to="product", product=product)
    product.delete()
    assert not PriceItem.objects.exists()
    assert not DiscountRule.objects.exists()
    assert PriceList.objects.count() == 1


def test_a_category_row_deleted_in_the_admin_takes_its_rules():
    category = make_category()
    make_rule("CAT", applies_to="category", category=category)
    category.delete()
    assert not DiscountRule.objects.exists()
