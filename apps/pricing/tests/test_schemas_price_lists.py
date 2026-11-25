"""Input schemas of the price lists: what a caller may send, and the 422 per field of what it may not."""

import datetime as dt
import uuid

from apps.pricing.schemas.price_lists import (
    PriceListDefaultIn,
    PriceListIn,
    PriceListListIn,
    PriceListPatchIn,
    PriceListRefIn,
)

from .test_schemas_fields import errors


def test_the_lists_are_active_by_name_by_default():
    params = PriceListListIn()
    assert (params.status, params.sort, params.dir) == ("active", "name", "asc")
    assert "sort" in errors(PriceListListIn, sort="item_count")
    assert PriceListListIn(tax_basis="business").tax_basis == "business"
    assert "tax_basis" in errors(PriceListListIn, tax_basis="maybe")


def test_a_list_needs_a_code_and_a_name_trimmed():
    data = PriceListIn(code="  VIP ", name="  VIP members ")
    # Without a currency the operation takes the business's (test_business_currency).
    assert (data.code, data.name, data.currency, data.tax_included, data.is_default) == (
        "VIP",
        "VIP members",
        None,
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


def test_the_currency_of_the_general_list_is_left_to_the_operation():
    # Only the operation knows the business's currency (its country's): the schema neither fixes nor refuses one.
    assert PriceListIn(code="c", name="n", is_default=True).currency is None
    assert PriceListIn(code="c", name="n", currency="USD", is_default=True).currency == "USD"


def test_a_list_is_named_by_id_or_by_its_code_or_name():
    assert PriceListRefIn(price_list=" wholesale ").price_list == "wholesale"
    assert errors(PriceListRefIn) == {"price_list": "value_error"}
    assert PriceListDefaultIn(price_list="VIP").is_default is True
    assert PriceListDefaultIn(price_list="VIP", is_default=False).is_default is False


def test_an_edit_sends_only_what_changes():
    data = PriceListPatchIn(price_list="VIP", customer_group_id=None)
    assert data.model_fields_set == {"price_list", "customer_group_id"}
    assert "code" in errors(PriceListPatchIn, price_list="VIP", code=" ")
