"""A recipient's tax ID, read ONE way by every app that writes it on a fiscal document.

Sales (at the till) and Invoicing (every document) both require Customers, so the reading lives here, pure:
it reads and writes nothing. A Spanish NIF, NIE or CIF and an EU VAT number (the AEAT's ``IDType`` 02) are
checked with python-stdnum and kept compact; a foreign document of another kind (03 passport, 04 tax ID of
its country, 05 residence certificate, 06 other document, 07 not registered) is taken as written — but a
foreign tax ID always says its kind: VeriFactu declares it as ``IDOtro``, which the tax agency refuses
without ``IDType``. The callers name the field and translate the refusal (``tests/test_tax_ids.py``).
"""

import pycountry
from stdnum.es import nif
from stdnum.eu import vat

#: The business's country while the platform has no setting for it; empty means it too.
HOME_COUNTRY = "ES"
#: The AEAT's kinds of foreign document (``IDType``), 02 being the EU VAT number.
ID_TYPES = ("02", "03", "04", "05", "06", "07")
EU_VAT = "02"
#: The EU VAT prefix that is not the ISO code of its country.
_VAT_PREFIX = {"GR": "EL"}


class InvalidTaxId(ValueError):
    """The tax ID does not check (a Spanish NIF, NIE or CIF, or an EU VAT number)."""


class IdTypeRequired(ValueError):
    """A foreign tax ID without its kind of document (or with an unknown one)."""


class InvalidCountry(ValueError):
    """Not an ISO 3166-1 alpha-2 code (a name, an alias such as UK, a three-letter code…)."""


#: Every ISO 3166-1 alpha-2 code (pycountry), as Invoicing's recipient schema reads them.
COUNTRY_CODES = frozenset(country.alpha_2 for country in pycountry.countries)


def normalize_country(value: str) -> str:
    """The recipient's country as a fiscal document keeps it: its ISO 3166-1 alpha-2 code in capitals,
    surrounding spaces aside; empty stays empty. The same reading as Invoicing's recipient schema
    (no aliases: «UK» or the VAT prefix «EL» are refused, as there)."""
    code = (value or "").strip().upper()
    if code and code not in COUNTRY_CODES:
        raise InvalidCountry(code)
    return code


def normalize_tax_id(value: str, *, country: str = "", id_type: str = "") -> str:
    """The tax ID as a document keeps it; ``country`` is ISO 3166-1 alpha-2 (empty = Spain) and
    ``id_type`` the AEAT's kind of a foreign document (empty = a Spanish NIF). Empty stays empty."""
    text = (value or "").strip()
    if not text:
        return ""
    home = country in ("", HOME_COUNTRY)
    if id_type == EU_VAT:
        prefix = _VAT_PREFIX.get(country, country)
        candidate = "".join(char for char in text.upper() if char.isalnum())
        if prefix and not candidate.startswith(prefix):
            candidate = prefix + candidate
        if not vat.is_valid(candidate):
            raise InvalidTaxId(text)
        return candidate
    if id_type and id_type not in ID_TYPES:
        raise IdTypeRequired(id_type)
    if home and not id_type:
        if not nif.is_valid(text):
            raise InvalidTaxId(text)
        return nif.compact(text)
    if not id_type:
        raise IdTypeRequired(country)
    return text
