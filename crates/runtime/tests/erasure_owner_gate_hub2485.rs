//! **hub#2485** — the owner gate of the kernel's erasure, through the real dispatcher and relay.
//!
//! Since hub#2467 a `<subject>.anonymized` event empties every terminal history row that names
//! `<subject>_id`. Any installed app could emit one: name a customer it does not own and her
//! history is gone; name a common word (`"id"`, a key of nearly every payload) and the hub's whole
//! history is gone. Now the relay only erases a subject that is a row of the EMITTER's own tables
//! in this hub, and only an id of the shape the hub generates.
//!
//! The real `customers` module erases its customer; a test app (`fixture_erasure2485/intruder`)
//! that emits the same event — or names its own row `"id"` — is refused, its event stays
//! undelivered with the refusal's code, and her history is untouched.
//!
//! Real Postgres, ephemeral schema per test.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

fn params(v: Json) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn intruder_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_erasure2485")
        .join("intruder")
}

fn admin() -> RequestContext {
    RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()])
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.expect("system tables");
    rt.install_from_dir(&erplora_runtime::e2e_support::modules_root().join("customers"))
        .await
        .expect("install customers");
    rt.install_from_dir(&intruder_dir())
        .await
        .expect("install intruder");
    rt
}

async fn one(rt: &Runtime, sql: &str, bind: &[(&str, &str)]) -> String {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(erplora_runtime::DEV_HUB_ID));
    for (k, v) in bind {
        p.insert((*k).into(), json!(v));
    }
    let rows = rt.db().query(sql, &p).await.expect("query").rows;
    assert_eq!(rows.len(), 1, "exactly one row for {sql}: {rows:?}");
    rows[0]["v"].as_str().unwrap_or_default().to_string()
}

/// Ana, created by the real customers app; her `customer.created` is delivered and kept in the
/// hub's history with her name — the trace the erasure is about.
async fn ana(rt: &Runtime) -> String {
    rt.execute_command(
        "customers.create",
        &params(json!({ "name": "Ana Pérez", "phone": "+34600111222" })),
        &admin(),
    )
    .await
    .expect("customers.create");
    rt.drain_outbox().await.expect("drain");
    one(
        rt,
        "SELECT id AS v FROM customers_customer WHERE hub_id = :hub_id",
        &[],
    )
    .await
}

async fn created_payload(rt: &Runtime) -> String {
    one(
        rt,
        "SELECT payload AS v FROM _event_outbox \
          WHERE hub_id = :hub_id AND event_name = 'customer.created'",
        &[],
    )
    .await
}

async fn erasure_row(rt: &Runtime, module: &str, field: &str) -> String {
    one(
        rt,
        &format!(
            "SELECT {field} AS v FROM _event_outbox \
              WHERE hub_id = :hub_id AND event_name LIKE '%.anonymized' AND module_id = :module"
        ),
        &[("module", module)],
    )
    .await
}

/// The bug: `intruder` emits `customer.anonymized` naming Ana, whose sheet is the customers
/// app's. Refused — undelivered, labelled with its code — and her history still names her. The
/// same erasure from `customers` goes through and empties it.
#[tokio::test]
async fn only_the_app_that_owns_the_customer_erases_her_history() {
    let rt = hub().await;
    let ana = ana(&rt).await;
    assert!(created_payload(&rt).await.contains("Ana Pérez"));

    rt.execute_command(
        "intruder.customers.forget",
        &params(json!({ "customer_id": ana })),
        &admin(),
    )
    .await
    .expect("intruder.customers.forget");
    rt.drain_outbox().await.expect("drain");

    assert!(
        created_payload(&rt).await.contains("Ana Pérez"),
        "an app that does not own her erased her history"
    );
    assert_eq!(erasure_row(&rt, "intruder", "status").await, "pending");
    let refusal = erasure_row(&rt, "intruder", "last_error").await;
    assert!(
        refusal.contains("erasure.subject_not_owned"),
        "the refusal names its code: {refusal}"
    );

    rt.execute_command(
        "customers.anonymize",
        &params(json!({ "customer_id": ana, "reason": "gdpr request" })),
        &admin(),
    )
    .await
    .expect("customers.anonymize");
    rt.drain_outbox().await.expect("drain");

    assert_eq!(erasure_row(&rt, "customers", "status").await, "delivered");
    assert_eq!(created_payload(&rt).await, "{}");
}

/// The vector of the issue: `intruder` owns a note whose id is `"id"` and erases it. As a needle,
/// `"id"` is a key of nearly every payload; the hub refuses an id it did not generate, even from
/// its owner, and nothing of Ana's moves.
#[tokio::test]
async fn an_app_cannot_empty_the_history_by_naming_a_common_word() {
    let rt = hub().await;
    ana(&rt).await;
    rt.execute_command(
        "intruder.notes.add",
        &params(json!({ "note_id": "id", "body": "x" })),
        &admin(),
    )
    .await
    .expect("intruder.notes.add");

    rt.execute_command(
        "intruder.notes.forget",
        &params(json!({ "note_id": "id" })),
        &admin(),
    )
    .await
    .expect("intruder.notes.forget");
    rt.drain_outbox().await.expect("drain");

    assert!(created_payload(&rt).await.contains("Ana Pérez"));
    assert_eq!(erasure_row(&rt, "intruder", "status").await, "pending");
    let refusal = erasure_row(&rt, "intruder", "last_error").await;
    assert!(
        refusal.contains("erasure.invalid_subject_id"),
        "the refusal names its code: {refusal}"
    );
}
