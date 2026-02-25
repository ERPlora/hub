"""
Currency formatting template filters for ERPlora Hub.

Usage:
    {% load currency %}
    {{ amount|currency }}       → 19,90 €  (based on HubConfig locale)
    {{ amount|currency:"USD" }} → $19.90
    {% currency_symbol %}       → €
    {% currency_symbol "USD" %} → $
"""
from django import template
from apps.core.services.currency_service import format_currency, get_currency_symbol

register = template.Library()


@register.filter(name='currency')
def currency_filter(amount, currency_code=None):
    """Format amount with locale-aware currency formatting from HubConfig."""
    if amount is None:
        return ''
    try:
        return format_currency(amount, currency=currency_code)
    except (ValueError, TypeError):
        return str(amount)


@register.simple_tag(name='currency_symbol')
def currency_symbol_tag(currency_code=None):
    """Return the currency symbol. Usage: {% currency_symbol %} or {% currency_symbol 'USD' %}"""
    return get_currency_symbol(currency_code)
