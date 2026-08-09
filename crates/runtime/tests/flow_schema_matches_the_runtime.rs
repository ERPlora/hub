//! hub#661 (ADR-0283 K7) — `schemas/flow.schema.json` and the runtime must be the SAME contract.
//!
//! The flow document is **frozen**: the core gains this last family of primitives and stops, so
//! whatever is written down now is what the module `flows`, its editor and every template will
//! speak against for as long as the product exists. That contract is written twice on purpose —
//! once in Rust (`flows::def`, what the hub judges against at save time) and once in JSON Schema
//! (what the editor and the toolkit judge against at authoring time) — because loading a JSON
//! Schema at runtime to validate a row is work a till should not do.
//!
//! Two lists that must agree, with nothing checking them, is exactly how hub#521 happened: the
//! module schema forbade `navigation[].actions` while the runtime had parsed it since ADR-0048.
//! This file is the seam. Change one side without the other and it goes red, naming the value.
use std::collections::BTreeSet;

use erplora_runtime::flows::def::{Op, StepKind, TriggerKind, SCHEMA_VERSION};

fn schema() -> serde_json::Value {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/flow.schema.json")
        .canonicalize()
        .expect("schemas/flow.schema.json ships with the hub");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

/// The values of an `enum` at a JSON Pointer.
fn enum_at(schema: &serde_json::Value, pointer: &str) -> BTreeSet<String> {
    schema
        .pointer(pointer)
        .unwrap_or_else(|| panic!("the schema has nothing at {pointer}"))
        .get("enum")
        .and_then(|e| e.as_array())
        .unwrap_or_else(|| panic!("the schema declares no enum at {pointer}"))
        .iter()
        .filter_map(|v| v.as_str().map(|s| s.to_string()))
        .collect()
}

fn keys_at(schema: &serde_json::Value, pointer: &str) -> BTreeSet<String> {
    schema
        .pointer(pointer)
        .unwrap_or_else(|| panic!("the schema has nothing at {pointer}"))
        .as_object()
        .unwrap_or_else(|| panic!("{pointer} is not an object"))
        .keys()
        .cloned()
        .collect()
}

#[test]
fn the_step_kinds_are_the_same_six_on_both_sides() {
    let declared = enum_at(&schema(), "/$defs/step/properties/kind");
    let known: BTreeSet<String> = StepKind::ALL
        .iter()
        .map(|k| k.as_str().to_string())
        .collect();
    assert_eq!(
        declared, known,
        "the vocabulary is frozen: a kind in one list and not the other is a document the editor \
         accepts and the hub refuses, or worse, the other way round"
    );
}

/// The `http` step's keys (hub#662). The runtime refuses a key it does not know — that is hub#521's
/// lesson written into this contract — so a key the editor offers and the runtime rejects is a
/// document that saves in one place and is refused in the other.
#[test]
fn the_keys_of_an_http_step_are_declared_on_both_sides() {
    let declared = keys_at(&schema(), "/$defs/step/properties");
    for key in ["method", "url", "headers", "body", "timeout"] {
        assert!(
            declared.contains(key),
            "`{key}` is accepted by `flows::def` for an http step and missing from the schema"
        );
    }
    // And the runtime really does accept exactly these.
    let accepted = erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
        "schema_version": 1,
        "steps": [{
            "id": "call", "kind": "http", "method": "POST",
            "url": "https://api.example.com/v1/x",
            "headers": { "Authorization": "Bearer {{secret.K}}" },
            "body": { "a": 1 },
            "timeout": 20
        }]
    }));
    assert!(accepted.is_ok(), "{accepted:?}");
}

#[test]
fn the_trigger_kinds_are_the_same_four_on_both_sides() {
    let declared = enum_at(&schema(), "/$defs/trigger/properties/kind");
    let known: BTreeSet<String> = TriggerKind::ALL
        .iter()
        .map(|k| k.as_str().to_string())
        .collect();
    assert_eq!(declared, known);
}

#[test]
fn the_condition_operators_are_the_same_nine_on_both_sides() {
    let declared = keys_at(
        &schema(),
        "/$defs/condition/additionalProperties/properties",
    );
    let known: BTreeSet<String> = Op::ALL.iter().map(|o| o.as_str().to_string()).collect();
    assert_eq!(
        declared, known,
        "an operator the schema allows and the runtime does not know is a filter that saves in the \
         editor and is refused by the hub"
    );
    // And the schema must forbid everything else, or the editor would happily accept `greater_than`
    // and the refusal would only arrive from the hub.
    assert_eq!(
        schema()
            .pointer("/$defs/condition/additionalProperties/additionalProperties")
            .and_then(|v| v.as_bool()),
        Some(false),
        "the operator set is closed on the schema side too"
    );
}

#[test]
fn the_document_declares_the_version_this_hub_speaks_and_requires_it() {
    let schema = schema();
    assert_eq!(
        schema.pointer("/properties/schema_version/const").unwrap(),
        &serde_json::json!(SCHEMA_VERSION),
        "the schema pins the version the runtime implements"
    );
    let required: BTreeSet<String> = schema["required"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|v| v.as_str().map(|s| s.to_string()))
        .collect();
    assert!(
        required.contains("schema_version"),
        "`schema_version` is required from day one: an unversioned document is one nobody can \
         refuse later"
    );
    assert!(
        required.contains("steps"),
        "a flow with no steps does nothing, and the runtime refuses it"
    );
    assert_eq!(
        schema["additionalProperties"].as_bool(),
        Some(false),
        "unknown top-level keys are refused, not dropped (hub#521)"
    );
}
