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
        .expect("instalar w1076");
    rt
}

/// Cuenta las filas pendientes del outbox para un `event_name` dado, en este hub — el oráculo de
/// "¿se encoló el evento?", igual que en `min_affected_rows_e2e.rs`.
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
        .expect("contar el outbox")
        .rows;
    rows[0]["n"]
        .as_i64()
        .unwrap_or_else(|| panic!("COUNT devolvió algo raro: {rows:?}"))
}

#[tokio::test]
async fn a_repeated_wa_message_id_leaves_one_row_and_one_event_hub1076() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    let payload = params(json!({ "wa_message_id": "wamid.ABC", "body": "hola" }));

    let first = rt
        .execute_command("w1076.messages.ingest", &payload, &ctx)
        .await
        .expect("primera entrega: OK");
    assert_eq!(first["ok"], json!(true));

    // Redelivery: el webhook manda el MISMO mensaje otra vez porque no vio el ACK a tiempo. El
    // caller tiene que ver exactamente lo mismo que la primera vez — nunca un 409/500 — o
    // reintentará para siempre.
    let second = rt
        .execute_command("w1076.messages.ingest", &payload, &ctx)
        .await
        .expect("segunda entrega (redelivery del webhook): OK, NUNCA 409/500");
    assert_eq!(second["ok"], json!(true));

    let rows = rt
        .execute_query("w1076.messages.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(
        rows.len(),
        1,
        "el UNIQUE(hub_id, wa_message_id) + ON CONFLICT ya dejaba una sola fila"
    );

    assert_eq!(
        outbox_count(&rt, "h1", "w1076.message.received").await,
        1,
        "`dedup_key` debe absorber la segunda emisión: 1 evento en el outbox, no 2"
    );
}

#[tokio::test]
async fn two_different_wa_message_ids_each_get_their_own_event_hub1076() {
    // `dedup_key` solo absorbe REPETIDOS de la MISMA clave — no debe convertirse en "este command
    // emite como mucho una vez por hub".
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    rt.execute_command(
        "w1076.messages.ingest",
        &params(json!({ "wa_message_id": "wamid.ONE", "body": "uno" })),
        &ctx,
    )
    .await
    .expect("primer mensaje");
    rt.execute_command(
        "w1076.messages.ingest",
        &params(json!({ "wa_message_id": "wamid.TWO", "body": "dos" })),
        &ctx,
    )
    .await
    .expect("segundo mensaje, clave distinta");

    assert_eq!(
        outbox_count(&rt, "h1", "w1076.message.received").await,
        2,
        "dos wa_message_id distintos son dos mensajes de negocio: dos eventos"
    );
}

#[tokio::test]
async fn without_dedup_key_a_duplicate_still_double_emits_legacy_hub1076() {
    // Acceptance criterion de hub#1076: un módulo publicado que NO adopta `dedup_key` conserva su
    // comportamiento EXACTO de siempre — opt-in, nunca un cambio de comportamiento en silencio.
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();
    let payload = params(json!({ "wa_message_id": "wamid.LEGACY", "body": "hola" }));

    rt.execute_command("w1076.messages.ingest_legacy", &payload, &ctx)
        .await
        .expect("primera entrega");
    rt.execute_command("w1076.messages.ingest_legacy", &payload, &ctx)
        .await
        .expect("segunda entrega");

    assert_eq!(
        outbox_count(&rt, "h1", "w1076.message.legacy_received").await,
        2,
        "sin `dedup_key` el command sigue emitiendo por EJECUCIÓN, como siempre (opt-in, hub#1076)"
    );
}
