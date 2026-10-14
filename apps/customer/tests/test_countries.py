"""The countries of the card: one list for the server and the screen, and one way to read a name.

The server validates a country with ``pycountry`` (ISO 3166-1); the screen offers the same list from
``frontend/lib/countries.json``, generated from it (``uv run python -m apps.customer.countries``), so
it never offers a country the server refuses (CLDR also names XK, AC, CP, DG, TA…). An import, by the
screen or by the API, reads a country written by its code or its name, in Spanish or English.
"""

import json

import pycountry
import pytest

from apps.customer.countries import JSON_PATH, country_from_text, iso_codes, write_json


def test_iso_codes_are_pycountrys_alpha_2_codes_sorted():
    codes = iso_codes()
    assert codes == sorted(country.alpha_2 for country in pycountry.countries)
    assert "ES" in codes and "XK" not in codes and "AC" not in codes


def test_the_screens_list_is_the_servers():
    # Regenerate with `uv run python -m apps.customer.countries` when pycountry changes.
    assert json.loads(JSON_PATH.read_text()) == iso_codes()


def test_write_json_writes_the_codes(tmp_path):
    target = tmp_path / "countries.json"
    write_json(target)
    assert json.loads(target.read_text()) == iso_codes()
    assert target.read_text().endswith("\n")


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("ES", "ES"),
        (" fr ", "FR"),
        ("España", "ES"),
        ("espana", "ES"),
        ("ESPAÑA", "ES"),
        ("Spain", "ES"),
        ("Francia", "FR"),
        ("Alemania", "DE"),
        ("United Kingdom", "GB"),
        ("Reino Unido", "GB"),
        ("IC", "ES"),
        ("EA", "ES"),
        ("", ""),
        ("Narnia", ""),
        ("XK", ""),
        ("ZZ", ""),
    ],
)
def test_country_from_text_reads_a_code_or_a_name_in_spanish_or_english(text, code):
    assert country_from_text(text) == code
