//! hub#1093 — `migrations.<dialect>[]` must accept the two forms `MigrationEntry` parses.
//!
//! The runtime has deserialized the object form `{ file, kind, since }` since hub#542 — it is the
//! ONLY way to declare a `contract`, and hence the only legitimate way to retire a column — while
//! the authoring schema kept `items: { "type": "string" }`, so `erplora validate` rejected every
//! manifest that used it. A contract that only exists in the runtime cannot be used by anyone:
//! `services/008` had to be written additive, with the dead column left in the table, because
//! neither door would let it declare the `contract` that retires it.
//!
//! This test pins the schema to the runtime, the way `manifest_fields_match_the_schema.rs` pins
//! the field lists and `records_schema_contract.rs` pins the `records` block: both doors must say
//! the same thing about BOTH forms — and refuse the same garbage.

use erplora_runtime::manifest::{MigrationEntry, Migrations};
use erplora_runtime::migration_guard::Kind;

fn schema() -> jsonschema::Validator {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/module.schema.json")
        .canonicalize()
        .expect("schemas/module.schema.json ships with the hub");
    let raw: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    jsonschema::validator_for(&raw).expect("the manifest schema compiles")
}

fn manifest_with_migrations(dialect: &str, entries: serde_json::Value) -> serde_json::Value {
    let mut migrations = serde_json::Map::new();
    migrations.insert(dialect.to_string(), entries);
    serde_json::json!({
        "id": "demo", "name": "Demo", "version": "1.0.0",
        "migrations": migrations
    })
}

#[test]
fn the_bare_path_stays_valid_and_reads_as_expand() {
    let schema = schema();
    let entries = serde_json::json!(["migrations/postgres/001_init.sql"]);
    assert!(
        schema.is_valid(&manifest_with_migrations("postgres", entries.clone())),
        "the bare path is the form of every published manifest"
    );
    let parsed: Migrations = serde_json::from_value(serde_json::json!({ "postgres": entries })).unwrap();
    assert!(matches!(parsed.postgres[0], MigrationEntry::Path(_)));
    assert_eq!(parsed.postgres[0].kind(), Kind::Expand, "a bare path is read as expand");
}

#[test]
fn the_declared_form_is_valid_and_parses_to_what_it_declares() {
    let schema = schema();
    let declared = serde_json::json!({
        "file": "migrations/postgres/008_discount_basis_points.sql",
        "kind": "contract",
        "since": "1.5.24"
    });
    // The form that had nowhere to be written: valid in `postgres`…
    assert!(
        schema.is_valid(&manifest_with_migrations("postgres", serde_json::json!([declared.clone()]))),
        "the runtime parses `{{file, kind, since}}` — the schema may not reject what the runtime reads"
    );
    // …in `sqlite` too (deprecated, but `Migrations` still parses it as `MigrationEntry`)…
    assert!(
        schema.is_valid(&manifest_with_migrations("sqlite", serde_json::json!([declared.clone()]))),
        "the deprecated dialect parses the same entries"
    );
    // …and the two forms mix, which is the shape a module that grows a `contract` ends up with.
    assert!(
        schema.is_valid(&manifest_with_migrations(
            "postgres",
            serde_json::json!(["migrations/postgres/001_init.sql", declared])
        )),
        "both forms coexist in one array"
    );

    let parsed: Migrations = serde_json::from_value(serde_json::json!({
        "postgres": [{
            "file": "migrations/postgres/008_discount_basis_points.sql",
            "kind": "contract",
            "since": "1.5.24"
        }]
    }))
    .unwrap();
    match &parsed.postgres[0] {
        MigrationEntry::Declared { file, kind, since } => {
            assert_eq!(file, "migrations/postgres/008_discount_basis_points.sql");
            assert_eq!(*kind, Kind::Contract);
            assert_eq!(since.as_deref(), Some("1.5.24"));
        }
        other => panic!("the declared form must parse as Declared, got {other:?}"),
    }
}

#[test]
fn an_entry_without_file_is_refused_by_both_doors() {
    let schema = schema();
    let no_file = serde_json::json!([{ "kind": "contract", "since": "1.5.24" }]);
    assert!(
        !schema.is_valid(&manifest_with_migrations("postgres", no_file.clone())),
        "an entry with no file points at nothing"
    );
    assert!(
        serde_json::from_value::<Migrations>(serde_json::json!({ "postgres": no_file })).is_err(),
        "the runtime's untagged enum refuses it too"
    );
}

#[test]
fn an_unknown_kind_is_refused_by_both_doors() {
    let schema = schema();
    let unknown_kind = serde_json::json!([{ "file": "migrations/postgres/009_x.sql", "kind": "destroy" }]);
    assert!(
        !schema.is_valid(&manifest_with_migrations("postgres", unknown_kind.clone())),
        "`kind` is a closed vocabulary: expand · backfill · contract"
    );
    assert!(
        serde_json::from_value::<Migrations>(serde_json::json!({ "postgres": unknown_kind })).is_err(),
        "the runtime cannot deserialize a kind it does not know — a manifest carrying it never installs"
    );
}
