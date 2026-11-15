"""The countries a tax rule is set for, and their names: the closed list ``schemas`` takes (``country_code``) and that
no field of the models labels, so the app declares it (``TaxConfig.choices``) and the assistant's card says each
country by its name, never by its ISO code (hub#678).

The codes are the 249 officially assigned ISO 3166-1 alpha-2 of ``pycountry`` (Debian's iso-codes; no ZZ, EU or XK):
a country no business can hold would give a rule that never matches anything. The names are CLDR's, said
in the active language (``base.business.country_name``): the ones the Rules screen's picker shows
(``Intl.DisplayNames``, CLDR too). No ORM, no models: ``apps.py`` reads it while the apps load.
"""

import pycountry
from django.utils import translation
from django.utils.functional import lazy

from base.business import country_name

#: The 249 officially assigned ISO 3166-1 alpha-2 codes (no ZZ, EU or XK).
COUNTRY_CODES: tuple[str, ...] = tuple(sorted(country.alpha_2 for country in pycountry.countries))


def _name_now(code: str) -> str:
    return country_name(code, translation.get_language())


#: A country's name, said when it is shown: in the language of whoever reads it.
country_label = lazy(_name_now, str)

#: Each country by its code and its name.
COUNTRY_LABELS: tuple[tuple[str, str], ...] = tuple((code, country_label(code)) for code in COUNTRY_CODES)

#: Each closed list by the name of its datum in the schemas, as ``LiveAppConfig.choices`` takes them.
CHOICES = {"country_code": COUNTRY_LABELS}
