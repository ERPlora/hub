"""The business's own data as the Hub shows it (APP-BASE-6, BASE-G97…G99): what ``base.business`` derives and names.

The SaaS owns the country, the time zone and the language (it pushes them in ``PUT /internal/hubs/{id}``); the
currency is not chosen anywhere: it is the one the country pays in (CLDR, through Babel), as Square, SumUp or Zettle
fix it by the merchant's country. A business without a country (a demo) is in euros, ERPlora's market.
"""

import datetime as dt

import pytest

from base import business

TODAY = dt.date(2026, 10, 24)


@pytest.mark.parametrize(
    ("country", "currency"),
    [("ES", "EUR"), ("PT", "EUR"), ("FR", "EUR"), ("PL", "PLN"), ("SE", "SEK"), ("DK", "DKK"), ("es", "EUR")],
)
def test_the_currency_is_the_one_the_country_pays_in(country, currency):
    assert business.currency_of(country, today=TODAY) == currency


@pytest.mark.parametrize("country", ["", "ZZ", "X"])
def test_without_a_country_it_knows_the_currency_is_the_euro(country):
    assert business.currency_of(country, today=TODAY) == "EUR"


def test_a_currency_that_has_no_cents_says_so():
    assert (business.currency_decimals("EUR"), business.currency_decimals("HUF"), business.currency_decimals("JPY")) == (
        2,
        2,
        0,
    )


@pytest.mark.parametrize(
    ("language", "country", "currency", "spoken"),
    [
        ("es", "España", "EUR · Euro", "Español"),
        ("en", "Spain", "EUR · Euro", "Spanish"),
    ],
)
def test_the_names_are_in_the_person_s_language_with_a_capital(language, country, currency, spoken):
    assert business.country_name("ES", language) == country
    assert business.currency_label("EUR", language) == currency
    assert business.language_name("es", language) == spoken


def test_another_currency_is_named_in_the_person_s_language():
    assert business.currency_label("PLN", "es") == "PLN · Esloti polaco"
    assert business.currency_label("PLN", "en") == "PLN · Polish Zloty"


def test_a_code_it_does_not_know_is_shown_as_it_is():
    assert (business.country_name("QQ", "es"), business.language_name("xx", "es")) == ("QQ", "xx")
    assert (business.country_name("", "es"), business.language_name("", "es")) == ("", "")
