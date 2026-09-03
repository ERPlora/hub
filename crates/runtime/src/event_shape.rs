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
//! Four signals, any one of them enough:
//!
//! 1. **The path.** A segment — the leaf or any ancestor — whose words name a person, a credential
//!    or a personal container: `customer.name`, `client_email`, `tax_id`, `iban`, `pin`. Ancestors
//!    count, which is why the container list can stay short and blunt: everything under `customer`
//!    is withheld and `product.name` is not.
//! 2. **The name of the EVENT**, for the payload that is flat. See below.
//! 3. **The key is free text** — `note`, `comment`, `description`. A hairdresser's note field can
//!    hold anything, up to and including health data, and no value-level rule sees that coming.
//! 4. **The value.** An email address, an IBAN, a card-length run of digits, a `+34…` phone —
//!    wherever the key happens to be called.
//!
//! # The signal the payload does not carry: the event's own name (hub#826)
//!
//! Signal 1 reads the path, and a flat payload has no path to read. `customers.create` emits the
//! whole card at the root — `name`, `city`, `company_name`, `email` — so there is no `customer.`
//! ancestor anywhere and the container rule, whose documented example is literally `customer.name`,
//! never fired for the case it was written for. `customer.created` handed over a real client's name
//! and city to any marketplace module holding `manage_flows`; `email` and `phone` were saved only
//! by signal 4, which reads values and cannot help with a name.
//!
//! The entity is in the event NAME, which the caller has and the payload dropped. So the entity of
//! `<entity>.<verb>` is read as an implicit root of every path — but it is a **weaker** signal than
//! an ancestor that is really there, and deliberately:
//!
//! - a `customer` **object inside a payload** is that person's record; everything in it was put
//!   there because of them, so the whole subtree goes (`customer.id` included);
//! - the event **name** is not in the payload. A `customer.created` payload mixes the person's own
//!   fields with the hub's bookkeeping ABOUT them — `lifecycle_stage`, `created_at`, `source`,
//!   what they have spent. Promoting the whole payload would cost the picker every amount, date,
//!   quantity and state it exists to show, and none of those is personal data. So the name
//!   promotes only the keys that name a person ([`PERSONAL_WHEN_ABOUT_A_PERSON`]): `name` is a
//!   haircut under `product.created` and a client under `customer.created`.
//!
//! `declared_by` is computed next door and is NOT used for this: it depends on which modules happen
//! to be installed, so the same event would answer differently on two hubs, and a module called
//! `reminders` declaring `customer.created` does not change whose data it is. The name is the
//! contract; the install list is not.
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

/// Words that name a person **only once something else says the record is about one** (hub#826).
///
/// They cannot go in [`PERSONAL_WORDS`] — that would withhold `product.name`, the example the
/// picker most needs — and they cannot go in [`PERSONAL_CONTAINERS`]: these are leaves, not
/// containers. What promotes them is the entity of the event name ([`event_is_about_a_person`]) or
/// a personal ancestor in the path, which is the only context in which `name` and `city` stop being
/// a haircut and a branch and become a client and where they live.
const PERSONAL_WHEN_ABOUT_A_PERSON: &[&str] = &[
    "name",
    "firstname",
    "lastname",
    "surname",
    "fullname",
    "nickname",
    "initials",
    "company",
    "companyname",
    "city",
    "town",
    "locality",
    "village",
    "province",
    "region",
    "gender",
    "age",
    "nationality",
    "avatar",
    "photo",
    "picture",
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

/// One row of the hub's event catalogue (hub#823): a name the flow editor can offer in «Cuando
/// pase…», with who declares it and when it last happened. **Names only** — what the event
/// carries stays behind [`EventShape`], with its redaction.
#[derive(Debug, Clone, serde::Serialize)]
pub struct EventCatalogEntry {
    pub name: String,
    /// Installed modules that declare they emit it, sorted. Empty means it really happened and
    /// nobody declares it any more — a core event, or the module was uninstalled.
    pub declared_by: Vec<String>,
    /// When it last happened here. `None` for a declared event that never fired (or whose last
    /// occurrence aged out of the ninety-day retention window, hub#699).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_seen_at: Option<String>,
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
///
/// `event_name` is not decoration: it is the only thing that says whose data a FLAT payload is
/// (hub#826 — see the module header). Pass the name the caller asked for, not one reconstructed
/// from the rows.
pub fn infer(event_name: &str, payloads: &[Json]) -> Vec<EventField> {
    let about_a_person = event_is_about_a_person(event_name);
    let mut acc: BTreeMap<String, Acc> = BTreeMap::new();
    for payload in payloads {
        walk(payload, "", 0, about_a_person, &mut acc);
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

fn walk(
    value: &Json,
    prefix: &str,
    depth: usize,
    about_a_person: bool,
    acc: &mut BTreeMap<String, Acc>,
) {
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
        record(&path, child, about_a_person, acc);
        if matches!(child, Json::Object(_)) && depth + 1 < MAX_DEPTH {
            walk(child, &path, depth + 1, about_a_person, acc);
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

fn record(path: &str, value: &Json, about_a_person: bool, acc: &mut BTreeMap<String, Acc>) {
    let kind = kind_of(value);
    let withheld = withhold(path, value, about_a_person);
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

/// Whether this value's example stays inside the hub. The four signals of the module header.
///
/// `about_a_person` is signal 2: the event's own name said this payload is somebody's record, so
/// the keys that name a person count even without an ancestor in the path (hub#826).
fn withhold(path: &str, value: &Json, about_a_person: bool) -> bool {
    if path_is_personal(path) || key_is_free_text(path) {
        return true;
    }
    if about_a_person && path_names_a_person(path) {
        return true;
    }
    match value {
        Json::String(s) => value_looks_personal(s),
        _ => false,
    }
}

/// **Is this event about a person?** Read from the entity of `<entity>.<verb>` — the first segment
/// — against the same list of containers signal 1 uses, in singular and in plural: a module is
/// named `customers` and declares `customer.created`, and both spellings turn up in manifests.
///
/// `sale.completed` and `product.created` are not about a person, which is what keeps «Total de la
/// venta — 42,50 €» and «Corte de pelo» in the picker (see the module header for why this signal is
/// deliberately weaker than a container that is really in the path).
fn event_is_about_a_person(event_name: &str) -> bool {
    let entity = event_name.split('.').next().unwrap_or_default();
    terms(entity).any(|t| {
        let singular = t.strip_suffix('s').unwrap_or(t.as_str());
        PERSONAL_CONTAINERS.contains(&t.as_str()) || PERSONAL_CONTAINERS.contains(&singular)
    })
}

/// Any segment of the path naming something that is a person's ONLY once the record is known to be
/// about one ([`PERSONAL_WHEN_ABOUT_A_PERSON`]).
fn path_names_a_person(path: &str) -> bool {
    path.split('.')
        .any(|segment| terms(segment).any(|t| PERSONAL_WHEN_ABOUT_A_PERSON.contains(&t.as_str())))
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
    let pairs: Vec<String> = words
        .windows(2)
        .map(|w| format!("{}{}", w[0], w[1]))
        .collect();
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
    // A UUID is a MACHINE identifier and it is never anybody's datum, so it is settled BEFORE the
    // shape heuristics below — which both catch one by accident once the hyphens are gone (hub#1381):
    //
    //   · the IBAN branch reads `fb394e22-…` as two letters, two digits and alphanumerics — about
    //     one id in eighteen, since a UUID's letters are `a`-`f`;
    //   · and any UUID carrying eleven consecutive decimal digits reads as a card or a phone.
    //
    // The cost was not a flaky test. `sale_id`, `order_id` and `customer_id` are exactly what the
    // flows picker exists to map (ADR-0283), and their example vanished for a share of the ids
    // while the identical event next door showed it — which reads as «the field is sometimes
    // empty», not as «we withheld it». Found by the battery runner (`run-module-hub-batteries.sh`)
    // on its first complete pass.
    //
    // The carve-out cannot become a hole: no IBAN is 32 characters of pure hex — every IBAN opens
    // with a two-letter country code, and the codes whose letters are both `a`-`f` (AD, AE, BA,
    // BE, DE, EE) are 16 to 24 characters long — and no card or phone is written in hex.
    if looks_like_a_uuid(trimmed) {
        return false;
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

/// The canonical `8-4-4-4-12` hexadecimal form, and the same 32 characters without its hyphens.
/// Case-insensitive: a hub writes them lower case and an imported payload may not.
fn looks_like_a_uuid(s: &str) -> bool {
    const GROUPS: [usize; 5] = [8, 4, 4, 4, 12];
    let hex = |part: &str, len: usize| {
        part.len() == len && part.bytes().all(|b| b.is_ascii_hexdigit())
    };
    if s.len() == 32 {
        return hex(s, 32);
    }
    let mut parts = s.split('-');
    for len in GROUPS {
        match parts.next() {
            Some(part) if hex(part, len) => {}
            _ => return false,
        }
    }
    parts.next().is_none()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// The shape of an event that is not about a person, which is where the path rules are judged
    /// on their own. The name matters since hub#826 — see [`shape_of`].
    fn shape(payloads: &[Json]) -> BTreeMap<String, EventField> {
        shape_of("sale.completed", payloads)
    }

    fn shape_of(event_name: &str, payloads: &[Json]) -> BTreeMap<String, EventField> {
        infer(event_name, payloads)
            .into_iter()
            .map(|f| (f.path.clone(), f))
            .collect()
    }

    /// **The event name says whose flat payload this is** (hub#826).
    ///
    /// `customers.create` emits the whole card at the ROOT — `name`, `city`, `company_name` — with
    /// no `customer.` ancestor anywhere. So the container rule that this module's own header
    /// quotes as its example («everything under `customer` is withheld and `product.name` is not»)
    /// never fired for the canonical case, and `GET /api/hub/events/shape?name=customer.created`
    /// handed a real client's name and city to any marketplace module holding `manage_flows`.
    #[test]
    fn a_flat_payload_is_judged_by_the_entity_its_event_name_carries() {
        let fields = shape_of(
            "customer.created",
            &[json!({
                "name": "Berta Segunda",
                "city": "Madrid",
                "company_name": "Segunda SL",
                "email": "berta@example.test",
                "lifecycle_stage": "lead",
                "created_at": "2026-08-11T10:30:00Z",
                "visits": 12,
                "total_spent": "42.50"
            })],
        );

        for withheld in ["name", "city", "company_name", "email"] {
            assert!(fields[withheld].redacted, "{withheld} was handed over");
            assert_eq!(fields[withheld].sample, None, "{withheld}");
        }
        // And the picker still works. An amount, a date, a quantity and a state are not personal
        // data; withholding those too would leave the owner choosing between six options that all
        // read «(sin ejemplo)», which is the failure this whole module exists to avoid.
        for kept in ["lifecycle_stage", "created_at", "visits", "total_spent"] {
            assert!(!fields[kept].redacted, "{kept} lost its example");
            assert!(fields[kept].sample.is_some(), "{kept} lost its example");
        }
    }

    /// The other half, without which the rule is a blanket: the same bare keys under an event that
    /// is not about a person keep their examples. `product.created` carries a haircut, not a client.
    #[test]
    fn the_same_flat_keys_under_an_impersonal_event_keep_their_examples() {
        let fields = shape_of(
            "product.created",
            &[json!({ "name": "Corte de pelo", "city": "Madrid", "total": "42.50" })],
        );

        for kept in ["name", "city", "total"] {
            assert!(!fields[kept].redacted, "{kept} lost its example");
        }
        assert_eq!(fields["name"].sample, Some(json!("Corte de pelo")));
    }

    /// The entity is read the way event names are actually written: plural (`customers.imported`,
    /// which is how the module that emits them is named) and with a verb of more than one segment.
    /// An event whose name carries no entity at all decides nothing on its own.
    #[test]
    fn the_entity_is_recognised_in_plural_and_in_a_longer_name() {
        for name in ["customers.imported", "customer.contact.updated"] {
            let fields = shape_of(name, &[json!({ "name": "Berta Segunda" })]);
            assert!(
                fields["name"].redacted,
                "{name} handed over a person's name"
            );
        }
        // No entity, no promotion: the path and the value rules are all there is, exactly as before.
        let fields = shape_of("reminder.due", &[json!({ "name": "Corte de pelo" })]);
        assert!(!fields["name"].redacted);
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
            "tax_id": "B12345674",
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
        assert_eq!(
            sample.chars().count(),
            MAX_SAMPLE_CHARS + 1,
            "cut plus the ellipsis"
        );
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
        assert_eq!(
            fields["coupon"].seen_in, 1,
            "present in one of two = optional"
        );
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
        assert_eq!(
            infer(
                "sale.completed",
                &[json!("just a string"), json!(7), json!(null)]
            ),
            Vec::new()
        );
    }

    /// A pathological payload cannot make the reply unbounded.
    #[test]
    fn the_walk_is_bounded_in_width_and_in_depth() {
        let mut wide = serde_json::Map::new();
        for i in 0..(MAX_FIELDS * 2) {
            wide.insert(format!("f{i}"), json!(i));
        }
        assert!(infer("sale.completed", &[Json::Object(wide)]).len() <= MAX_FIELDS);

        let mut deep = json!({ "leaf": 1 });
        for _ in 0..(MAX_DEPTH * 3) {
            deep = json!({ "n": deep });
        }
        assert!(infer("sale.completed", &[deep])
            .iter()
            .all(|f| f.path.split('.').count() <= MAX_DEPTH));
    }
    /// A UUID is a MACHINE identifier and it must never be withheld as if it were somebody's bank
    /// account. Found by the module battery runner (hub#1381) on its first complete pass:
    /// `sales/tests/void.hub.test.py` asserts that the newest `sale.voided` names the sale it just
    /// voided, and it failed reading `None` for one `sale_id` and passed for the next — the
    /// difference was the random UUID, nothing else.
    ///
    /// Two of the heuristics catch one: strip the hyphens and a canonical UUID becomes 32
    /// alphanumeric characters, so `fb394e22-…` reads as an IBAN (two letters `fb`, two digits
    /// `39`, alphanumerics after) — roughly one id in eighteen — and any UUID that happens to
    /// carry eleven consecutive decimal digits reads as a card or a phone.
    ///
    /// The cost was not the flaky test. `sale_id`, `order_id` and `customer_id` are exactly the
    /// fields the flows picker exists to map (ADR-0283), and their example vanished at random for
    /// a share of the ids while an identical event next door showed it — the kind of inconsistency
    /// that reads as «the field is sometimes empty», not as «we withheld it».
    #[test]
    fn a_uuid_is_a_machine_id_and_keeps_its_example_hub1381() {
        // Every one of these is a real UUID that the IBAN branch used to withhold: two letters,
        // then two digits, then alphanumerics once the hyphens are gone.
        for id in [
            "fb394e22-03fe-4389-a3c4-471b78d12789",
            "de964b46-77d6-4fa6-bcc3-b0b7387a834b",
            "ab12cdef-1234-4567-89ab-cdef01234567",
        ] {
            let fields = shape(&[json!({ "sale_id": id })]);
            let field = &fields["sale_id"];
            assert!(
                !field.redacted,
                "{id} was withheld as if it were personal data"
            );
            assert_eq!(field.sample, Some(json!(id)), "{id} lost its example");
        }

        // Upper case and the un-hyphenated form of the same value are the same identifier.
        for id in [
            "FB394E22-03FE-4389-A3C4-471B78D12789",
            "fb394e2203fe4389a3c4471b78d12789",
        ] {
            assert!(
                !shape(&[json!({ "sale_id": id })])["sale_id"].redacted,
                "{id} was withheld"
            );
        }

        // And the carve-out is narrow: it must not become a hole for the values these rules were
        // written for. An IBAN, a card and an email keep going.
        for (path, value) in [
            ("account", "ES91 2100 0418 4502 0005 1332"),
            ("card", "4111 1111 1111 1111"),
            ("contact", "someone@example.com"),
        ] {
            assert!(
                shape(&[json!({ path: value })])[path].redacted,
                "{value} was handed over"
            );
        }
    }
}
