#![allow(non_snake_case)] // the names shout the part that matters, like the rest of the battery
//! hub#1701 — a module declares WHERE the owner may put a rule: `policies/*.checkpoint.json`.
//!
//! The contract is a **folder convention, NOT a manifest key**, for the same reason as `flows/`
//! (ADR-0463) and `locales/`: the root of the manifest is `additionalProperties: false`
//! (ADR-0286), so a new key would put a hub version floor on **every** module that declared it.
//! By folder, a module publishes with no floor and without a single warning, and its checkpoints
//! show up on their own on the first boot after this release, because `rehydrate_installed` goes
//! through the installer again on every boot.
//!
//! ```text
//! policies/
//!   <name>.checkpoint.json   { "command": …, "facts": [ … ], "outcomes": [ … ] }
//! ```
//!
//! Loading is **best-effort** —this comes out of a third party's zip and runs on every boot— but
//! **not mute** (hub#1649): what is discarded comes out with its code and its reason, because
//! «this module declares no checkpoint at all» and «it declares one and the hub threw it away»
//! look exactly the same from the counter.
//!
//! 🔴 **The valve of the fail-closed denial lives HERE.** The gate denies when, at run time, a
//! `fact` the checkpoint declares is missing (architecture/hub/policies.md §6.1). So that can
//! never stop a till by surprise, loading rejects a checkpoint whose `facts` the command **does
//! not declare in its schema**: it shows at install time, not in the middle of a sale.
use std::fs;
use std::path::{Path, PathBuf};

use erplora_runtime::manifest::Manifest;
use erplora_runtime::policies;

/// Its own temp folder, like the rest of the runtime tests (there is no `tempfile` in dev-deps).
fn tmp_module() -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-policy-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// A `sales` module with ONE command that declares its payload schema.
fn write_module(dir: &Path) -> Manifest {
    fs::create_dir_all(dir.join("schemas")).unwrap();
    fs::write(
        dir.join("schemas/set_discount.json"),
        serde_json::to_string(&serde_json::json!({
            "type": "object",
            "properties": {
                "discount_percent": { "type": "number" },
                "order": { "type": "object" }
            }
        }))
        .unwrap(),
    )
    .unwrap();
    let manifest = serde_json::json!({
        "id": "sales",
        "name": "Sales",
        "version": "1.0.0",
        "commands": {
            "sales.order.set_discount": {
                "permission": "sales.add_sale",
                "schema": "schemas/set_discount.json",
                "sql": ["UPDATE sales_order SET discount = :discount_percent"]
            }
        }
    });
    fs::write(
        dir.join("module.json"),
        serde_json::to_string(&manifest).unwrap(),
    )
    .unwrap();
    Manifest::load(dir).unwrap()
}

fn write_checkpoint(dir: &Path, name: &str, body: serde_json::Value) {
    let folder = dir.join("policies");
    fs::create_dir_all(&folder).unwrap();
    fs::write(
        folder.join(format!("{name}.checkpoint.json")),
        serde_json::to_string(&body).unwrap(),
    )
    .unwrap();
}

#[test]
fn a_module_without_the_folder_declares_nothing_and_discards_nothing_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(
        scan.checkpoints.is_empty() && scan.discards.is_empty(),
        "un módulo sin `policies/` es el caso de 27 de 27 hoy: ni checkpoints ni descartes, {scan:?}"
    );
}

#[test]
fn a_well_formed_checkpoint_is_registered_under_module_slash_name_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "discount_limit",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.discards.is_empty(), "nada que descartar: {scan:?}");
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
    let cp = &scan.checkpoints[0];
    // `<module>/<name>` — the same stable name as `_flow.template_ref` (v60): it is what the
    // module already knows about itself and does not change between its own releases.
    assert_eq!(cp.id, "sales/discount_limit");
    assert_eq!(cp.command, "sales.order.set_discount");
    assert_eq!(cp.facts, vec!["discount_percent".to_string()]);
}

#[test]
fn a_checkpoint_on_a_command_of_ANOTHER_module_is_refused_hub1701() {
    // A module only speaks in its own namespace — the same rule as the domain error ABI
    // (hub#139) and as elevation (hub#351). Stopping someone else's commands already has its own
    // door, and it is `protects` (hub#775), which the protected module knows about.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "foreign",
        serde_json::json!({
            "command": "inventory.stock.adjust",
            "facts": ["quantity"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_FOREIGN_COMMAND],
        "{scan:?}"
    );
}

#[test]
fn a_checkpoint_on_a_command_the_manifest_does_not_declare_is_refused_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "ghost",
        serde_json::json!({
            "command": "sales.order.set_tip",
            "facts": ["tip"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_COMMAND_NOT_DECLARED],
        "{scan:?}"
    );
}

#[test]
fn a_fact_the_commands_schema_does_not_declare_is_refused_at_LOAD_hub1701() {
    // 🔴 This is the valve that makes the gate's fail-closed denial safe: a `fact` the command
    // cannot supply shows at install time, not in the middle of a sale.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "margin",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent", "margin_pct"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    let discard = scan.discards.first().expect("un descarte, {scan:?}");
    assert_eq!(discard.code, policies::DISCARD_FACT_NOT_DECLARED);
    assert!(
        discard.detail.contains("margin_pct"),
        "el motivo tiene que NOMBRAR el hecho que falta, o no se puede arreglar: {discard:?}"
    );
}

#[test]
fn a_nested_fact_is_accepted_by_its_ROOT_property_hub1701() {
    // `order.total` is a dotted path of the flows' frozen language: its root (`order`) IS
    // declared by the schema, and `resolve_path` resolves the rest.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "order_total",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["order.total"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.discards.is_empty(), "{scan:?}");
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
}

#[test]
fn a_collection_fact_the_frozen_language_cannot_resolve_is_refused_hub1701() {
    // `lines[].margin_pct` is NOT resolved by `flows::def::resolve_path` (plain dotted paths
    // only), so accepting it would declare a fact the gate can NEVER read → it would always deny.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "lines",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["order[].margin_pct"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_INVALID_FACT_PATH],
        "{scan:?}"
    );
}

#[test]
fn a_command_without_a_payload_schema_cannot_carry_a_checkpoint_hub1701() {
    // With no schema there are no `facts` the command DECLARES, so there is nothing to validate
    // the valve above against — and the gate would deny on every single run.
    let dir = tmp_module();
    fs::write(
        dir.join("module.json"),
        serde_json::to_string(&serde_json::json!({
            "id": "sales", "name": "Sales", "version": "1.0.0",
            "commands": { "sales.void": { "permission": "sales.add_sale", "sql": ["DELETE FROM sales_order"] } }
        }))
        .unwrap(),
    )
    .unwrap();
    let manifest = Manifest::load(&dir).unwrap();
    write_checkpoint(
        &dir,
        "void",
        serde_json::json!({ "command": "sales.void", "facts": ["reason"], "outcomes": ["block"] }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_COMMAND_WITHOUT_SCHEMA],
        "{scan:?}"
    );
}

#[test]
fn an_unreadable_or_malformed_document_is_discarded_not_panicked_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    let folder = dir.join("policies");
    fs::create_dir_all(&folder).unwrap();
    fs::write(folder.join("broken.checkpoint.json"), "{ not json").unwrap();

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_INVALID_DOCUMENT],
        "{scan:?}"
    );
}

#[test]
fn an_outcome_outside_the_closed_vocabulary_is_refused_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "weird",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent"],
            "outcomes": ["allow"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_UNKNOWN_OUTCOME],
        "{scan:?}"
    );
}

#[test]
fn a_checkpoint_may_still_declare_elevate_even_though_this_core_only_runs_block_hub1701() {
    // `elevate:<permission>` IS contract vocabulary; what this core does not know yet is how to
    // RUN it (hub#1710). Throwing the whole checkpoint away for naming it would leave the module
    // without its `block`, which does work — the door that closes is WRITING a policy like that.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "discount_limit",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent"],
            "outcomes": ["block", "elevate:sales.discount.over_limit"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.discards.is_empty(), "{scan:?}");
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
}

#[test]
fn two_checkpoints_on_the_SAME_command_keep_only_the_first_by_name_hub1701() {
    // Two gates on the same command would make which rule applies depend on the order in which
    // the file system returns the entries. The first by name stays and the other one is reported;
    // deterministic across two boots.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    for name in ["b_second", "a_first"] {
        write_checkpoint(
            &dir,
            name,
            serde_json::json!({
                "command": "sales.order.set_discount",
                "facts": ["discount_percent"],
                "outcomes": ["block"]
            }),
        );
    }

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
    assert_eq!(scan.checkpoints[0].id, "sales/a_first", "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_DUPLICATE_COMMAND],
        "{scan:?}"
    );
}

#[test]
fn a_checkpoint_with_no_facts_has_nothing_to_reason_about_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "empty",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": [],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_NO_FACTS],
        "{scan:?}"
    );
}
