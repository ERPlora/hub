"""Input schemas of the cart_checkout app: what an operation refuses before it touches the database.

The cases come from the old module's JSON schemas and handler (Rust): a session code of 1 to 128
characters, a quantity above 0, a price in whole minor units that is never negative, an order email
shaped as one, a mandatory reason to fail an order; and the currency of a cart is a real ISO 4217 code.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.cart_checkout.schemas import (
    CURRENCY_UNKNOWN,
    EMAIL_INVALID,
    EXPIRY_PASSED,
    MAX_AMOUNT,
    MAX_QUANTITY,
    QUANTITY_NOT_POSITIVE,
    REASON_REQUIRED,
    SAY_WHICH_CART,
    SAY_WHICH_ORDER,
    AbandonIn,
    CartIn,
    CartListIn,
    CartRefIn,
    CheckoutIn,
    CustomerEraseIn,
    FailIn,
    ItemAddIn,
    ItemListIn,
    ItemUpdateIn,
    OrderListIn,
    OrderRefIn,
)

from .conftest import NOW


def messages(error: ValidationError) -> dict[str, str]:
    return {
        ".".join(str(part) for part in item["loc"]): str(
            (item.get("ctx") or {}).get("error") or item["msg"]
        )
        for item in error.errors()
    }


def add_in(**fields) -> ItemAddIn:
    data = {
        "session_token": "sess_1",
        "product_ref": "p-1",
        "product_name": "Champú",
        "quantity": "2",
        "unit_price": 1250,
    } | fields
    return ItemAddIn(**data)


# Carts


def test_a_cart_needs_only_its_session_code(clock):
    data = CartIn(session_token="  sess_a1b2c3  ")
    assert data.session_token == "sess_a1b2c3"
    assert (data.customer_email, data.customer_name) == ("", "")
    assert (data.currency, data.expires_at) == (None, None)


@pytest.mark.parametrize("token", ["", "   ", "x" * 129])
def test_a_session_code_is_1_to_128_characters(token, clock):
    with pytest.raises(ValidationError) as caught:
        CartIn(session_token=token)
    assert set(messages(caught.value)) == {"session_token"}


def test_a_cart_email_must_be_an_email_when_given(clock):
    assert CartIn(session_token="s", customer_email=" Ana@Example.com ").customer_email == "Ana@Example.com"
    with pytest.raises(ValidationError) as caught:
        CartIn(session_token="s", customer_email="ana")
    assert messages(caught.value) == {"customer_email": str(EMAIL_INVALID)}


def test_the_currency_is_a_real_code_uppercased_and_empty_means_the_business_one(clock):
    assert CartIn(session_token="s", currency="jpy").currency == "JPY"
    assert CartIn(session_token="s", currency=None).currency is None
    assert CartIn(session_token="s", currency="  ").currency is None
    with pytest.raises(ValidationError) as caught:
        CartIn(session_token="s", currency="XYZ")
    assert messages(caught.value) == {"currency": str(CURRENCY_UNKNOWN)}


def test_the_expiry_must_be_in_the_future_and_a_bare_time_is_the_business_one(clock):
    later = CartIn(session_token="s", expires_at="2026-10-15T10:00:00")
    # Without an offset, the time is Madrid's (UTC+2 in October).
    assert later.expires_at == dt.datetime(2026, 10, 15, 8, 0, tzinfo=dt.UTC)
    with pytest.raises(ValidationError) as caught:
        CartIn(session_token="s", expires_at=(NOW - dt.timedelta(minutes=1)).isoformat())
    assert messages(caught.value) == {"expires_at": str(EXPIRY_PASSED)}


def test_a_cart_input_refuses_a_field_it_does_not_declare(clock):
    with pytest.raises(ValidationError):
        CartIn(session_token="s", hub_id="h1")


def test_a_cart_is_named_by_its_id_its_session_code_or_its_customer():
    assert CartRefIn(cart_id=uuid.uuid7()).session_token is None
    assert CartRefIn(session_token=" sess_1 ").session_token == "sess_1"
    assert CartRefIn(customer="ana@example.com").customer == "ana@example.com"
    with pytest.raises(ValidationError) as caught:
        CartRefIn()
    assert messages(caught.value) == {"": str(SAY_WHICH_CART)}


def test_an_abandonment_reason_is_optional_and_at_most_500_characters():
    assert AbandonIn(session_token="s").reason == ""
    assert AbandonIn(session_token="s", reason="  gone  ").reason == "gone"
    with pytest.raises(ValidationError):
        AbandonIn(session_token="s", reason="x" * 501)


def test_the_cart_list_pages_up_to_100_newest_first():
    params = CartListIn()
    assert (params.limit, params.offset, params.sort) == (50, 0, "-created_at")
    with pytest.raises(ValidationError):
        CartListIn(limit=101)
    with pytest.raises(ValidationError):
        CartListIn(colour="red")
    with pytest.raises(ValidationError):
        CartListIn(sort="-hub_id")


# Lines


def test_a_line_takes_a_quantity_with_three_decimals_and_a_price_in_minor_units():
    data = add_in(quantity="0.5", unit_price=1200, variant_attributes={"size": "M"})
    assert (data.quantity, data.unit_price) == (Decimal("0.5"), 1200)
    assert data.variant_attributes == {"size": "M"}
    assert data.sku == ""


@pytest.mark.parametrize("quantity", ["0", "-1"])
def test_a_line_quantity_must_be_above_zero(quantity):
    with pytest.raises(ValidationError) as caught:
        add_in(quantity=quantity)
    assert messages(caught.value) == {"quantity": str(QUANTITY_NOT_POSITIVE)}


def test_a_quantity_with_more_than_three_decimals_is_refused():
    with pytest.raises(ValidationError) as caught:
        add_in(quantity="0.0005")
    assert set(messages(caught.value)) == {"quantity"}


@pytest.mark.parametrize("price", [-1, MAX_AMOUNT + 1, 12.5])
def test_a_price_is_whole_minor_units_never_negative(price):
    with pytest.raises(ValidationError) as caught:
        add_in(unit_price=price)
    assert set(messages(caught.value)) == {"unit_price"}


@pytest.mark.parametrize("field", ["product_ref", "product_name"])
def test_a_line_names_its_product(field):
    with pytest.raises(ValidationError) as caught:
        add_in(**{field: "  "})
    assert set(messages(caught.value)) == {field}


def test_a_new_quantity_of_zero_removes_the_line_and_a_negative_one_is_refused():
    assert ItemUpdateIn(item_id=uuid.uuid7(), quantity="0").quantity == Decimal("0")
    with pytest.raises(ValidationError):
        ItemUpdateIn(item_id=uuid.uuid7(), quantity="-1")


def test_the_lines_are_listed_by_their_cart():
    assert ItemListIn(session_token="s").sort == "created_at"
    with pytest.raises(ValidationError) as caught:
        ItemListIn()
    assert messages(caught.value) == {"": str(SAY_WHICH_CART)}


# Orders


def test_an_order_email_is_optional_but_must_be_an_email():
    data = CheckoutIn(session_token="s")
    assert data.customer_email is None
    assert (data.shipping_address, data.billing_address) == ({}, None)
    assert CheckoutIn(session_token="s", customer_email="ana@example.com").customer_email == "ana@example.com"
    with pytest.raises(ValidationError) as caught:
        CheckoutIn(session_token="s", customer_email="a@")
    assert messages(caught.value) == {"customer_email": str(EMAIL_INVALID)}


def test_an_address_is_a_set_of_free_fields():
    data = CheckoutIn(
        session_token="s",
        shipping_address={"line1": "Calle Mayor 1", "city": "Madrid"},
    )
    assert data.shipping_address == {"line1": "Calle Mayor 1", "city": "Madrid"}
    with pytest.raises(ValidationError):
        CheckoutIn(session_token="s", shipping_address={"line1": {"nested": "no"}})


def test_an_order_is_named_by_its_id_or_its_number_in_capitals():
    assert OrderRefIn(order_number=" os-20261014-0003 ").order_number == "OS-20261014-0003"
    with pytest.raises(ValidationError) as caught:
        OrderRefIn()
    assert messages(caught.value) == {"": str(SAY_WHICH_ORDER)}


def test_failing_an_order_needs_its_reason():
    assert FailIn(order_number="OS-1", reason=" card declined ").reason == "card declined"
    with pytest.raises(ValidationError) as caught:
        FailIn(order_number="OS-1", reason="   ")
    assert messages(caught.value) == {"reason": str(REASON_REQUIRED)}
    with pytest.raises(ValidationError):
        FailIn(order_number="OS-1", reason="x" * 501)


def test_the_order_list_pages_up_to_100_newest_first():
    params = OrderListIn()
    assert (params.limit, params.offset, params.sort) == (50, 0, "-created_at")
    with pytest.raises(ValidationError):
        OrderListIn(limit=0)


@pytest.mark.parametrize("quantity", [str(MAX_QUANTITY + 1), "1000000000000"])
def test_a_quantity_above_the_cap_is_refused_before_any_sum(quantity):
    # Review (BAJO): an unbounded quantity times a price overflowed the database's bigint (a 500).
    with pytest.raises(ValidationError) as caught:
        add_in(quantity=quantity)
    assert set(messages(caught.value)) == {"quantity"}
    with pytest.raises(ValidationError):
        ItemUpdateIn(item_id=uuid.uuid7(), quantity=quantity)


def test_the_cap_itself_is_a_quantity():
    assert add_in(quantity=str(MAX_QUANTITY)).quantity == Decimal(MAX_QUANTITY)


# Personal data (CART_CHECKOUT-F14)


def test_a_customer_to_erase_is_named_by_an_exact_email():
    assert CustomerEraseIn(email=" Ana@Example.com ").email == "Ana@Example.com"
    for wrong in ("", "ana"):
        with pytest.raises(ValidationError) as caught:
            CustomerEraseIn(email=wrong)
        assert set(messages(caught.value)) == {"email"}
