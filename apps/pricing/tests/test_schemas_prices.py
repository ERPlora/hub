"""Input schemas of the prices of a list: what a caller may send, and the 422 per field of what it may not."""

import uuid
from decimal import Decimal

from apps.pricing.schemas.prices import PriceItemIn, PriceItemListIn, PriceItemPatchIn, PriceItemRefIn

from .test_schemas_fields import errors


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
