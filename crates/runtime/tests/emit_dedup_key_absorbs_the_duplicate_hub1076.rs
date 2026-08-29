//! hub#1076 — `emit.dedup_key` absorbs a duplicate emission from an idempotent ingestion door.
//!
//! A declarative command had exactly one way to skip emitting: `min_affected_rows`/`expect_rows`
//! (hub#140/#139), and both **roll back the whole transaction** and hand the caller an error. That
//! is the wrong shape for an ingestion door that is at-least-once by construction — a WhatsApp
//! webhook redelivering a message it never saw acknowledged, or the outbox relay retrying a
//! listener. Rejecting the duplicate turns "I already have this" into a 409/500 the webhook
//! retries forever, or a message the relay dead-letters despite the hub already holding it —
//! exactly backwards for at-least-once delivery (`whatsapp_inbox` PR #34, closing
//! `whatsapp_inbox`#30).
//!
//! `dedup_key` names the field of the command's bound payload whose value derives the outbox
//! row's id, the same mechanism `outbox::insert_core_event_once` already uses for a core-ingested
//! event (`"wa-<wa_message_id>"`). Market precedent: Stripe's `Idempotency-Key`, Kafka's keyed
//! dedup — the key is evaluated against the request and a repeat within the store's own
//! uniqueness window is absorbed, never rejected.
//!
//! Fixture: `tests/fixture_1076` declares `w1076.messages.ingest` (`ON CONFLICT DO NOTHING` at the
//! SQL layer + `emit: [{event, dedup_key: "wa_message_id"}]`) and a `..._legacy` twin with the
//! plain string form, to prove the field is opt-in and a manifest that has not adopted it keeps
//! double-emitting exactly as before (hub#1076 acceptance criterion: no behaviour change for
//! published modules).

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_1076")
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

async fn fresh_runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture_dir())
        .await
        .expect("install w1076");
    rt
}

/// Counts the outbox rows of a given `event_name` in this hub — the "was the event queued?"
/// oracle, same as in `min_affected_rows_e2e.rs`.
async fn outbox_count(rt: &Runtime, hub_id: &str, event_name: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("event_name".into(), json!(event_name));
    let rows = rt
        .db()
        .query(
            "SELECT COUNT(*) AS n FROM _event_outbox WHERE hub_id = :hub_id AND event_name = :event_name",
            &p,
        )
        .await
        .expect("count the outbox")
        .rows;
    rows[0]["n"]
        .as_i64()
        .unwrap_or_else(|| panic!("COUNT returned something odd: {rows:?}"))
}

#[tokio::test]
async fn a_repeated_wa_message_id_leaves_one_row_and_one_event_hub1076() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    let payload = params(json!({ "wa_message_id": "wamid.ABC", "body": "hola" }));

    let first = rt
        .execute_command("w1076.messages.ingest", &payload, &ctx)
        .await
        .expect("first delivery: OK");
    assert_eq!(first["ok"], json!(true));

    // Redelivery: the webhook sends the SAME message again because it never saw the ACK in time.
    // The caller has to see exactly what it saw the first time — never a 409/500 — or it will
    // retry forever.
    let second = rt
        .execute_command("w1076.messages.ingest", &payload, &ctx)
        .await
        .expect("second delivery (webhook redelivery): OK, NEVER 409/500");
    assert_eq!(second["ok"], json!(true));

    let rows = rt
        .execute_query("w1076.messages.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(
        rows.len(),
        1,
        "UNIQUE(hub_id, wa_message_id) + ON CONFLICT already left a single row"
    );

    assert_eq!(
        outbox_count(&rt, "h1", "w1076.message.received").await,
        1,
        "`dedup_key` must absorb the second emission: 1 event in the outbox, not 2"
    );
}

#[tokio::test]
async fn two_different_wa_message_ids_each_get_their_own_event_hub1076() {
    // `dedup_key` only absorbs REPEATS of the SAME key — it must not turn into "this command
    // emits at most once per hub".
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    rt.execute_command(
        "w1076.messages.ingest",
        &params(json!({ "wa_message_id": "wamid.ONE", "body": "uno" })),
        &ctx,
    )
    .await
    .expect("first message");
    rt.execute_command(
        "w1076.messages.ingest",
        &params(json!({ "wa_message_id": "wamid.TWO", "body": "dos" })),
        &ctx,
    )
    .await
    .expect("second message, different key");

    assert_eq!(
        outbox_count(&rt, "h1", "w1076.message.received").await,
        2,
        "two different wa_message_id are two business messages: two events"
    );
}

#[tokio::test]
async fn without_dedup_key_a_duplicate_still_double_emits_legacy_hub1076() {
    // Acceptance criterion of hub#1076: a published module that does NOT adopt `dedup_key` keeps
    // its EXACT historical behaviour — opt-in, never a silent behaviour change.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    let payload = params(json!({ "wa_message_id": "wamid.LEGACY", "body": "hola" }));

    rt.execute_command("w1076.messages.ingest_legacy", &payload, &ctx)
        .await
        .expect("first delivery");
    rt.execute_command("w1076.messages.ingest_legacy", &payload, &ctx)
        .await
        .expect("second delivery");

    assert_eq!(
        outbox_count(&rt, "h1", "w1076.message.legacy_received").await,
        2,
        "without `dedup_key` the command keeps emitting per EXECUTION, as always (opt-in, hub#1076)"
    );
}
