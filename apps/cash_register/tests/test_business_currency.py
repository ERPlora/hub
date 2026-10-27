"""The drawer counts in the business's currency (flow business-currency): its country's, as ``base.business.get``
reads it from this hub's registry (APP-BASE-6), never a euro fixed in the app nor a call to erplora.com. A business in
Poland counts zlotys with their notes and coins; one in Spain, euros; each hub its own. An API key holds only the
permission of the operation it opened, and still gets the business's currency."""

import pytest
from live.context import OperationContext, Scope
from live.errors import InvalidPayload

from apps.cash_register.tests.conftest import A, B, ctx_for, open_session, run
from apps.printing.models import PrintJob
from base.models import Hub

pytestmark = pytest.mark.django_db


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def test_a_business_in_poland_counts_in_zlotys_with_their_notes_and_coins():
    business_in("PL")
    currency = run("cash_register.currency.get")
    assert (currency.currency, currency.decimals) == ("PLN", 2)
    assert currency.bills == ["500", "200", "100", "50", "20", "10"]
    assert currency.coins == ["5", "2", "1", "0.50", "0.20", "0.10", "0.05", "0.02", "0.01"]


def test_a_business_in_spain_still_counts_in_euros():
    business_in("ES")
    currency = run("cash_register.currency.get")
    assert (currency.currency, currency.decimals) == ("EUR", 2)


def test_an_api_key_with_only_its_operation_s_permission_gets_the_business_s_currency():
    business_in("PL")
    key = OperationContext(scope=A, actor="key", permissions=frozenset({"cash_register.view_session"}))
    assert run("cash_register.currency.get", {}, key).currency == "PLN"


def test_each_hub_counts_in_its_own_business_s_currency():
    business_in("PL", "a")
    business_in("ES", "b")
    assert run("cash_register.currency.get").currency == "PLN"
    assert run("cash_register.currency.get", {}, ctx_for(scope=B)).currency == "EUR"


def test_a_count_takes_the_zloty_s_coins_and_refuses_the_euro_s_notes():
    business_in("PL")
    open_session(10000)
    # 5 zł is a coin; 5 € is a note, which a Polish drawer does not hold.
    count = run("cash_register.count.add", {"type": "closing", "denominations": {"coins": {"5": 2}}})
    assert (count.denominations, count.total) == ({"coins": {"5": 2}}, 1000)
    with pytest.raises(InvalidPayload):
        run("cash_register.count.add", {"type": "closing", "denominations": {"bills": {"5": 1}}})


def test_the_printed_report_takes_the_decimals_of_the_business_s_currency():
    # The yen has no cents: 10000 is ¥10,000 on the paper, not 100.00.
    business_in("JP")
    run("printing.printer.create", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"})
    session = open_session(10000)
    printed = run("cash_register.session.print", {"session_id": str(session.id)})
    document = PrintJob.objects.get(pk=printed.job_id).document
    assert (document["decimals"], document["opening_balance"]) == (0, 10000.0)


@pytest.mark.parametrize(("country", "currency", "decimals", "three_ones"), [("PL", "PLN", 2, 300), ("JP", "JPY", 0, 3)])
def test_erploras_own_hub_counts_in_the_currency_of_its_issuer_s_country(settings, country, currency, decimals, three_ones):
    # Phase 1's platform hub has no business on erplora.com (no registry row, create_platform_hub) and every module is on
    # in it (base.activation.is_platform): its drawer counts and prints in the currency of its issuer's country, as its
    # sales and invoices do (hub#286), never a 404 because there is no business to read.
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = country
    platform = ctx_for(scope=Scope("host", "erplora"))
    read = run("cash_register.currency.get", {}, platform)
    assert (read.currency, read.decimals) == (currency, decimals)
    run(
        "printing.printer.create",
        {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"},
        platform,
    )
    session = run("cash_register.session.open", {"opening_balance": 10000}, platform)
    count = run("cash_register.count.add", {"type": "closing", "denominations": {"coins": {"1": 3}}}, platform)
    assert count.total == three_ones
    printed = run("cash_register.session.print", {"session_id": str(session.id)}, platform)
    assert PrintJob.objects.get(pk=printed.job_id).document["decimals"] == decimals
