//! **hub#1171 / hub#1119 — the fiscal chain refused by an UNGRANTED capability is seen at once,
//! and seals itself when the owner flips the switch.**
//!
//! The production observation (hub#1119, QA hub `qa-pm149-20260822-1435`, 2026-08-25): `invoice` +
//! `verifactu` installed, VeriFactu enabled in `testing`, identity stamped — and the switch
//! «Certificado del negocio (firma fiscal)» of Ajustes → Permisos OFF, which is what a hub whose
//! modules were installed by blueprint/API (not by the consent dialog of the Apps page) looks like.
//! Every sale produced an issued invoice and **zero** VeriFactu records, while «Eventos caídos»
//! said «Todo en orden».
//!
//! The unit tests of `outbox.rs` pin the relay's rule with a synthetic module. This test walks the
//! REAL chain through the real doors — the real `sales`/`invoice` WASM handlers, the real
//! `verifactu` manifest and its real native engine, the real relay, the real capability gate and
//! the real dead-letter API the screen reads — so that closing hub#1119 rests on evidence about
//! `invoice.created → verifactu.records.ingest_invoice` itself, not on a stand-in:
//!
//! 1. the sale is charged and invoiced, and the chain is EMPTY (the symptom, reproduced);
//! 2. the refusal is in the dead-letter **on the first pass** — `module.capability_denied`,
//!    retryable, naming the listener and the capability — so the badge is non-zero in seconds;
//! 3. a manual retry WITHOUT the grant never runs the engine: it dies again, classified afresh
//!    (visibility, not permissiveness — the gate still fails closed);
//! 4. granting the capability replays the row and the relay seals the invoice: one record in
//!    `verifactu_record`, for that very invoice, with nobody pressing anything else.

use std::path::PathBuf;
use std::sync::Arc;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::outbox::{RetryOutcome, FAILURE_CAPABILITY_DENIED};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}
/// Shares the Runtime's `hub_id` so the settings written here and the dispatcher's enricher read
/// the same `hub_settings` row (hub#328, ADR-0203).
fn admin() -> RequestContext {
    RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()])
}
fn handlers_built() -> bool {
    ["sales", "invoice"]
        .iter()
        .all(|m| mdir(m).join("dist/handler.wasm").exists())
}

/// The hub of hub#1119: the whole fiscal chain installed, identity stamped, VeriFactu enabled in
/// `testing` — and the `certificate` capability NOT granted, which is the default of a hub whose
/// modules did not come through the consent dialog.
async fn hub_with_the_switch_off() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.expect("system tables");
    // The host mounts the first-party engine at boot (`crates/server/src/lib.rs`); the test is the
    // host here.
    rt.register_native("verifactu", Arc::new(erplora_verifactu::VerifactuEngine));
    for m in [
        "taxes",
        "inventory",
        "customers",
        "sales",
        "invoice",
        "verifactu",
    ] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    let mut identity = serde_json::Map::new();
    identity.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    identity.insert("business_tax_id".into(), json!("B12345674"));
    rt.set_settings(&identity, "u1")
        .await
        .expect("fiscal identity");
    // Exactly what the QA hub had: `enabled:1, mode:"verifactu", environment:"testing"`. The save
    // is plain SQL, so the ungranted capability does not stop it — the config AFFIRMS it works.
    rt.execute_command(
        "verifactu.config.save",
        &params(json!({ "enabled": true, "mode": "verifactu", "environment": "testing" })),
        &admin(),
    )
    .await
    .expect("verifactu.config.save");
    rt
}

async fn cash_method_id(rt: &Runtime, ctx: &RequestContext) -> String {
    let rows = rt
        .execute_query("sales.payment_methods", &Params::new(), ctx)
        .await
        .expect("sales.payment_methods");
    rows.iter()
        .find(|r| r["type"] == json!("cash"))
        .unwrap_or_else(|| panic!("the hub catalogue must ship the `cash` method: {rows:?}"))["id"]
        .as_str()
        .expect("payment method id")
        .to_string()
}

async fn count(rt: &Runtime, sql: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(erplora_runtime::DEV_HUB_ID));
    rt.db().query(sql, &p).await.expect("count").rows[0]["c"]
        .as_i64()
        .unwrap_or(-1)
}
async fn chain_records(rt: &Runtime) -> i64 {
    count(
        rt,
        "SELECT COUNT(*) AS c FROM verifactu_record WHERE hub_id = :hub_id",
    )
    .await
}
async fn pending_rows(rt: &Runtime) -> i64 {
    count(
        rt,
        "SELECT COUNT(*) AS c FROM _event_outbox WHERE status = 'pending'",
    )
    .await
}

async fn charge_one_sale(rt: &Runtime, ctx: &RequestContext) -> String {
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "idempotency_key": "hub1119-sealed-nothing",
            "payment_method_id": cash_method_id(rt, ctx).await,
            "customer_name": "Bar Manolo",
            "tax_included": false,
            "items": [{ "product_name": "Café", "price": 200, "quantity": 2, "tax_rate": 21.0 }]
        })),
        ctx,
    )
    .await
    .expect("the sale is charged");
    rt.drain_outbox().await.expect("drain");
    let invoices = rt
        .execute_query("invoice.list", &Params::new(), ctx)
        .await
        .expect("invoice.list");
    assert_eq!(
        invoices.len(),
        1,
        "the sale IS invoiced — that link has no capability in front of it: {invoices:?}"
    );
    invoices[0]["id"].as_str().expect("invoice id").to_string()
}

/// **hub#1119, end to end.** Charged, invoiced, NOT sealed — and then seen, kept closed, and
/// recovered by the one gesture the owner is asked to make.
#[tokio::test]
async fn the_unsealed_invoice_is_seen_at_once_and_seals_itself_when_the_capability_is_granted() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !handlers_built() {
        eprintln!("SKIP: sales/invoice handler.wasm missing");
        return;
    }
    let rt = hub_with_the_switch_off().await;
    let ctx = admin();

    // ── 1 · The symptom, reproduced ────────────────────────────────────────────────────────────
    let invoice_id = charge_one_sale(&rt, &ctx).await;
    assert_eq!(
        chain_records(&rt).await,
        0,
        "the chain is empty: nothing was sealed"
    );

    // ── 2 · …and it is SEEN, on the first pass ─────────────────────────────────────────────────
    // Before hub#1171 this row was `pending` with `attempts = 1` and a due time minutes away: the
    // badge read 0, the screen said «Todo en orden», and it stayed that way for ~4 minutes per
    // invoice. A capability nobody granted is not a stumble the ladder can outwait.
    assert_eq!(
        pending_rows(&rt).await,
        0,
        "nothing is left circling on the ladder"
    );
    assert_eq!(
        rt.count_dead_events().await.unwrap(),
        1,
        "the badge (hub#747) lights up NOW"
    );
    let dead = rt.list_dead_events(50).await.expect("dead-letter listing");
    let row = dead
        .iter()
        .find(|d| d.event_name == "invoice.created")
        .unwrap_or_else(|| panic!("the dead-letter holds the invoice's event: {dead:?}"));
    assert_eq!(
        row.failure_kind, FAILURE_CAPABILITY_DENIED,
        "machine-readable reason: {row:?}"
    );
    assert!(
        row.retryable,
        "granting is the remedy, so the button must be offered: {row:?}"
    );
    assert_eq!(
        row.attempts, 0,
        "it died on the FIRST pass, not after the ladder: {row:?}"
    );
    assert!(
        row.last_error.contains("verifactu.records.ingest_invoice"),
        "the operator reads WHICH listener was refused: {}",
        row.last_error
    );
    assert!(
        row.last_error.contains("certificate"),
        "…and WHICH capability to grant: {}",
        row.last_error
    );
    assert_eq!(
        row.payload["invoice_id"],
        json!(invoice_id),
        "the payload is intact — this is not a scrubbed dead end: {row:?}"
    );

    // ── 3 · Visibility is not permissiveness: a retry WITHOUT the grant never runs the engine ──
    assert_eq!(
        rt.retry_dead_event(&row.id).await.unwrap(),
        RetryOutcome::Requeued
    );
    rt.drain_outbox().await.expect("drain");
    assert_eq!(
        chain_records(&rt).await,
        0,
        "the gate still fails CLOSED: no record without the grant"
    );
    let again = rt.list_dead_events(50).await.unwrap();
    assert_eq!(again.len(), 1, "dead again, at once: {again:?}");
    assert_eq!(
        again[0].failure_kind, FAILURE_CAPABILITY_DENIED,
        "classified afresh: {again:?}"
    );

    // ── 4 · The remedy is the switch, and only the switch ──────────────────────────────────────
    rt.set_module_capability("verifactu", "certificate", true, "hub_user:1")
        .await
        .expect("the owner grants it in Ajustes → Permisos");
    assert_eq!(
        rt.count_dead_events().await.unwrap(),
        0,
        "flipping the switch put the refused event back in front of the relay by itself"
    );
    rt.drain_outbox().await.expect("drain");

    assert_eq!(pending_rows(&rt).await, 0);
    assert_eq!(
        rt.count_dead_events().await.unwrap(),
        0,
        "nothing died on the way back"
    );
    assert_eq!(
        chain_records(&rt).await,
        1,
        "the invoice that could not be sealed is sealed now"
    );
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(erplora_runtime::DEV_HUB_ID));
    let rec = rt
        .db()
        .query(
            "SELECT invoice_id, record_type, status FROM verifactu_record WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(
        rec[0]["invoice_id"],
        json!(invoice_id),
        "…and it is THAT invoice: {rec:?}"
    );
    assert_eq!(rec[0]["record_type"], json!("alta"), "{rec:?}");
    assert_eq!(
        count(&rt, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status = 'delivered' AND event_name = 'invoice.created'").await,
        1,
        "the event is delivered, once"
    );
}
