"""
Country data using phonenumbers + pytz.

Provides country codes, dial codes, flags, and timezone mappings
without hardcoding. Used by the setup wizard phone input and locale detection.
"""
import phonenumbers
from phonenumbers import COUNTRY_CODE_TO_REGION_CODE
import pytz


def _country_flag(code):
    """Generate flag emoji from ISO 3166-1 alpha-2 country code."""
    return chr(0x1F1E6 + ord(code[0]) - ord('A')) + chr(0x1F1E6 + ord(code[1]) - ord('A'))


def _build_region_to_dial():
    """Map region code -> dial code from phonenumbers."""
    region_to_dial = {}
    for dial_code, regions in COUNTRY_CODE_TO_REGION_CODE.items():
        for region in regions:
            # Keep the first (primary) dial code for each region
            if region not in region_to_dial:
                region_to_dial[region] = f'+{dial_code}'
    return region_to_dial


# Priority countries shown first in the phone dropdown
PRIORITY_COUNTRIES = [
    'ES', 'US', 'GB', 'FR', 'DE', 'IT', 'PT', 'NL', 'BE', 'AT',
    'CH', 'SE', 'NO', 'DK', 'FI', 'IE', 'PL', 'CZ', 'GR', 'RO',
    'MX', 'BR', 'AR', 'CO', 'CL', 'PE', 'CA', 'JP', 'CN', 'IN',
    'AU', 'KR', 'AE', 'SA', 'MA',
]


def get_all_countries():
    """
    Get all countries with dial codes, flags, and primary timezone.

    Returns list of dicts: [{ code, name, dial, flag, tz }, ...]
    Priority countries appear first, then alphabetical.
    """
    region_to_dial = _build_region_to_dial()
    priority_set = set(PRIORITY_COUNTRIES)
    priority = []
    others = []

    for region in sorted(phonenumbers.SUPPORTED_REGIONS):
        name = pytz.country_names.get(region, region)
        dial = region_to_dial.get(region, '')
        flag = _country_flag(region)
        timezones = pytz.country_timezones.get(region, [])

        entry = {
            'code': region,
            'name': name,
            'dial': dial,
            'flag': flag,
            'tz': timezones[0] if timezones else 'UTC',
        }

        if region in priority_set:
            priority.append(entry)
        else:
            others.append(entry)

    # Sort priority by PRIORITY_COUNTRIES order
    priority_order = {code: i for i, code in enumerate(PRIORITY_COUNTRIES)}
    priority.sort(key=lambda c: priority_order.get(c['code'], 999))

    return priority + others


def get_locale_map(languages):
    """
    Build locale detection map from available data.

    Maps browser locale strings (e.g. 'es-ES', 'en-US') to
    { lang, country, tz } using phonenumbers + pytz + Django LANGUAGES.

    Args:
        languages: Django settings.LANGUAGES list of (code, name) tuples
    """
    available_langs = {code for code, _ in languages}
    region_to_dial = _build_region_to_dial()
    locale_map = {}

    for region in phonenumbers.SUPPORTED_REGIONS:
        timezones = pytz.country_timezones.get(region, [])
        tz = timezones[0] if timezones else 'UTC'

        # Map region to its likely languages using pytz country info
        # We'll generate entries for common locale patterns
        _add_locale_entries(locale_map, region, tz, available_langs)

    return locale_map


# Mapping of language codes to their primary regions and default timezone
_LANG_REGION_DEFAULTS = {
    'es': [
        ('ES', 'Europe/Madrid'), ('MX', 'America/Mexico_City'),
        ('AR', 'America/Argentina/Buenos_Aires'), ('CO', 'America/Bogota'),
        ('CL', 'America/Santiago'), ('PE', 'America/Lima'),
        ('VE', 'America/Caracas'), ('EC', 'America/Guayaquil'),
        ('UY', 'America/Montevideo'), ('PY', 'America/Asuncion'),
        ('BO', 'America/La_Paz'), ('CR', 'America/Costa_Rica'),
        ('PA', 'America/Panama'), ('DO', 'America/Santo_Domingo'),
        ('GT', 'America/Guatemala'), ('HN', 'America/Tegucigalpa'),
        ('SV', 'America/El_Salvador'), ('NI', 'America/Managua'),
        ('CU', 'America/Havana'), ('PR', 'America/Puerto_Rico'),
    ],
    'en': [
        ('US', 'America/New_York'), ('GB', 'Europe/London'),
        ('AU', 'Australia/Sydney'), ('CA', 'America/Toronto'),
        ('IE', 'Europe/Dublin'), ('IN', 'Asia/Kolkata'),
        ('NZ', 'Pacific/Auckland'), ('ZA', 'Africa/Johannesburg'),
        ('SG', 'Asia/Singapore'), ('PH', 'Asia/Manila'),
    ],
    'fr': [
        ('FR', 'Europe/Paris'), ('BE', 'Europe/Brussels'),
        ('CH', 'Europe/Zurich'), ('CA', 'America/Toronto'),
        ('MA', 'Africa/Casablanca'), ('SN', 'Africa/Dakar'),
    ],
    'de': [
        ('DE', 'Europe/Berlin'), ('AT', 'Europe/Vienna'),
        ('CH', 'Europe/Zurich'), ('LI', 'Europe/Vaduz'),
    ],
    'it': [('IT', 'Europe/Rome'), ('CH', 'Europe/Zurich')],
    'pt': [
        ('PT', 'Europe/Lisbon'), ('BR', 'America/Sao_Paulo'),
        ('AO', 'Africa/Luanda'), ('MZ', 'Africa/Maputo'),
    ],
    'nl': [('NL', 'Europe/Amsterdam'), ('BE', 'Europe/Brussels')],
    'ja': [('JP', 'Asia/Tokyo')],
    'ko': [('KR', 'Asia/Seoul')],
    'zh': [('CN', 'Asia/Shanghai'), ('TW', 'Asia/Taipei'), ('HK', 'Asia/Hong_Kong')],
    'ar': [
        ('SA', 'Asia/Riyadh'), ('AE', 'Asia/Dubai'),
        ('MA', 'Africa/Casablanca'), ('EG', 'Africa/Cairo'),
    ],
    'ru': [('RU', 'Europe/Moscow')],
    'pl': [('PL', 'Europe/Warsaw')],
    'sv': [('SE', 'Europe/Stockholm')],
    'da': [('DK', 'Europe/Copenhagen')],
    'fi': [('FI', 'Europe/Helsinki')],
    'el': [('GR', 'Europe/Athens')],
    'ro': [('RO', 'Europe/Bucharest')],
    'cs': [('CZ', 'Europe/Prague')],
    'tr': [('TR', 'Europe/Istanbul')],
    'hi': [('IN', 'Asia/Kolkata')],
}


def _add_locale_entries(locale_map, region, tz, available_langs):
    """Add locale map entries for a region."""
    for lang, regions in _LANG_REGION_DEFAULTS.items():
        # Find the best available Django language
        django_lang = lang if lang in available_langs else 'en'

        for reg_code, reg_tz in regions:
            if reg_code == region:
                # Specific locale: e.g. 'es-ES'
                locale_key = f'{lang}-{region}'
                if locale_key not in locale_map:
                    locale_map[locale_key] = {
                        'lang': django_lang,
                        'country': region,
                        'tz': reg_tz,
                    }

    # Add base language entries (e.g. 'es' -> first region)
    for lang, regions in _LANG_REGION_DEFAULTS.items():
        base_key = lang
        if base_key not in locale_map and regions:
            django_lang = lang if lang in available_langs else 'en'
            first_region, first_tz = regions[0]
            locale_map[base_key] = {
                'lang': django_lang,
                'country': first_region,
                'tz': first_tz,
            }
