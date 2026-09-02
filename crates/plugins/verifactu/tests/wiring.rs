//! Tests de cableado del handler nativo `ingest_invoice`.
//!
//! `ingest_invoice` se ejercita con un [`MockHost`] que devuelve filas canned según la SQL
//! (config singleton / fila de factura `invoice_invoice` / ancla de cadena DESC) — sin BD real.
//! Se comprueba que, dada una factura, produce la **intención** de crear el registro `alta`.
use erplora_db::Params;
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::Result;
use erplora_verifactu::VerifactuEngine;
use serde_json::{json, Value};

/// Host de prueba: discrimina por la SQL (factura / config / ancla de cadena).
struct MockHost {
    config: Vec<Value>,
    invoice: Vec<Value>,
    anchor: Vec<Value>,
}

#[async_trait::async_trait]
impl NativeHost for MockHost {
    async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Value>> {
        if sql.contains("invoice_invoice") {
            Ok(self.invoice.clone())
        } else if sql.contains("verifactu_config") {
            Ok(self.config.clone())
        } else {
            Ok(self.anchor.clone())
        }
    }
}

fn context(now: &str, ids: usize) -> Value {
    let new_ids: Vec<Value> = (0..ids).map(|i| Value::String(format!("id-{i}"))).collect();
    json!({ "hub_id": "1e7d3f0a-5c2b-4a89-b0d6-3e94a1c7f258", "current_user_id": "u-1", "now": now, "new_ids": new_ids })
}

/// Fila de factura canónica que devuelve la lectura sobre `invoice_invoice`.
///
/// Lleva `customer_tax_id`: los registros de este fichero son **F1**, y una F1 sin destinatario
/// identificado es exactamente el XML que la AEAT rechaza con el error **1189**. Hasta hub#287
/// esta fila iba sin NIF de cliente y el test afirmaba que salía una F1 — fijando una conducta que
/// Hacienda no acepta. El caso real sin NIF ya no pasa por aquí: sale como F2 (`tests/chain.rs`,
/// `resolve_invoice_type`).
fn invoice_row() -> Value {
    json!({
        "invoice_type": "F1",
        "number": "FACT-2026-000001",
        "issue_date": "2026-06-10",
        "issuer_nif": "B12345678",
        "issuer_name": "ACME",
        "customer_tax_id": "B87654321",
        "customer_name": "Cliente SL",
        "base_amount": 10000,
        "tax_amount": 2100,
        "total_amount": 12100,
    })
}

#[tokio::test]
async fn ingest_invoice_creates_alta_from_invoice_row() {
    // config vacío (auto_transmit por defecto) + fila de factura + ancla vacía (primer registro).
    let host = MockHost { config: vec![], invoice: vec![invoice_row()], anchor: vec![] };
    let input = json!({
        "payload": { "invoice_id": "inv-1" },
        "context": context("2026-06-10T10:00:00+00:00", 4),
    });
    let out = VerifactuEngine.call("ingest_invoice", &input, &host).await.unwrap();
    let rec = &out.operations[0];
    assert_eq!(rec.command, "verifactu._insert_record");
    assert_eq!(rec.params.get("record_type").unwrap().as_str().unwrap(), "alta");
    assert_eq!(rec.params.get("invoice_number").unwrap().as_str().unwrap(), "FACT-2026-000001");
    assert_eq!(rec.params.get("invoice_type").unwrap().as_str().unwrap(), "F1");
    assert_eq!(rec.params.get("issuer_nif").unwrap().as_str().unwrap(), "B12345678");
    assert_eq!(out.operations[1].command, "verifactu._insert_event");
}

#[tokio::test]
async fn ingest_invoice_skips_when_invoice_missing() {
    // La factura no existe → no se crea registro (no es error).
    let host = MockHost { config: vec![], invoice: vec![], anchor: vec![] };
    let input = json!({
        "payload": { "invoice_id": "inv-1" },
        "context": context("2026-06-10T10:00:00+00:00", 4),
    });
    let out = VerifactuEngine.call("ingest_invoice", &input, &host).await.unwrap();
    assert!(out.operations.is_empty());
}
