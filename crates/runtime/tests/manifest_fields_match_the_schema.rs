//! hub#521 — the runtime's idea of the manifest contract and `schemas/module.schema.json` must be
//! the SAME list.
//!
//! The hub now refuses (or warns about) a field it does not know, so "what the contract knows" has
//! become load-bearing. It is written twice: once in `manifest::known_fields` (what the installer
//! judges against) and once in the JSON Schema (what `erplora validate` judges against, at
//! authoring time). Two lists that must agree and nothing checking them is how the drift this
//! issue is about happened in the first place — the schema forbade `navigation[].actions` while
//! the runtime had parsed it since ADR-0048, and it forbade `compatibility` while the SaaS was
//! already reading `compatibility.min_erplora_version` out of published manifests.
//!
//! So this test is the seam: update one list without the other and it goes red, naming the field.
//!
//! The seam has a third side since hub#1237: a name this core RETIRES has to leave BOTH lists. A
//! retired field still declared by the schema keeps being advertised to every module author, by
//! `erplora validate` and by their editor — the same false promise the retirement ends.

use std::collections::BTreeSet;

/// The schema as it ships with the hub. It is not loaded at runtime (deliberately: a 1 100-line
//  JSON Schema is the toolkit's job, not the till's), only read here.
fn schema() -> serde_json::Value {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/module.schema.json")
        .canonicalize()
        .expect("schemas/module.schema.json ships with the hub");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

/// Property names the schema declares at `pointer` (a JSON Pointer to the object schema).
fn schema_properties(schema: &serde_json::Value, pointer: &str) -> BTreeSet<String> {
    schema
        .pointer(pointer)
        .unwrap_or_else(|| panic!("the schema has no object at {pointer}"))
        .get("properties")
        .and_then(|p| p.as_object())
        .unwrap_or_else(|| panic!("the schema declares no properties at {pointer}"))
        .keys()
        .cloned()
        .collect()
}

fn known(path: &str) -> BTreeSet<String> {
    erplora_runtime::manifest::known_fields(path)
        .unwrap_or_else(|| panic!("the runtime knows no field table for `{path}`"))
        .iter()
        .map(|s| (*s).to_string())
        .collect()
}

/// Left = the JSON Pointer into the schema, right = the dotted path the runtime judges by.
/// A `*` segment stands for "any key of this map" / "any item of this array".
const BLOCKS: &[(&str, &str)] = &[
    ("", ""),
    ("/properties/commands/additionalProperties", "commands.*"),
    ("/properties/queries/additionalProperties", "queries.*"),
    ("/properties/events", "events"),
    (
        "/properties/events/properties/listen/additionalProperties",
        "events.listen.*",
    ),
    ("/properties/capabilities", "capabilities"),
    ("/properties/migrations", "migrations"),
    ("/properties/seed", "seed"),
    ("/properties/roles/items", "roles[]"),
    ("/$defs/scheduledTask", "scheduled_tasks[]"),
    ("/properties/navigation/items", "navigation[]"),
    ("/properties/protects/items", "protects[]"),
    ("/$defs/widget", "widgets.*"),
    ("/properties/setup", "setup"),
    ("/properties/settings", "settings"),
    ("/properties/agent", "agent"),
    ("/properties/static_files", "static_files"),
    ("/properties/compatibility", "compatibility"),
    ("/properties/errors/additionalProperties", "errors.*"),
    ("/properties/records/additionalProperties", "records.*"),
];

#[test]
fn every_block_the_runtime_judges_has_the_same_fields_as_the_schema() {
    let schema = schema();
    for (pointer, path) in BLOCKS {
        let from_schema = schema_properties(&schema, pointer);
        let from_runtime = known(path);
        assert_eq!(
            from_schema,
            from_runtime,
            "`{}` disagrees with the schema at `{pointer}`.\n  only in the schema: {:?}\n  only in the runtime: {:?}",
            if path.is_empty() { "<root>" } else { path },
            from_schema.difference(&from_runtime).collect::<Vec<_>>(),
            from_runtime.difference(&from_schema).collect::<Vec<_>>(),
        );
    }
}

#[test]
fn a_retired_name_is_not_also_a_known_field() {
    // A name cannot be both "we understand this" and "this does nothing": the first would install
    // it in silence, which is the whole bug. Retirement is the loud exit, so the two lists are
    // disjoint by construction — and this is what keeps someone from "fixing" a warning by
    // quietly adding the field back to the known table.
    for (path, field, _why) in erplora_runtime::manifest::RETIRED_FIELDS {
        let table = known(path);
        assert!(
            !table.contains(*field),
            "`{field}` is retired at `{path}` but the runtime also lists it as known"
        );
    }
}

/// Regression test for ERPlora/hub#1237 — retiring a name has to take it out of the AUTHOR's door
/// too, not only the installer's.
///
/// `RETIRED_FIELDS` is what the installer says when it meets the name; `schemas/module.schema.json`
/// is what `erplora validate` and the author's editor OFFER while the manifest is being written.
/// Leaving the field in the schema is how a retirement turns into the worst of both: the toolkit
/// keeps advertising it, an author writes it, and the hub answers with a warning saying it does
/// nothing. Both doors have to have stopped naming it.
#[test]
fn a_retired_name_is_not_declared_by_the_schema_either_hub1237() {
    let schema = schema();
    for (path, field, _why) in erplora_runtime::manifest::RETIRED_FIELDS {
        let (pointer, _) = BLOCKS
            .iter()
            .find(|(_, p)| p == path)
            .unwrap_or_else(|| panic!("`{path}` is retired but has no pointer into the schema"));
        assert!(
            !schema_properties(&schema, pointer).contains(*field),
            "`{field}` is retired at `{path}` but the schema still declares it at `{pointer}`, so \
             `erplora validate` keeps offering it to module authors"
        );
    }
}
