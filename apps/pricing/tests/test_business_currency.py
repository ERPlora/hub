"""Price lists in the business's currency (flow pricing-business-currency): its country's, as ``base.business.get``
reads it from this hub's registry (APP-BASE-6), never a euro fixed in the app. A business in Poland prices its lines
with its general list in zlotys (one in euros never competes: currencies are not compared without converting), makes
a zloty list the general one and not a euro one, and a list created without a currency is in zlotys; one in Spain
stays in euros; each hub its own. A list already stored keeps its currency."""

import pytest
from live.context import Scope
from live.errors import Conflict, InvalidPayload
from live.operations import get

from apps.pricing.models import PriceList
from base.models import Hub

from .conftest import B, ctx_for, make_customer, make_group, make_item, make_list, make_product

pytestmark = pytest.mark.django_db


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def run(name, data, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


def refused(error, name, data, ctx=None):
    with pytest.raises(error) as caught:
        run(name, data, ctx)
    return caught.value


def resolve(ctx=None, **data):
    return run("pricing.price.resolve", data, ctx)


# The price of a line (PRICING-F13)


def test_a_business_in_poland_prices_a_line_with_its_general_list_in_zlotys():
    business_in("PL")
    product = make_product("Shampoo", "SH-1", price=1250)
    make_item(make_list("GEN", currency="PLN", is_default=True), product, price=900)
    line = resolve(product_id=str(product.id))
    assert (line.unit_price, line.price_list_code, line.currency) == (900, "GEN", "PLN")


def test_in_poland_a_list_in_euros_never_competes_with_the_zloty_ones():
    # 5,00 € is not cheaper than 9,00 zł: prices of different currencies are never compared (gh:pricing#7).
    business_in("PL")
    product = make_product("Shampoo", "SH-1", price=1250)
    vip = make_group("VIP")
    lucia = make_customer(groups=[vip])
    make_item(make_list("GEN", currency="PLN", is_default=True), product, price=900)
    make_item(make_list("EURO", currency="EUR", customer_group_id=vip.id), product, price=500)
    line = resolve(product_id=str(product.id), customer_id=str(lucia.id))
    assert (line.unit_price, line.price_list_code, line.currency) == (900, "GEN", "PLN")


def test_in_poland_a_line_without_lists_is_in_zlotys():
    business_in("PL")
    product = make_product("Shampoo", "SH-1", price=1250)
    line = resolve(product_id=str(product.id))
    assert (line.unit_price, line.price_list_id, line.currency) == (1250, None, "PLN")


def test_an_api_key_with_only_the_view_permission_prices_in_the_business_s_currency():
    business_in("PL")
    product = make_product("Shampoo", "SH-1", price=1250)
    line = resolve(ctx_for(permissions={"pricing.view"}), product_id=str(product.id))
    assert line.currency == "PLN"


def test_a_business_in_spain_still_prices_in_euros():
    business_in("ES")
    product = make_product("Shampoo", "SH-1", price=1250)
    make_item(make_list("GEN", currency="EUR", is_default=True), product, price=900)
    line = resolve(product_id=str(product.id))
    assert (line.unit_price, line.currency) == (900, "EUR")


# The general list (PRICING-F04) and a new list (PRICING-F02)


def test_in_poland_a_zloty_list_becomes_the_general_one_and_a_euro_one_does_not():
    business_in("PL")
    make_list("ZLOTY", currency="PLN")
    make_list("EURO", currency="EUR")
    assert run("pricing.price_list.set_default", {"price_list": "ZLOTY"}).is_default is True
    error = refused(Conflict, "pricing.price_list.set_default", {"price_list": "EURO"})
    assert error.code == "pricing.default_currency" and "PLN" in str(error)
    assert list(PriceList.objects.filter(is_default=True).values_list("code", flat=True)) == ["ZLOTY"]


def test_in_poland_a_list_created_without_currency_is_in_zlotys():
    business_in("PL")
    row = run("pricing.price_list.create", {"code": "VIP", "name": "VIP"})
    assert row.currency == "PLN" and PriceList.objects.get(code="VIP").currency == "PLN"


def test_in_poland_a_general_list_is_created_in_zlotys_and_never_in_euros():
    business_in("PL")
    assert run("pricing.price_list.create", {"code": "GEN", "name": "General", "is_default": True}).currency == "PLN"
    error = refused(InvalidPayload, "pricing.price_list.create", {"code": "EU", "name": "EU", "currency": "EUR", "is_default": True})
    assert set(error.fields) == {"is_default"} and "PLN" in error.fields["is_default"]
    assert not PriceList.objects.filter(code="EU").exists()


def test_in_poland_the_general_list_cannot_move_to_euros():
    business_in("PL")
    make_list("GEN", currency="PLN", is_default=True)
    error = refused(InvalidPayload, "pricing.price_list.update", {"price_list": "GEN", "currency": "EUR"})
    assert set(error.fields) == {"currency"} and "PLN" in error.fields["currency"]
    assert PriceList.objects.get(code="GEN").currency == "PLN"


def test_a_business_in_spain_still_creates_its_lists_in_euros():
    business_in("ES")
    assert run("pricing.price_list.create", {"code": "VIP", "name": "VIP"}).currency == "EUR"
    make_list("ZLOTY", currency="PLN")
    assert refused(Conflict, "pricing.price_list.set_default", {"price_list": "ZLOTY"}).code == "pricing.default_currency"


def test_a_list_stored_before_keeps_its_currency_when_the_business_moves():
    # No rewriting of what is stored: a list in euros of a business that moves to Poland stays in euros.
    make_list("OLD", currency="EUR")
    business_in("PL")
    run("pricing.price_list.update", {"price_list": "OLD", "name": "Old prices"})
    assert PriceList.objects.get(code="OLD").currency == "EUR"


def test_each_hub_creates_its_lists_in_its_own_business_s_currency():
    business_in("PL", "a")
    business_in("ES", "b")
    assert run("pricing.price_list.create", {"code": "VIPA", "name": "VIP"}).currency == "PLN"
    assert run("pricing.price_list.create", {"code": "VIPB", "name": "VIP"}, ctx_for(scope=B)).currency == "EUR"


@pytest.mark.parametrize(("country", "currency"), [("PL", "PLN"), ("ES", "EUR")])
def test_erploras_own_hub_prices_in_the_currency_of_its_issuer_s_country(settings, country, currency):
    # Phase 1's platform hub has no business on erplora.com (no registry row, create_platform_hub): its lists keep
    # the currency of its issuer's country, as its sales and invoices do (hub#286), never a 404 for want of a business.
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = country
    platform = ctx_for(scope=Scope("host", "erplora"))
    product = make_product("Shampoo", "SH-1", price=1250)
    assert resolve(platform, product_id=str(product.id)).currency == currency
    assert run("pricing.price_list.create", {"code": "VIP", "name": "VIP"}, platform).currency == currency
