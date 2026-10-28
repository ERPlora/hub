"""The business's own data as the Hub shows it (APP-BASE-6, BASE-G97…G99): what ``base.business`` derives and names.

The SaaS owns the country, the time zone and the language (it pushes them in ``PUT /internal/hubs/{id}``); the
currency is not chosen anywhere: it is the one the country pays in (CLDR, through Babel), as Square, SumUp or Zettle
fix it by the merchant's country. A business without a country (a demo) is in euros, ERPlora's market.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import translation

from base import business

TODAY = dt.date(2026, 10, 24)


@pytest.mark.parametrize(
    ("country", "currency"),
    [("ES", "EUR"), ("PT", "EUR"), ("FR", "EUR"), ("PL", "PLN"), ("SE", "SEK"), ("DK", "DKK"), ("es", "EUR")],
)
def test_the_currency_is_the_one_the_country_pays_in(country, currency):
    assert business.currency_of(country, today=TODAY) == currency


def test_bulgaria_pays_in_euros_since_2026_though_the_cldr_of_babel_still_says_lev():
    # Bulgaria adopted the euro on 1 January 2026 (Council decision of 8 July 2025); Babel 2.18's CLDR has no end to BGN.
    assert business.currency_of("BG", today=TODAY) == "EUR"
    assert business.currency_of("BG", today=dt.date(2025, 12, 31)) == "BGN"


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


#: What the browser writes for the same amount (``new Intl.NumberFormat(language, {style: "currency", currency})``, Node
#: 26), copied as it prints: a currency written in letters is kept off the figure by a no-break space (U+00A0, CLDR's
#: currency spacing), a sign of its own («€», «¥», «$») touches it. Babel's ``format_currency`` skips that spacing and
#: glues «PLN15.50». In Spanish the thousands are grouped from four digits, as every screen of the Hub paints them
#: (hub#1090), where Intl's default would not.
AS_INTL = [
    (1550, "PLN", "en", "PLN\xa015.50"),
    (1550, "CHF", "en", "CHF\xa015.50"),
    (1550, "EUR", "en", "€15.50"),
    (1550, "EUR", "es", "15,50\xa0€"),
    (1550, "PLN", "es", "15,50\xa0PLN"),
    (1500, "JPY", "en", "¥1,500"),
    (-1550, "PLN", "en", "-PLN\xa015.50"),
    (123456, "PLN", "en", "PLN\xa01,234.56"),
    (-123456, "CHF", "en", "-CHF\xa01,234.56"),
    (-123456, "PLN", "es", "-1.234,56\xa0PLN"),
    (-1550, "USD", "en", "-$15.50"),
    (1550, "MXN", "en", "MX$15.50"),
    # A locale whose code follows the figure with no space in its pattern (Khmer, Luba-Katanga): spaced too.
    (1550, "PLN", "km", "15.50\xa0PLN"),
    (1550, "PLN", "lu", "15,50\xa0PLN"),
]


@pytest.mark.parametrize(("cents", "currency", "language", "text"), AS_INTL)
def test_an_amount_is_written_as_the_browser_writes_it(cents, currency, language, text):
    # flow: money-text — the server and the app in the browser write the same amount the same way.
    assert business.money_text(cents, currency, language=language) == text


def test_an_amount_is_written_in_the_active_language_by_default():
    with translation.override("en"):
        assert business.money_text(1550, "PLN") == "PLN\xa015.50"
    with translation.override("es"):
        assert business.money_text(1550, "PLN") == "15,50\xa0PLN"


def test_a_locale_that_already_spaces_the_code_is_not_spaced_twice():
    assert business.money_text(1550, "CHF", language="de-ch") == "CHF\xa015.50"


@pytest.mark.parametrize("language", ["es-es", "es_ES", "es"])
def test_the_language_is_read_as_django_or_as_babel_writes_it(language):
    assert business.money_text(1550, "PLN", language=language) == "15,50\xa0PLN"


def test_an_amount_to_read_back_is_written_without_grouping():
    assert business.money_text(123456, "PLN", language="en", grouped=False) == "PLN\xa01234.56"
    assert business.money_text(123456, "EUR", language="es", grouped=False) == "1234,56\xa0€"


def test_a_fraction_of_a_minor_unit_keeps_its_decimals():
    # A unit price without VAT (0.8264 €) is not rounded to the cent; a whole number of cents keeps the currency's.
    assert business.money_text(Decimal("82.64"), "EUR", language="es") == "0,8264\xa0€"
    assert business.money_text(Decimal("82.64"), "PLN", language="en") == "PLN\xa00.8264"
    assert business.money_text(Decimal("8200"), "EUR", language="en") == "€82.00"
