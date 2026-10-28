"""Carts and orders in the business's currency (flow cart-checkout-business-currency): a cart created without a
currency is born in the business's, its country's as ``base.business.get`` reads it from this hub's registry
(``base.operations.business_currency``, BASE-F50), never a euro fixed in the app nor in the model. Each cart and
each order keeps its own currency (a record is never rewritten) and says the decimals the server counts it in (CLDR:
2 in PLN and in HUF, 0 in JPY), so the screens paint «42,50 zł» or «¥150», never the browser's Intl decimals (which
gives the forint none)."""

import pytest
from live.context import OperationContext, Scope
from live.models import OutboxEvent

from apps.cart_checkout.models import Cart, Order
from base.models import Hub

from .conftest import A, B, ctx_for, make_cart, make_item, make_order

pytestmark = pytest.mark.django_db


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def run(name: str, data: dict, ctx: OperationContext | None = None):
    from live.operations import get

    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


def created_currency() -> str:
    return OutboxEvent.objects.filter(name="cart_checkout.cart.created").latest("id").payload["currency"]


@pytest.mark.parametrize(("country", "currency"), [("PL", "PLN"), ("SE", "SEK"), ("HU", "HUF"), ("ES", "EUR")])
def test_a_cart_without_a_currency_is_born_in_the_currency_of_the_business_s_country(country, currency):
    # cart_checkout#32, #34: a hub that did not work in euros got euro carts from the screen, the assistant and the API.
    business_in(country)
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1"})
    assert cart.currency == currency
    assert Cart.objects.get(pk=cart.id).currency == currency
    assert created_currency() == currency


def test_a_currency_the_customer_asked_for_still_wins():
    business_in("PL")
    assert run("cart_checkout.cart.create", {"session_token": "sess_1", "currency": "eur"}).currency == "EUR"


def test_each_hub_creates_its_carts_in_its_own_business_s_currency():
    business_in("PL", "a")
    business_in("ES", "b")
    assert run("cart_checkout.cart.create", {"session_token": "sess_a"}).currency == "PLN"
    assert run("cart_checkout.cart.create", {"session_token": "sess_b"}, ctx_for(scope=B)).currency == "EUR"


def test_an_api_key_with_only_the_cart_permission_gets_the_business_s_currency():
    business_in("PL")
    key = OperationContext(scope=A, actor="key", permissions=frozenset({"cart_checkout.manage_cart"}))
    assert run("cart_checkout.cart.create", {"session_token": "sess_1"}, key).currency == "PLN"


@pytest.mark.parametrize(("country", "currency"), [("PL", "PLN"), ("JP", "JPY")])
def test_erploras_own_hub_creates_its_carts_in_the_currency_of_its_issuer_s_country(settings, country, currency):
    # Phase 1's platform hub has no business on erplora.com and every module is on in it: its carts go in the
    # currency of its issuer's country, as its sales and invoices do, never a 404 because there is no business to read.
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = country
    platform = ctx_for(scope=Scope("host", "erplora"))
    assert run("cart_checkout.cart.create", {"session_token": "sess_1"}, platform).currency == currency


def test_the_model_invents_no_currency():
    # Only the operation knows the business: a row built without one has none, never a silent euro.
    assert Cart().currency == ""
    assert Order().currency == ""


def money_of_cart(cart) -> tuple:
    """(currency, currency_decimals) of ``cart`` as the list, its read and a write that gives it back say them."""
    listed = [row for row in run("cart_checkout.cart.list", {"limit": 100}).rows if row.id == cart.id]
    read = run("cart_checkout.cart.get", {"cart_id": str(cart.id)})
    written = run("cart_checkout.cart.mark_abandoned", {"cart_id": str(cart.id)})
    said = {(row.currency, row.currency_decimals) for row in [*listed, read, written]}
    assert len(said) == 1, said
    return said.pop()


@pytest.mark.parametrize(("currency", "decimals"), [("PLN", 2), ("JPY", 0), ("HUF", 2), ("EUR", 2)])
def test_a_cart_says_its_currency_and_the_decimals_the_server_counts_it_in(currency, decimals):
    cart = make_cart("sess_1", currency=currency)
    assert money_of_cart(cart) == (currency, decimals)


@pytest.mark.parametrize(("currency", "decimals"), [("PLN", 2), ("JPY", 0), ("HUF", 2)])
def test_an_order_says_its_currency_and_the_decimals_the_server_counts_it_in(currency, decimals):
    order = make_order(make_cart("sess_1", currency=currency), currency=currency)
    [listed] = [row for row in run("cart_checkout.order.list", {"limit": 100}).rows if row.id == order.id]
    read = run("cart_checkout.order.get", {"order_id": str(order.id)})
    assert {(listed.currency, listed.currency_decimals), (read.currency, read.currency_decimals)} == {(currency, decimals)}


def test_a_cart_and_its_order_keep_their_currency_when_the_business_s_changes():
    # A record is never rewritten: a cart born in euros stays in euros, and its order is initiated in them.
    business_in("ES")
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1"})
    run(
        "cart_checkout.item.add",
        {"cart_id": str(cart.id), "product_ref": "p-1", "product_name": "Champú", "quantity": "1", "unit_price": 1250},
    )
    business_in("PL")
    order = run("cart_checkout.checkout.initiate", {"cart_id": str(cart.id), "customer_email": "ana@example.com"})
    assert (order.currency, order.currency_decimals, order.total_amount) == ("EUR", 2, 1250)
    assert money_of_cart(Cart.objects.get(pk=cart.id))[0] == "EUR"


def test_a_cart_in_yen_counts_its_lines_in_whole_yen():
    cart = make_cart("sess_1", currency="JPY")
    make_item(cart, unit_price=150)
    read = run("cart_checkout.cart.get", {"cart_id": str(cart.id)})
    assert (read.currency, read.currency_decimals, read.items[0].unit_price) == ("JPY", 0, 150)
