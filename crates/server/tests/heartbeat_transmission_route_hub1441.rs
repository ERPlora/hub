//! hub#1441 — **the heartbeat says by WHICH of the two routes this hub reaches the AEAT.**
//!
//! The hub has decided the route since hub#1314 (`certificate::route_of` → `own` | `delegated`,
//! ADR-0320 §1) and shows it on its own screen, but it did not tell the SaaS through any channel.
//! The cost was not cosmetic: the grant page asked EVERY hub to sign the Anexo I, including the
//! one that files with its own certificate and therefore delegates nothing to anybody — a
//! document that is not needed and a human review nobody can resolve.
//!
//! These tests hold the seam that makes the field true, not just serializable: the route is READ
//! from the certificate slots on every beat, so a hub that uploads its own `.p12` stops being
//! asked for the grant on the next one.
//!
//! The frozen bytes of the payload live next door in `heartbeat_payload_contract_hub1406.rs`.

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::daily_usage::collect_daily_usage;
use serde_json::{json, Value};

const NOW: &str = "2026-09-02T10:00:00Z";

/// A hub with the system tables in place and no certificate in either slot.
async fn hub() -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-a");
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// Occupies one certificate slot. The bytes are irrelevant here — `occupied_slots` selects on
/// `pkcs12_b64 <> ''`, which is what «this slot holds a certificate» means to the route.
async fn occupy_slot(rt: &Runtime, kind: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("hub-a"));
    p.insert("kind".into(), json!(kind));
    rt.db()
        .execute(
            "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, \
             uploaded_by) VALUES (:hub_id, :kind, 'not-empty', '', '2026-09-01T09:00:00Z', 'test')",
            &p,
        )
        .await
        .unwrap();
}

/// What actually travels: the serialized body, not the struct.
async fn wire(rt: &Runtime) -> Value {
    let usage = collect_daily_usage(rt.db(), "hub-a", NOW, &[]).await;
    serde_json::to_value(&usage).expect("the heartbeat serializes")
}

/// A hub whose only occupied slot is the DELEGATED one reports `delegated` — and that is the
/// regression the issue asks for. `certificate::can_sign` answers «own OR delegated», so a route
/// deduced from it would call this hub `own` and take its grant page away.
#[tokio::test]
async fn hub1441_a_delegated_only_hub_reports_the_delegated_route() {
    let rt = hub().await;
    occupy_slot(&rt, "delegated").await;

    assert_eq!(
        wire(&rt).await["transmission_route"],
        json!("delegated"),
        "ERPlora files ON BEHALF of this taxpayer: the Anexo I is exactly what authorises it"
    );
}

/// The owner uploads their own `.p12` and the route flips on the very next beat — no second
/// setting, no reconfiguration. This is what stops the SaaS asking them for a grant they do not
/// owe (saas#1745 already holds the mirror column and the «you need not sign anything» card).
#[tokio::test]
async fn hub1441_an_own_certificate_flips_the_route_on_the_next_beat() {
    let rt = hub().await;
    occupy_slot(&rt, "own").await;

    assert_eq!(
        wire(&rt).await["transmission_route"],
        json!("own"),
        "the taxpayer signs and files themselves: nothing is delegated, so no Anexo I exists"
    );
}

/// A hub with NEITHER certificate is `delegated`: it is the route waiting for it the moment the
/// control plane hands it the Sello, and the one the SaaS must keep offering. Answering `own`
/// there would hide the grant page from somebody who has no `.p12` at all.
#[tokio::test]
async fn hub1441_a_hub_with_no_certificate_at_all_is_still_delegated() {
    let rt = hub().await;

    assert_eq!(wire(&rt).await["transmission_route"], json!("delegated"));
}

/// And an UNREADABLE route travels **absent**, never as a fabricated `delegated`: the SaaS leaves
/// its mirror as it was, because «no news» must not read as «went back to delegated». Same rule
/// `orders_today` and `cert_version` already follow in this payload.
#[tokio::test]
async fn hub1441_an_unreadable_route_is_absent_not_a_fabricated_delegated() {
    // No system tables: `_hub_certificate` does not exist, so the read fails rather than
    // answering. This is the shape of an early boot, and of a database that would not read.
    let db = fresh_db().await;

    let usage = collect_daily_usage(&db, "hub-a", NOW, &[]).await;
    let body = serde_json::to_value(&usage).unwrap();

    assert!(
        body.get("transmission_route").is_none(),
        "«I could not read it» is an ABSENT field, never a route the hub is not on: {body}"
    );
}
