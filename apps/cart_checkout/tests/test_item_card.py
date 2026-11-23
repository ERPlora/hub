"""The assistant's card for a line added to a cart (``cart_checkout.item.add``). A normal card is one line with its
first three data, and the cart, the reference and the name left the quantity and the price out: «Pedro QA · BRAVAS ·
Bravas (ración)» did not say whether it was 4 at 6,00 € or 40 at 0,60 € (hub#2291). In Cart & checkout whoever asks
says the quantity and the price, so the card says them beside the product, as the line will keep them."""

import pytest
from live.operations import get

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB

ADD = "cart_checkout.item.add"
BRAVAS = {"product_ref": "BRAVAS", "product_name": "Bravas (ración)", "quantity": "4", "unit_price": 600}
#: A cart created without a currency is in the business's, euros here, and its card reads it from the cart.
EUROS = {"money": {"currency": "EUR", "decimals": 2}}


@pytest.fixture
def pedro():
    op = get("cart_checkout.cart.create")
    data = {"session_token": "sess_pedro", "customer_name": "Pedro QA"}
    return op(ctx_for(), op.input.model_validate(data))


def drawn(arguments: dict, language: str = "es") -> list[dict]:
    from base import assistant

    return assistant.cards.card(get(ADD), arguments, language, ctx_for())["fields"]


def its_line(fields: list[dict]) -> list[dict]:
    """What a normal card's one line shows (``cardLine`` of @erplora/ui): its first three data that are not empty."""
    return [field for field in fields if field["kind"] != "empty"][:3]


def line_of(fields: list[dict]) -> dict:
    return next(field for field in fields if field["name"] == "item")


@pytest.mark.parametrize(("language", "label"), [("es", "Línea del carrito"), ("en", "Cart line")])
def test_its_line_says_the_cart_and_the_product_with_how_many_and_the_price_of_one(pedro, language, label):
    shown = its_line(drawn({"customer": "Pedro QA", **BRAVAS}, language))
    assert [field["name"] for field in shown] == ["customer", "item", "product_ref"]
    assert (shown[0]["value"], shown[2]["value"]) == ("Pedro QA", "BRAVAS")
    assert {key: shown[1][key] for key in ("label", "kind", "value")} == {
        "label": label,
        "kind": "object",
        "value": {"product_name": "Bravas (ración)", "quantity": "4", "unit_price": {"kind": "money", "value": 600, **EUROS}},
    }


def test_the_rest_of_what_it_sends_follows_the_line(pedro):
    fields = drawn({"session_token": "sess_pedro", **BRAVAS, "sku": "BRV-1", "variant_attributes": {"size": "XL"}})
    assert [field["name"] for field in fields] == ["session_token", "item", "product_ref", "sku", "variant_attributes"]
    assert {field["name"]: field["value"] for field in fields}["product_ref"] == "BRAVAS"


@pytest.mark.parametrize(
    ("sent", "language", "said"),
    [
        ("0.5", "es", "0,5"),
        ("0.5", "en", "0.5"),
        ("1250", "es", "1.250"),
        ("1250", "en", "1,250"),
        ("4.000", "es", "4"),
        (2, "es", "2"),
    ],
)
def test_the_quantity_is_written_as_the_screens_write_one(pedro, sent, language, said):
    fields = drawn({"customer": "Pedro QA", **BRAVAS, "quantity": sent}, language)
    assert line_of(fields)["value"]["quantity"] == said


def test_the_price_is_in_the_currency_of_its_cart():
    op = get("cart_checkout.cart.create")
    op(ctx_for(), op.input.model_validate({"session_token": "sess_ann", "customer_name": "Ann", "currency": "USD"}))
    fields = drawn({"customer": "Ann", **BRAVAS})
    assert line_of(fields)["value"]["unit_price"] == {
        "kind": "money", "value": 600, "money": {"currency": "USD", "decimals": 2},
    }


def test_data_the_write_refuses_keep_the_card_as_they_came(pedro):
    fields = drawn({"customer": "Pedro QA", **BRAVAS, "quantity": "0"})
    assert [field["name"] for field in fields] == ["customer", "product_ref", "product_name", "quantity", "unit_price"]


@pytest.mark.parametrize("said", ["Nadie", "Pedro"], ids=["none", "several"])
def test_a_cart_it_cannot_tell_prices_nothing_in_a_currency_made_up(pedro, said):
    op = get("cart_checkout.cart.create")
    op(ctx_for(), op.input.model_validate({"session_token": "sess_ruiz", "customer_name": "Pedro Ruiz"}))
    fields = drawn({"customer": said, **BRAVAS})
    assert "item" not in {field["name"] for field in fields}
    assert {field["name"]: field["kind"] for field in fields}["unit_price"] != "money"
