//! The phone contract (ERPlora/appointments#313) — ONE reading of a typed phone for every module.
//!
//! Customers learnt to save a card's phone in E.164 (customers#121) with its own copy of the
//! libphonenumber rules, and Appointments needed the very same reading for the copy it keeps on
//! each appointment: the «appointment confirmed» WhatsApp is only sent to the exact international
//! number. A second copy of the rules is how two modules end up reading «600 111 222» as two
//! different people, so the reading lives here, next to the money and the tax rule.
//!
//! These tests are the contract every handler that links `erplora_guest_sdk::phone` shares.

use erplora_guest_sdk::phone::{to_e164, InvalidPhone, DEFAULT_COUNTRY, REGIONS};

fn ok(raw: &str, home: &str) -> String {
    to_e164(raw, home).unwrap_or_else(|_| panic!("{raw:?} in {home} must be valid"))
}

#[test]
fn spanish_number_typed_any_way_is_one_e164() {
    for raw in [
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
    ] {
        assert_eq!(ok(raw, "ES"), "+34600111222", "{raw:?}");
    }
}

#[test]
fn empty_phone_stays_empty() {
    assert_eq!(to_e164("", "ES"), Ok(String::new()));
    assert_eq!(to_e164("   ", "ES"), Ok(String::new()));
}

#[test]
fn number_too_short_or_too_long_for_its_country_is_refused() {
    assert_eq!(to_e164("600111", "ES"), Err(InvalidPhone));
    assert_eq!(to_e164("12", "ES"), Err(InvalidPhone));
    assert_eq!(to_e164("+34 600 111", "ES"), Err(InvalidPhone));
    // Two numbers in one field.
    assert_eq!(to_e164("600111222 / 611222333", "ES"), Err(InvalidPhone));
}

#[test]
fn letters_extension_or_a_second_plus_are_refused() {
    assert_eq!(to_e164("600 111 222 ext 12", "ES"), Err(InvalidPhone));
    assert_eq!(to_e164("call me", "ES"), Err(InvalidPhone));
    assert_eq!(to_e164("+34 +600111222", "ES"), Err(InvalidPhone));
    assert_eq!(to_e164("600+111222", "ES"), Err(InvalidPhone));
    assert_eq!(to_e164("+", "ES"), Err(InvalidPhone));
}

#[test]
fn a_plus_after_the_first_digit_is_refused_even_when_the_digits_would_read_as_a_number() {
    // «600+111222» above is refused whatever the rule: its digits are no number. These digits ARE
    // one once the `+` is taken as the international mark, so only the rule «a `+` goes before the
    // first digit» refuses them.
    assert_eq!(to_e164("34+600111222", "ES"), Err(InvalidPhone));
    assert_eq!(to_e164("600 111 222 +34", "ES"), Err(InvalidPhone));
}

#[test]
fn foreign_number_keeps_its_own_country() {
    assert_eq!(ok("+33 6 12 34 56 78", "ES"), "+33612345678");
    assert_eq!(ok("0033 6 12 34 56 78", "ES"), "+33612345678");
    // Same national digits, another country: another person.
    assert_ne!(ok("+33 600 111 222", "ES"), ok("600 111 222", "ES"));
}

#[test]
fn trunk_zero_is_dropped_nationally_and_inside_parentheses() {
    assert_eq!(ok("07700 900123", "GB"), "+447700900123");
    assert_eq!(ok("+44 (0)7700 900123", "ES"), "+447700900123");
    assert_eq!(ok("+44 7700 900123", "ES"), "+447700900123");
    assert_eq!(ok("06 12 34 56 78", "FR"), "+33612345678");
}

#[test]
fn trunk_zero_is_dropped_even_when_the_number_would_be_possible_with_it() {
    // Germany allows 4 to 15 digits, so «0301234567» is a possible length WITH its trunk zero too;
    // libphonenumber still drops it — no German number starts with 0 after the +49.
    assert_eq!(ok("030 12345678", "DE"), "+493012345678");
    assert_eq!(ok("+49 (0)30 12345678", "ES"), "+493012345678");
}

#[test]
fn a_trunk_zero_never_survives_behind_the_calling_code() {
    // «01234 5678» in the United Kingdom is 8 digits after its trunk zero: not a UK number. It must
    // be refused, not saved as «+44012345678», which no UK number looks like.
    assert_eq!(to_e164("01234 5678", "GB"), Err(InvalidPhone));
    assert_eq!(to_e164("+44 01234 5678", "ES"), Err(InvalidPhone));
}

#[test]
fn a_leading_trunk_digit_stays_when_dropping_it_leaves_no_possible_number() {
    // Russian freephone typed WITHOUT the trunk «8»: its own first 8 is part of the number.
    assert_eq!(ok("800 123-45-67", "RU"), "+78001234567");
}

#[test]
fn regions_sharing_a_calling_code_share_their_trunk_prefix() {
    // The international reading takes the trunk of the first region with the calling code (+1 is
    // the United States, Canada and the Caribbean; +7 Russia and Kazakhstan): it is only right
    // while every region behind one code dials the same trunk prefix.
    for r in REGIONS {
        for other in REGIONS.iter().filter(|o| o.code == r.code) {
            assert_eq!(r.trunk, other.trunk, "{} and {} share +{}", r.iso, other.iso, r.code);
        }
    }
}

#[test]
fn italy_keeps_its_leading_zero() {
    assert_eq!(ok("06 1234 5678", "IT"), "+390612345678");
    assert_eq!(ok("+39 06 1234 5678", "ES"), "+390612345678");
}

#[test]
fn international_prefix_of_the_business_country_is_read() {
    // From the United States, `011` is the international prefix.
    assert_eq!(ok("011 34 600 111 222", "US"), "+34600111222");
    assert_eq!(ok("(212) 555-0123", "US"), "+12125550123");
    assert_eq!(ok("1 212 555 0123", "US"), "+12125550123");
}

#[test]
fn the_national_reading_wins_over_the_own_calling_code_without_plus() {
    // Germany allows 4 to 15 digits: «4930 123456» is possible as it stands AND as «49» +
    // «30123456». Read nationally first.
    assert_eq!(ok("4930 123456", "DE"), "+494930123456");
}

#[test]
fn russian_freephone_keeps_its_eight() {
    // `8` is Russia's trunk prefix AND the first digit of its freephone numbers.
    assert_eq!(ok("+7 800 123 45 67", "ES"), "+78001234567");
    assert_eq!(ok("8 912 345 67 89", "RU"), "+79123456789");
}

#[test]
fn unknown_or_empty_business_country_reads_as_spain() {
    assert_eq!(ok("600 111 222", ""), "+34600111222");
    assert_eq!(ok("600 111 222", "es"), "+34600111222");
    assert_eq!(ok("600 111 222", "XX"), "+34600111222");
}

#[test]
fn default_country_is_in_the_table() {
    assert!(REGIONS.iter().any(|r| r.iso == DEFAULT_COUNTRY));
}

#[test]
fn unknown_calling_code_is_refused() {
    // +999 is not assigned.
    assert_eq!(to_e164("+999 123 456 789", "ES"), Err(InvalidPhone));
}

#[test]
fn an_e164_number_is_read_back_as_itself() {
    // What a module saved yesterday is read again today (a sweep, an edit that keeps the phone):
    // the canonical form must be a fixed point, or every pass would rewrite it.
    for e164 in ["+34600111222", "+447700900123", "+390612345678", "+12125550123", "+78001234567"] {
        assert_eq!(ok(e164, "ES"), e164);
        assert_eq!(ok(e164, "US"), e164);
    }
}
