//! Tests de recuperación/validación de cadena y del parser de consulta a la AEAT.
//!
//! Los handlers nativos (`validate_chain`, `recover_manual`) se ejercitan con un [`MockHost`]
//! que devuelve filas canned según la SQL — sin BD real. Se comprueba que producen las
//! **intenciones** correctas (los INSERT/UPDATE que el runtime persistiría).
use erplora_db::Params;
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::Result;
use erplora_verifactu::{chain, VerifactuEngine};
use serde_json::{json, Value};

/// Host de prueba: discrimina por la SQL (config singleton / ancla DESC / cadena ASC).
struct MockHost {
    config: Vec<Value>,
    chain_rows: Vec<Value>,
    anchor: Vec<Value>,
}

#[async_trait::async_trait]
impl NativeHost for MockHost {
    async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Value>> {
        if sql.contains("verifactu_config") {
            Ok(self.config.clone())
        } else if sql.contains("ORDER BY sequence_number ASC") {
            Ok(self.chain_rows.clone())
        } else {
            Ok(self.anchor.clone())
        }
    }
}

fn empty_host() -> MockHost {
    MockHost { config: vec![], chain_rows: vec![], anchor: vec![] }
}

fn context(now: &str, ids: usize) -> Value {
    let new_ids: Vec<Value> = (0..ids).map(|i| Value::String(format!("id-{i}"))).collect();
    json!({ "hub_id": "1e7d3f0a-5c2b-4a89-b0d6-3e94a1c7f258", "current_user_id": "u-1", "now": now, "new_ids": new_ids })
}

/// Fila `alta` con la huella REAL calculada por `chain::alta_hash` (importes en céntimos).
fn alta_row(seq: i64, num: &str, prev: &str, ts: &str, is_first: i64) -> (Value, String) {
    let hash = chain::alta_hash("B12345678", num, "2026-06-10", "F1", 21.0, 121.0, prev, ts);
    let row = json!({
        "id": format!("r-{seq}"),
        "record_type": "alta",
        "sequence_number": seq,
        "issuer_nif": "B12345678",
        "invoice_number": num,
        "invoice_date": "2026-06-10",
        "invoice_type": "F1",
        "tax_amount": 2100,    // céntimos → /100 = 21.00 €
        "total_amount": 12100, // céntimos → /100 = 121.00 €
        "previous_hash": prev,
        "record_hash": hash,
        "is_first_record": is_first,
        "generation_timestamp": ts,
    });
    (row, hash)
}

// ── recover_manual ────────────────────────────────────────────────────────────

#[tokio::test]
async fn recover_manual_inserts_anchor_with_normalized_hash() {
    let host = empty_host(); // sin registros previos → secuencia 1
    let hash_lower = "a".repeat(64);
    let input = json!({
        "payload": { "issuer_nif": "B12345678", "record_hash": hash_lower },
        "context": context("2026-06-10T10:00:00+00:00", 8),
    });
    let out = VerifactuEngine.call("recover_manual", &input, &host).await.unwrap();
    assert_eq!(out.operations.len(), 2, "ancla + evento");
    let anchor = &out.operations[0];
    assert_eq!(anchor.command, "verifactu._insert_recovery");
    assert_eq!(anchor.params.get("record_hash").unwrap().as_str().unwrap(), "A".repeat(64));
    assert_eq!(anchor.params.get("sequence_number").unwrap().as_i64().unwrap(), 1);
    assert_eq!(out.operations[1].command, "verifactu._insert_event");
}

#[tokio::test]
async fn recover_manual_continues_from_existing_sequence() {
    // Ya hay registros: la última secuencia es 7 → el ancla debe ir a 8.
    let host = MockHost { config: vec![], chain_rows: vec![], anchor: vec![json!({ "sequence_number": 7 })] };
    let input = json!({
        "payload": { "issuer_nif": "B12345678", "record_hash": "b".repeat(64) },
        "context": context("2026-06-10T10:00:00+00:00", 8),
    });
    let out = VerifactuEngine.call("recover_manual", &input, &host).await.unwrap();
    assert_eq!(out.operations[0].params.get("sequence_number").unwrap().as_i64().unwrap(), 8);
}

#[tokio::test]
async fn recover_manual_rejects_bad_hash() {
    let host = empty_host();
    let input = json!({
        "payload": { "issuer_nif": "B12345678", "record_hash": "no-es-hex" },
        "context": context("2026-06-10T10:00:00+00:00", 8),
    });
    assert!(VerifactuEngine.call("recover_manual", &input, &host).await.is_err());
}

// ── validate_chain ──────────────────────────────────────────────────────────────

#[tokio::test]
async fn validate_chain_ok_for_consistent_chain() {
    let (r1, h1) = alta_row(1, "FA/001", "", "2026-06-10T12:00:00+00:00", 1);
    let (r2, _) = alta_row(2, "FA/002", &h1, "2026-06-10T13:00:00+00:00", 0);
    let host = MockHost { config: vec![], chain_rows: vec![r1, r2], anchor: vec![] };
    let input = json!({
        "payload": { "issuer_nif": "B12345678" },
        "context": context("2026-06-10T14:00:00+00:00", 4),
    });
    let out = VerifactuEngine.call("validate_chain", &input, &host).await.unwrap();
    assert_eq!(out.operations.len(), 1);
    let ev = &out.operations[0];
    assert_eq!(ev.command, "verifactu._insert_event");
    assert_eq!(ev.params.get("event_type").unwrap().as_str().unwrap(), "chain_validated");
}

#[tokio::test]
async fn validate_chain_detects_tampering() {
    let (r1, h1) = alta_row(1, "FA/001", "", "2026-06-10T12:00:00+00:00", 1);
    let (mut r2, _) = alta_row(2, "FA/002", &h1, "2026-06-10T13:00:00+00:00", 0);
    r2["record_hash"] = json!("DEADBEEF"); // huella almacenada falseada
    let host = MockHost { config: vec![], chain_rows: vec![r1, r2], anchor: vec![] };
    let input = json!({
        "payload": { "issuer_nif": "B12345678" },
        "context": context("2026-06-10T14:00:00+00:00", 4),
    });
    let out = VerifactuEngine.call("validate_chain", &input, &host).await.unwrap();
    assert_eq!(out.operations[0].params.get("event_type").unwrap().as_str().unwrap(), "chain_error");
}

#[tokio::test]
async fn validate_chain_trusts_recovery_anchor() {
    // recovery (no se recomputa) + alta encadenada desde su huella → cadena íntegra.
    let anchor_hash = "C".repeat(64);
    let anchor = json!({
        "id": "rec-0", "record_type": "recovery", "sequence_number": 5,
        "issuer_nif": "B12345678", "invoice_number": "AEAT-x", "invoice_date": "2026-06-10",
        "invoice_type": "F1", "tax_amount": 0, "total_amount": 0,
        "previous_hash": "", "record_hash": anchor_hash, "is_first_record": 0,
        "generation_timestamp": "2026-06-10T11:00:00+00:00",
    });
    let (next, _) = alta_row(6, "FA/100", &anchor_hash, "2026-06-10T12:00:00+00:00", 0);
    let host = MockHost { config: vec![], chain_rows: vec![anchor, next], anchor: vec![] };
    let input = json!({
        "payload": { "issuer_nif": "B12345678" },
        "context": context("2026-06-10T14:00:00+00:00", 4),
    });
    let out = VerifactuEngine.call("validate_chain", &input, &host).await.unwrap();
    assert_eq!(out.operations[0].params.get("event_type").unwrap().as_str().unwrap(), "chain_validated");
}

// ── consulta AEAT ─────────────────────────────────────────────────────────────
//
// El sobre, el parser (sobre la respuesta REAL capturada de preproducción) y la elección del
// ancla viven en `tests/consult.rs`: son el núcleo de hub#287 y merecen fichero propio. Los que
// había aquí iban contra un XML inventado que la AEAT no devuelve.

#[test]
fn is_valid_hash_checks_64_hex() {
    assert!(chain::is_valid_hash(&"a".repeat(64)));
    assert!(chain::is_valid_hash(&"F0".repeat(32)));
    assert!(!chain::is_valid_hash(&"a".repeat(63)));
    assert!(!chain::is_valid_hash(&"g".repeat(64)));
}
