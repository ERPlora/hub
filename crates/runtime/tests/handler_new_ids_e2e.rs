//! hub#776 — a handler command answers with the ids it CONSUMED, not the whole pre-allocated
//! batch.
//!
//! The host hands every WASM/native handler `NEW_IDS_BATCH` (256) pre-generated UUIDs in
//! `context.new_ids` (the guest has no randomness; the host is the only id authority). The bug:
//! `persist_handler_output` echoed the FULL batch back to the caller, so opening one order or
//! creating one reservation answered with 256 UUIDs — multi-KB responses per POS tap, and 255 ids
//! that correspond to no row anywhere, indistinguishable from rows actually created.
//!
//! Contract under test:
//!  - the response's `new_ids` contains exactly the batch ids the handler's operations
//!    materialised, in batch order (so `new_ids[0]` keeps being the main entity for the callers
//!    that already rely on it);
//!  - a handler that consumes none answers with an empty list;
//!  - ids referenced twice are reported once;
//!  - ids nested inside structured params (order lines) are found too.
//!
//! The handler is NATIVE on purpose: it shares the exact `persist_handler_output` path with WASM
//! (see `outbox_delivery_e2e.rs` for the same trick) without compiling a `.wasm` in tests.
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{native::NativeHandler, RequestContext, Runtime};
use erplora_wasm_host::{Operation, Output};
use serde_json::{json, Value as Json};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_new_ids")
        .join("nid")
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Consumes as many batch ids as the payload's `use` asks for, through `nid._insert` operations.
/// `use = 0` returns no operation at all; `nested: true` hides the id inside a structured param
/// (the order-lines shape); `repeat: true` references the same id from two operations.
#[derive(Debug)]
struct ConsumingHandler;

#[async_trait]
impl NativeHandler for ConsumingHandler {
    async fn call(
        &self,
        _function: &str,
        input: &Json,
        _host: &dyn erplora_runtime::native::NativeHost,
    ) -> Result<Output, erplora_runtime::errors::RuntimeError> {
        let payload = &input["payload"];
        let ids = input["context"]["new_ids"]
            .as_array()
            .expect("the host always hands the batch")
            .clone();
        let n = payload["use"].as_u64().unwrap_or(0) as usize;
        let nested = payload["nested"].as_bool().unwrap_or(false);
        let repeat = payload["repeat"].as_bool().unwrap_or(false);

        let mut output = Output::new();
        for i in 0..n {
            let mut params = serde_json::Map::new();
            if nested {
                // The id travels inside a structured param, the way order lines carry theirs.
                params.insert("id".into(), ids[i].clone());
                params.insert(
                    "name".into(),
                    json!({ "lines": [{ "ref": ids[i].clone() }] }),
                );
            } else {
                params.insert("id".into(), ids[i].clone());
                params.insert("name".into(), json!(format!("item {i}")));
            }
            output = output.with_operation(Operation::sql("nid._insert", params));
        }
        if repeat && n > 0 {
            // A second operation referencing an ALREADY used id: the response must not list it twice.
            let mut params = serde_json::Map::new();
            params.insert("id".into(), json!(format!("copy-of-0")));
            params.insert("name".into(), ids[0].clone());
            output = output.with_operation(Operation::sql("nid._insert", params));
        }
        Ok(output)
    }
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.expect("install nid");
    rt.register_native("nid", Arc::new(ConsumingHandler));
    rt
}

async fn create(rt: &Runtime, payload: Json) -> Vec<String> {
    let params: Params = payload.as_object().cloned().unwrap_or_default();
    let res = rt
        .execute_command("nid.create", &params, &admin())
        .await
        .expect("nid.create runs");
    res["new_ids"]
        .as_array()
        .expect("the handler path always answers with new_ids")
        .iter()
        .map(|v| v.as_str().expect("ids are strings").to_string())
        .collect()
}

/// One entity created → exactly ONE id in the response, and it is the row's id.
#[tokio::test]
async fn one_consumed_id_answers_with_exactly_that_id() {
    let rt = runtime().await;
    let ids = create(&rt, json!({ "use": 1 })).await;
    assert_eq!(
        ids.len(),
        1,
        "one row created must answer with one id, not the whole batch (hub#776): got {}",
        ids.len()
    );

    // And it is the id the row was actually materialised with.
    let rows = rt
        .db_for_test()
        .query("SELECT id FROM nid_item ORDER BY id", &Params::new())
        .await
        .unwrap();
    assert_eq!(rows.rows.len(), 1);
    assert_eq!(rows.rows[0]["id"].as_str().unwrap(), ids[0]);
}

/// A handler that creates nothing answers with an empty list — no phantom ids.
#[tokio::test]
async fn zero_consumed_ids_answers_with_an_empty_list() {
    let rt = runtime().await;
    let ids = create(&rt, json!({ "use": 0 })).await;
    assert!(
        ids.is_empty(),
        "no row created → no id to report, got {} ids",
        ids.len()
    );
}

/// N entities → the N consumed ids, in batch order, so `new_ids[0]` keeps being the main entity
/// for every caller that already reads it (the compatibility clause of hub#776).
#[tokio::test]
async fn n_consumed_ids_answer_in_batch_order() {
    let rt = runtime().await;
    let ids = create(&rt, json!({ "use": 3 })).await;
    assert_eq!(ids.len(), 3, "three rows → three ids, got {}", ids.len());

    let rows = rt
        .db_for_test()
        .query("SELECT id, name FROM nid_item", &Params::new())
        .await
        .unwrap();
    let by_name = |name: &str| {
        rows.rows
            .iter()
            .find(|r| r["name"].as_str() == Some(name))
            .and_then(|r| r["id"].as_str())
            .map(str::to_string)
            .expect("row exists")
    };
    // Batch order = operation order here (the handler takes ids from the front): item 0 first.
    assert_eq!(ids[0], by_name("item 0"), "new_ids[0] is the main entity");
    assert_eq!(ids[1], by_name("item 1"));
    assert_eq!(ids[2], by_name("item 2"));
}

/// The same id referenced by two operations is reported once (it names ONE row).
#[tokio::test]
async fn a_repeated_id_is_reported_once() {
    let rt = runtime().await;
    let ids = create(&rt, json!({ "use": 1, "repeat": true })).await;
    assert_eq!(
        ids.len(),
        1,
        "one distinct id consumed → one id reported, got {ids:?}"
    );
}

/// Ids nested inside structured params (order lines) are found too: the whole point is that the
/// caller can correlate every row the handler materialised, wherever the id travelled.
#[tokio::test]
async fn a_nested_id_is_still_reported() {
    let rt = runtime().await;
    let ids = create(&rt, json!({ "use": 2, "nested": true })).await;
    assert_eq!(
        ids.len(),
        2,
        "both ids consumed (one nested) must be reported, got {ids:?}"
    );
}
