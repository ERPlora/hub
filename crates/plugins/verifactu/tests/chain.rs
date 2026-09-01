//! La cadena fiscal: de qué eslabón cuelga el siguiente registro y cómo se recupera — hub#287.
//!
//! Tres cosas, todas decididas **antes** de que nada consuma secuencia (la cadena es inmutable:
//! un registro mal construido ya ha gastado su número cuando la AEAT lo rechaza):
//!
//! 1. **El tipo de factura.** Una F1 exige el bloque `Destinatarios`; sin NIF de cliente el XML
//!    sale sin él y la AEAT lo rechaza con **1189**. Una venta a consumidor final sin NIF es
//!    justo el supuesto de la **simplificada (F2)**. El tipo entra en el cálculo de la huella,
//!    así que se resuelve antes de encadenar, no se parchea después (saas#1070/#1062).
//! 2. **De dónde sale `previous_hash`.** Del último registro que la AEAT tiene, no del último
//!    que hay en la tabla: encadenar desde uno **rechazado** apunta a una huella que Hacienda no
//!    conoce, y convierte un fallo puntual en una cadena que ya no avanza sola.
//! 3. **La recuperación automática.** Ante un rechazo de encadenamiento (**2007** y familia), el
//!    sistema se re-ancla desde la AEAT y reintenta **una vez**, en vez de dejar el registro
//!    esperando a que alguien pulse un botón. El caso real que lo dispara es **restaurar un
//!    backup**: la cadena local retrocede y la AEAT conserva lo posterior.
use erplora_db::Params;
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::Result;
use erplora_verifactu::{aeat, chain, VerifactuEngine};
use serde_json::{json, Value};
use std::sync::Mutex;

/// Host de prueba que además **registra las SQL** que se le piden: la consulta del ancla es un
/// contrato (no puede seleccionar registros rechazados) y aquí se comprueba.
#[derive(Default)]
struct SpyHost {
    config: Vec<Value>,
    invoice: Vec<Value>,
    anchor: Vec<Value>,
    chain_rows: Vec<Value>,
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
        } else if sql.contains("ORDER BY sequence_number ASC") {
            Ok(self.chain_rows.clone())
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
            .expect("se consultó el ancla de la cadena")
    }
}

fn context(now: &str, ids: usize) -> Value {
    let new_ids: Vec<Value> = (0..ids).map(|i| Value::String(format!("id-{i}"))).collect();
    json!({ "hub_id": "1e7d3f0a-5c2b-4a89-b0d6-3e94a1c7f258", "current_user_id": "u-1", "now": now, "new_ids": new_ids })
}

/// Fila de `invoice_invoice` tal como la lee `ingest_invoice`.
fn invoice_row(invoice_type: &str, customer_tax_id: &str, total_cents: i64) -> Value {
    json!({
        "invoice_type": invoice_type,
        "number": "FACT-2026-000001",
        "issue_date": "2026-08-02",
        "issuer_nif": "B27593136",
        "issuer_name": "ERPLORA CLOUD SL",
        "customer_tax_id": customer_tax_id,
        "customer_name": if customer_tax_id.is_empty() { "" } else { "Cliente SL" },
        "base_amount": total_cents * 100 / 121,
        "tax_amount": total_cents - (total_cents * 100 / 121),
        "total_amount": total_cents,
        "tax_breakdown": "{}",
    })
}

async fn ingest(host: &SpyHost) -> Value {
    let input = json!({
        "payload": { "invoice_id": "inv-1" },
        "context": context("2026-08-02T10:00:00+00:00", 8),
    });
    let out = VerifactuEngine
        .call("ingest_invoice", &input, host)
        .await
        .expect("ingest");
    out.operations[0].params.clone().into()
}

// ── 1. Paridad de tipo: F2 sin NIF, F1 con NIF ────────────────────────────────────────────

/// Sin NIF de destinatario una F1 produce un XML sin `Destinatarios` que la AEAT rechaza con
/// 1189 — y lo rechaza DESPUÉS de que el registro haya consumido su número en la cadena.
#[tokio::test]
async fn una_f1_sin_nif_de_cliente_se_declara_como_simplificada() {
    let host = SpyHost {
        invoice: vec![invoice_row("F1", "", 12100)],
        ..Default::default()
    };
    let rec = ingest(&host).await;
    assert_eq!(rec["invoice_type"], json!("F2"), "{rec}");
}

#[tokio::test]
async fn una_f1_con_nif_de_cliente_sigue_siendo_f1() {
    let host = SpyHost {
        invoice: vec![invoice_row("F1", "B12345678", 12100)],
        ..Default::default()
    };
    let rec = ingest(&host).await;
    assert_eq!(rec["invoice_type"], json!("F1"), "{rec}");
}

/// Una rectificativa sin NIF **no** es una simplificada: es una rectificativa **de** simplificada
/// (R5). Degradarla a F2 declararía una venta donde hay una devolución.
#[tokio::test]
async fn una_rectificativa_sin_nif_se_declara_como_r5_no_como_f2() {
    let host = SpyHost {
        invoice: vec![invoice_row("R1", "", -12100)],
        ..Default::default()
    };
    let rec = ingest(&host).await;
    assert_eq!(rec["invoice_type"], json!("R5"), "{rec}");
}

#[tokio::test]
async fn una_f2_no_se_toca() {
    let host = SpyHost {
        invoice: vec![invoice_row("F2", "", 500)],
        ..Default::default()
    };
    let rec = ingest(&host).await;
    assert_eq!(rec["invoice_type"], json!("F2"));
}

/// El tipo entra en el cálculo de la huella: si se resolviera DESPUÉS de encadenar, la huella
/// almacenada no correspondería al XML que se manda.
#[tokio::test]
async fn el_tipo_ya_resuelto_es_el_que_entra_en_la_huella() {
    let host = SpyHost {
        invoice: vec![invoice_row("F1", "", 12100)],
        ..Default::default()
    };
    let rec = ingest(&host).await;
    let esperada = chain::alta_hash(
        "B27593136",
        "FACT-2026-000001",
        "2026-08-02",
        "F2", // el tipo YA degradado
        rec["tax_amount"].as_f64().unwrap() / 100.0,
        rec["total_amount"].as_f64().unwrap() / 100.0,
        "",
        rec["generation_timestamp"].as_str().unwrap(),
    );
    assert_eq!(rec["record_hash"], json!(esperada));
}

// ── 2. El ancla no cuelga de un registro rechazado ────────────────────────────────────────

/// Contrato de la consulta del ancla: un registro **rechazado** no está en la AEAT, así que su
/// huella no puede ser el `previous_hash` del siguiente. Encadenar ahí garantiza otro rechazo.
#[tokio::test]
async fn el_ancla_de_la_cadena_excluye_los_registros_rechazados() {
    let host = SpyHost {
        invoice: vec![invoice_row("F2", "", 500)],
        ..Default::default()
    };
    ingest(&host).await;
    let sql = host.anchor_query();
    assert!(
        sql.contains("status"),
        "la consulta del ancla debe filtrar por estado: {sql}"
    );
    assert!(
        sql.contains("'rejected'"),
        "un registro rechazado no puede ser el eslabón anterior: {sql}"
    );
}

/// Un registro en vuelo (`pending`/`error`, encolado en contingencia) **sí** es eslabón: se
/// transmitirá con la huella que ya calculó. Excluirlo bifurcaría la cadena.
#[test]
fn los_estados_en_vuelo_siguen_siendo_eslabon() {
    for s in [
        "pending",
        "transmitted",
        "accepted",
        "retry",
        "error",
        "recovery",
    ] {
        assert!(
            erplora_verifactu::is_chainable_status(s),
            "{s} debe seguir encadenando"
        );
    }
    assert!(!erplora_verifactu::is_chainable_status("rejected"));
}

/// `validate_chain` recorre la cadena en memoria: si el ancla ya no cuelga de los rechazados,
/// el validador tampoco puede contarlos como eslabón o marcaría rota una cadena correcta.
#[tokio::test]
async fn validate_chain_salta_los_rechazados_igual_que_el_ancla() {
    let h1 = chain::alta_hash(
        "B27593136",
        "FA/001",
        "2026-08-02",
        "F2",
        21.0,
        121.0,
        "",
        "2026-08-02T10:00:00+00:00",
    );
    let fila = |seq: i64, num: &str, prev: &str, ts: &str, first: i64, status: &str| {
        let hash = chain::alta_hash("B27593136", num, "2026-08-02", "F2", 21.0, 121.0, prev, ts);
        json!({
            "id": format!("r-{seq}"), "record_type": "alta", "sequence_number": seq,
            "issuer_nif": "B27593136", "invoice_number": num, "invoice_date": "2026-08-02",
            "invoice_type": "F2", "tax_amount": 2100, "total_amount": 12100,
            "previous_hash": prev, "record_hash": hash, "is_first_record": first,
            "generation_timestamp": ts, "status": status,
        })
    };
    // 1 aceptado → 2 RECHAZADO → 3 encadena desde 1 (que es lo que la AEAT tiene).
    let rows = vec![
        fila(1, "FA/001", "", "2026-08-02T10:00:00+00:00", 1, "accepted"),
        fila(2, "FA/002", &h1, "2026-08-02T11:00:00+00:00", 0, "rejected"),
        fila(3, "FA/003", &h1, "2026-08-02T12:00:00+00:00", 0, "accepted"),
    ];
    let host = SpyHost {
        chain_rows: rows,
        ..Default::default()
    };
    let input = json!({
        "payload": { "issuer_nif": "B27593136" },
        "context": context("2026-08-02T13:00:00+00:00", 4),
    });
    let out = VerifactuEngine
        .call("validate_chain", &input, &host)
        .await
        .unwrap();
    assert_eq!(
        out.operations[0].params["event_type"],
        json!("chain_validated"),
        "saltarse el rechazado deja la cadena íntegra: {:?}",
        out.operations[0].params
    );
}

// ── 3. Recuperación automática ante 2007 y familia ────────────────────────────────────────

/// El rechazo que dispara la recuperación. `2007` es el que devuelve la AEAT tras restaurar un
/// backup: «No debe informarse como primer registro, existen facturas emitidas con el obligado
/// emisión y el sistema informático actual».
#[test]
fn el_2007_se_reconoce_como_rechazo_de_encadenamiento() {
    assert!(aeat::is_chaining_rejection(
        "2007",
        "No debe informarse como primer registro, existen facturas emitidas con el obligado \
         emisión y el sistema informático actual."
    ));
}

/// La familia no es solo el 2007: la AEAT describe el problema en texto y los códigos exactos
/// dependen del caso. Se reconoce también por la descripción.
#[test]
fn la_familia_del_encadenamiento_se_reconoce_por_la_descripcion() {
    assert!(aeat::is_chaining_rejection(
        "1234",
        "El registro anterior informado no se corresponde con el último registro remitido"
    ));
    assert!(aeat::is_chaining_rejection(
        "",
        "Error de encadenamiento: la huella del registro anterior no coincide"
    ));
}

/// Un rechazo que NO es de encadenamiento no puede disparar una re-ancla: re-anclar mueve la
/// cadena, y hacerlo por un NIF mal escrito sería mucho peor que el fallo original.
#[test]
fn un_rechazo_cualquiera_no_dispara_la_reancla() {
    assert!(!aeat::is_chaining_rejection(
        "1189",
        "Es obligatorio informar el bloque Destinatarios para este tipo de factura"
    ));
    assert!(!aeat::is_chaining_rejection(
        "1100",
        "El NIF no está identificado en el censo de la AEAT"
    ));
    assert!(!aeat::is_chaining_rejection("", ""));
}

/// Re-anclar es recomponer el registro rechazado sobre el último eslabón que la AEAT SÍ tiene:
/// cambia `previous_hash`, la secuencia y —por tanto— la propia huella. La AEAT no tiene el
/// registro rechazado, así que reescribirlo localmente es legítimo; lo que no vale es mandarlo
/// otra vez colgando de la huella equivocada.
#[test]
fn re_anclar_recalcula_la_huella_sobre_el_eslabon_que_la_aeat_tiene() {
    let ancla = aeat::ConsultRecord {
        issuer_nif: "B27593136".into(),
        invoice_number: "PRU-0003".into(),
        invoice_date: "01-08-2026".into(),
        record_hash: "A".repeat(64),
        generated_at: "2026-08-01T18:38:11Z".into(),
        ..Default::default()
    };
    let rechazado = json!({
        "id": "r-9", "record_type": "alta", "sequence_number": 2,
        "issuer_nif": "B27593136", "invoice_number": "FA/009", "invoice_date": "2026-08-02",
        "invoice_type": "F2", "tax_amount": 2100, "total_amount": 12100,
        "previous_hash": "", "record_hash": "vieja", "is_first_record": 1,
        "generation_timestamp": "2026-08-02T10:00:00+00:00",
    });

    let (rechained, op) = erplora_verifactu::rechain_record(&rechazado, &ancla, 5);

    assert_eq!(rechained["previous_hash"], json!("A".repeat(64)));
    assert_eq!(rechained["sequence_number"], json!(5));
    assert_eq!(
        rechained["is_first_record"],
        json!(0),
        "ya no es el primero: la AEAT tiene registros anteriores"
    );
    let esperada = chain::alta_hash(
        "B27593136",
        "FA/009",
        "2026-08-02",
        "F2",
        21.0,
        121.0,
        &"A".repeat(64),
        "2026-08-02T10:00:00+00:00",
    );
    assert_eq!(rechained["record_hash"], json!(esperada));
    // La intención que persiste el cambio en la fila.
    assert_eq!(op.command, "verifactu._rechain_record");
    assert_eq!(op.params["record_id"], json!("r-9"));
    assert_eq!(op.params["record_hash"], json!(esperada));
    assert_eq!(op.params["sequence_number"], json!(5));
}
