//! A phone number in E.164 (`+34600111222`) — the ONE reading every module handler shares
//! (ERPlora/appointments#313).
//!
//! The phone is what the hub compares people by: Customers saves the card's number in E.164
//! (customers#121, CUSTOMERS-F11), Appointments keeps a copy on each appointment, and the
//! «appointment confirmed» WhatsApp looks the conversation up with that copy by the exact
//! international number. A phone saved as typed («600 111 222», «600111») either matched nobody or
//! matched somebody else, so every write of a phone goes through [`to_e164`]: one canonical form,
//! or a refusal. It lived in Customers' handler first; it is here so a second module reads a typed
//! number exactly as the first one did, instead of carrying its own copy of the rules.
//!
//! The rules are libphonenumber's, on its own metadata ([`REGIONS`], generated from it by
//! `crates/guest-sdk/tools/phone-metadata`): the library itself does not fit the hub's WASM sandbox
//! (loading its metadata spends more fuel than a handler call is given). The contract is
//! `tests/phone_test.rs`.

mod metadata;

pub use metadata::{Region, REGIONS};

/// The country a number without prefix belongs to when the hub never saved one (CUSTOMERS-F10).
pub const DEFAULT_COUNTRY: &str = "ES";

/// The typed text is not a phone number of its country.
#[derive(Debug, PartialEq, Eq)]
pub struct InvalidPhone;

/// `raw` as E.164, reading a number without prefix as one of `home_iso` (the business's country,
/// ISO 3166 alpha-2; empty or unknown → [`DEFAULT_COUNTRY`]). The empty phone stays empty: only
/// the name is required on a card or an appointment.
///
/// Accepted: digits with spaces, `-`, `.`, `/` and parentheses, an optional leading `+` or the
/// international call prefix dialled from the business's country (`00` in Spain), and a national
/// trunk prefix (`07700…` in the United Kingdom, `+44 (0)7700…`). Refused: letters (an extension,
/// a note), more than one `+`, and a national number whose length is not possible for its country
/// («600111» in Spain) — that also catches two numbers typed in the same field.
pub fn to_e164(raw: &str, home_iso: &str) -> Result<String, InvalidPhone> {
    let text = raw.trim();
    if text.is_empty() {
        return Ok(String::new());
    }
    let mut digits = String::new();
    let mut plus = false;
    for c in text.chars() {
        match c {
            '0'..='9' => digits.push(c),
            '+' if !plus && digits.is_empty() => plus = true,
            ' ' | '\u{a0}' | '\t' | '-' | '.' | '/' | '(' | ')' => {}
            _ => return Err(InvalidPhone),
        }
    }
    let home = home_region(home_iso).ok_or(InvalidPhone)?;

    if plus {
        return international(&digits);
    }
    if !home.idd.is_empty() && digits.len() > home.idd.len() && digits.starts_with(home.idd) {
        return international(&digits[home.idd.len()..]);
    }
    let national = strip_trunk(&digits, home.trunk, home.code);
    if possible(home.code, national) {
        return Ok(format!("+{}{}", home.code, national));
    }
    // «34600111222» typed in Spain: the business's own calling code without its `+`.
    if let Some(rest) = digits.strip_prefix(home.code) {
        if possible(home.code, rest) {
            return Ok(format!("+{}{}", home.code, rest));
        }
    }
    Err(InvalidPhone)
}

/// The business's region; an empty or unknown code falls back to [`DEFAULT_COUNTRY`] (always in
/// the generated table — `default_country_is_in_the_table` pins it).
fn home_region(iso: &str) -> Option<&'static Region> {
    let iso = iso.trim().to_ascii_uppercase();
    REGIONS
        .iter()
        .find(|r| r.iso == iso)
        .or_else(|| REGIONS.iter().find(|r| r.iso == DEFAULT_COUNTRY))
}

/// Digits after the `+` (or after the international call prefix): calling code, then national.
fn international(digits: &str) -> Result<String, InvalidPhone> {
    // Calling codes are prefix-free (ITU-T E.164): the first 1–3 digit prefix that is one, is it.
    let code = (1..=3.min(digits.len()))
        .map(|n| &digits[..n])
        .find(|prefix| REGIONS.iter().any(|r| r.code == *prefix))
        .ok_or(InvalidPhone)?;
    let rest = &digits[code.len()..];
    // Every region of a shared calling code dials the same trunk prefix (pinned by
    // `regions_sharing_a_calling_code_share_their_trunk_prefix`).
    let trunk = REGIONS
        .iter()
        .find(|r| r.code == code)
        .map_or("", |r| r.trunk);
    let national = strip_trunk(rest, trunk, code);
    if possible(code, national) {
        Ok(format!("+{code}{national}"))
    } else {
        Err(InvalidPhone)
    }
}

/// Drops the national trunk prefix. A trunk `0` always goes: no country that dials one writes its
/// numbers with a `0` after the calling code, so what is left has to stand on its own (Italy and
/// the others that keep their `0` have no trunk prefix). Another trunk digit goes only when the
/// number is not possible with it: Russia's `8 800…` freephone, typed without its trunk, begins
/// with an `8` of its own. (Without a trunk prefix, `rest` is `digits`.)
fn strip_trunk<'a>(digits: &'a str, trunk: &str, code: &str) -> &'a str {
    match digits.strip_prefix(trunk) {
        Some(rest)
            if trunk == "0" || !possible(code, digits) =>
        {
            rest
        }
        _ => digits,
    }
}

/// Whether `national` has a length some region of `code` allows.
fn possible(code: &str, national: &str) -> bool {
    // No region has a zero length, so the empty number is never possible.
    let len = national.len();
    REGIONS
            .iter()
            .filter(|r| r.code == code)
            .any(|r| r.lengths.iter().any(|l| usize::from(*l) == len))
}
