//! Regression test for ERPlora/hub#1270 — LOCAL half of hub#325 (ADR-0413, cierre del hub como
//! kernel). The AEAT-preproduction half of hub#325 stays BLOCKED on the FNMT seal (pm#73) and the
//! convenio 017 (pm#71); this file needs neither: no network, no real certificate material.
//!
//! **The property.** The certificate a hub signs with is a fact of the CORE
//! (`_hub_certificate`, ADR-0202 §2.1) and can be rotated at any moment — the business
//! re-uploads its own `.p12`, or ERPlora rotates the delegated one. The fiscal hash chain must
//! not care: `chain::alta_hash` (`crates/verifactu/src/chain.rs`) composes the AEAT fingerprint
//! from `IDEmisorFactura&NumSerieFactura&FechaExpedicionFactura&TipoFactura&CuotaTotal&
//! ImporteTotal&Huella&FechaHoraHusoGenRegistro` (Orden HAC/1177/2024) — the PREVIOUS record's
//! own hash, never who signed it. `crates/verifactu/src/lib.rs::environment_chain_tests` pins
//! this at the unit level with a synthetic host; this file is the e2e half: the REAL `verifactu`
//! module, its REAL native engine, and a REAL certificate rotation through `_hub_certificate` —
//! on a real Postgres, through the real dispatcher (`Runtime::execute_command`).
//!
//! Nothing here reaches the AEAT: the stored `.p12` bytes are a placeholder that cannot become a
//! real mTLS identity, so `create_record`'s inline transmission attempt fails locally and the
//! record stays `pending` — exactly the same "signed, not yet transmitted" outcome a real hub
//! shows the instant a certificate is swapped out from under a queued record. That failure mode
//! is not what this file measures; the chain surviving the rotation is.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::certificate::{self, CertificateKind};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

const HUB: &str = "c4d9f6a1-3b7e-4c2a-9f0d-8e5a1b6c7d29";

/// Same resolution as the `require_modules_workspace` guard — it honours `$ERPLORA_MODULES_DIR`.
fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

/// The real fiscal chain: `verifactu` `depends_on: invoice`, which needs `sales` (`sales.get` for
/// `create_from_sale`) and `taxes` (the rule catalog), and `sales` needs `inventory`. Same install
/// order `crates/runtime/tests/verifactu_chain_import_e2e.rs` already uses.
async fn runtime_with_verifactu(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables()
        .await
        .expect("ensure_system_tables");
    // The host mounts the first-party engine at boot (`crates/server/src/lib.rs`); the test is
    // the host here (same pattern as `capability_denied_listener_e2e.rs`).
    rt.register_native(
        "verifactu",
        std::sync::Arc::new(erplora_verifactu::VerifactuEngine),
    );
    for m in ["taxes", "inventory", "sales", "invoice", "verifactu"] {
        rt.install_from_dir(&modules_root().join(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    // The owner's explicit consent (Ajustes → Permisos) for the `certificate` capability
    // `verifactu` declares — a hub whose modules came through the normal install dialog would
    // already carry this; a bare `install_from_dir` in a test does not (hub#1119/hub#1171).
    // Without it every command of the module is refused with `CapabilityDenied`, independent of
    // whether `_hub_certificate` holds a row — this is the SEPARATE gate from the one under test.
    rt.set_module_capability("verifactu", "certificate", true, "hub_user:1")
        .await
        .expect("the owner grants the certificate capability");
    rt
}

/// Writes one slot straight into the core table, exactly like
/// `crates/runtime/tests/certificate_fallback_e2e.rs::store_slot` — going through the real
/// writers would need the process-global `HUB_SECRETS_KEY`, and everything this file reads (the
/// dispatcher's `can_sign`, the engine's `has_certificate`) looks only at the PRESENCE of the
/// row, never at its content. `marker` stands in for "which physical certificate" purely for the
/// test's own readability: cert A and cert B share nothing, on purpose.
async fn store_cert(db: &dyn DatabaseAdapter, hub_id: &str, kind: CertificateKind, marker: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind.as_str()));
    p.insert("pkcs12_b64".into(), json!(format!("v1:{marker}")));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :kind, :pkcs12_b64, 'v1:ciphertext', '2026-08-07T09:00:00Z', 'x')",
        &p,
    )
    .await
    .expect("the slot is stored");
}

fn admin() -> RequestContext {
    RequestContext::new(
        HUB,
        "u1",
        [
            "verifactu.manage_verifactu".to_string(),
            "verifactu.view_verifactu".to_string(),
        ],
    )
}

/// `record_type: "anulacion"` — not `"alta"` — and NOT a simplification of the scenario.
///
/// `records.create`'s own manifest schema (`schemas/record_create.json`) never accepts a
/// `tax_breakdown`, so every call through this public command binds an EMPTY STRING to that
/// column. On Postgres 18 that empty string trips a pre-existing bug in the sibling
/// `ERPlora/verifactu` module (migration `011_arithmetic_integrity.sql`): its `alta`-only CHECK
/// constraints call `JSON_EXISTS(tax_breakdown, … FALSE ON ERROR)`, and Postgres raises
/// `invalid input syntax for type json` for that empty string — `ON ERROR` does not catch it —
/// before the constraint's own `record_type <> 'alta'` guard ever gets to short-circuit it.
/// Reproduced directly: `SELECT JSON_EXISTS('', 'strict $[*]' FALSE ON ERROR);` fails the same
/// way against a bare `erplora-test-pg-5433`. That bug lives in `ERPlora/verifactu`, not in this
/// repo (`origin: ERPlora/verifactu`, filed separately) — hub#1270 does not touch it.
///
/// `anulacion` sidesteps it cleanly: every one of those CHECKs starts with `record_type <>
/// 'alta' OR …`, so an `anulacion` never reaches the broken `JSON_EXISTS` call, and
/// `chain::anulacion_hash` is exactly as certificate-independent as `chain::alta_hash` — the
/// property under test does not care which of the two record types carries it.
fn record_payload(invoice_number: &str) -> Params {
    json!({
        "record_type": "anulacion",
        "issuer_nif": "B27593136",
        "issuer_name": "ERPLORA CLOUD SL",
        "invoice_number": invoice_number,
        "invoice_date": "2026-08-06",
        "invoice_type": "F2",
    })
    .as_object()
    .cloned()
    .expect("record payload is a JSON object")
}

/// The persisted chain, in sequence order — read straight from the table, never from what
/// `execute_command` echoed back, so the assertions are about what actually landed.
async fn chain(rt: &Runtime, hub_id: &str) -> Vec<Json> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    rt.db()
        .query(
            "SELECT sequence_number, previous_hash, record_hash, status \
             FROM verifactu_record WHERE hub_id = :hub_id ORDER BY sequence_number ASC",
            &p,
        )
        .await
        .expect("query verifactu_record")
        .rows
}

/// The `event_type` of the most recent `chain_validated`/`chain_error` audit row `chain.validate`
/// leaves behind — the same table the module's own Events screen reads.
async fn last_chain_event(rt: &Runtime, hub_id: &str) -> String {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let rows = rt
        .db()
        .query(
            "SELECT event_type FROM verifactu_event \
             WHERE hub_id = :hub_id AND event_type IN ('chain_validated', 'chain_error') \
             ORDER BY created_at DESC, id DESC LIMIT 1",
            &p,
        )
        .await
        .expect("query verifactu_event")
        .rows;
    rows.first()
        .and_then(|r| r["event_type"].as_str())
        .unwrap_or("<none>")
        .to_string()
}

/// Flips one record's stored `record_hash` — as if it had been silently re-signed instead of
/// merely re-transmitted. Direct SQL on purpose: the module has no command that lets a caller
/// rewrite a sealed hash, because a sealed hash must never change (RD 1007/2023).
async fn tamper_record_hash(rt: &Runtime, hub_id: &str, invoice_number: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("invoice_number".into(), json!(invoice_number));
    p.insert("fake_hash".into(), json!("f".repeat(64)));
    rt.db()
        .execute(
            "UPDATE verifactu_record SET record_hash = :fake_hash \
             WHERE hub_id = :hub_id AND invoice_number = :invoice_number",
            &p,
        )
        .await
        .expect("tamper record_hash");
}

#[tokio::test]
async fn the_chain_does_not_break_when_the_certificate_changes_hub1270() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = runtime_with_verifactu(HUB).await;
    let ctx = admin();

    // Record 1, signed while the hub's OWN certificate (cert A) is the one active.
    store_cert(rt.db(), HUB, CertificateKind::Own, "cert-A").await;
    rt.execute_command(
        "verifactu.records.create",
        &record_payload("F-2026-000001"),
        &ctx,
    )
    .await
    .expect("record 1 is created while cert A signs");

    // Certificate ROTATION: cert A is gone, ERPlora's delegated cert (cert B) takes over — a
    // completely different identity, sharing nothing with the one that signed record 1.
    certificate::delete(rt.db(), HUB, CertificateKind::Own)
        .await
        .expect("delete cert A");
    store_cert(rt.db(), HUB, CertificateKind::Delegated, "cert-B").await;
    rt.execute_command(
        "verifactu.records.create",
        &record_payload("F-2026-000002"),
        &ctx,
    )
    .await
    .expect("record 2 is created after the rotation, while cert B signs");

    let records = chain(&rt, HUB).await;
    assert_eq!(
        records.len(),
        2,
        "both records must have been persisted: {records:?}"
    );
    assert_eq!(
        records[0]["previous_hash"],
        json!(""),
        "record 1 opens the chain: {records:?}"
    );
    assert_ne!(
        records[0]["record_hash"],
        json!(""),
        "record 1 must carry its own fingerprint: {records:?}"
    );
    assert_eq!(
        records[1]["previous_hash"], records[0]["record_hash"],
        "record 2 must chain on record 1's OWN fingerprint — the certificate rotation between \
         the two must not touch it: {records:?}"
    );

    // A verifier walking the chain accepts it — across the rotation.
    rt.execute_command(
        "verifactu.chain.validate",
        &json!({ "issuer_nif": "B27593136" })
            .as_object()
            .cloned()
            .unwrap(),
        &ctx,
    )
    .await
    .expect("chain.validate runs");
    assert_eq!(
        last_chain_event(&rt, HUB).await,
        "chain_validated",
        "the chain must still validate after the certificate rotation"
    );

    // NEGATIVE: a tampered record 1 still breaks the chain the verifier walks — proving the
    // positive assertion above is not a verifier that always answers "valid".
    tamper_record_hash(&rt, HUB, "F-2026-000001").await;
    rt.execute_command(
        "verifactu.chain.validate",
        &json!({ "issuer_nif": "B27593136" })
            .as_object()
            .cloned()
            .unwrap(),
        &ctx,
    )
    .await
    .expect("chain.validate runs");
    assert_eq!(
        last_chain_event(&rt, HUB).await,
        "chain_error",
        "a tampered record must still break the chain the verifier walks"
    );
}
