//! hub#1091 (criterio de aceptación 3, la mitad del schema) — `expect_rows.statement` must be a
//! key the AUTHORING contract accepts, not just one the runtime parses.
//!
//! The runtime has deserialized the anchor since PR #1114: `ExpectRows.statement`, validated at
//! install (`commands.rs::anchored_statement_index` refuses an anchor naming no statement of the
//! command) and honored by both doors (declarative ops and handler-resolved ops). But
//! `schemas/module.schema.json` kept `expect_rows` closed (`additionalProperties: false`) without
//! it, so the two halves of the contract disagreed about the same manifest:
//!
//! * `erplora validate` (toolkit, vendored copy of this schema) flagged `statement` as an unknown
//!   key — a warning today, noise that teaches authors to drop the anchor;
//! * `online_booking` published `bookings.create` with the anchor on main, so the published shape
//!   and the authoring contract were already out of step.
//!
//! A guard that only the runtime understands is a guard authors cannot write. This test pins the
//! schema to the runtime the way `migrations_schema_contract.rs` pins both `migrations[]` forms:
//! both doors must accept the anchored gate, keep accepting the published unanchored one, and
//! refuse the same garbage.

use erplora_runtime::manifest::{ExpectRows, ExpectRowsOp};

fn schema() -> jsonschema::Validator {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/module.schema.json")
        .canonicalize()
        .expect("schemas/module.schema.json ships with the hub");
    let raw: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    jsonschema::validator_for(&raw).expect("the manifest schema compiles")
}

fn manifest_with_expect_rows(gate: serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "id": "demo", "name": "Demo", "version": "1.0.0",
        "commands": {
            "demo.bookings.create": {
                "permission": "demo.book",
                "sql": ["commands/booking_create.sql", "commands/counter_upsert.sql"],
                "emit": ["demo.booking.created"],
                "expect_rows": gate
            }
        }
    })
}

/// The shape `online_booking` already publishes on main: the anchor sits beside `op`/`n`/`error`
/// and names the guarded statement by its `sql` path.
fn anchored_gate() -> serde_json::Value {
    serde_json::json!({
        "op": "min",
        "n": 1,
        "statement": "commands/booking_create.sql",
        "error": "demo.outside_booking_window",
        "message": "That date and time are outside the booking window this business allows."
    })
}

#[test]
fn the_anchor_is_valid_and_parses_to_the_anchor() {
    let schema = schema();
    assert!(
        schema.is_valid(&manifest_with_expect_rows(anchored_gate())),
        "the runtime parses `expect_rows.statement` (PR #1114) and online_booking publishes it: \
         the schema may not reject what the runtime reads"
    );

    let parsed: ExpectRows = serde_json::from_value(anchored_gate()).unwrap();
    assert!(matches!(parsed.op, ExpectRowsOp::Min));
    assert_eq!(parsed.n, 1);
    assert_eq!(
        parsed.statement.as_deref(),
        Some("commands/booking_create.sql"),
        "the anchor deserializes as the `sql` path it is declared to be"
    );
}

#[test]
fn the_gate_without_an_anchor_stays_valid() {
    let schema = schema();
    let published = serde_json::json!({
        "op": "min",
        "n": 1,
        "error": "demo.cannot_confirm",
        "message": "This booking can no longer be confirmed: it is not pending any more."
    });
    assert!(
        schema.is_valid(&manifest_with_expect_rows(published.clone())),
        "every published gate is unanchored: the batch-sum contract stays first-class"
    );
    let parsed: ExpectRows = serde_json::from_value(published).unwrap();
    assert_eq!(parsed.statement, None, "no anchor = the batch sum, as documented");
}

#[test]
fn an_empty_anchor_is_refused_by_the_schema_before_the_runtime_sees_it() {
    let schema = schema();
    let mut gate = anchored_gate();
    gate["statement"] = serde_json::json!("");
    assert!(
        !schema.is_valid(&manifest_with_expect_rows(gate.clone())),
        "an empty path names no statement: it is the neutralized-gate shape hub#1091 closes"
    );
    // The runtime's door refuses the same thing LATER, at install, where the command and path
    // can be named (`anchored_statement_index`: an anchor matching no `sql` entry of the command
    // never installs — pinned by `expect_rows_statement_e2e`). The two doors do not need to
    // refuse at the same moment, only in the same direction — and they do not need a third
    // vocabulary here: an anchor is a `sql` path, written exactly as `sql` writes it.
    let parsed: ExpectRows = serde_json::from_value(gate).unwrap();
    assert_eq!(parsed.statement.as_deref(), Some(""), "serde is tolerant by design (hub#521); the refusal is positional");
}
