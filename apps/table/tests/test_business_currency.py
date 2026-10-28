"""What a check charged, in the currency it was charged in (flow table-business-currency): Sales charges in the
business's currency (its country's, ``base.business.get``) and each sale keeps it, never rewritten; a check says
that currency and the decimals the server counts it in (CLDR: 2 in PLN, 0 in JPY), so the screens paint «42,50 zł»
or «¥150», never a euro fixed in the app nor the browser's Intl decimals. Nothing charged says no currency."""

import pytest

from base.models import Hub

from .conftest import (
    add_line,
    charge,
    make_session,
    make_table,
    make_zone,
    open_check,
    run,
)

pytestmark = pytest.mark.django_db


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


def seated(number: str = "4"):
    """A check of Sales at table ``number``."""
    order = open_check(f"Table {number}")
    return make_session(make_table(number, zone=make_zone()), order_id=order.id)


def money(session) -> tuple:
    """(paid_total, currency, currency_decimals) of ``session`` as the list and its read say them."""
    row = run("table.session.get", {"id": str(session.id)})
    [listed] = [r for r in run("table.session.list", {"limit": 100}).rows if r.id == session.id]
    said = (row.paid_total, row.currency, row.currency_decimals)
    assert (listed.paid_total, listed.currency, listed.currency_decimals) == said
    return said


@pytest.mark.parametrize(
    ("country", "currency", "decimals"),
    [("ES", "EUR", 2), ("PL", "PLN", 2), ("JP", "JPY", 0)],
)
def test_a_charged_check_says_the_currency_it_was_charged_in_and_its_decimals(coffee, country, currency, decimals):
    business_in(country)
    session = seated()
    add_line(session.order_id, coffee)
    charge(session.order_id, key=f"currency-{country}")
    assert money(session) == (150, currency, decimals)


def test_nothing_charged_says_no_currency_and_a_voided_charge_takes_it_away(coffee):
    business_in("PL")
    session = seated()
    assert money(session) == (None, None, None)
    first = add_line(session.order_id, coffee).lines[0]
    add_line(session.order_id, coffee)
    sale = charge(session.order_id, key="currency-void", line_ids=[first.id])
    assert money(session) == (150, "PLN", 2)
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    assert money(session) == (None, None, None)


def test_what_was_charged_keeps_its_currency_when_the_business_s_changes(coffee):
    # A record is never rewritten: charged in euros, the check still says euros after the country moves.
    business_in("ES")
    session = seated()
    add_line(session.order_id, coffee)
    charge(session.order_id, key="currency-kept")
    business_in("PL")
    assert money(session) == (150, "EUR", 2)


def test_another_hub_s_country_does_not_change_this_one_s_check(coffee):
    business_in("PL", "a")
    business_in("JP", "b")
    session = seated()
    add_line(session.order_id, coffee)
    charge(session.order_id, key="currency-hub-b")
    assert money(session) == (150, "PLN", 2)
