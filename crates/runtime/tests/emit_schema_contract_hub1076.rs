//! hub#1076 (review) — the two wire shapes of `commands.*.emit[]` are pinned in the AUTHORING
//! contract (`schemas/module.schema.json`), not only in the runtime.
//!
//! `kernel_contract_engine.rs` proves the runtime deserialises both forms; this test proves the
//! schema — the copy `erplora validate` vendors byte for byte — accepts exactly the same two and
//! refuses the same garbage, the way `expect_rows_schema_contract.rs` pins `expect_rows.statement`.
//! A guard only the runtime understands is a guard authors cannot write.
//!
//! It also sweeps the published catalogue: no published `emit` list may be refused by the schema
//! that grew the new form, which is the acceptance criterion "no behaviour change for a module
//! that has not adopted it" measured on the 27 real manifests rather than asserted.

fn schema() -> jsonschema::Validator {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/module.schema.json")
        .canonicalize()
        .expect("schemas/module.schema.json ships with the hub");
    let raw: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    jsonschema::validator_for(&raw).expect("the manifest schema compiles")
}

fn manifest_with_emit(emit: serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "id": "demo", "name": "Demo", "version": "1.0.0",
        "commands": {
            "demo.messages.ingest": {
                "permission": "demo.ingest",
                "sql": ["commands/messages_ingest.sql"],
                "emit": emit
            }
        }
    })
}

#[test]
fn the_plain_name_and_the_keyed_object_are_both_valid_hub1076() {
    let schema = schema();
    assert!(
        schema.is_valid(&manifest_with_emit(serde_json::json!([
            "demo.message.received"
        ]))),
        "the plain string form every published module writes must keep validating"
    );
    assert!(
        schema.is_valid(&manifest_with_emit(serde_json::json!([
            { "event": "demo.message.received", "dedup_key": "wa_message_id" }
        ]))),
        "the keyed object form the runtime reads (hub#1076) must validate"
    );
    assert!(
        schema.is_valid(&manifest_with_emit(serde_json::json!([
            "demo.message.legacy",
            { "event": "demo.message.received", "dedup_key": "wa_message_id" }
        ]))),
        "both forms may coexist in one list"
    );
}

#[test]
fn the_schema_refuses_what_the_runtime_would_not_read_hub1076() {
    let schema = schema();
    let garbage = [
        (
            serde_json::json!([{ "event": "demo.message.received" }]),
            "an object without `dedup_key` is a misspelt string, not a plain emission",
        ),
        (
            serde_json::json!([{ "dedup_key": "wa_message_id" }]),
            "an object without `event` names no event",
        ),
        (
            serde_json::json!([{ "event": "demo.message.received", "dedup_key": "wa_message_id", "extra": 1 }]),
            "the object is closed",
        ),
        (
            serde_json::json!([{ "event": "demo.message.received", "dedup_key": 7 }]),
            "`dedup_key` is a field NAME, a string",
        ),
        (serde_json::json!([42]), "a number is neither form"),
    ];
    for (emit, why) in garbage {
        assert!(
            !schema.is_valid(&manifest_with_emit(emit.clone())),
            "{why}: {emit}"
        );
    }
}

/// The keyed form refuses nothing the catalogue publishes: no published manifest gets a schema
/// error under any `emit` list. Scoped to `emit` on purpose — the sweep guards THIS contract, and a
/// manifest's unrelated debt elsewhere (a root key the schema does not know, an over-long text) is
/// its own issue, not a reason to block the field. Skips (loudly) where `modules-workspace` is not
/// checked out, like every other catalogue sweep.
#[test]
fn no_published_emit_list_is_refused_by_the_schema_hub1076() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let schema = schema();
    let root = erplora_runtime::modules_root();
    let mut seen = 0;
    let mut failures = Vec::new();
    // `published_module_dirs` and not `read_dir`: the fleet keeps its worktrees inside
    // `modules-workspace/modules` and each one carries a copy of its module's manifest (hub#1448).
    for (_module, dir) in erplora_runtime::published_module_dirs() {
        let manifest = dir.join("module.json");
        seen += 1;
        let raw: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&manifest).unwrap()).unwrap();
        let errors: Vec<String> = schema
            .iter_errors(&raw)
            .filter(|e| e.instance_path.as_str().contains("/emit"))
            .map(|e| format!("{} — {e}", e.instance_path))
            .collect();
        if !errors.is_empty() {
            failures.push(format!("{}: {}", dir.display(), errors.join(" | ")));
        }
    }
    assert!(
        seen >= 25,
        "the catalogue sweep saw only {seen} manifests under {}",
        root.display()
    );
    assert!(
        failures.is_empty(),
        "published `emit` lists the schema now refuses:\n  {}",
        failures.join("\n  ")
    );
}
