"""A phone number in E.164 (``+34600111222``): the one reading every write and every lookup shares.

The phone is what the business compares people by (CUSTOMER-F10, F11): the card's number is saved
in E.164, other apps copy it already normalised, and the lookup by number reads the question with
the same rules. A phone saved as typed («600 111 222», «600111») either matches nobody or matches
somebody else, so every write of a phone goes through :func:`to_e164`: one canonical form, or a
refusal.

The rules are libphonenumber's, through its Python port ``phonenumbers``: a number without prefix is
read in the business's country, and it must be a valid number of its country (its numbering plan,
not only its length). On top, our own refusals: letters (an extension, a note) and a ``+`` that is
not the first sign. The contract, ported from the product's guest SDK
(``crates/guest-sdk/tests/phone_test.rs``, which copied the length rules only), is
``tests/test_phones.py``.
"""

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

#: The country a number without prefix belongs to while the business has not set its own.
DEFAULT_COUNTRY = "ES"

#: What may separate the digits of a typed number (a no-break space included).
_SEPARATORS = frozenset("  \t-./()")


class InvalidPhone(ValueError):
    """The typed text is not a phone number of its country."""


def to_e164(raw: str | None, home_iso: str) -> str:
    """``raw`` as E.164, reading a number without prefix as one of ``home_iso``.

    ``home_iso`` is the business's country (ISO 3166 alpha-2, any case; empty or unknown →
    :data:`DEFAULT_COUNTRY`). The empty phone stays empty: only the name is required on a card.
    Raises :class:`InvalidPhone` for letters, a ``+`` that is not the first sign, or a number that is
    not a valid number of its country («600111» in Spain, two numbers in one field, a trunk zero
    left behind the calling code).
    """
    text = (raw or "").strip()
    if not text:
        return ""
    # libphonenumber would read letters as a vanity number or an extension: refused here first.
    seen_digit = seen_plus = False
    for char in text:
        if "0" <= char <= "9":
            seen_digit = True
        elif char == "+" and not (seen_plus or seen_digit):
            seen_plus = True
        elif char not in _SEPARATORS:
            raise InvalidPhone(raw)
    try:
        number = phonenumbers.parse(text, _home_region(home_iso))
    except NumberParseException as exc:
        raise InvalidPhone(raw) from exc
    if number.extension or not phonenumbers.is_valid_number(number):
        raise InvalidPhone(raw)
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def candidates(question: str | None, home_iso: str) -> set[str]:
    """The E.164 numbers a lookup by ``question`` may mean (CUSTOMER-F10); empty when none.

    The question is read as a card's phone is saved (:func:`to_e164`) and, when it carries no
    ``+``, also as an international number without its ``+``, the way WhatsApp and a caller id give
    it: in a Spanish business «447700900123» is ``+447700900123``. A question no reading makes
    possible asks nothing: never the whole list.
    """
    text = (question or "").strip()
    found: set[str] = set()
    for reading in (text, f"+{text}" if text and "+" not in text else ""):
        if not reading:
            continue
        try:
            number = to_e164(reading, home_iso)
        except InvalidPhone:
            continue
        if number:
            found.add(number)
    return found


def _home_region(iso: str) -> str:
    """The business's region; an empty or unknown code falls back to :data:`DEFAULT_COUNTRY`."""
    region = (iso or "").strip().upper()
    return region if region in phonenumbers.SUPPORTED_REGIONS else DEFAULT_COUNTRY
