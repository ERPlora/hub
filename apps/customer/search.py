"""The text a card is searched by and the term a search box sends (CUSTOMER-F02). Pure text, no database.

Every card keeps ``search_text``: its name, email, phone, tax id and company, lowercased and without
accents, so «garcia» finds «García» without the ``unaccent`` extension. A term made only of a
phone's characters is searched by its digits, without the ``00`` prefix, the national zero or a
«(0)»: those digits are always a piece of the E.164 phone a card keeps («600 111 222», «0034
600-111-222» and «+44 (0)7700 900123» all find their card). Any other term is searched normalized.
"""

import re
import unicodedata

_PHONE_ONLY = re.compile(r"^[\d\s+\-()./]+$")


def normalize(text: str) -> str:
    """``text`` lowercased, trimmed and without combining accents («Núñez» → «nunez»)."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return (
        "".join(char for char in decomposed if not unicodedata.combining(char))
        .lower()
        .strip()
    )


def searchable(*parts: str) -> str:
    """The ``search_text`` of a card: its non-empty parts, normalized and joined by a space."""
    return " ".join(
        normalized for normalized in (normalize(part) for part in parts) if normalized
    )


def search_term(typed: str) -> str:
    """What to look for in ``search_text``; empty for a blank term (no search)."""
    text = (typed or "").strip()
    if not text:
        return ""
    if not _PHONE_ONLY.match(text) or not any(char.isdigit() for char in text):
        return normalize(text)
    digits = re.sub(r"\D", "", text.replace("(0)", ""))
    return digits.lstrip("0") or digits
