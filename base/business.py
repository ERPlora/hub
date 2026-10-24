"""The business's own data as the Hub shows it (APP-BASE-6): its currency and the names of what the SaaS registered.

The SaaS owns the business's name, country, time zone and language (CLAUDE.md, «Contrato SaaS ↔ Hub»): it pushes them
in ``PUT /internal/hubs/{id}`` and the Hub keeps them in its registry, never asking. The currency is not chosen
anywhere: it is the one the business's country pays in (CLDR, through Babel), as Square, SumUp or Zettle fix it by the
merchant's country; a business without a country (a demo) is in euros, ERPlora's market. Names come in the person's
language, with a capital letter (CLDR writes «euro», «español»); a code CLDR does not know is shown as it is.
"""

import datetime as dt

from babel import Locale, UnknownLocaleError
from babel.numbers import get_currency_name, get_currency_precision, get_territory_currencies
from django.utils import timezone

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


def currency_label(currency: str, language: str) -> str:
    """«EUR · Euro»: the code, then its name in ``language``."""
    return f"{currency} · {_capital(get_currency_name(currency, locale=_locale(language)))}"


def country_name(country: str, language: str) -> str:
    """«España» / «Spain»; the code itself when CLDR does not name it, and nothing without one."""
    if not country:
        return ""
    name = _locale(language).territories.get(country.upper())
    return _capital(name) if name else country


def language_name(code: str, language: str) -> str:
    """«Español» / «Spanish»: the language ``code`` named in ``language``."""
    if not code:
        return ""
    name = _locale(language).languages.get(code.lower())
    return _capital(name) if name else code


def _locale(language: str) -> Locale:
    try:
        return Locale.parse(language or "en", sep="-")
    except (ValueError, UnknownLocaleError):
        return Locale.parse("en")


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]
