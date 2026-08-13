//! hub#632 — the `records` block (declared mutability) and PATCH semantics in the dispatcher.
//!
//! 46 update commands across 20 modules require the WHOLE object (13 with >3 required fields;
//! `customers.update` asks for 18). A caller that fills one from memory corrupts a record that
//! carries a tax id. The decision (Ioan, 2026-08-09):
//!
//! 1. Each module DECLARES per record what can be edited (`records`): `mutable: false` (with a
//!    closed `reason` vocabulary and `correct_with` pointers) or `mutable: true` with its
//!    `update` command and an optional `patch: { read, key }`.
//! 2. When a command with `patch` receives a PARTIAL payload, the runtime runs the declared
//!    `read`, merges the sent keys ON TOP — limited to the keys of the update's schema, because
//!    the `get` returns columns the update does not accept and `additionalProperties: false`
//!    would refuse them — validates the COMPLETE object against the usual schema, and runs the
//!    SQL untouched. An explicit `null` overwrites (clears); an omitted key preserves.
//!
//! The block's conditional validation (mutable:false forbids update/patch) lives ONLY in
//! `schemas/module.schema.json` — see `records_schema_contract.rs`.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_records")
        .join("rec")
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.expect("install rec");
    rt
}

/// Creates an order and returns its id.
async fn create_order(rt: &Runtime) -> String {
    let mut p = Params::new();
    p.insert("customer".into(), json!("Ana García"));
    p.insert("notes".into(), json!("no onions"));
    p.insert("status".into(), json!("open"));
    let res = rt
        .execute_command("rec.order.create", &p, &admin())
        .await
        .expect("create order");
    res["new_ids"][0].as_str().expect("created id").to_string()
}

async fn order_row(rt: &Runtime, id: &str) -> Json {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    rt.db_for_test()
        .query(
            "SELECT customer, notes, status FROM rec_order WHERE id = :id",
            &p,
        )
        .await
        .unwrap()
        .rows
        .into_iter()
        .next()
        .expect("row exists")
}

/// The core of hub#632: a PARTIAL call to a command with `patch` succeeds — the runtime reads the
/// current record, merges the sent keys on top, and the untouched fields survive. Also proves the
/// merge is limited to the update schema's keys: the `get` returns an `id` column the update's
/// schema does not accept (`additionalProperties: false`), so leaking it would fail validation.
#[tokio::test]
async fn a_partial_update_preserves_the_untouched_fields() {
    let rt = runtime().await;
    let id = create_order(&rt).await;

    let mut p = Params::new();
    p.insert("order_id".into(), json!(id));
    p.insert("notes".into(), json!("extra napkins"));
    rt.execute_command("rec.order.update", &p, &admin())
        .await
        .expect("a partial payload must pass through the patch read-merge (hub#632)");

    let row = order_row(&rt, &id).await;
    assert_eq!(row["notes"], json!("extra napkins"), "the sent key wins");
    assert_eq!(row["customer"], json!("Ana García"), "an omitted key preserves");
    assert_eq!(row["status"], json!("open"), "an omitted key preserves");
}

/// An explicit `null` OVERWRITES (clears) — omitting and nulling are different things again.
#[tokio::test]
async fn an_explicit_null_clears_while_omitting_preserves() {
    let rt = runtime().await;
    let id = create_order(&rt).await;

    let mut p = Params::new();
    p.insert("order_id".into(), json!(id));
    p.insert("notes".into(), Json::Null);
    rt.execute_command("rec.order.update", &p, &admin())
        .await
        .expect("an explicit null is a valid partial payload");

    let row = order_row(&rt, &id).await;
    assert_eq!(row["notes"], Json::Null, "explicit null clears the field");
    assert_eq!(row["customer"], json!("Ana García"), "everything omitted preserves");
}

/// A FULL payload keeps working exactly as before: the merge under a complete object is the
/// identity, and the SQL runs untouched.
#[tokio::test]
async fn a_full_update_still_works_unchanged() {
    let rt = runtime().await;
    let id = create_order(&rt).await;

    let mut p = Params::new();
    p.insert("order_id".into(), json!(id));
    p.insert("customer".into(), json!("Pedro"));
    p.insert("notes".into(), json!("window table"));
    p.insert("status".into(), json!("closed"));
    rt.execute_command("rec.order.update", &p, &admin())
        .await
        .expect("full payload");

    let row = order_row(&rt, &id).await;
    assert_eq!(row["customer"], json!("Pedro"));
    assert_eq!(row["notes"], json!("window table"));
    assert_eq!(row["status"], json!("closed"));
}

/// A partial call against a record that DOES NOT EXIST cannot invent the missing fields: the read
/// returns nothing, the merge has nothing to fill with, and the schema refuses the incomplete
/// payload — nothing is written.
#[tokio::test]
async fn a_partial_update_of_a_missing_record_is_refused_not_invented() {
    let rt = runtime().await;
    let mut p = Params::new();
    p.insert("order_id".into(), json!("no-such-order"));
    p.insert("notes".into(), json!("ghost"));
    let err = rt
        .execute_command("rec.order.update", &p, &admin())
        .await
        .expect_err("no record to read → the partial payload stays incomplete → invalid");
    assert!(
        err.to_string().contains("rec.order.update"),
        "the refusal names the command: {err}"
    );
}

/// The `records` block is parsed off the manifest: declared immutability is available to whoever
/// asks (the assistant explains "an issued invoice is not edited: it is corrected with X").
#[test]
fn the_records_block_parses() {
    let manifest =
        erplora_runtime::manifest::Manifest::load(&fixture()).expect("fixture manifest loads");
    let receipt = manifest.records.get("receipt").expect("receipt is declared");
    assert!(!receipt.mutable);
    assert_eq!(receipt.reason.as_deref(), Some("fiscal"));
    assert_eq!(receipt.correct_with, vec!["rec.receipt.void".to_string()]);
    let order = manifest.records.get("order").expect("order is declared");
    assert!(order.mutable);
    assert_eq!(order.update.as_deref(), Some("rec.order.update"));
    let patch = order.patch.as_ref().expect("order declares patch");
    assert_eq!(patch.read, "rec.order.get");
    assert_eq!(patch.key, "order_id");
}
