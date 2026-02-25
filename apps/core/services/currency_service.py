"""
Currency formatting service for ERPlora Hub.

Provides locale-aware currency formatting based on HubConfig settings.
Uses Babel for full international currency support (all ISO 4217 currencies).
All modules should use this service for consistent currency display.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional, Union

from babel.numbers import (
    format_currency as babel_format_currency,
    format_decimal as babel_format_decimal,
    get_currency_symbol as babel_get_currency_symbol,
    parse_decimal as babel_parse_decimal,
)


def _get_locale() -> str:
    """
    Build a Babel locale string from HubConfig language + country_code.

    Returns:
        str: Babel locale (e.g., 'es_ES', 'en_US', 'fr_FR')
    """
    from apps.configuration.models import HubConfig
    lang = HubConfig.get_value('language', 'en')
    country = HubConfig.get_value('country_code', '')
    if country:
        return f"{lang}_{country.upper()}"
    return lang


def get_currency() -> str:
    """
    Get the current currency code from HubConfig.

    Returns:
        str: Currency code (e.g., 'EUR', 'USD')
    """
    from apps.configuration.models import HubConfig
    return HubConfig.get_value('currency', 'EUR')


def get_currency_symbol(currency_code: Optional[str] = None) -> str:
    """
    Get the symbol for a currency code.

    First tries the Hub's locale. If Babel returns the raw code (e.g., 'GBP'
    instead of '£'), falls back to 'en_US' which knows most symbols.

    Args:
        currency_code: ISO 4217 code (defaults to HubConfig.currency)

    Returns:
        str: Currency symbol (e.g., '€', '$', '£', 'zł')
    """
    if currency_code is None:
        currency_code = get_currency()
    try:
        symbol = babel_get_currency_symbol(currency_code, locale=_get_locale())
        # If Babel returned the raw code, try en_US as fallback
        if symbol == currency_code:
            symbol = babel_get_currency_symbol(currency_code, locale='en_US')
        return symbol
    except Exception:
        return currency_code


def format_currency(
    amount: Union[Decimal, float, int],
    currency: Optional[str] = None,
    show_symbol: bool = True,
    decimal_places: int = 2
) -> str:
    """
    Format an amount as currency with locale-aware formatting.

    Supports all ISO 4217 currencies with correct symbol placement,
    thousand separators, and decimal separators for the Hub's locale.

    Args:
        amount: The amount to format
        currency: Currency code (defaults to HubConfig.currency)
        show_symbol: Whether to show the currency symbol
        decimal_places: Number of decimal places

    Returns:
        str: Formatted currency string (e.g., '19,90 €', '$19.90')

    Example:
        >>> format_currency(19.90)          # Hub set to EUR, locale es_ES
        '19,90 €'
        >>> format_currency(19.90, 'USD')   # locale en_US
        '$19.90'
        >>> format_currency(1234.56)
        '1.234,56 €'
    """
    if currency is None:
        currency = get_currency()

    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    locale = _get_locale()

    try:
        if show_symbol:
            return babel_format_currency(
                amount, currency, locale=locale,
                decimal_quantization=True,
                currency_digits=False,
                format=None,
            )
        else:
            return babel_format_decimal(
                amount, locale=locale,
                decimal_quantization=False,
            )
    except Exception:
        # Fallback if locale is invalid
        formatted = f"{amount:,.{decimal_places}f}"
        if show_symbol:
            symbol = get_currency_symbol(currency)
            return f"{symbol}{formatted}"
        return formatted


def format_number(
    number: Union[Decimal, float, int],
    decimal_places: int = 2
) -> str:
    """
    Format a number with locale-aware thousand separators.

    Args:
        number: The number to format
        decimal_places: Number of decimal places

    Returns:
        str: Formatted number string

    Example:
        >>> format_number(1234.567)    # locale es_ES
        '1.234,57'
        >>> format_number(1234567, 0)  # locale en_US
        '1,234,567'
    """
    if not isinstance(number, Decimal):
        number = Decimal(str(number))

    try:
        return babel_format_decimal(
            round(number, decimal_places),
            locale=_get_locale(),
            decimal_quantization=False,
        )
    except Exception:
        return f"{number:,.{decimal_places}f}"


def parse_currency(
    value: str,
    currency: Optional[str] = None
) -> Decimal:
    """
    Parse a locale-formatted currency string to Decimal.

    Handles any locale's thousand/decimal separators and currency symbols.

    Args:
        value: The currency string to parse
        currency: Currency code (unused, kept for API compat)

    Returns:
        Decimal: The parsed amount

    Example:
        >>> parse_currency('19,90 €')
        Decimal('19.90')
        >>> parse_currency('$1,234.56')
        Decimal('1234.56')
    """
    locale = _get_locale()

    # Strip currency symbols and whitespace
    cleaned = value.strip()
    if currency is None:
        currency = get_currency()
    symbol = get_currency_symbol(currency)
    cleaned = cleaned.replace(symbol, '').replace(currency, '').strip()

    try:
        return babel_parse_decimal(cleaned, locale=locale)
    except Exception:
        # Fallback: strip non-numeric except . and -
        fallback = ''.join(c for c in cleaned if c in '0123456789.-')
        try:
            return Decimal(fallback)
        except InvalidOperation:
            return Decimal('0')


# Shorthand for templates
def currency(amount: Union[Decimal, float, int]) -> str:
    """Shorthand for format_currency()."""
    return format_currency(amount)


__all__ = [
    'get_currency',
    'get_currency_symbol',
    'format_currency',
    'format_number',
    'parse_currency',
    'currency',
]
