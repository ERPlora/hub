"""The phone contract: ONE reading of a typed phone, in E.164 (CUSTOMER-F10, F11).

Ported from the product's guest SDK (``crates/guest-sdk/tests/phone_test.rs``, appointments#313),
which copied libphonenumber's rules; here the rules ARE libphonenumber (``phonenumbers``), and these
cases pin the reading the product's cards and lookups depend on.
"""

import phonenumbers
import pytest

from apps.customer.phones import DEFAULT_COUNTRY, InvalidPhone, candidates, to_e164


def ok(raw: str, home: str) -> str:
    return to_e164(raw, home)


def refused(raw: str, home: str) -> bool:
    with pytest.raises(InvalidPhone):
        to_e164(raw, home)
    return True


@pytest.mark.parametrize(
    "raw",
    [
        "600 111 222",
        "600111222",
        "600-111-222",
        "600.111.222",
        "+34 600 111 222",
        "+34600111222",
        "0034 600 111 222",
        "34600111222",
        "(+34) 600 11 12 22",
        "  600 111 222  ",
        "600 111 222",
    ],
)
def test_a_spanish_number_typed_any_way_is_one_e164(raw):
    assert ok(raw, "ES") == "+34600111222"


def test_the_empty_phone_stays_empty():
    assert ok("", "ES") == ""
    assert ok("   ", "ES") == ""


@pytest.mark.parametrize(
    "raw", ["600111", "12", "+34 600 111", "600111222 / 611222333"]
)
def test_a_number_too_short_or_too_long_for_its_country_is_refused(raw):
    # The last one is two numbers in one field.
    assert refused(raw, "ES")


@pytest.mark.parametrize(
    "raw", ["600 111 222 ext 12", "call me", "+34 +600111222", "600+111222", "+"]
)
def test_letters_an_extension_or_a_second_plus_are_refused(raw):
    assert refused(raw, "ES")


@pytest.mark.parametrize("raw", ["34+600111222", "600 111 222 +34"])
def test_a_plus_after_the_first_digit_is_refused_even_when_the_digits_would_read_as_a_number(
    raw,
):
    assert refused(raw, "ES")


def test_a_foreign_number_keeps_its_own_country():
    assert ok("+33 6 12 34 56 78", "ES") == "+33612345678"
    assert ok("0033 6 12 34 56 78", "ES") == "+33612345678"
    # The same national digits behind another code are another person.
    assert ok("+33 600 111 222", "ES") != ok("600 111 222", "ES")


def test_the_trunk_zero_is_dropped_nationally_and_inside_parentheses():
    assert ok("07911 123456", "GB") == "+447911123456"
    assert ok("+44 (0)7911 123456", "ES") == "+447911123456"
    assert ok("+44 7911 123456", "ES") == "+447911123456"
    assert ok("06 12 34 56 78", "FR") == "+33612345678"


def test_the_trunk_zero_is_dropped_even_when_the_number_would_be_possible_with_it():
    # Germany allows 4 to 15 digits; still, no German number starts with 0 after +49.
    assert ok("030 12345678", "DE") == "+493012345678"
    assert ok("+49 (0)30 12345678", "ES") == "+493012345678"


def test_a_trunk_zero_never_survives_behind_the_calling_code():
    assert refused("01234 5678", "GB")
    assert refused("+44 01234 5678", "ES")


def test_a_leading_trunk_digit_stays_when_dropping_it_leaves_no_possible_number():
    # Russian freephone typed WITHOUT the trunk «8»: its own first 8 is part of the number.
    assert ok("800 123-45-67", "RU") == "+78001234567"


def test_italy_keeps_its_leading_zero():
    assert ok("06 1234 5678", "IT") == "+390612345678"
    assert ok("+39 06 1234 5678", "ES") == "+390612345678"


def test_the_international_prefix_of_the_business_country_is_read():
    # From the United States, 011 is the international prefix.
    assert ok("011 34 600 111 222", "US") == "+34600111222"
    assert ok("(212) 555-0123", "US") == "+12125550123"
    assert ok("1 212 555 0123", "US") == "+12125550123"


def test_the_own_calling_code_without_plus_is_read_when_the_rest_is_a_valid_number():
    # libphonenumber reads «4930 123456» in Germany as +49 30 123456 (Berlin): the national reading
    # «4930123456» is no valid German number. (The SDK's length-only copy read it nationally.)
    assert ok("4930 123456", "DE") == "+4930123456"


def test_the_russian_freephone_keeps_its_eight():
    assert ok("+7 800 123 45 67", "ES") == "+78001234567"
    assert ok("8 912 345 67 89", "RU") == "+79123456789"


@pytest.mark.parametrize("home", ["", "es", "XX"])
def test_an_unknown_or_empty_business_country_reads_as_spain(home):
    assert ok("600 111 222", home) == "+34600111222"


@pytest.mark.parametrize("home", ["gb", " GB "])
def test_the_business_country_is_read_whatever_its_case(home):
    assert ok("07911 123456", home) == "+447911123456"


def test_the_default_country_is_a_region_of_the_library():
    assert DEFAULT_COUNTRY == "ES"
    assert DEFAULT_COUNTRY in phonenumbers.SUPPORTED_REGIONS


def test_a_number_of_a_range_its_country_does_not_use_is_refused():
    # Ofcom's 07700 900xxx is reserved for fiction: no real British phone.
    assert refused("07700 900123", "GB")
    assert refused("+34 6001112229", "ES")


def test_an_unknown_calling_code_is_refused():
    assert refused("+999 123 456 789", "ES")


@pytest.mark.parametrize(
    "e164",
    ["+34600111222", "+447911123456", "+390612345678", "+12125550123", "+78001234567"],
)
def test_an_e164_number_is_read_back_as_itself(e164):
    # What was saved yesterday is read again today: the canonical form is a fixed point.
    assert ok(e164, "ES") == e164
    assert ok(e164, "US") == e164


# candidates: how CUSTOMER-F10 reads the question (the creation's reading plus WhatsApp's)


def test_whatsapp_digits_are_also_read_as_an_international_number():
    # A British «447911123456» writing to a Spanish salon is no Spanish number.
    assert candidates("447911123456", "ES") == {"+447911123456"}


def test_the_question_is_read_like_a_creation_first():
    assert candidates("600 111 222", "ES") == {"+34600111222"}
    assert candidates("34600111222", "ES") == {"+34600111222"}
    assert candidates("+44 (0)7911 123456", "ES") == {"+447911123456"}
    assert candidates("0044 (0)7911 123456", "ES") == {"+447911123456"}


def test_digits_that_read_the_same_both_ways_give_one_number():
    # In Italy «39061234567» is +39 06 1234567 read as typed and as WhatsApp sends it.
    assert candidates("39061234567", "IT") == {"+39061234567"}
    assert candidates("34600111222", "ES") == {"+34600111222"}


def test_another_countrys_digits_read_only_as_theirs():
    assert candidates("33612345678", "ES") == {"+33612345678"}


@pytest.mark.parametrize("question", ["", "   ", "+ -", "600111", "call me", None])
def test_a_question_nobody_can_read_asks_nothing(question):
    assert candidates(question, "ES") == set()
