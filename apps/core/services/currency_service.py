"""
Currency formatting service for ERPlora Hub.

Provides currency formatting based on HubConfig settings.
All plugins should use this service for consistent currency display.
"""

from decimal import Decimal
from typing import Optional, Union
import locale


def get_currency() -> str:
    """
    Get the current currency code from HubConfig.

    Returns:
        str: Currency code (e.g., 'EUR', 'USD')
    """
    from apps.configuration.models import HubConfig
    return HubConfig.get_value('currency', 'EUR')


def format_currency(
    amount: Union[Decimal, float, int],
    currency: Optional[str] = None,
    show_symbol: bool = True,
    decimal_places: int = 2
) -> str:
    """
    Format an amount as currency.

    Args:
        amount: The amount to format
        currency: Currency code (defaults to HubConfig.currency)
        show_symbol: Whether to show the currency symbol
        decimal_places: Number of decimal places

    Returns:
        str: Formatted currency string (e.g., '€19.90', '$25.00')

    Example:
        >>> format_currency(19.90)
        '€19.90'
        >>> format_currency(19.90, 'USD')
        '$19.90'
        >>> format_currency(1234.56)
        '€1,234.56'
    """
    if currency is None:
        currency = get_currency()

    # Convert to Decimal for precision
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    # Currency symbols
    symbols = {
        'EUR': '€',
        'USD': '$',
        'GBP': '£',
        'JPY': '¥',
        'CHF': 'CHF',
        'CAD': 'CA$',
        'AUD': 'A$',
        'MXN': 'MX$',
        'BRL': 'R$',
        'CNY': '¥',
    }

    symbol = symbols.get(currency, currency)

    # Format the number with thousand separators
    formatted = f"{amount:,.{decimal_places}f}"

    if show_symbol:
        # Position symbol based on currency
        if currency in ['EUR', 'GBP', 'CHF']:
            return f"{symbol}{formatted}"
        else:
            return f"{symbol}{formatted}"

    return formatted


def format_number(
    number: Union[Decimal, float, int],
    decimal_places: int = 2
) -> str:
    """
    Format a number with thousand separators.

    Args:
        number: The number to format
        decimal_places: Number of decimal places

    Returns:
        str: Formatted number string

    Example:
        >>> format_number(1234.567)
        '1,234.57'
        >>> format_number(1234567, 0)
        '1,234,567'
    """
    if not isinstance(number, Decimal):
        number = Decimal(str(number))

    return f"{number:,.{decimal_places}f}"


def parse_currency(
    value: str,
    currency: Optional[str] = None
) -> Decimal:
    """
    Parse a currency string to Decimal.

    Args:
        value: The currency string to parse
        currency: Currency code for symbol removal

    Returns:
        Decimal: The parsed amount

    Example:
        >>> parse_currency('€19.90')
        Decimal('19.90')
        >>> parse_currency('1,234.56')
        Decimal('1234.56')
    """
    if currency is None:
        currency = get_currency()

    # Remove currency symbols
    symbols = ['€', '$', '£', '¥', 'CHF', 'CA$', 'A$', 'MX$', 'R$']
    cleaned = value
    for sym in symbols:
        cleaned = cleaned.replace(sym, '')

    # Remove thousand separators and whitespace
    cleaned = cleaned.replace(',', '').replace(' ', '').strip()

    return Decimal(cleaned)


# Shorthand functions for templates
def currency(amount: Union[Decimal, float, int]) -> str:
    """Shorthand for format_currency()."""
    return format_currency(amount)


__all__ = [
    'get_currency',
    'format_currency',
    'format_number',
    'parse_currency',
    'currency',
]
