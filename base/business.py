"""The business's own data as the Hub shows it (APP-BASE-6): its currency and the names of what the SaaS registered.

The SaaS owns the business's name, country, time zone and language (CLAUDE.md, «Contrato SaaS ↔ Hub»): it pushes them
in ``PUT /internal/hubs/{id}`` and the Hub keeps them in its registry, never asking. The currency is not chosen
anywhere: it is the one the business's country pays in (CLDR, through Babel), as Square, SumUp or Zettle fix it by the
merchant's country; a business without a country (a demo) is in euros, ERPlora's market. Names come in the person's
language, with a capital letter (CLDR writes «euro», «español»); a code CLDR does not know is shown as it is. An
amount is written here and nowhere else in the server (``money_text``), as the browser writes it.
"""

import datetime as dt
import unicodedata
from decimal import Decimal

from babel import Locale, UnknownLocaleError
from babel.numbers import (
    format_currency,
    get_currency_name,
    get_currency_precision,
    get_currency_symbol,
    get_territory_currencies,
)
from django.conf import settings
from django.utils import timezone, translation

#: The currency of a business without a country (a demo): ERPlora's market.
DEFAULT_CURRENCY = "EUR"
#: Changes of currency newer than the CLDR that Babel ships: country → (currency, since). Bulgaria adopted the euro on
#: 1 January 2026; Babel 2.18 still gives the lev with no end.
ADOPTED_SINCE: dict[str, tuple[str, dt.date]] = {"BG": ("EUR", dt.date(2026, 1, 1))}


def currency_of(country: str, *, today: dt.date | None = None) -> str:
    """The currency ``country`` (ISO 3166-1 alpha-2) pays in today; the euro without one CLDR knows."""
    if len(country) != 2:
        return DEFAULT_CURRENCY
    today = today or timezone.localdate()
    adopted = ADOPTED_SINCE.get(country.upper())
    if adopted and today >= adopted[1]:
        return adopted[0]
    found = get_territory_currencies(country.upper(), start_date=today, tender=True)
    return found[0] if found else DEFAULT_CURRENCY


def currency_decimals(currency: str) -> int:
    """The decimals of ``currency`` (ISO 4217): 2 in EUR, 0 in JPY."""
    return get_currency_precision(currency)


def money_text(cents: int | Decimal, currency: str, *, language: str | None = None, grouped: bool = True) -> str:
    """``cents`` (minor units of ``currency``, with its decimals: 1550 is 15.50, and ¥1,550 in yen) as the Hub writes
    money, the same as the browser (``Intl.NumberFormat``): «PLN 15.50», «€15.50», «15,50 PLN», «¥1,500».

    CLDR's pattern for ``language`` (the active one by default) with CLDR's currency spacing, which Babel skips (flow
    money-text). The thousands are grouped as every screen paints them (hub#1090), but with ``grouped=False``, for an
    export its import reads back. A fraction of a minor unit (a unit price without VAT, 0.8264 €) keeps its decimals.
    """
    cents = Decimal(cents)
    whole = cents == cents.to_integral_value()
    units = cents.scaleb(-get_currency_precision(currency))
    locale = babel_locale(language or translation.get_language() or settings.LANGUAGE_CODE)
    text = format_currency(
        units if whole else units.normalize(),
        currency,
        locale=locale,
        group_separator=grouped,
        decimal_quantization=whole,
    )
    return _spaced(text, get_currency_symbol(currency, locale=locale))


def _spaced(text: str, symbol: str) -> str:
    """CLDR's currency spacing (root ``currencySpacing``): a symbol whose side towards the figure is no sign (``S*``)
    nor space (``Z*``), a code in letters, is kept off a digit by a no-break space («PLN 15.50», «-PLN 15.50»); a sign
    of its own touches it («€15.50», «MX$15.50»)."""
    at = text.find(symbol) if symbol else -1
    if at < 0:
        return text
    end = at + len(symbol)
    if text[end : end + 1].isdecimal() and _letter(symbol[-1]):
        return f"{text[:end]}\xa0{text[end:]}"
    if at and text[at - 1].isdecimal() and _letter(symbol[0]):
        return f"{text[:at]}\xa0{text[at:]}"
    return text


def _letter(char: str) -> bool:
    return unicodedata.category(char)[0] not in "SZ"


def currency_label(currency: str, language: str) -> str:
    """«EUR · Euro»: the code, then its name in ``language``."""
    return f"{currency} · {_capital(get_currency_name(currency, locale=babel_locale(language)))}"


def country_name(country: str, language: str) -> str:
    """«España» / «Spain»; the code itself when CLDR does not name it, and nothing without one."""
    if not country:
        return ""
    name = babel_locale(language).territories.get(country.upper())
    return _capital(name) if name else country


def language_name(code: str, language: str) -> str:
    """«Español» / «Spanish»: the language ``code`` named in ``language``."""
    if not code:
        return ""
    name = babel_locale(language).languages.get(code.lower())
    return _capital(name) if name else code


def babel_locale(language: str) -> Locale:
    """``language`` as Django writes it (``es-es``) or as Babel does (``es_ES``); English for one CLDR does not know."""
    try:
        return Locale.parse((language or "en").replace("_", "-"), sep="-")
    except (ValueError, UnknownLocaleError):
        return Locale.parse("en")


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]
