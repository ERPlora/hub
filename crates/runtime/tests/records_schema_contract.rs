//! hub#632 — the `records` block's conditional validation lives ONLY in the authoring schema
//! (`schemas/module.schema.json`), by decision: no Rust duplicate, no over-engineering — the
//! human pre-publication review covers the rest. This test pins that contract on the schema file
//! itself, the way `manifest_fields_match_the_schema.rs` pins the field lists.
//!
//! What the schema must enforce:
//!  - `mutable: false` FORBIDS declaring `update`/`patch` (an immutable record has no update
//!    door, and that is the point of declaring it);
//!  - `reason` is a CLOSED vocabulary (`fiscal` · `ledger` · `identity` · `audit`) so it is
//!    translatable and explainable by the assistant;
//!  - `patch` requires both `read` and `key`.

fn schema() -> jsonschema::Validator {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/module.schema.json")
        .canonicalize()
        .expect("schemas/module.schema.json ships with the hub");
    let raw: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    jsonschema::validator_for(&raw).expect("the manifest schema compiles")
}

fn manifest_with_records(records: serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "id": "rec", "name": "Records", "version": "1.0.0", "records": records
    })
}

#[test]
fn an_immutable_record_cannot_declare_an_update_door() {
    let schema = schema();
    for offending in [
        serde_json::json!({ "sale": { "mutable": false, "reason": "fiscal", "update": "sales.update" } }),
        serde_json::json!({ "sale": { "mutable": false, "reason": "fiscal",
            "patch": { "read": "sales.get", "key": "sale_id" } } }),
    ] {
        assert!(
            !schema.is_valid(&manifest_with_records(offending.clone())),
            "`mutable: false` with an update/patch door must be invalid: {offending}"
        );
    }
}

#[test]
fn a_valid_records_block_passes() {
    let schema = schema();
    let valid = manifest_with_records(serde_json::json!({
        "sale":  { "mutable": false, "reason": "fiscal", "correct_with": ["sales.void"] },
        "order": { "mutable": true, "update": "sales.order.update_line",
                   "patch": { "read": "sales.order.get", "key": "order_id" } }
    }));
    if let Err(e) = schema.validate(&valid) {
        panic!("the canonical shape of hub#632 must validate: {e}");
    }
}

#[test]
fn the_reason_vocabulary_is_closed() {
    let schema = schema();
    for reason in ["fiscal", "ledger", "identity", "audit"] {
        let ok = manifest_with_records(serde_json::json!({
            "sale": { "mutable": false, "reason": reason }
        }));
        assert!(
            schema.is_valid(&ok),
            "`{reason}` belongs to the closed vocabulary"
        );
    }
    let bad = manifest_with_records(serde_json::json!({
        "sale": { "mutable": false, "reason": "marketing" }
    }));
    assert!(
        !schema.is_valid(&bad),
        "a reason outside fiscal/ledger/identity/audit must be refused: the vocabulary is closed \
         so it stays translatable and explainable"
    );
}

#[test]
fn a_patch_declares_both_read_and_key() {
    let schema = schema();
    for incomplete in [
        serde_json::json!({ "order": { "mutable": true, "update": "m.u", "patch": { "read": "m.g" } } }),
        serde_json::json!({ "order": { "mutable": true, "update": "m.u", "patch": { "key": "id" } } }),
    ] {
        assert!(
            !schema.is_valid(&manifest_with_records(incomplete.clone())),
            "a half-declared patch must be invalid: {incomplete}"
        );
    }
}

#[test]
fn mutable_is_required() {
    let schema = schema();
    let missing = manifest_with_records(serde_json::json!({ "sale": { "reason": "fiscal" } }));
    assert!(
        !schema.is_valid(&missing),
        "declaring a record without saying whether it is mutable declares nothing"
    );
}
