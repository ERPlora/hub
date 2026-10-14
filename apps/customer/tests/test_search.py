"""The text a card is searched by and the term a search box sends (CUSTOMER-F02).

Search ignores case and accents («garcia» finds «García»), and a term made only of a phone's
characters is searched by its digits, without the ``00`` prefix, the national zero or a «(0)»:
those digits are always a piece of the E.164 phone the card keeps (the product's
``ui/lib/phone-search.ts``).
"""

import pytest

from apps.customer.search import normalize, search_term, searchable


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("García", "garcia"),
        ("ÁNGELES Núñez", "angeles nunez"),
        ("Çağla Øster", "cagla øster"),
        ("  Ana  ", "ana"),
        ("", ""),
    ],
)
def test_normalize_drops_case_and_accents(text, expected):
    assert normalize(text) == expected


def test_searchable_joins_the_normalized_parts_and_skips_the_empty_ones():
    assert searchable(
        "Ana García", "ANA@example.com", "+34600111222", "", "Peluquería Sol"
    ) == ("ana garcia ana@example.com +34600111222 peluqueria sol")


@pytest.mark.parametrize(
    ("typed", "term"),
    [
        ("600 111 222", "600111222"),
        ("0034 600-111-222", "34600111222"),
        ("+34 600 111 222", "34600111222"),
        ("+44 (0)7700 900123", "447700900123"),
        ("07700 900123", "7700900123"),
        ("(600) 111.222", "600111222"),
    ],
)
def test_a_phone_like_term_is_searched_by_its_digits(typed, term):
    assert search_term(typed) == term


@pytest.mark.parametrize(
    ("typed", "term"),
    [
        ("García", "garcia"),
        ("ana@example.com", "ana@example.com"),
        ("12345678Z", "12345678z"),
        ("B-12345678", "b-12345678"),
        ("  Peluquería  ", "peluqueria"),
    ],
)
def test_any_other_term_is_searched_normalized(typed, term):
    assert search_term(typed) == term


@pytest.mark.parametrize("typed", ["", "   "])
def test_a_blank_term_is_no_search(typed):
    assert search_term(typed) == ""


@pytest.mark.parametrize("typed", ["+ -", "()"])
def test_phone_signs_without_digits_are_searched_as_typed(typed):
    # As in the product: only a term with digits is read as a phone; these find nobody.
    assert search_term(typed) == typed


def test_a_term_of_zeros_keeps_its_digits():
    # Stripping every leading zero of «000» would leave nothing; the zeros are the term then.
    assert search_term("000") == "000"
