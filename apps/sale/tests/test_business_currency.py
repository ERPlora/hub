"""Sales charges in the business's currency (flow business-currency): its country's, as ``base.business.get`` reads it
from this hub's registry (APP-BASE-6), never a euro fixed in the app nor a call to erplora.com. A sale keeps the
currency it was charged in: what was charged is shown, refused and printed with its own, never rewritten when the
business's changes. Its decimals are the ones the server counts (CLDR): the yen has none, the forint two. A business
in Spain still charges in euros, with its legal limits in euros as the law writes them."""

import pytest
from django.utils import translation
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict

from apps.printing.models import PrintJob
from apps.sale.models import Sale
from apps.sale.queries import money_text
from apps.sale.tests.conftest import A, B, ctx_for, run
from base.models import Hub

pytestmark = pytest.mark.django_db

ISSUER = {
    "legal_name": "Bar Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


@pytest.fixture
def coffee(product):
    product("Coffee", "COF", 150, "restaurant.drink")


@pytest.fixture
def till(db):
    return run("printing.printer.create", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"})


def charge(key: str = "sale-currency-1", ctx: OperationContext | None = None, sku: str = "COF", **more):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "lines": [{"product": sku, "quantity": "2"}], "payments": [{"method": "card"}], **more},
        ctx,
    )


def coffee_in(scope: Scope, sku: str) -> None:
    """A coffee of 150 in ``scope``'s catalog (phase 1: one database, a SKU is the deployment's)."""
    data = {"name": "Coffee", "sku": sku, "price": 150, "tax_category_key": "restaurant.drink"}
    run("inventory.product.create", data, system_context(scope))


def jobs() -> list[PrintJob]:
    return list(PrintJob.objects.order_by("created_at", "id"))


# ── The sale keeps the business's currency ───────────────────────────────────────────────────────


def test_a_business_in_poland_charges_in_zlotys(coffee):
    business_in("PL")
    sale = charge()
    assert sale.currency == "PLN" and Sale.objects.get(pk=sale.id).currency == "PLN"
    detail = run("sale.sale.get", {"sale_id": str(sale.id)})
    assert (detail.currency, detail.currency_decimals, detail.total) == ("PLN", 2, 300)


def test_a_business_in_spain_still_charges_in_euros(coffee):
    business_in("ES")
    sale = charge()
    assert (sale.currency, sale.currency_decimals) == ("EUR", 2)


def test_each_hub_charges_in_its_own_business_s_currency(product):
    business_in("PL", "a")
    business_in("ES", "b")
    product("Coffee", "COF", 150, "restaurant.drink")
    coffee_in(B, "COF-B")
    assert charge("sale-currency-a").currency == "PLN"
    assert charge("sale-currency-b", ctx_for(scope=B), sku="COF-B").currency == "EUR"


def test_an_api_key_with_only_its_operation_s_permission_charges_in_the_business_s_currency(coffee):
    business_in("PL")
    # A key that charges holds what an employee charging holds, not the Home's permission that reads the business.
    charging = ctx_for("hub_employee").permissions - {"base.view_home"}
    key = OperationContext(scope=A, actor="key", permissions=charging)
    assert charge(ctx=key).currency == "PLN"


@pytest.mark.parametrize(("country", "currency", "decimals"), [("PL", "PLN", 2), ("JP", "JPY", 0), ("HU", "HUF", 2)])
def test_a_sale_says_the_decimals_of_its_currency_as_the_server_counts_them(coffee, country, currency, decimals):
    # Intl gives the forint no decimals; the server (CLDR) two: a screen paints with these, never the browser's.
    business_in(country)
    sale = charge()
    assert (sale.currency, sale.currency_decimals) == (currency, decimals)
    (row,) = run("sale.sale.list", {}).rows
    assert (row.currency, row.currency_decimals) == (currency, decimals)


def test_a_charged_sale_keeps_its_currency_when_the_business_s_changes(coffee):
    business_in("PL")
    zlotys = charge("sale-currency-pl")
    business_in("ES")
    euros = charge("sale-currency-es")
    assert run("sale.sale.get", {"sale_id": str(zlotys.id)}).currency == "PLN"
    assert euros.currency == "EUR"
    rows = {row.number: row.currency for row in run("sale.sale.list", {}).rows}
    assert rows == {zlotys.number: "PLN", euros.number: "EUR"}


@pytest.mark.parametrize("country", ["PL", "JP"])
def test_erploras_own_hub_charges_in_the_currency_of_its_issuer_s_country(settings, country):
    # Phase 1's platform hub has no business on erplora.com (no registry row, create_platform_hub): its sales keep the
    # currency of its issuer's country, as its invoices do (hub#273), and the charge never fails for it.
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = country
    platform = Scope("host", "erplora")
    coffee_in(platform, "COF-ERPLORA")
    sale = charge(ctx=ctx_for(scope=platform), sku="COF-ERPLORA")
    assert sale.currency == {"PL": "PLN", "JP": "JPY"}[country]


# ── What a sale says and prints, in its currency ─────────────────────────────────────────────────


def test_money_in_a_sentence_takes_the_decimals_and_the_sign_of_its_currency():
    with translation.override("en"):
        assert money_text(5003, "JPY") == "¥5,003"
        assert money_text(123456, "PLN") == "PLN\xa01,234.56"
        assert money_text(None, "PLN") == "—"
    with translation.override("es"):
        assert money_text(123456, "EUR") == "1.234,56\xa0€"


def test_a_refused_refund_says_the_amounts_in_the_sale_s_currency(coffee):
    business_in("PL")
    sale = charge()
    card = str(sale.payments[0].id)
    with translation.override("en"), pytest.raises(Conflict) as refusal:
        run("sale.sale.refund", {"sale_id": str(sale.id), "reason": "returned", "allocations": [{"payment_id": card, "amount": 400}], "lines": []})
    assert refusal.value.code == "sale.refund_exceeds_tender"
    assert "PLN\xa04.00" in refusal.value.message and "PLN\xa03.00" in refusal.value.message and "€" not in refusal.value.message


def test_a_service_s_range_is_said_in_the_business_s_currency(db):
    business_in("JP")
    colour = run(
        "service.service.create",
        {"name": "Colour", "pricing_type": "from", "price": 6000, "min_price": 5000, "max_price": 9000, "tax_category_key": "service.generic"},
        system_context(A),
    )
    order = run("sale.order.open", {})
    with translation.override("en"), pytest.raises(Conflict) as refusal:
        run("sale.order.add_service_line", {"order_id": str(order.id), "service_id": str(colour.id), "unit_price": 3000})
    assert refusal.value.code == "sale.service_price_out_of_range"
    assert "¥5,000" in refusal.value.message and "¥9,000" in refusal.value.message


def test_the_cash_limit_of_spain_is_still_said_in_euros(product):
    # Ley 7/2012 writes it in euros: a business of Spain is told «1.000,00 €» whatever language it reads.
    business_in("ES")
    product("Gold", "GLD", 100000, "product.generic")
    with translation.override("es"), pytest.raises(Conflict) as refusal:
        run("sale.sale.complete", {"idempotency_key": "sale-gold", "lines": [{"product": "GLD"}], "payments": [{"method": "cash"}]})
    assert refusal.value.code == "sale.cash_limit_exceeded" and "1.000,00\xa0€" in refusal.value.message


def test_the_bill_on_paper_takes_the_decimals_of_the_business_s_currency(coffee, till):
    # The yen has no cents: two coffees of 150 are ¥300 on the paper, not 3.00.
    business_in("JP")
    order = run("sale.order.open", {"lines": [{"product": "COF", "quantity": "2"}], "label": "Table 4"})
    run("sale.order.print_bill", {"order_id": str(order.id)})
    (job,) = jobs()
    assert (job.document["decimals"], job.document["total"]) == (0, 300.0)


def test_the_receipt_prints_in_the_currency_of_its_sale_even_after_the_business_s_changes(coffee, till):
    run("invoice.issuer.update", ISSUER)
    business_in("JP")
    sale = charge()
    business_in("ES")
    run("sale.sale.print", {"sale_id": str(sale.id), "duplicate": True})
    receipt, copy = jobs()
    assert (receipt.document["decimals"], receipt.document["total"]) == (0, 300.0)
    assert (copy.document["decimals"], copy.document["total"]) == (0, 300.0)


def test_what_a_sale_can_give_back_is_said_in_its_own_currency(coffee):
    # The refund screen paints what each tender has left with the sale's money, whatever the business's is now.
    business_in("JP")
    sale = charge()
    business_in("ES")
    options = run("sale.refund.options", {"sale_id": str(sale.id)})
    assert (options.currency, options.currency_decimals, options.refundable_total) == ("JPY", 0, 300)
