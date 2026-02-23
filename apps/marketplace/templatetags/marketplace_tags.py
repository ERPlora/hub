from django import template

register = template.Library()


@register.filter
def country_flag(country_code):
    """Convert ISO 3166-1 alpha-2 country code to flag emoji."""
    if not country_code or len(country_code) != 2:
        return ''
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in country_code.upper())
