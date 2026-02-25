"""
Currency configuration using Babel.

Provides all ISO 4217 currency codes with localized names.
"""
from babel.numbers import list_currencies, get_currency_name


def get_all_currency_choices():
    """
    Get all available currencies from Babel.

    Returns:
        list: List of tuples (code, name) for all currencies

    Example:
        [
            ('USD', 'US Dollar'),
            ('EUR', 'Euro'),
            ('GBP', 'Pound Sterling'),
            ...
        ]
    """
    currencies = list_currencies()
    # Sort by currency code for easier navigation
    return sorted(
        [(code, get_currency_name(code, locale='en')) for code in currencies],
        key=lambda x: x[0],
    )


def get_popular_currency_choices():
    """
    Get most commonly used currencies for forms/UI.

    Returns:
        list: List of tuples (code, name) for popular currencies
    """
    popular_codes = [
        'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'CAD', 'AUD',
        'NZD', 'SEK', 'NOK', 'DKK', 'SGD', 'HKD', 'KRW', 'MXN',
        'BRL', 'ARS', 'CLP', 'COP', 'INR', 'RUB', 'ZAR', 'TRY',
    ]

    all_currencies = {code: name for code, name in get_all_currency_choices()}

    return [(code, all_currencies[code]) for code in popular_codes if code in all_currencies]


# Pre-compute for settings to avoid runtime overhead
CURRENCY_CHOICES = get_all_currency_choices()
POPULAR_CURRENCY_CHOICES = get_popular_currency_choices()
