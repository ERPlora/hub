//! hub#1786 — a command announces each event ONCE, even when it declares it AND its handler emits it.
//!
//! Measured on `banco-pre` on 2026-09-13: every refund left a `sale.refunded` in the dead-letter.
//! `sales.refund` declares `emit: ["sale.refunded"]` and its handler emits `sale.refunded` too, and
//! the handler path of the dispatcher enqueued BOTH — the handler's (with `refund_ref`, delivered)
//! and the declared one, whose payload is only the command's params. `cash_register` rightly refused
//! that copy (no stable document reference) and it died after seven attempts; the other listeners
//! reacted to an event that should not exist. ~20 commands across 9 published modules have the same
//! shape, so the fix lives in the dispatcher, not in each manifest.
//!
//! Contract under test:
//!  - an event the handler emits is enqueued with the HANDLER's payload and never a second time
//!    from `emit`;
//!  - a declared event the handler does NOT emit is still enqueued, once, as before;
//!  - a handler that emits the same event several times (one per row) keeps every one of them.
//!
//! The handler is NATIVE on purpose: it shares the exact persist path with WASM without compiling
//! a `.wasm` in tests (same trick as `handler_new_ids_e2e.rs`).
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{native::NativeHandler, RequestContext, Runtime};
use erplora_wasm_host::{Event, Output};
use serde_json::{json, Value as Json};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_emit_once")
        .join("eo")
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Emits `eo.refunded` as many times as the payload's `refunds` says, each with its own
/// `refund_ref` — the shape `sales.refund` has. It never emits `eo.audited`.
#[derive(Debug)]
struct RefundHandler;

#[async_trait]
impl NativeHandler for RefundHandler {
    async fn call(
        &self,
        _function: &str,
        input: &Json,
        _host: &dyn erplora_runtime::native::NativeHost,
    ) -> Result<Output, erplora_runtime::errors::RuntimeError> {
        let refunds = input["payload"]["refunds"].as_u64().unwrap_or(1);
        let mut output = Output::new();
        for i in 0..refunds {
            output = output.with_event(Event::new(
                "eo.refunded",
                json!({ "refund_ref": format!("R-{i}"), "sale_id": "S-1" }),
            ));
        }
        Ok(output)
    }
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.expect("install eo");
    rt.register_native("eo", Arc::new(RefundHandler));
    rt
}

async fn refund(rt: &Runtime, payload: Json) {
    let params: Params = payload.as_object().cloned().unwrap_or_default();
    rt.execute_command("eo.refund", &params, &admin())
        .await
        .expect("eo.refund runs");
}

/// Every outbox row this hub holds for `event`, with its payload parsed.
async fn enqueued(rt: &Runtime, event: &str) -> Vec<Json> {
    let mut p = Params::new();
    p.insert("event".into(), json!(event));
    let rows = rt
        .db_for_test()
        .query(
            "SELECT payload FROM _event_outbox WHERE event_name = :event ORDER BY created_at",
            &p,
        )
        .await
        .expect("outbox readable");
    rows.rows
        .iter()
        .map(|r| match &r["payload"] {
            Json::String(s) => serde_json::from_str(s).expect("payload is JSON"),
            other => other.clone(),
        })
        .collect()
}

/// 🔴 The banco-pre symptom: declared AND emitted by the handler → exactly ONE row, the handler's.
#[tokio::test]
async fn an_event_the_handler_emits_is_not_enqueued_again_from_emit() {
    let rt = runtime().await;
    refund(&rt, json!({ "refunds": 1, "reason": "damaged" })).await;

    let rows = enqueued(&rt, "eo.refunded").await;
    assert_eq!(
        rows.len(),
        1,
        "one refund must announce `eo.refunded` once, not once per source (hub#1786): {rows:?}"
    );
    assert_eq!(
        rows[0]["refund_ref"],
        json!("R-0"),
        "the row that survives is the HANDLER's, the one carrying the document reference: {rows:?}"
    );
}

/// The other half: a declared event the handler does not emit keeps being announced, once.
#[tokio::test]
async fn a_declared_event_the_handler_does_not_emit_is_still_enqueued_once() {
    let rt = runtime().await;
    refund(&rt, json!({ "refunds": 1, "reason": "damaged" })).await;

    let rows = enqueued(&rt, "eo.audited").await;
    assert_eq!(rows.len(), 1, "{rows:?}");
    assert_eq!(
        rows[0]["reason"],
        json!("damaged"),
        "a declared event still carries the command's params, as it always did: {rows:?}"
    );
}

/// A handler that emits the same event once per row keeps every row — dedupe is against the
/// DECLARED copy, never between the handler's own events.
#[tokio::test]
async fn a_handler_emitting_the_same_event_per_row_keeps_every_row() {
    let rt = runtime().await;
    refund(&rt, json!({ "refunds": 3 })).await;

    let rows = enqueued(&rt, "eo.refunded").await;
    // Rows written in one transaction can share `created_at`, so the order is not the contract.
    let mut refs: Vec<String> = rows
        .iter()
        .map(|r| r["refund_ref"].as_str().unwrap_or("<none>").to_string())
        .collect();
    refs.sort();
    assert_eq!(
        refs,
        vec!["R-0", "R-1", "R-2"],
        "three refunds emitted by the handler are three events, and none comes from `emit`: {rows:?}"
    );
}
