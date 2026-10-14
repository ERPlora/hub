"""The countries of the card: the ISO 3166-1 list the server validates with, and reading a name.

``iso_codes`` is what ``schemas.country_code`` accepts (``pycountry``); ``write_json`` copies it to
``frontend/lib/countries.json`` for the screen's picker, so the screen never offers a country the
server refuses (``tests/test_countries.py`` checks they match). Regenerate with
``uv run python -m apps.customer.countries``.

``country_from_text`` reads what a file or a person writes — a code, or a name in Spanish or English,
case and accents aside — as the screen does (product customers#72); Canarias (IC) and Ceuta y Melilla
(EA) are Spain. No ORM.
"""

import gettext
import json
import unicodedata
from functools import cache
from pathlib import Path

import pycountry

JSON_PATH = Path(__file__).resolve().parent / "frontend" / "lib" / "countries.json"

#: Spanish regions with a code of their own outside ISO 3166-1: they are Spain.
SPANISH_REGIONS = {"IC", "EA"}
SPAIN = "ES"
#: The languages a name is read in, besides the codes.
NAME_LANGUAGES = ("es",)


def iso_codes() -> list[str]:
    """Every ISO 3166-1 alpha-2 code, sorted."""
    return sorted(country.alpha_2 for country in pycountry.countries)


def write_json(path: Path = JSON_PATH) -> None:
    """Writes the codes the screen offers."""
    path.write_text(json.dumps(iso_codes()) + "\n")


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(plain.casefold().split())


@cache
def _names() -> dict[str, str]:
    """Normalized name → code: English names (official and common too) and their translations."""
    index: dict[str, str] = {}
    translations = [
        gettext.translation(
            "iso3166-1", pycountry.LOCALES_DIR, languages=[language], fallback=True
        )
        for language in NAME_LANGUAGES
    ]
    for country in pycountry.countries:
        english = [
            getattr(country, attribute, "")
            for attribute in ("name", "official_name", "common_name")
        ]
        for name in [
            *english,
            *(t.gettext(n) for t in translations for n in english if n),
        ]:
            if name:
                index.setdefault(_normalize(name), country.alpha_2)
    return index


def country_from_text(text: str) -> str:
    """The code ``text`` names (a code or a name in Spanish or English); ``''`` when none."""
    value = text.strip()
    if not value:
        return ""
    if len(value) == 2 and value.isalpha():
        code = value.upper()
        if code in SPANISH_REGIONS:
            return SPAIN
        return code if pycountry.countries.get(alpha_2=code) else ""
    return _names().get(_normalize(value), "")


if __name__ == "__main__":
    write_json()
    print(f"{JSON_PATH}: {len(iso_codes())} countries")
