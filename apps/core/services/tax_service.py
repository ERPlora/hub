"""
Tax calculation service for ERPlora Hub.

Provides tax calculations based on StoreConfig settings.
All modules should use this service for consistent tax handling.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple, Dict, Union


def get_tax_config() -> Dict:
    """
    Get the current tax configuration from StoreConfig.

    Returns:
        dict: Tax configuration with 'rate' and 'included' keys
    """
    from apps.configuration.models import StoreConfig
    return {
        'rate': StoreConfig.get_value('tax_rate', Decimal('0.00')),
        'included': StoreConfig.get_value('tax_included', True),
    }


def get_tax_rate() -> Decimal:
    """
    Get the current tax rate as a Decimal.

    Returns:
        Decimal: Tax rate percentage (e.g., 21.00 for 21%)
    """
    config = get_tax_config()
    rate = config['rate']
    if not isinstance(rate, Decimal):
        rate = Decimal(str(rate))
    return rate


def is_tax_included() -> bool:
    """
    Check if tax is included in prices.

    Returns:
        bool: True if tax is included in displayed prices
    """
    return get_tax_config()['included']


def calculate_tax(
    amount: Union[Decimal, float, int],
    tax_rate: Optional[Decimal] = None,
    tax_included: Optional[bool] = None
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Calculate tax for an amount.

    Args:
        amount: The amount to calculate tax for
        tax_rate: Tax rate percentage (defaults to StoreConfig.tax_rate)
        tax_included: Whether tax is included (defaults to StoreConfig.tax_included)

    Returns:
        Tuple[Decimal, Decimal, Decimal]: (net_amount, tax_amount, gross_amount)

    Example:
        >>> calculate_tax(121)  # If tax_rate=21%, tax_included=True
        (Decimal('100.00'), Decimal('21.00'), Decimal('121.00'))

        >>> calculate_tax(100)  # If tax_rate=21%, tax_included=False
        (Decimal('100.00'), Decimal('21.00'), Decimal('121.00'))
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    if tax_rate is None:
        tax_rate = get_tax_rate()
    elif not isinstance(tax_rate, Decimal):
        tax_rate = Decimal(str(tax_rate))

    if tax_included is None:
        tax_included = is_tax_included()

    # Convert rate to multiplier (21% -> 0.21)
    rate_multiplier = tax_rate / Decimal('100')

    if tax_included:
        # Amount includes tax, calculate net from gross
        gross_amount = amount
        net_amount = (gross_amount / (1 + rate_multiplier)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        tax_amount = (gross_amount - net_amount).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    else:
        # Amount is net, calculate tax and gross
        net_amount = amount
        tax_amount = (net_amount * rate_multiplier).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        gross_amount = (net_amount + tax_amount).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    return net_amount, tax_amount, gross_amount


def get_net_amount(
    gross_amount: Union[Decimal, float, int],
    tax_rate: Optional[Decimal] = None
) -> Decimal:
    """
    Extract net amount from a gross amount (tax included).

    Args:
        gross_amount: The amount including tax
        tax_rate: Tax rate percentage

    Returns:
        Decimal: Net amount without tax
    """
    net, _, _ = calculate_tax(gross_amount, tax_rate, tax_included=True)
    return net


def get_gross_amount(
    net_amount: Union[Decimal, float, int],
    tax_rate: Optional[Decimal] = None
) -> Decimal:
    """
    Calculate gross amount from a net amount.

    Args:
        net_amount: The amount without tax
        tax_rate: Tax rate percentage

    Returns:
        Decimal: Gross amount with tax
    """
    _, _, gross = calculate_tax(net_amount, tax_rate, tax_included=False)
    return gross


def get_tax_amount(
    amount: Union[Decimal, float, int],
    tax_rate: Optional[Decimal] = None,
    tax_included: Optional[bool] = None
) -> Decimal:
    """
    Calculate just the tax amount.

    Args:
        amount: The base amount
        tax_rate: Tax rate percentage
        tax_included: Whether tax is already included

    Returns:
        Decimal: Tax amount
    """
    _, tax, _ = calculate_tax(amount, tax_rate, tax_included)
    return tax


def format_tax_rate(rate: Optional[Decimal] = None) -> str:
    """
    Format tax rate for display.

    Args:
        rate: Tax rate (defaults to StoreConfig.tax_rate)

    Returns:
        str: Formatted tax rate (e.g., '21%', '0%')
    """
    if rate is None:
        rate = get_tax_rate()
    elif not isinstance(rate, Decimal):
        rate = Decimal(str(rate))

    # Remove trailing zeros
    rate_str = f"{rate:.2f}".rstrip('0').rstrip('.')
    return f"{rate_str}%"


__all__ = [
    'get_tax_config',
    'get_tax_rate',
    'is_tax_included',
    'calculate_tax',
    'get_net_amount',
    'get_gross_amount',
    'get_tax_amount',
    'format_tax_rate',
]
