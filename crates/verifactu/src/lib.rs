//! # erplora-verifactu
//!
//! Motor fiscal **VeriFactu** (RD 1007/2023) como **plugin nativo first-party**
//! ([ADR-0009]): cadena de hash SHA-256 encadenada por `(hub_id, issuer_nif)`,
//! construcción del XML SOAP y transmisión a la AEAT con TLS mutua (PKCS#12).
//!
//! Es la "segunda clase de módulo" del sistema: el SQL declarativo y la UI del módulo
//! `verifactu` siguen el modelo normal; SOLO este motor va horneado en el runtime
//! (no es un `handler.wasm` descargable). Contrato idéntico al WASM Tier 2: nunca
//! escribe en la BD — lee vía [`NativeHost`] (solo SELECT) y devuelve *intenciones*
//! (ops sobre commands SQL internos del propio módulo: `verifactu._insert_record`,
//! `verifactu._insert_event`, `verifactu._enqueue_contingency`,
//! `verifactu._apply_transmission`) que el runtime valida y persiste en una transacción.
//!
//! Funciones (commands del manifest con `handler.type: "native"`):
//! - `create_record` (issue verifactu#2) — alta/anulación encadenada + QR.
//! - `transmit_record` (issue verifactu#3) — SOAP + TLS mutua + respuesta AEAT.
//! - `validate_chain` / `process_contingency_queue` — pendientes (issues #4 / #7).
//!
//! [ADR-0009]: ../../../architecture/00-overview/decision-log.md
use erplora_db::Params;
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::{Result, RuntimeError};
use erplora_wasm_host::{Operation, Output};
use serde_json::{json, Value as Json};

pub mod aeat;
pub mod chain;

/// Errores internos del motor (se aplanan a [`RuntimeError::Native`]).
#[derive(Debug, thiserror::Error)]
pub enum VerifactuError {
    #[error("payload inválido: {0}")]
    Payload(String),
    #[error("certificado: {0}")]
    Certificate(String),
    #[error("transmisión AEAT: {0}")]
    Transmission(String),
}

impl From<VerifactuError> for RuntimeError {
    fn from(e: VerifactuError) -> Self {
        RuntimeError::Native(e.to_string())
    }
}

/// El plugin nativo del módulo `verifactu`. Se registra en el runtime con
/// `runtime.register_native("verifactu", Arc::new(VerifactuEngine))`.
#[derive(Debug, Default)]
pub struct VerifactuEngine;

#[async_trait::async_trait]
impl NativeHandler for VerifactuEngine {
    async fn call(&self, function: &str, input: &Json, host: &dyn NativeHost) -> Result<Output> {
        match function {
            "create_record" => create_record(input, host).await,
            "transmit_record" => transmit_record(input, host).await,
            "validate_chain" => Err(RuntimeError::Native(
                "validate_chain pendiente de implementación (issue verifactu#4)".into(),
            )),
            "process_contingency_queue" => Err(RuntimeError::Native(
                "process_contingency_queue pendiente de implementación (issue verifactu#7)".into(),
            )),
            other => Err(RuntimeError::Native(format!(
                "función desconocida del plugin verifactu: `{other}`"
            ))),
        }
    }
}

// ── helpers de input ─────────────────────────────────────────────────────────

fn str_field(v: &Json, k: &str) -> String {
    v.get(k).and_then(|x| x.as_str()).unwrap_or_default().to_string()
}

fn num_field(v: &Json, k: &str, default: f64) -> f64 {
    match v.get(k) {
        Some(Json::Number(n)) => n.as_f64().unwrap_or(default),
        Some(Json::String(s)) => s.trim().parse().unwrap_or(default),
        _ => default,
    }
}

fn int_field(v: &Json, k: &str, default: i64) -> i64 {
    match v.get(k) {
        Some(Json::Number(n)) => n.as_i64().unwrap_or(default),
        Some(Json::String(s)) => s.trim().parse().unwrap_or(default),
        _ => default,
    }
}

struct Ctx {
    hub_id: String,
    now: String,
    new_ids: Vec<String>,
}

fn split_input(input: &Json) -> Result<(Json, Ctx)> {
    let payload = input.get("payload").cloned().unwrap_or(Json::Null);
    let context = input.get("context").cloned().unwrap_or(Json::Null);
    let hub_id = str_field(&context, "hub_id");
    if hub_id.is_empty() {
        return Err(RuntimeError::Native("input sin context.hub_id".into()));
    }
    let new_ids = context
        .get("new_ids")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|x| x.as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    let now = chain::format_timestamp(&str_field(&context, "now"));
    Ok((payload, Ctx { hub_id, now, new_ids }))
}

fn params(pairs: Json) -> Params {
    pairs.as_object().cloned().unwrap_or_default()
}

fn op(command: &str, p: Json) -> Operation {
    Operation::sql(command, params(p))
}

/// Lee la config VeriFactu del hub (fila singleton; `None` si no se ha guardado nunca).
async fn read_config(host: &dyn NativeHost, hub_id: &str) -> Result<Option<Json>> {
    let rows = host
        .read(
            "SELECT * FROM verifactu_config WHERE hub_id = :hub_id AND is_deleted = 0 LIMIT 1",
            &params(json!({ "hub_id": hub_id })),
        )
        .await?;
    Ok(rows.into_iter().next())
}

// ── create_record (issue verifactu#2) ────────────────────────────────────────

const INVOICE_TYPES: [&str; 8] = ["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"];

/// Genera el registro fiscal encadenado (alta/anulación): ancla de cadena por
/// `(hub_id, issuer_nif)`, huella SHA-256 (formatos AEAT exactos), `qr_url`, e
/// intenciones INSERT record(pending) + event + (si `auto_transmit` off) cola.
///
/// Atomicidad de la secuencia: el ancla se lee antes de calcular, y el índice único
/// `uq_verifactu_record_hub_seq (hub_id, issuer_nif, sequence_number)` cierra la ventana
/// TOCTOU — si dos creates compiten, el segundo INSERT viola el índice y SU transacción
/// entera revierte (sin fork de cadena). En SQLite además las escrituras se serializan.
async fn create_record(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;

    // Validación del payload (espejo de schemas/record_create.json).
    let record_type = str_field(&payload, "record_type");
    if record_type != "alta" && record_type != "anulacion" {
        return Err(VerifactuError::Payload("record_type debe ser alta|anulacion".into()).into());
    }
    let issuer_nif = str_field(&payload, "issuer_nif");
    let issuer_name = str_field(&payload, "issuer_name");
    let invoice_number = str_field(&payload, "invoice_number");
    let invoice_date = str_field(&payload, "invoice_date");
    let invoice_type = str_field(&payload, "invoice_type");
    for (name, v) in [
        ("issuer_nif", &issuer_nif),
        ("issuer_name", &issuer_name),
        ("invoice_number", &invoice_number),
        ("invoice_date", &invoice_date),
    ] {
        if v.is_empty() {
            return Err(VerifactuError::Payload(format!("falta {name}")).into());
        }
    }
    if !INVOICE_TYPES.contains(&invoice_type.as_str()) {
        return Err(VerifactuError::Payload("invoice_type debe ser F1-F3|R1-R5".into()).into());
    }
    if chrono::NaiveDate::parse_from_str(&invoice_date, "%Y-%m-%d").is_err() {
        return Err(VerifactuError::Payload("invoice_date debe ser YYYY-MM-DD".into()).into());
    }

    let base_amount = num_field(&payload, "base_amount", 0.0);
    let tax_rate = num_field(&payload, "tax_rate", 21.0);
    let tax_amount = num_field(&payload, "tax_amount", 0.0);
    let total_amount = num_field(&payload, "total_amount", 0.0);

    // Ancla de cadena: última fila por (hub_id, issuer_nif). Ver doc de atomicidad arriba.
    let anchor = host
        .read(
            "SELECT record_hash, sequence_number FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif AND is_deleted = 0 \
             ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({ "hub_id": ctx.hub_id, "issuer_nif": issuer_nif })),
        )
        .await?;
    let (previous_hash, sequence_number, is_first) = match anchor.first() {
        Some(row) => (str_field(row, "record_hash"), int_field(row, "sequence_number", 0) + 1, false),
        None => (String::new(), 1, true),
    };

    // Huella (formatos AEAT exactos — chain.rs) + QR.
    let generation_timestamp = ctx.now.clone();
    let record_hash = if record_type == "alta" {
        chain::alta_hash(
            &issuer_nif,
            &invoice_number,
            &invoice_date,
            &invoice_type,
            tax_amount,
            total_amount,
            &previous_hash,
            &generation_timestamp,
        )
    } else {
        chain::anulacion_hash(
            &issuer_nif,
            &invoice_number,
            &invoice_date,
            &previous_hash,
            &generation_timestamp,
        )
    };
    let qr_url = chain::qr_url(&issuer_nif, &invoice_number, &invoice_date, total_amount);

    let config = read_config(host, &ctx.hub_id).await?;
    let auto_transmit = config
        .as_ref()
        .map(|c| int_field(c, "auto_transmit", 1) != 0)
        .unwrap_or(true);

    let ids = &ctx.new_ids;
    if ids.len() < 3 {
        return Err(RuntimeError::Native("context.new_ids insuficientes".into()));
    }
    let record_id = ids[0].clone();

    let mut output = Output::new()
        .with_operation(op(
            "verifactu._insert_record",
            json!({
                "record_id": record_id,
                "record_type": record_type,
                "sequence_number": sequence_number,
                "invoice_id": payload.get("invoice_id").cloned().unwrap_or(Json::Null),
                "issuer_nif": issuer_nif,
                "issuer_name": issuer_name,
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "invoice_type": invoice_type,
                "description": str_field(&payload, "description"),
                "base_amount": base_amount,
                "tax_rate": tax_rate,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "previous_hash": previous_hash,
                "record_hash": record_hash,
                "is_first_record": if is_first { 1 } else { 0 },
                "generation_timestamp": generation_timestamp,
                "qr_url": qr_url,
            }),
        ))
        .with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ids[1],
                "record_id": record_id,
                "event_type": "record_created",
                "severity": "info",
                "message": format!("Registro {record_type} #{sequence_number} de {invoice_number} creado"),
                "details": json!({
                    "sequence_number": sequence_number,
                    "record_hash": record_hash,
                    "is_first_record": is_first,
                }).to_string(),
                "timestamp": ctx.now,
            }),
        ));

    // Sin auto-transmisión (o en contingencia declarada): el registro queda encolado.
    if !auto_transmit {
        output = output.with_operation(op(
            "verifactu._enqueue_contingency",
            json!({
                "queue_id": ids[2],
                "record_id": record_id,
                "priority": 2,
                "attempts": 0,
                "last_attempt_at": Json::Null,
                "last_error": "",
                "next_attempt_at": ctx.now,
                "queue_status": "pending",
            }),
        ));
    }

    // El evento `verifactu.record.created` lo emite el `emit` declarado del command.
    Ok(output)
}

// ── transmit_record (issue verifactu#3) ──────────────────────────────────────

/// Transmite un registro a la AEAT: XML SOAP + identidad PKCS#12 + POST TLS-mutua al
/// endpoint del entorno configurado (`testing` = default). Respuesta → UPDATE del
/// registro (accepted/rejected/error) + evento; fallo de red → cola de contingencia
/// con backoff exponencial (5,10,20,40,60 min cap).
async fn transmit_record(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let record_id = str_field(&payload, "record_id");
    if record_id.is_empty() {
        return Err(VerifactuError::Payload("falta record_id".into()).into());
    }
    if ctx.new_ids.len() < 2 {
        return Err(RuntimeError::Native("context.new_ids insuficientes".into()));
    }

    let rows = host
        .read(
            "SELECT * FROM verifactu_record WHERE id = :record_id AND hub_id = :hub_id \
             AND is_deleted = 0 LIMIT 1",
            &params(json!({ "record_id": record_id, "hub_id": ctx.hub_id })),
        )
        .await?;
    let record = rows
        .into_iter()
        .next()
        .ok_or_else(|| RuntimeError::Native(format!("registro `{record_id}` no encontrado")))?;
    if str_field(&record, "status") == "accepted" {
        return Err(RuntimeError::Native("el registro ya fue aceptado por la AEAT".into()));
    }

    let config = read_config(host, &ctx.hub_id)
        .await?
        .ok_or_else(|| RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into()))?;
    let certificate_path = str_field(&config, "certificate_path");
    if certificate_path.is_empty() {
        return Err(VerifactuError::Certificate(
            "certificado PKCS#12 no configurado (certificate_path)".into(),
        )
        .into());
    }
    // TODO(runtime): certificate_password debe llegar descifrada por el runtime cuando
    // exista cifrado at-rest de secretos de módulo; hoy se usa tal cual está almacenada.
    let certificate_password = str_field(&config, "certificate_password");
    let der = std::fs::read(&certificate_path).map_err(|e| {
        VerifactuError::Certificate(format!("no se pudo leer `{certificate_path}`: {e}"))
    })?;
    let identity = aeat::identity_from_pkcs12(&der, &certificate_password)?;

    // Registro anterior de la cadena (para el bloque Encadenamiento del XML).
    let is_first = int_field(&record, "is_first_record", 0) != 0;
    let prev = if is_first {
        None
    } else {
        host.read(
            "SELECT issuer_nif, invoice_number, invoice_date, record_hash FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif AND sequence_number = :prev_seq \
             AND is_deleted = 0 LIMIT 1",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": str_field(&record, "issuer_nif"),
                "prev_seq": int_field(&record, "sequence_number", 1) - 1,
            })),
        )
        .await?
        .into_iter()
        .next()
    };

    let xml = aeat::build_soap(&record, &config, prev.as_ref(), &ctx.hub_id);
    let environment = {
        let e = str_field(&config, "environment");
        if e.is_empty() { "testing".to_string() } else { e }
    };
    let endpoint_url = aeat::endpoint(&environment);

    match aeat::post_soap(endpoint_url, identity, &xml).await {
        Ok(body) => {
            let resp = aeat::parse_response(&body);
            let status = match resp.estado_registro.as_str() {
                "Correcto" | "AceptadoConErrores" => "accepted",
                "Incorrecto" => "rejected",
                _ if resp.estado_envio == "Correcto" => "accepted",
                _ => "error",
            };
            let (code, message) = if status == "accepted" {
                (resp.estado_registro.clone(), resp.estado_envio.clone())
            } else {
                (resp.codigo_error.clone(), resp.descripcion_error.clone())
            };
            let event_type =
                if status == "accepted" { "transmission_success" } else { "transmission_failure" };
            let severity = if status == "accepted" { "info" } else { "error" };
            Ok(Output::new()
                .with_operation(apply_transmission(&record_id, status, &code, &message, &resp.csv, &xml, 0))
                .with_operation(op(
                    "verifactu._insert_event",
                    json!({
                        "event_id": ctx.new_ids[0],
                        "record_id": record_id,
                        "event_type": event_type,
                        "severity": severity,
                        "message": format!("AEAT ({environment}): {} {}", resp.estado_envio, resp.estado_registro),
                        "details": json!({
                            "estado_envio": resp.estado_envio,
                            "estado_registro": resp.estado_registro,
                            "csv": resp.csv,
                            "codigo_error": resp.codigo_error,
                            "descripcion_error": resp.descripcion_error,
                        }).to_string(),
                        "timestamp": ctx.now,
                    }),
                )))
        }
        Err(err) => {
            // Fallo de conexión/transporte → contingencia con backoff (WASM-TODO §5).
            let queue = host
                .read(
                    "SELECT attempts FROM verifactu_contingencyqueue \
                     WHERE record_id = :record_id AND is_deleted = 0 LIMIT 1",
                    &params(json!({ "record_id": record_id })),
                )
                .await?;
            let attempts = queue.first().map(|q| int_field(q, "attempts", 0)).unwrap_or(0) + 1;
            let interval = config
                .get("retry_interval_minutes")
                .and_then(|v| v.as_i64())
                .filter(|v| *v > 0)
                .unwrap_or(5);
            let backoff_minutes = (interval * 2_i64.pow((attempts - 1).min(8) as u32)).min(60);
            let next_attempt_at = chrono::DateTime::parse_from_rfc3339(&ctx.now)
                .map(|dt| {
                    (dt + chrono::Duration::minutes(backoff_minutes))
                        .to_rfc3339_opts(chrono::SecondsFormat::Secs, false)
                })
                .unwrap_or_else(|_| ctx.now.clone());
            let reason = err.to_string();
            Ok(Output::new()
                .with_operation(apply_transmission(&record_id, "error", "", &reason, "", &xml, 1))
                .with_operation(op(
                    "verifactu._insert_event",
                    json!({
                        "event_id": ctx.new_ids[0],
                        "record_id": record_id,
                        "event_type": "transmission_failure",
                        "severity": "error",
                        "message": format!("Fallo de transmisión AEAT ({environment}); reintento en {backoff_minutes} min"),
                        "details": json!({ "error": reason, "attempts": attempts }).to_string(),
                        "timestamp": ctx.now,
                    }),
                ))
                .with_operation(op(
                    "verifactu._enqueue_contingency",
                    json!({
                        "queue_id": ctx.new_ids[1],
                        "record_id": record_id,
                        "priority": 2,
                        "attempts": attempts,
                        "last_attempt_at": ctx.now,
                        "last_error": reason,
                        "next_attempt_at": next_attempt_at,
                        "queue_status": "retrying",
                    }),
                )))
        }
    }
    // El evento `verifactu.record.transmitted` lo emite el `emit` declarado del command.
}

/// Intención UPDATE del registro tras un intento de transmisión.
fn apply_transmission(
    record_id: &str,
    status: &str,
    code: &str,
    message: &str,
    csv: &str,
    xml: &str,
    retry_increment: i64,
) -> Operation {
    op(
        "verifactu._apply_transmission",
        json!({
            "record_id": record_id,
            "status": status,
            "aeat_response_code": code,
            "aeat_response_message": message,
            "aeat_csv": csv,
            "xml_content": xml,
            "retry_increment": retry_increment,
        }),
    )
}
