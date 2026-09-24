//! `commands.<name>.on_unique` — the race between a module's guard and its unique index answers
//! with the module's own code, not with `db` (ERPlora/hub#2081).
//!
//! A module checks "is this already taken?" with a read and backs the rule with a unique index,
//! because two requests can pass the read at the same time. The index stops the second write — but
//! the refusal used to surface as `RuntimeError::Db` (code `db`, "the request could not be
//! completed"), so the person who lost the race was told nothing, while the one who did not race
//! got a clear, translated reason. `on_unique` lets the module name, per index of its own, the code
//! of its catalogue that refusal means.
//!
//! The race itself is reproduced deterministically: the write the guard would have stopped is
//! simply issued twice, so the second one is refused by the index — exactly what the loser of the
//! race meets.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{Runtime, RuntimeError};
use kernel_fixture::{admin, broken_copy, Scratch};
use serde_json::json;

const INDEX: &str = "uq_kfx_item_live_name";
const CODE: &str = "kfx.name_taken";

/// The fixture plus a unique index over the live item names, the code in its catalogue and, when
/// `declare` is set, the `on_unique` clause on the two commands that write items — the declarative
/// `kfx.item.create` and the Tier 2 `kfx.items.bulk`.
fn fixture_with_unique_index(tag: &str, declare: bool) -> Scratch {
    let scratch = broken_copy(tag, |m| {
        m["migrations"]["postgres"]
            .as_array_mut()
            .expect("the fixture declares postgres migrations")
            .push(json!({
                "file": "migrations/postgres/004_unique_live_name.sql",
                "kind": "expand",
                "since": "1.1.0"
            }));
        m["errors"][CODE] = json!({});
        if declare {
            for command in ["kfx.item.create", "kfx.items.bulk"] {
                m["commands"][command]["on_unique"] = json!({ INDEX: CODE });
            }
        }
    });
    std::fs::write(
        scratch
            .path()
            .join("migrations/postgres/004_unique_live_name.sql"),
        format!(
            "CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON kfx_item (hub_id, name) \
             WHERE deleted_at IS NULL;\n"
        ),
    )
    .expect("write the index migration");
    scratch
}

async fn runtime_with(scratch: &Scratch) -> Runtime {
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(scratch.path())
        .await
        .unwrap_or_else(|e| panic!("install the fixture with its unique index: {e}"));
    rt
}

async fn create(rt: &Runtime, name: &str) -> Result<serde_json::Value, RuntimeError> {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    rt.execute_command("kfx.item.create", &p, &admin()).await
}

async fn live_items(rt: &Runtime) -> usize {
    rt.db_for_test()
        .query(
            "SELECT id FROM kfx_item WHERE deleted_at IS NULL",
            &Params::new(),
        )
        .await
        .expect("count the items")
        .rows
        .len()
}

/// 🔑 The declarative path: the second write of the same name is refused by the index and the
/// caller gets the declared code — the one the module translates — and nothing was written twice.
#[tokio::test]
async fn the_index_refusal_answers_with_the_declared_code_hub2081() {
    let scratch = fixture_with_unique_index("on-unique-sql", true);
    let rt = runtime_with(&scratch).await;

    create(&rt, "Ana").await.expect("the first write goes in");
    match create(&rt, "Ana")
        .await
        .expect_err("the index refuses the second one")
    {
        RuntimeError::Domain { code, .. } => assert_eq!(code, CODE),
        other => panic!("expected the declared code `{CODE}`, got {other:?}"),
    }
    assert_eq!(live_items(&rt).await, 1, "and the index still did its job");
}

/// The same door on the Tier 2 path: a handler whose operations collide with the index reaches
/// the database through `persist_handler_output`, and the refusal is named just the same. This is
/// the shape of the case that opened the issue (staff#55: a WASM handler + a partial unique index).
#[tokio::test]
async fn a_handler_write_refused_by_the_index_answers_with_the_declared_code_hub2081() {
    let scratch = fixture_with_unique_index("on-unique-wasm", true);
    let rt = runtime_with(&scratch).await;

    let mut p = Params::new();
    p.insert("names".into(), json!(["Ana", "Ana"]));
    match rt
        .execute_command("kfx.items.bulk", &p, &admin())
        .await
        .expect_err("the second insert of the batch collides with the first")
    {
        RuntimeError::Domain { code, .. } => assert_eq!(code, CODE),
        other => panic!("expected the declared code `{CODE}`, got {other:?}"),
    }
    assert_eq!(live_items(&rt).await, 0, "the whole batch rolled back");
}

/// 🔴 The control: WITHOUT the declaration the refusal is still the database's. The mapping is
/// opt-in and keyed on the module's word — the kernel never guesses a code for an index.
#[tokio::test]
async fn without_on_unique_the_refusal_stays_a_database_error_hub2081() {
    let scratch = fixture_with_unique_index("on-unique-undeclared", false);
    let rt = runtime_with(&scratch).await;

    create(&rt, "Ana").await.expect("the first write goes in");
    let err = create(&rt, "Ana")
        .await
        .expect_err("the index refuses the second one");
    assert!(matches!(err, RuntimeError::Db(_)), "got {err:?}");
}

/// A violation of an index OTHER than the one declared is not renamed: the code is bound to the
/// index its author named, never to "any unique violation of this command".
#[tokio::test]
async fn a_violation_of_another_index_is_not_renamed_hub2081() {
    let scratch = fixture_with_unique_index("on-unique-other-index", false);
    let manifest_path = scratch.path().join("module.json");
    let mut manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest_path).unwrap()).unwrap();
    manifest["commands"]["kfx.item.create"]["on_unique"] =
        json!({ "uq_kfx_item_some_other_rule": CODE });
    std::fs::write(&manifest_path, manifest.to_string()).unwrap();
    let rt = runtime_with(&scratch).await;

    create(&rt, "Ana").await.expect("the first write goes in");
    let err = create(&rt, "Ana")
        .await
        .expect_err("the index refuses the second one");
    assert!(matches!(err, RuntimeError::Db(_)), "got {err:?}");
}

/// The installer's door: the declared code must be one the module may raise — its own namespace,
/// and listed in its `errors` catalogue when it has one (ADR-0398). A code that is not declared is
/// exactly the silent surface the catalogue exists to make visible.
#[tokio::test]
async fn the_installer_refuses_a_code_outside_the_catalogue_hub2081() {
    let scratch = fixture_with_unique_index("on-unique-uncatalogued", true);
    let manifest_path = scratch.path().join("module.json");
    let mut manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest_path).unwrap()).unwrap();
    manifest["commands"]["kfx.item.create"]["on_unique"] = json!({ INDEX: "kfx.not_in_catalogue" });
    std::fs::write(&manifest_path, manifest.to_string()).unwrap();

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let err = rt
        .install_from_dir(scratch.path())
        .await
        .expect_err("the code is not in the catalogue");
    let text = err.to_string();
    assert!(
        text.contains("on_unique") && text.contains("kfx.not_in_catalogue"),
        "the refusal names the clause and the code: {text}"
    );
}

#[tokio::test]
async fn the_installer_refuses_another_modules_code_hub2081() {
    let scratch = fixture_with_unique_index("on-unique-foreign-code", true);
    let manifest_path = scratch.path().join("module.json");
    let mut manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest_path).unwrap()).unwrap();
    manifest["commands"]["kfx.item.create"]["on_unique"] = json!({ INDEX: "sales.name_taken" });
    // Without a catalogue (the lenient ADR-0205 mode), so it is the NAMESPACE rule that refuses —
    // with the catalogue in place, its own check would refuse first and hide a missing one.
    manifest
        .as_object_mut()
        .expect("the manifest is an object")
        .remove("errors");
    std::fs::write(&manifest_path, manifest.to_string()).unwrap();

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    let err = rt
        .install_from_dir(scratch.path())
        .await
        .expect_err("a module only raises codes of its own namespace");
    let text = err.to_string();
    assert!(
        text.contains("on_unique") && text.contains("sales.name_taken"),
        "the refusal names the clause and the code: {text}"
    );
}
