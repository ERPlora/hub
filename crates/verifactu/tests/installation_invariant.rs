//! Installation invariant (ADR-0202 §4.2, phase 0) — hub#312.
//!
//! `NumeroInstalacion` identifies ONE installation of the software before the AEAT and can
//! never be reused nor inherited: it is the hub's UUID (`hub_id`) — never a slug, never the
//! business name or NIF, never empty. Two hubs of the same NIF are independent "virtual SIFs"
//! with separate chains (AEAT developer FAQ §4); a new hub is a new installation and opens its
//! own chain with `PrimerRegistro=S`.

use erplora_db::Params;
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::Result;
use erplora_verifactu::{aeat, VerifactuEngine};
use serde_json::{json, Value};
use std::sync::Mutex;

const HUB_A: &str = "6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10";
const HUB_B: &str = "a3d94f1c-8e57-4d0a-b6c2-91e0f4728c55";

/// Test host that also records the SQL it is asked to run: the anchor query is a contract
/// (the chain is scoped per hub) and it is asserted here.
#[derive(Default)]
struct SpyHost {
    config: Vec<Value>,
    invoice: Vec<Value>,
    anchor: Vec<Value>,
    queries: Mutex<Vec<String>>,
}

#[async_trait::async_trait]
impl NativeHost for SpyHost {
    async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Value>> {
        self.queries.lock().unwrap().push(sql.to_string());
        if sql.contains("invoice_invoice") {
            Ok(self.invoice.clone())
        } else if sql.contains("verifactu_config") {
            Ok(self.config.clone())
        } else {
            Ok(self.anchor.clone())
        }
    }
}

impl SpyHost {
    fn anchor_query(&self) -> String {
        self.queries
            .lock()
            .unwrap()
            .iter()
            .find(|q| q.contains("verifactu_record") && q.contains("ORDER BY sequence_number DESC"))
            .cloned()
            .expect("the chain anchor was queried")
    }
}

/// A simplified invoice (F2, no recipient) as `ingest_invoice` reads it.
fn invoice_row() -> Value {
    json!({
        "invoice_type": "F2",
        "number": "FACT-2026-000001",
        "issue_date": "2026-08-02",
        "issuer_nif": "B27593136",
        "issuer_name": "ERPLORA CLOUD SL",
        "customer_tax_id": "",
        "customer_name": "",
        "base_amount": 413,
        "tax_amount": 87,
        "total_amount": 500,
        "tax_breakdown": "{}",
    })
}

/// Runs `ingest_invoice` under the given hub and returns the record row (INSERT params).
async fn ingest(host: &SpyHost, hub_id: &str) -> Result<Value> {
    let new_ids: Vec<Value> = (0..8).map(|i| Value::String(format!("id-{i}"))).collect();
    let input = json!({
        "payload": { "invoice_id": "inv-1" },
        "context": {
            "hub_id": hub_id,
            "current_user_id": "u-1",
            "now": "2026-08-05T10:00:00+00:00",
            "new_ids": new_ids,
        },
    });
    let out = VerifactuEngine.call("ingest_invoice", &input, host).await?;
    Ok(out.operations[0].params.clone().into())
}

// ── 1. Two hubs of the same NIF = two installations, two fresh chains ─────────────────────

#[tokio::test]
async fn two_hubs_with_the_same_nif_get_distinct_installation_numbers_and_fresh_chains() {
    let host_a = SpyHost { invoice: vec![invoice_row()], ..Default::default() };
    let rec_a = ingest(&host_a, HUB_A).await.expect("hub A builds its record");
    let host_b = SpyHost { invoice: vec![invoice_row()], ..Default::default() };
    let rec_b = ingest(&host_b, HUB_B).await.expect("hub B builds its record");

    // No anchor on either hub → each one opens its OWN chain.
    assert_eq!(rec_a["is_first_record"], json!(1), "{rec_a}");
    assert_eq!(rec_b["is_first_record"], json!(1), "{rec_b}");

    // The XML declares each installation's own UUID, and both open with PrimerRegistro=S.
    let config = json!({});
    let xml_a = aeat::build_soap(&rec_a, &config, None, HUB_A);
    let xml_b = aeat::build_soap(&rec_b, &config, None, HUB_B);
    assert!(
        xml_a.contains(&format!("<sum1:NumeroInstalacion>{HUB_A}</sum1:NumeroInstalacion>")),
        "hub A must declare ITS hub_id as NumeroInstalacion: {xml_a}"
    );
    assert!(
        xml_b.contains(&format!("<sum1:NumeroInstalacion>{HUB_B}</sum1:NumeroInstalacion>")),
        "hub B must declare ITS hub_id as NumeroInstalacion: {xml_b}"
    );
    assert!(xml_a.contains("<sum1:PrimerRegistro>S</sum1:PrimerRegistro>"), "{xml_a}");
    assert!(xml_b.contains("<sum1:PrimerRegistro>S</sum1:PrimerRegistro>"), "{xml_b}");

    // Contract: the anchor is scoped per hub — another hub's records can never be the anchor.
    let anchor_sql = host_a.anchor_query();
    assert!(anchor_sql.contains("hub_id = :hub_id"), "{anchor_sql}");
}

// ── 2. NumeroInstalacion is the hub UUID — never empty, never a slug ──────────────────────

#[tokio::test]
async fn a_record_is_never_built_for_an_empty_or_non_uuid_hub_id() {
    for bad in ["", "bar-manolo", "h1", "B27593136"] {
        let host = SpyHost { invoice: vec![invoice_row()], ..Default::default() };
        let result = ingest(&host, bad).await;
        assert!(
            result.is_err(),
            "hub_id {bad:?} must be rejected: NumeroInstalacion can only be the hub UUID \
             (a record built with it would register a bogus installation with the AEAT)"
        );
    }
}

#[tokio::test]
async fn a_valid_hub_uuid_is_accepted_verbatim() {
    // `hub_id` is not part of the INSERT params (the runtime row contract injects it);
    // what this pins is that a UUID hub passes the guard and the record gets built.
    let host = SpyHost { invoice: vec![invoice_row()], ..Default::default() };
    let rec = ingest(&host, HUB_A).await.expect("a UUID hub_id builds the record");
    assert_eq!(rec["record_type"], json!("alta"), "{rec}");
}
