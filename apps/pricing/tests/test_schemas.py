"""Input schemas of the pricing app: what a caller may send, and the 422 per field of what it may not.

Coherence between fields that an edit may send alone (a rule's type and its value, a scope and its
target, a range of days) is the service's (``schemas.rule_problems``, tested here as a pure function).
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.pricing.schemas import (
    CatalogEventIn,
    PageIn,
    PriceItemIn,
    PriceItemListIn,
    PriceItemPatchIn,
    PriceItemRefIn,
    PriceListDefaultIn,
    PriceListIn,
    PriceListListIn,
    PriceListPatchIn,
    PriceListRefIn,
    ResolveIn,
    RuleIn,
    RuleListIn,
    RulePatchIn,
    RuleRefIn,
    rule_problems,
)


def errors(schema, **data) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return {".".join(str(p) for p in e["loc"]): e["type"] for e in caught.value.errors()}


def test_a_page_asks_for_at_most_100_rows_and_refuses_an_unknown_filter():
    assert (PageIn().limit, PageIn().offset) == (50, 0)
    assert "limit" in errors(PageIn, limit=101)
    assert "offset" in errors(PageIn, offset=-1)
    assert errors(PriceListListIn, colour="red") == {"colour": "extra_forbidden"}


def test_the_lists_are_active_by_name_by_default():
    params = PriceListListIn()
    assert (params.status, params.sort, params.dir) == ("active", "name", "asc")
    assert "sort" in errors(PriceListListIn, sort="item_count")
    assert PriceListListIn(tax_basis="business").tax_basis == "business"
    assert "tax_basis" in errors(PriceListListIn, tax_basis="maybe")


# Price lists


def test_a_list_needs_a_code_and_a_name_trimmed():
    data = PriceListIn(code="  VIP ", name="  VIP members ")
    assert (data.code, data.name, data.currency, data.tax_included, data.is_default) == (
        "VIP",
        "VIP members",
        "EUR",
        None,
        False,
    )
    assert set(errors(PriceListIn, code=" ", name="")) == {"code", "name"}
    assert "code" in errors(PriceListIn, code="x" * 51, name="n")
    assert "name" in errors(PriceListIn, code="c", name="x" * 201)


def test_a_currency_is_an_iso_code_with_two_decimals():
    assert PriceListIn(code="c", name="n", currency=" usd ").currency == "USD"
    assert "currency" in errors(PriceListIn, code="c", name="n", currency="XYZ")
    # The yen has no cents: an amount typed with two decimals would be wrong by a hundred.
    assert "currency" in errors(PriceListIn, code="c", name="n", currency="JPY")


def test_a_list_does_not_end_before_it_starts():
    data = PriceListIn(code="c", name="n", valid_from="2026-07-01", valid_until="2026-07-01")
    assert (data.valid_from, data.valid_until) == (dt.date(2026, 7, 1), dt.date(2026, 7, 1))
    assert errors(PriceListIn, code="c", name="n", valid_from="2026-07-02", valid_until="2026-07-01") == {
        "valid_until": "value_error"
    }


def test_the_general_list_has_no_group():
    group = uuid.uuid7()
    assert errors(PriceListIn, code="c", name="n", customer_group_id=group, is_default=True) == {
        "is_default": "value_error"
    }
    assert errors(PriceListIn, code="c", name="n", customer_group="VIP", is_default=True) == {
        "is_default": "value_error"
    }


def test_the_general_list_is_in_euros():
    assert PriceListIn(code="c", name="n", is_default=True).currency == "EUR"
    assert errors(PriceListIn, code="c", name="n", currency="USD", is_default=True) == {"is_default": "value_error"}


def test_a_list_is_named_by_id_or_by_its_code_or_name():
    assert PriceListRefIn(price_list=" wholesale ").price_list == "wholesale"
    assert errors(PriceListRefIn) == {"price_list": "value_error"}
    assert PriceListDefaultIn(price_list="VIP").is_default is True
    assert PriceListDefaultIn(price_list="VIP", is_default=False).is_default is False


def test_an_edit_sends_only_what_changes():
    data = PriceListPatchIn(price_list="VIP", customer_group_id=None)
    assert data.model_fields_set == {"price_list", "customer_group_id"}
    assert "code" in errors(PriceListPatchIn, price_list="VIP", code=" ")


# Prices


def test_a_price_names_its_list_and_one_article():
    data = PriceItemIn(price_list="VIP", product="SHAMPOO-1", price=999)
    assert (data.min_quantity, data.price) == (Decimal("1"), 999)
    assert PriceItemIn(price_list_id=uuid.uuid7(), service="Haircut", price=0).service == "Haircut"
    assert errors(PriceItemIn, price_list="VIP", price=1) == {"product": "value_error"}
    # Both: said on the article field the form shows first.
    assert errors(PriceItemIn, price_list="VIP", product="a", service="b", price=1) == {"product": "value_error"}
    assert errors(PriceItemIn, product="a", price=1) == {"price_list": "value_error"}


def test_a_price_is_cents_and_a_quantity_more_than_zero_with_three_decimals():
    assert "price" in errors(PriceItemIn, price_list="VIP", product="a", price=-1)
    assert "price" in errors(PriceItemIn, price_list="VIP", product="a", price=12.5)
    assert "min_quantity" in errors(PriceItemIn, price_list="VIP", product="a", price=1, min_quantity="0")
    assert "min_quantity" in errors(PriceItemIn, price_list="VIP", product="a", price=1, min_quantity="0.0005")
    assert PriceItemIn(price_list="VIP", product="a", price=1, min_quantity="0.5").min_quantity == Decimal("0.5")


def test_a_price_is_changed_by_its_id_and_named_by_list_article_and_quantity():
    the_id = uuid.uuid7()
    assert PriceItemPatchIn(id=the_id, price=100).model_fields_set == {"id", "price"}
    assert PriceItemRefIn(id=the_id).id == the_id
    named = PriceItemRefIn(price_list="VIP", product="Shampoo")
    assert (named.min_quantity, named.product) == (Decimal("1"), "Shampoo")
    assert errors(PriceItemRefIn, product="Shampoo") == {"price_list": "value_error"}
    assert errors(PriceItemRefIn, price_list="VIP") == {"product": "value_error"}


def test_the_prices_of_a_list_or_of_an_article_across_lists():
    assert PriceItemListIn(price_list="VIP").sort == "name"
    assert PriceItemListIn(product_id=uuid.uuid7()).price_list is None
    assert "kind" in errors(PriceItemListIn, kind="bundle")


# Rules


def test_a_rule_needs_code_name_and_type():
    rule = RuleIn(code="TEN", name="Ten off", rule_type="percent", percent="10")
    assert (rule.applies_to, rule.priority, rule.tiers, rule.percent) == ("all", 100, [], Decimal("10"))
    assert set(errors(RuleIn, code="", name="")) == {"code", "name", "rule_type"}
    assert "rule_type" in errors(RuleIn, code="c", name="n", rule_type="coupon")
    assert "percent" in errors(RuleIn, code="c", name="n", rule_type="percent", percent="100.5")
    assert "percent" in errors(RuleIn, code="c", name="n", rule_type="percent", percent="0")
    assert "amount" in errors(RuleIn, code="c", name="n", rule_type="fixed", amount=0)
    assert "buy_quantity" in errors(RuleIn, code="c", name="n", rule_type="buy_x_get_y", buy_quantity=0)
    assert "tiers" in errors(RuleIn, code="c", name="n", rule_type="tiered", tiers=[{"min_quantity": "1", "percent": "5"}] * 11)
    assert "tiers.0.percent" in errors(RuleIn, code="c", name="n", rule_type="tiered", tiers=[{"min_quantity": "1", "percent": "0"}])
    assert "applies_to" in errors(RuleIn, code="c", name="n", rule_type="percent", percent="5", applies_to="customer_segment")


def test_a_rule_is_named_by_id_code_or_name():
    assert RuleRefIn(rule=" 2x1 ").rule == "2x1"
    assert errors(RuleRefIn) == {"rule": "value_error"}
    assert RulePatchIn(rule="2x1", priority=5).model_fields_set == {"rule", "priority"}


def test_the_rules_are_active_by_name_by_default():
    params = RuleListIn()
    assert (params.status, params.sort, params.dir) == ("active", "name", "asc")
    assert "sort" in errors(RuleListIn, sort="value")


def test_rule_problems_ask_for_the_value_of_each_type_and_refuse_another_types():
    assert rule_problems({"rule_type": "percent", "percent": Decimal("10"), "applies_to": "all"}) == {}
    assert set(rule_problems({"rule_type": "percent", "applies_to": "all"})) == {"percent"}
    assert set(rule_problems({"rule_type": "fixed", "applies_to": "all"})) == {"amount"}
    assert set(rule_problems({"rule_type": "buy_x_get_y", "buy_quantity": 2, "applies_to": "all"})) == {"get_quantity"}
    assert set(rule_problems({"rule_type": "tiered", "tiers": [], "applies_to": "all"})) == {"tiers"}
    # A value of another type was sent on purpose: said, never silently dropped.
    assert set(rule_problems({"rule_type": "percent", "percent": Decimal("5"), "amount": 50, "applies_to": "all"})) == {
        "amount"
    }


def test_rule_problems_want_tiers_rising():
    tiers = [{"min_quantity": Decimal("6"), "percent": Decimal("15")}, {"min_quantity": Decimal("3"), "percent": Decimal("10")}]
    assert set(rule_problems({"rule_type": "tiered", "tiers": tiers, "applies_to": "all"})) == {"tiers"}
    same = [{"min_quantity": Decimal("3"), "percent": Decimal("10")}, {"min_quantity": Decimal("3"), "percent": Decimal("15")}]
    assert set(rule_problems({"rule_type": "tiered", "tiers": same, "applies_to": "all"})) == {"tiers"}


def test_rule_problems_want_the_target_of_the_scope_and_no_other():
    base = {"rule_type": "percent", "percent": Decimal("5")}
    assert set(rule_problems({**base, "applies_to": "category"})) == {"category"}
    assert set(rule_problems({**base, "applies_to": "product"})) == {"product"}
    assert set(rule_problems({**base, "applies_to": "service"})) == {"service"}
    assert rule_problems({**base, "applies_to": "product", "product_id": uuid.uuid7()}) == {}
    assert set(rule_problems({**base, "applies_to": "all", "product_id": uuid.uuid7()})) == {"product"}


def test_rule_problems_want_the_days_in_order():
    base = {"rule_type": "percent", "percent": Decimal("5"), "applies_to": "all"}
    assert set(rule_problems({**base, "valid_from": dt.date(2026, 7, 2), "valid_until": dt.date(2026, 7, 1)})) == {
        "valid_until"
    }


# The price of a line


def test_the_price_of_a_line_names_one_article_and_a_moment_with_its_zone():
    data = ResolveIn(product="Shampoo")
    assert (data.quantity, data.when, data.customer, data.price_list) == (Decimal("1"), None, None, None)
    assert errors(ResolveIn) == {"product": "value_error"}
    assert errors(ResolveIn, product="a", service_id=uuid.uuid7()) == {"product": "value_error"}
    assert "quantity" in errors(ResolveIn, product="a", quantity="0")
    assert "when" in errors(ResolveIn, product="a", when="2026-07-15T10:00:00")
    assert ResolveIn(product="a", when="2026-07-15T10:00:00+02:00").when.utcoffset() == dt.timedelta(hours=2)


def test_an_event_payload_keeps_only_the_id():
    the_id = uuid.uuid7()
    assert CatalogEventIn.model_validate({"id": str(the_id), "sku": "S", "name": "N"}).id == the_id
