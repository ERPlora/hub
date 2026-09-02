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
    assert_eq!(
        parsed.statement, None,
        "no anchor = the batch sum, as documented"
    );
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
    assert_eq!(
        parsed.statement.as_deref(),
        Some(""),
        "serde is tolerant by design (hub#521); the refusal is positional"
    );
}

// ── PARIDAD del gate legado `min_affected_rows` (hub#1091, revisión) ─────────────────────────
//
// El schema no puede ser MÁS estricto que el runtime: un manifest que `erplora validate` rechaza y
// el hub instala (o al revés) es la deriva que este fichero existe para cazar. Y aquí hubo una: el
// `if` se escribió como
//
//     "if": { "required": ["min_affected_rows"], "properties": { "sql": { "minItems": 2 } } }
//
// y `properties` en JSON Schema **solo restringe las claves PRESENTES**. Un command de HANDLER no
// declara `sql`, así que la rama `sql` pasaba en vacío, el `if` casaba igual y el `then` prohibía
// `min_affected_rows` — mientras el installer (`command.sql.len() > 1` → `0 > 1`, falso) y el
// `checkRowGates` del toolkit lo aceptaban tan campantes.
//
// El arreglo es declarar que el antecedente necesita LAS DOS claves: `"required": ["min_affected_rows", "sql"]`.

fn manifest_with_command(command: serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "id": "demo", "name": "Demo", "version": "1.0.0",
        "commands": { "demo.op": command }
    })
}

/// El caso que la revisión encontró: sin `sql` no hay lote que neutralizar, así que la guarda no
/// aplica — y el schema tiene que decir lo mismo que el installer.
#[test]
fn a_handler_command_with_no_sql_may_declare_min_affected_rows() {
    let schema = schema();
    let handler_command = serde_json::json!({
        "permission": "demo.write",
        "handler": { "type": "wasm", "file": "dist/handler.wasm", "function": "run" },
        "min_affected_rows": 1
    });
    assert!(
        schema.is_valid(&manifest_with_command(handler_command)),
        "un command de handler no tiene `sql`: no hay lote, la guarda no puede quedar neutralizada, \
         y el installer (`command.sql.len() > 1`) lo acepta — el schema no puede ser más estricto"
    );
}

/// La otra mitad de la paridad, para que el arreglo no se pase de frenada: lo que el installer SÍ
/// rechaza, el schema lo sigue rechazando.
#[test]
fn the_multi_statement_legacy_gate_is_still_refused_by_both_doors() {
    let schema = schema();
    let batched = serde_json::json!({
        "permission": "demo.write",
        "sql": ["commands/_bump.sql", "commands/create.sql"],
        "min_affected_rows": 1
    });
    assert!(
        !schema.is_valid(&manifest_with_command(batched)),
        "dos sentencias y un entero que no puede anclarse: es la forma neutralizable de hub#1091"
    );
}

/// Y el caso legítimo del catálogo publicado (`flows.drafts.resolve`) sigue validando: una
/// sentencia ES el lote.
#[test]
fn the_single_statement_legacy_gate_stays_valid() {
    let schema = schema();
    let single = serde_json::json!({
        "permission": "demo.write",
        "sql": ["commands/resolve.sql"],
        "min_affected_rows": 1
    });
    assert!(
        schema.is_valid(&manifest_with_command(single)),
        "`flows.drafts.resolve` es exactamente esta forma y es la única del catálogo"
    );
}
