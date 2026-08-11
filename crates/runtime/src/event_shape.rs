//! **What an event actually carries**, learned from the hub's own events (hub#715).
//!
//! The flow editor (pm#110) has to let an owner say «the total of the sale goes in the message».
//! To offer that it needs to know what fields a `sale.completed` carries — and the hub had no way
//! to tell it:
//!
//! - there is **no payload schema**. `emit` is an array of strings in `schemas/module.schema.json`
//!   (ADR-0127 phase 3, declared and never built): nothing describes the shape of a payload;
//! - the payloads **are** stored, in `_event_outbox.payload`, but the only endpoint that ever
//!   returned one is `GET /api/hub/events/dead` — and only for events that FAILED. A healthy hub
//!   has none.
//!
//! So the shape is inferred from **real events of this hub**, which is also where the research
//! behind the editor landed: the owner should not pick `sale.total`, they should pick «Total de la
//! venta — 42,50 €» with the number from their own last sale beside it. It is the project's
//! no-mocks rule applied to a picker.
//!
//! # What is handed out: the SHAPE, not the payload
//!
//! This module returns keys + type + **one sample value**, never the stored payload. The
//! difference is not cosmetic:
//!
//! - The consumer is a **module from the marketplace** reaching this through `manage_flows`
//!   (hub#714). A route that returns the last N payloads of any event is an export of the
//!   business's customer data with an editor drawn on top: page `sale.completed`,
//!   `appointment.booked`, `customer.created` and you have the address book. The shape answers the
//!   editor's question and hands over strictly less of what it did not ask for.
//! - It is also the better answer. N raw payloads make the editor diff them itself, and it still
//!   would not know that a field is only there *sometimes* — which is exactly what breaks a
//!   mapping three weeks later. [`EventField::seen_in`] says it.
//!
//! The dead-letter queue keeps returning the whole payload, and that stays right: there an
//! operator is deciding whether to replay one specific row, and the payload IS the decision.
//!
//! # What happens to values that look like a person
//!
//! **The field is always listed; only the sample is withheld.** The editor needs to know that
//! `customer.email` exists — that is how the owner maps it into a message — but it does not need
//! to show a customer's email address to render the option. A withheld field arrives with
//! `redacted: true` and no `sample`, and the picker shows «Email del cliente» with no example.
//!
//! Three signals, any one of them enough:
//!
//! 1. **The path.** A segment — the leaf or any ancestor — whose words name a person, a credential
//!    or a personal container: `customer.name`, `client_email`, `tax_id`, `iban`, `pin`. Ancestors
//!    count, which is why the container list can stay short and blunt: everything under `customer`
//!    is withheld and `product.name` is not.
//! 2. **The key is free text** — `note`, `comment`, `description`. A hairdresser's note field can
//!    hold anything, up to and including health data, and no value-level rule sees that coming.
//! 3. **The value.** An email address, an IBAN, a card-length run of digits, a `+34…` phone —
//!    wherever the key happens to be called.
//!
//! It errs towards withholding on purpose: a false positive costs the editor one example, a false
//! negative puts a customer's phone number on somebody's screen. And it is **minimisation, not
//! anonymisation** — claiming otherwise would be false. A sample is a real value from a real
//! event; what this does is refuse to hand one over wherever that value could be about a person.
//!
//! # Why nothing is offered from inside an array
//!
//! [`crate::flows::def::resolve_path`] walks `a.b.c` and **has no array indexing** — deliberately
//! (v1 maps fields; «the third line of the ticket» belongs in a query). So an array is listed as
//! one field with its length and the walk does not descend into it. Offering `lines.0.total` would
//! be offering a mapping the kernel cannot resolve, which is worse than offering nothing.

use std::collections::BTreeMap;

use serde_json::Value as Json;

/// Samples read when the caller does not ask for a number. Enough for [`EventField::seen_in`] to
/// mean something, small enough that the reply is not a page of a hub's history.
pub const DEFAULT_SAMPLES: i64 = 5;

/// The most anybody may ask for. More samples exist to catch optional fields; past this the reply
/// grows without the picker getting better.
pub const MAX_SAMPLES: i64 = 20;

/// Hard cap on how many fields one shape describes. A payload with thousands of keys is a bug
/// somewhere, and truncating beats answering with a document nothing can render.
pub const MAX_FIELDS: usize = 200;

/// How deep the walk goes. Nesting past this is not something a person maps in a picker.
pub const MAX_DEPTH: usize = 6;

/// How much of a string sample survives. An example is there to be recognised, not read.
pub const MAX_SAMPLE_CHARS: usize = 64;

/// Words that name a person or a credential, matched against the words of ANY segment of a path —
/// so `customer.email`, `client_email` and `billing.email` are the same answer.
const PERSONAL_WORDS: &[&str] = &[
    "email",
    "mail",
    "phone",
    "mobile",
    "telephone",
    "tel",
    "whatsapp",
    "address",
    "street",
    "postcode",
    "postalcode",
    "zipcode",
    "iban",
    "bic",
    "swift",
    "card",
    "cardnumber",
    "pan",
    "cvv",
    "cvc",
    "nif",
    "cif",
    "dni",
    "nie",
    "nss",
    "ssn",
    "taxid",
    "vatnumber",
    "accountnumber",
    "passport",
    "birthdate",
    "birthday",
    "dob",
    "password",
    "secret",
    "token",
    "apikey",
    "authorization",
    "pin",
    "latitude",
    "longitude",
    "lat",
    "lng",
];

/// Words that make a whole subtree personal. Deliberately blunt: this is the rule that catches
/// `customer.name`, which no leaf-key list can, without also hiding `product.name`.
const PERSONAL_CONTAINERS: &[&str] = &[
    "customer",
    "client",
    "patient",
    "contact",
    "recipient",
    "employee",
    "staff",
    "user",
    "member",
    "guest",
    "attendee",
    "billing",
    "shipping",
    "payer",
];

/// Keys whose value is FREE TEXT. Nothing about the value tells you what a person typed there, so
/// the sample never leaves.
const FREE_TEXT_WORDS: &[&str] = &[
    "note",
    "notes",
    "comment",
    "comments",
    "description",
    "message",
    "body",
    "reason",
    "observations",
    "remarks",
    "feedback",
];

/// One field of an event payload, as the editor needs it: a path its mapping language can resolve,
/// what kind of value lives there, and — when it is safe to hand over — one real example.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct EventField {
    /// The path as [`crate::flows::def::resolve_path`] walks it (`total`, `customer.id`), so the
    /// editor can paste `event.<path>` into a mapping and have it resolve.
    pub path: String,
    /// JSON type: `string` · `number` · `boolean` · `object` · `array` · `null`.
    #[serde(rename = "type")]
    pub kind: &'static str,
    /// A real value from a real event of this hub. Absent when it was withheld
    /// ([`EventField::redacted`]) or when the field holds an object or an array.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sample: Option<Json>,
    /// The sample was withheld because the value could be about a person. **The field is still
    /// here**: the editor offers it, it just has no example to show.
    pub redacted: bool,
    /// The sample was cut at [`MAX_SAMPLE_CHARS`].
    pub truncated: bool,
    /// Items in the newest sample, for an `array`. The walk does not go inside (see the module
    /// header): the mapping language has no array indexing.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub items: Option<usize>,
    /// In how many of the sampled events this path was present. Fewer than
    /// [`EventShape::samples`] means **optional**, which is the thing that quietly breaks a
    /// mapping weeks after somebody drew it.
    pub seen_in: usize,
}

/// Everything this hub knows about one event name.
#[derive(Debug, Clone, serde::Serialize)]
pub struct EventShape {
    pub event_name: String,
    /// Installed modules that declare they emit it (`events.emits`, or a command's `emit`). Empty
    /// with `samples > 0` means it happened but nobody declares it — a core event, or a manifest
    /// with the hole hub#722 warns about.
    pub declared_by: Vec<String>,
    /// How many real events the shape was inferred from. **`0` is a first-class answer**: the
    /// event is known but no example survives — it has never fired, or the last one aged out of
    /// the ninety-day window (hub#699). The editor says «todavía sin ejemplos» instead of
    /// pretending the event does not exist, which is what a `404` means.
    pub samples: usize,
    /// When the newest sampled event happened. `None` when there are no samples.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_seen_at: Option<String>,
    /// Sorted by path, so two calls against a hub that has not traded answer the same thing.
    pub fields: Vec<EventField>,
}

/// What is accumulated across the sampled payloads for one path.
#[derive(Debug)]
struct Acc {
    kind: &'static str,
    sample: Option<Json>,
    redacted: bool,
    truncated: bool,
    items: Option<usize>,
    seen_in: usize,
}

/// The union of the fields of `payloads`, **newest first**.
///
/// Newest first is load-bearing: a path's sample comes from the most recent event that carried it,
/// which is the one whose numbers the owner recognises.
pub fn infer(payloads: &[Json]) -> Vec<EventField> {
    let mut acc: BTreeMap<String, Acc> = BTreeMap::new();
    for payload in payloads {
        walk(payload, "", 0, &mut acc);
    }
    acc.into_iter()
        .map(|(path, a)| EventField {
            path,
            kind: a.kind,
            sample: a.sample,
            redacted: a.redacted,
            truncated: a.truncated,
            items: a.items,
            seen_in: a.seen_in,
        })
        .collect()
}

fn walk(value: &Json, prefix: &str, depth: usize, acc: &mut BTreeMap<String, Acc>) {
    // A payload that is not an object has no paths to offer. `_event_outbox.payload` is always
    // written from a params map, so this is the unparseable-row case, not a shape.
    let Json::Object(map) = value else {
        return;
    };
    for (key, child) in map {
        let path = join(prefix, key);
        if acc.len() >= MAX_FIELDS && !acc.contains_key(&path) {
            continue;
        }
        record(&path, child, acc);
        if matches!(child, Json::Object(_)) && depth + 1 < MAX_DEPTH {
            walk(child, &path, depth + 1, acc);
        }
    }
}

fn join(prefix: &str, key: &str) -> String {
    if prefix.is_empty() {
        key.to_string()
    } else {
        format!("{prefix}.{key}")
    }
}

fn record(path: &str, value: &Json, acc: &mut BTreeMap<String, Acc>) {
    let kind = kind_of(value);
    let withheld = withhold(path, value);
    let (sample, truncated) = if withheld {
        (None, false)
    } else {
        sample_of(value)
    };
    let items = match value {
        Json::Array(items) => Some(items.len()),
        _ => None,
    };
    match acc.get_mut(path) {
        Some(existing) => {
            existing.seen_in += 1;
            // Once withheld, always withheld: the same key in an older event is the same key.
            existing.redacted |= withheld;
            if existing.redacted {
                existing.sample = None;
            } else if existing.sample.as_ref().is_none_or(Json::is_null)
                && !matches!(value, Json::Null)
            {
                // The newest event had nothing there and an older one does. That older value is
                // exactly the example the owner needs: a picker whose only sample is `null`
                // teaches nothing about the field.
                existing.kind = kind;
                existing.sample = sample;
                existing.truncated = truncated;
                existing.items = items;
            }
        }
        None => {
            acc.insert(
                path.to_string(),
                Acc {
                    kind,
                    sample,
                    redacted: withheld,
                    truncated,
                    items,
                    seen_in: 1,
                },
            );
        }
    }
}

fn kind_of(value: &Json) -> &'static str {
    match value {
        Json::Null => "null",
        Json::Bool(_) => "boolean",
        Json::Number(_) => "number",
        Json::String(_) => "string",
        Json::Array(_) => "array",
        Json::Object(_) => "object",
    }
}

/// The example for a value, already cut to [`MAX_SAMPLE_CHARS`]. Objects and arrays get none: an
/// object sample is the payload dump this module exists in order not to be.
fn sample_of(value: &Json) -> (Option<Json>, bool) {
    match value {
        Json::String(s) => {
            let mut rest = s.chars();
            let cut: String = rest.by_ref().take(MAX_SAMPLE_CHARS).collect();
            if rest.next().is_some() {
                (Some(Json::String(format!("{cut}…"))), true)
            } else {
                (Some(Json::String(cut)), false)
            }
        }
        Json::Object(_) | Json::Array(_) => (None, false),
        other => (Some(other.clone()), false),
    }
}

/// Whether this value's example stays inside the hub. The three signals of the module header.
fn withhold(path: &str, value: &Json) -> bool {
    if path_is_personal(path) || key_is_free_text(path) {
        return true;
    }
    match value {
        Json::String(s) => value_looks_personal(s),
        _ => false,
    }
}

/// Any segment of the path — the leaf or any ancestor — naming a person, a credential or a
/// personal container.
fn path_is_personal(path: &str) -> bool {
    path.split('.').any(|segment| {
        terms(segment).any(|t| {
            PERSONAL_WORDS.contains(&t.as_str()) || PERSONAL_CONTAINERS.contains(&t.as_str())
        })
    })
}

/// Only the leaf: `notes.customer_id` is an id, `customer.notes` is free text.
fn key_is_free_text(path: &str) -> bool {
    let leaf = path.rsplit('.').next().unwrap_or(path);
    terms(leaf).any(|t| FREE_TEXT_WORDS.contains(&t.as_str()))
}

/// The terms of one key: its words plus its adjacent PAIRS.
///
/// Words come from lowercasing and splitting on `_`, `-`, ` ` and camelCase boundaries, so
/// `customerEmail`, `customer_email` and `customer-email` read the same. The pairs are what
/// catches the compound names that mean something only together — `tax_id`, `card_number`,
/// `postal_code` — without putting `tax`, `card` or `code` on a list that would then hide
/// `tax_rate` and `discount_code`, which are exactly the samples a picker needs.
fn terms(segment: &str) -> impl Iterator<Item = String> {
    let mut words: Vec<String> = Vec::new();
    let mut current = String::new();
    for ch in segment.chars() {
        if ch == '_' || ch == '-' || ch == ' ' {
            if !current.is_empty() {
                words.push(std::mem::take(&mut current));
            }
        } else if ch.is_ascii_uppercase() && !current.is_empty() {
            words.push(std::mem::take(&mut current));
            current.push(ch.to_ascii_lowercase());
        } else {
            current.push(ch.to_ascii_lowercase());
        }
    }
    if !current.is_empty() {
        words.push(current);
    }
    let pairs: Vec<String> = words.windows(2).map(|w| format!("{}{}", w[0], w[1])).collect();
    words.into_iter().chain(pairs)
}

/// A value that could be about a person whatever its key is called.
fn value_looks_personal(s: &str) -> bool {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        return false;
    }
    // An email address, wherever it lives.
    if let Some((local, domain)) = trimmed.split_once('@') {
        if !local.is_empty()
            && domain.contains('.')
            && !trimmed.chars().any(char::is_whitespace)
            && trimmed.len() <= 254
        {
            return true;
        }
    }
    let compact: String = trimmed
        .chars()
        .filter(|c| !c.is_whitespace() && *c != '-' && *c != '.')
        .collect();
    // A card, an IBAN, an account or a phone: a run of digits nobody writes by hand. Eleven is
    // below a Spanish mobile with its prefix and below every card length, and deliberately below
    // rather than above — a timestamp caught by it costs one example, a phone missed by it does not.
    let mut run = 0usize;
    for ch in compact.chars() {
        if ch.is_ascii_digit() {
            run += 1;
            if run >= 11 {
                return true;
            }
        } else {
            run = 0;
        }
    }
    // `ES91 2100 0418 4502 0005 1332`: two letters, two digits, then alphanumerics.
    let bytes = compact.as_bytes();
    if (15..=34).contains(&compact.len())
        && bytes[..2].iter().all(u8::is_ascii_alphabetic)
        && bytes[2..4].iter().all(u8::is_ascii_digit)
        && bytes[4..].iter().all(u8::is_ascii_alphanumeric)
    {
        return true;
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn shape(payloads: &[Json]) -> BTreeMap<String, EventField> {
        infer(payloads)
            .into_iter()
            .map(|f| (f.path.clone(), f))
            .collect()
    }

    /// A path is offered only where the mapping language can walk it: into objects, never into an
    /// array. `resolve_path` splits on `.` and indexes nothing.
    #[test]
    fn objects_are_walked_and_arrays_are_not() {
        let fields = shape(&[json!({
            "total": "42.50",
            "customer": { "id": "c-1", "loyalty": { "points": 12 } },
            "lines": [{ "sku": "a" }, { "sku": "b" }]
        })]);

        assert!(fields.contains_key("customer.id"));
        assert!(fields.contains_key("customer.loyalty.points"));
        assert_eq!(fields["lines"].kind, "array");
        assert_eq!(fields["lines"].items, Some(2));
        assert_eq!(fields["lines"].sample, None);
        assert!(
            !fields.keys().any(|p| p.starts_with("lines.")),
            "an offered path the kernel cannot resolve is worse than no path: {:?}",
            fields.keys().collect::<Vec<_>>()
        );
    }

    /// The container rule is what makes the leaf lists able to stay short — and what keeps
    /// `product.name` usable while `customer.name` is not.
    #[test]
    fn everything_under_a_personal_container_is_withheld_and_nothing_else_is() {
        let fields = shape(&[json!({
            "customer": { "name": "Marta", "id": "c-1" },
            "product": { "name": "Corte de pelo", "id": "p-1" },
            "total": "42.50"
        })]);

        for withheld in ["customer.name", "customer.id"] {
            assert!(fields[withheld].redacted, "{withheld} was handed over");
            assert_eq!(fields[withheld].sample, None);
        }
        assert!(!fields["product.name"].redacted);
        assert_eq!(fields["product.name"].sample, Some(json!("Corte de pelo")));
        assert_eq!(fields["total"].sample, Some(json!("42.50")));
    }

    /// Compound keys mean something their words do not. `tax_id` is a person's when the business
    /// is a sole trader; `tax_rate` is a number a picker should show.
    #[test]
    fn a_compound_key_is_judged_as_a_pair_not_as_its_words() {
        let fields = shape(&[json!({
            "tax_id": "B12345678",
            "taxRate": 21,
            "card_number": "4111111111111111",
            "discount_code": "VERANO",
            "postal_code": "08001",
            "line_count": 3
        })]);

        for withheld in ["tax_id", "card_number", "postal_code"] {
            assert!(fields[withheld].redacted, "{withheld} was handed over");
        }
        for kept in ["taxRate", "discount_code", "line_count"] {
            assert!(
                !fields[kept].redacted,
                "{kept} lost its example: a rule that hides everything makes the picker useless"
            );
        }
    }

    /// The value is the last line of defence: a key nobody could have predicted, holding something
    /// that is unmistakably about a person.
    #[test]
    fn a_personal_value_is_withheld_whatever_its_key_is_called() {
        let fields = shape(&[json!({
            "ref": "marta@example.com",
            "code": "+34600111222",
            "account": "ES9121000418450200051332",
            "sku": "CORTE-2026",
            "invoice_number": "F2026-0001"
        })]);

        for withheld in ["ref", "code", "account"] {
            assert!(fields[withheld].redacted, "{withheld} was handed over");
        }
        assert!(!fields["sku"].redacted);
        assert!(
            !fields["invoice_number"].redacted,
            "an invoice number is not a person"
        );
    }

    /// Free text can hold anything a person typed, including what a salon knows about a client's
    /// health. No value rule sees that coming, so the key alone decides.
    #[test]
    fn free_text_never_carries_an_example() {
        let fields = shape(&[json!({
            "note": "alérgica al amoniaco",
            "description": "Corte + color",
            "notes": { "customer_id": "c-1" }
        })]);

        assert!(fields["note"].redacted);
        assert!(fields["description"].redacted);
        assert!(
            fields["notes.customer_id"].redacted,
            "…and a personal ancestor still decides for its leaves"
        );
    }

    /// A sample is there to be recognised, not read: a long string is cut, and says it was.
    #[test]
    fn a_long_sample_is_cut_and_admits_it() {
        let long = "x".repeat(MAX_SAMPLE_CHARS + 20);
        let fields = shape(&[json!({ "label": long })]);

        assert!(fields["label"].truncated);
        let sample = fields["label"].sample.as_ref().unwrap().as_str().unwrap();
        assert_eq!(sample.chars().count(), MAX_SAMPLE_CHARS + 1, "cut plus the ellipsis");
        assert!(sample.ends_with('…'));
    }

    /// Several events: the count says which fields are optional, and a field that is `null` in the
    /// newest one still gets the example an older one can give.
    #[test]
    fn the_union_says_what_is_optional_and_finds_the_useful_example() {
        let fields = shape(&[
            json!({ "total": "20.00", "discount": null }),
            json!({ "total": "10.00", "discount": "2.00", "coupon": "VERANO" }),
        ]);

        assert_eq!(fields["total"].seen_in, 2);
        assert_eq!(
            fields["total"].sample,
            Some(json!("20.00")),
            "the newest event supplies the example"
        );
        assert_eq!(fields["coupon"].seen_in, 1, "present in one of two = optional");
        assert_eq!(
            fields["discount"].sample,
            Some(json!("2.00")),
            "a `null` in the newest sale teaches nothing; an older real value does"
        );
        assert_eq!(fields["discount"].kind, "string");
    }

    /// A payload that is not an object has no paths, and does not panic on the way to saying so.
    #[test]
    fn a_payload_that_is_not_an_object_has_no_fields() {
        assert_eq!(infer(&[json!("just a string"), json!(7), json!(null)]), Vec::new());
    }

    /// A pathological payload cannot make the reply unbounded.
    #[test]
    fn the_walk_is_bounded_in_width_and_in_depth() {
        let mut wide = serde_json::Map::new();
        for i in 0..(MAX_FIELDS * 2) {
            wide.insert(format!("f{i}"), json!(i));
        }
        assert!(infer(&[Json::Object(wide)]).len() <= MAX_FIELDS);

        let mut deep = json!({ "leaf": 1 });
        for _ in 0..(MAX_DEPTH * 3) {
            deep = json!({ "n": deep });
        }
        assert!(infer(&[deep])
            .iter()
            .all(|f| f.path.split('.').count() <= MAX_DEPTH));
    }
}
