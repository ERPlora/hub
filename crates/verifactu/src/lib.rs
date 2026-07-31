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
            "ingest_invoice" => ingest_invoice(input, host).await,
            "transmit_record" => transmit_record(input, host).await,
            "validate_chain" => validate_chain(input, host).await,
            "query_aeat_records" => query_aeat_records(input, host).await,
            "recover_from_aeat" => recover_from_aeat(input, host).await,
            "recover_manual" => recover_manual(input, host).await,
            "process_contingency_queue" => process_contingency_queue(input, host).await,
            "run_diagnostics" => run_diagnostics(input, host).await,
            other => Err(RuntimeError::Native(format!(
                "función desconocida del plugin verifactu: `{other}`"
            ))),
        }
    }
}

// ── helpers de input ─────────────────────────────────────────────────────────

fn str_field(v: &Json, k: &str) -> String {
    v.get(k)
        .and_then(|x| x.as_str())
        .unwrap_or_default()
        .to_string()
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

/// Deriva el **TipoImpositivo** (% IVA) para el DesgloseIVA del registro VeriFactu a partir del
/// desglose real de la factura. El registro lleva un **único** `tax_rate` (un solo bloque de
/// desglose), así que:
/// - Si el `tax_breakdown` de la factura (JSON `{"21.00":{base,tax}, …}`, importes en céntimos)
///   tiene **un único tipo** → se usa ESE tipo exacto (lo correcto y el caso normal del POS).
/// - Si tiene **varios tipos** (factura mixta 21%+10%) o está vacío/inválido → se cae al **tipo
///   efectivo** `tax/base*100` redondeado a 2 decimales.
///
/// El desglose multi-tipo REAL (varias líneas DesgloseIVA en el XML) queda pendiente de diseño del
/// humano (TODO §G / decision-log). Antes esto era fijo 21% — incorrecto en facturas a 10% (QA 2026-06-25).
fn derive_tax_rate(tax_breakdown: &str, base_cents: f64, tax_cents: f64) -> f64 {
    if let Ok(Json::Object(map)) = serde_json::from_str::<Json>(tax_breakdown) {
        if map.len() == 1 {
            if let Some(rate) = map.keys().next().and_then(|k| k.trim().parse::<f64>().ok()) {
                return rate;
            }
        }
    }
    // Fallback (multi-tipo o sin desglose): tipo efectivo redondeado a 2 decimales. La división
    // conserva el signo en rectificativas (base y cuota negativas → ratio positivo).
    if base_cents != 0.0 {
        (tax_cents / base_cents * 10_000.0).round() / 100.0
    } else {
        0.0
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
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();
    let now = chain::format_timestamp(&str_field(&context, "now"));
    Ok((
        payload,
        Ctx {
            hub_id,
            now,
            new_ids,
        },
    ))
}

fn params(pairs: Json) -> Params {
    pairs.as_object().cloned().unwrap_or_default()
}

fn op(command: &str, p: Json) -> Operation {
    Operation::sql(command, params(p))
}

/// Lee la config VeriFactu del hub (fila singleton; `None` si no se ha guardado nunca).
///
/// **Certificado (ADR-0079/0081):** el PKCS#12 del negocio vive en el core (`_hub_certificate`,
/// subido en Ajustes → Negocio), NO en `verifactu_config`. Si existe, aquí solo se marca su
/// presencia (`certificate_source = "core"`) — **los bytes del `.p12` y la contraseña NUNCA se
/// copian a la config del módulo**; la firma/transmisión usa la capability opaca
/// `certificate_identity(hub_id)` (el core hace la cripto; ver `build_identity`). El acceso está
/// gateado por la capability `certificate` (el dispatcher la exige antes del handler nativo),
/// así que llegar aquí implica que el usuario la concedió.
async fn read_config(host: &dyn NativeHost, hub_id: &str) -> Result<Option<Json>> {
    let rows = host
        .read(
            "SELECT * FROM verifactu_config WHERE hub_id = :hub_id AND is_deleted = 0 LIMIT 1",
            &params(json!({ "hub_id": hub_id })),
        )
        .await?;
    let mut config = rows.into_iter().next();

    // Certificado del core: sondea _hub_certificate (el único origen válido desde ADR-0081).
    // Tolerante: si la tabla no existe (hub sin la migración del sistema), se queda sin marcador.
    if let Ok(cert_rows) = host
        .read(
            "SELECT pkcs12_b64, password FROM _hub_certificate WHERE hub_id = :hub_id LIMIT 1",
            &params(json!({ "hub_id": hub_id })),
        )
        .await
    {
        if let Some(c) = cert_rows.into_iter().next() {
            let b64 = c.get("pkcs12_b64").and_then(|v| v.as_str()).unwrap_or("");
            if !b64.is_empty() {
                // ADR-0079/0081: el `.p12` es del CORE. **No** copiamos los bytes ni la contraseña
                // a la config del módulo — solo un marcador. La firma/transmisión usa la capability
                // opaca `certificate_identity(hub_id)` (el core hace toda la cripto PKCS#12; la clave
                // nunca cruza al módulo). Ver `build_identity`.
                let obj = config.get_or_insert_with(|| json!({}));
                if let Some(m) = obj.as_object_mut() {
                    m.insert("certificate_source".into(), json!("core"));
                }
            }
        }
    }
    Ok(config)
}

/// Construye la **Identity mTLS** para firmar/transmitir a la AEAT.
///
/// El certificado fiscal (.p12) es un recurso del NEGOCIO/hub (ADR-0079/0081): vive en
/// `_hub_certificate` (se sube en Ajustes → Negocio). La capability opaca
/// `host.certificate_identity(hub_id)` lee la tabla del core y hace TODA la cripto PKCS#12;
/// **los bytes del `.p12` y la contraseña NUNCA entran al módulo**. Si no hay certificado del
/// core, se devuelve un error claro (el usuario debe subirlo en Ajustes → Negocio).
async fn build_identity(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
) -> Result<reqwest::Identity> {
    if !has_certificate(config) {
        return Err(VerifactuError::Certificate(
            "certificado del negocio no configurado: súbelo en Ajustes → Negocio".into(),
        )
        .into());
    }
    host.certificate_identity(hub_id).await
}

/// ¿Hay un certificado del core disponible para transmitir? Gate barato que NO carga los bytes
/// del `.p12`: basta el marcador `certificate_source` que `read_config` pone al detectar
/// `_hub_certificate`.
fn has_certificate(config: &Json) -> bool {
    str_field(config, "certificate_source") == "core"
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

    build_record_output(
        host,
        &ctx,
        RecordInput {
            record_type,
            issuer_nif,
            issuer_name,
            invoice_number,
            invoice_date,
            invoice_type,
            description: str_field(&payload, "description"),
            base_amount: num_field(&payload, "base_amount", 0.0),
            tax_rate: num_field(&payload, "tax_rate", 21.0),
            tax_breakdown: str_field(&payload, "tax_breakdown"),
            tax_amount: num_field(&payload, "tax_amount", 0.0),
            total_amount: num_field(&payload, "total_amount", 0.0),
            invoice_id: payload.get("invoice_id").cloned().unwrap_or(Json::Null),
            recipient_nif: str_field(&payload, "recipient_nif"),
            recipient_name: str_field(&payload, "recipient_name"),
            // Sustitución (F3): el caller manual puede pasarlos; normalmente vacíos.
            substitutes_number: str_field(&payload, "substitutes_number"),
            substitutes_date: str_field(&payload, "substitutes_date"),
            substitutes_nif: str_field(&payload, "substitutes_nif"),
        },
    )
    .await
}

// ── ingest_invoice: alta automática desde el módulo invoice ───────────────────

/// Listener de `invoice.created` / `invoice.rectified`: crea automáticamente un **RegistroAlta**
/// VeriFactu desde una factura emitida (o rectificativa). Modelo español: una factura no se
/// anula — la devolución es una **factura rectificativa** (TipoFactura R1–R5, importes negativos)
/// que también se declara como alta. (El `RegistroAnulación` es solo para errores de envío, vía
/// `create_record`.) El `record_type` es **siempre `alta`**; el `invoice_type` real (F1–F3 / R1–R5)
/// se toma de la factura.
///
/// El payload del evento solo trae el id de la factura; el **número oficial** (`PREFIX-YYYY-NNNNNN`)
/// se calcula en SQL al insertar la factura y no viaja en el evento WASM `invoice.created`, así que
/// se resuelve con una lectura acotada por id de `invoice_invoice` (excepción documentada para el
/// plugin nativo first-party; `verifactu depends_on invoice`). Idempotente: si la factura no existe
/// devuelve vacío, y el índice único `uq_verifactu_record` evita duplicar el registro en reentregas.
async fn ingest_invoice(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;

    // El id de factura llega como `invoice_id` (invoice.created) o `new_id` (invoice.rectified).
    let invoice_id = {
        let candidates = [
            str_field(&payload, "invoice_id"),
            str_field(&payload, "new_id"),
            str_field(&payload, "id"),
        ];
        candidates
            .into_iter()
            .find(|s| !s.is_empty())
            .unwrap_or_default()
    };
    if invoice_id.is_empty() {
        return Ok(Output::new()); // nada que ingerir
    }

    // Lectura acotada por id de la factura (snapshot fiscal: número oficial + importes). El
    // LEFT JOIN a sí misma por `substitutes_invoice_id` trae, EN LA MISMA lectura (respeta la
    // "única lectura acotada" de ADR-0058), los datos de la F2 sustituida cuando esta factura es
    // una F3 — para el bloque XML FacturasSustituidas. NULL/'' si no es sustitución.
    let rows = host
        .read(
            "SELECT i.invoice_type, i.number, i.issue_date, i.issuer_nif, i.issuer_name, \
             i.customer_tax_id, i.customer_name, i.description, \
             i.base_amount, i.tax_amount, i.total_amount, i.tax_breakdown, \
             COALESCE(sub.number, '') AS substitutes_number, \
             COALESCE(sub.issue_date, '') AS substitutes_date, \
             COALESCE(sub.issuer_nif, '') AS substitutes_nif \
             FROM invoice_invoice i \
             LEFT JOIN invoice_invoice sub \
               ON sub.id = i.substitutes_invoice_id AND sub.hub_id = i.hub_id AND sub.is_deleted = 0 \
             WHERE i.id = :invoice_id AND i.hub_id = :hub_id AND i.is_deleted = 0 LIMIT 1",
            &params(json!({ "invoice_id": invoice_id, "hub_id": ctx.hub_id })),
        )
        .await?;
    let inv = match rows.into_iter().next() {
        Some(r) => r,
        None => return Ok(Output::new()), // factura inexistente/borrada → no-op idempotente
    };

    // NIF del emisor (obligado tributario): viene de la factura, que a su vez lo toma de la
    // identidad fiscal GLOBAL del hub (hub_settings, vía _insert_invoice). La AEAT lo exige no
    // vacío (es el ancla de la cadena de hash) y el resto del módulo lo rechaza así (create_record).
    // Antes este punto devolvía OK/0-operaciones en silencio (verifactu#109): la factura→VeriFactu
    // aparentaba éxito y no generaba registro, hash ni cola fiscal — falsa sensación de cumplimiento.
    // Ahora rechaza con un error claro para que el operario vea que falta configurar la identidad
    // fiscal global del hub.
    let issuer_nif = str_field(&inv, "issuer_nif");
    if issuer_nif.is_empty() {
        return Err(VerifactuError::Payload(
            "missing_issuer_nif: falta el NIF del emisor (identidad fiscal global del hub sin configurar); \
             no se puede encadenar el registro VeriFactu".into(),
        )
        .into());
    }

    let invoice_type = {
        let t = str_field(&inv, "invoice_type");
        if INVOICE_TYPES.contains(&t.as_str()) {
            t
        } else {
            "F1".to_string()
        }
    };

    // DescripcionOperacion: la AEAT la exige NO vacía (rechaza con código 1100). Usa la descripción
    // de la factura; si está vacía, un fallback genérico con el nº de factura.
    let invoice_number = str_field(&inv, "number");
    let description = {
        let d = str_field(&inv, "description");
        if d.trim().is_empty() {
            format!("Venta {invoice_number}")
        } else {
            d
        }
    };

    build_record_output(
        host,
        &ctx,
        RecordInput {
            record_type: "alta".to_string(),
            issuer_nif,
            issuer_name: str_field(&inv, "issuer_name"),
            invoice_number: invoice_number.clone(),
            invoice_date: str_field(&inv, "issue_date"),
            invoice_type,
            description,
            // El módulo invoice guarda importes en CÉNTIMOS (ADR-0007), igual que `create_record`;
            // `build_record_output` espera céntimos y divide /100 al formatear para la AEAT/QR.
            // NO convertir aquí (el `* 100.0` previo declaraba importes ×100 a la AEAT — QA 2026-06-25).
            base_amount: num_field(&inv, "base_amount", 0.0),
            // Tipo EFECTIVO de la factura. Es la columna de la fila y el fallback de facturas sin
            // desglose; el XML ya NO lo usa en factura mixta (emite una línea por tipo real).
            tax_rate: derive_tax_rate(
                &str_field(&inv, "tax_breakdown"),
                num_field(&inv, "base_amount", 0.0),
                num_field(&inv, "tax_amount", 0.0),
            ),
            // El desglose real viaja íntegro hasta el XML: es lo que la AEAT tiene que ver.
            tax_breakdown: str_field(&inv, "tax_breakdown"),
            tax_amount: num_field(&inv, "tax_amount", 0.0),
            total_amount: num_field(&inv, "total_amount", 0.0),
            invoice_id: Json::String(invoice_id),
            // Destinatario para el bloque XML Destinatarios (F1/F3/R1-R4). Tiquets (F2) sin cliente
            // → vacío → sin Destinatarios. Evita el error AEAT 1189 en facturas completas.
            recipient_nif: str_field(&inv, "customer_tax_id"),
            recipient_name: str_field(&inv, "customer_name"),
            // F3 → FacturasSustituidas: datos de la F2 sustituida (del LEFT JOIN). Vacíos si no es F3.
            substitutes_number: str_field(&inv, "substitutes_number"),
            substitutes_date: str_field(&inv, "substitutes_date"),
            substitutes_nif: str_field(&inv, "substitutes_nif"),
        },
    )
    .await
}

/// Campos fiscales ya resueltos para emitir un registro (compartido por `create_record` y
/// `ingest_invoice`). Importes en **céntimos** (ADR-0007); la huella/XML/QR convierten a euros.
struct RecordInput {
    record_type: String,
    issuer_nif: String,
    issuer_name: String,
    invoice_number: String,
    invoice_date: String,
    invoice_type: String,
    description: String,
    base_amount: f64,
    /// Tipo EFECTIVO (`cuota/base`). Ya NO es lo que se declara a la AEAT en factura mixta: el XML
    /// emite una línea `DetalleDesglose` por tipo real (ver `aeat::desglose`). Se conserva como
    /// columna de la fila —consultas, listados— y como fallback de facturas sin desglose.
    tax_rate: f64,
    /// Desglose REAL por tipo, tal cual lo escribe el módulo `invoice`:
    /// `{"21.00":{"base":1000,"tax":210},"10.00":{…}}` en céntimos. Es lo que la AEAT necesita para
    /// que un ticket de bar (caña 21% + tapa 10%) declare sus DOS tipos y no uno inventado.
    tax_breakdown: String,
    tax_amount: f64,
    total_amount: f64,
    invoice_id: Json,
    /// Destinatario (cliente) — obligatorio en el XML para F1/F3/R1-R4 (error AEAT 1189). Vacío
    /// para tiquets simplificados (F2). Se usa al construir el SOAP en la transmisión inline.
    recipient_nif: String,
    recipient_name: String,
    /// Factura SUSTITUIDA (F3 → F2, ADR-0140): nº+serie, fecha de expedición y NIF del emisor de la
    /// simplificada que esta factura completa sustituye. Alimentan el bloque XML `FacturasSustituidas`
    /// (XSD IDFacturaARType). Vacíos si el registro no es una sustitución (todo lo que no sea F3).
    substitutes_number: String,
    substitutes_date: String,
    substitutes_nif: String,
}

/// Núcleo de encadenado: lee el ancla `(hub_id, issuer_nif)`, calcula la huella SHA-256 (formatos
/// AEAT exactos) + `qr_url`, y devuelve las intenciones INSERT record(pending) + event + (si
/// `auto_transmit` está off) cola de contingencia.
///
/// Atomicidad de la secuencia: el ancla se lee antes de calcular, y el índice único
/// `uq_verifactu_record_hub_seq (hub_id, issuer_nif, sequence_number)` cierra la ventana TOCTOU —
/// si dos creates compiten, el segundo INSERT viola el índice y SU transacción entera revierte
/// (sin fork de cadena). En SQLite además las escrituras se serializan.
async fn build_record_output(host: &dyn NativeHost, ctx: &Ctx, r: RecordInput) -> Result<Output> {
    // Ancla de cadena: última fila por (hub_id, issuer_nif).
    let anchor = host
        .read(
            "SELECT record_hash, sequence_number FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif AND is_deleted = 0 \
             ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({ "hub_id": ctx.hub_id, "issuer_nif": r.issuer_nif })),
        )
        .await?;
    let (previous_hash, sequence_number, is_first) = match anchor.first() {
        Some(row) => (
            str_field(row, "record_hash"),
            int_field(row, "sequence_number", 0) + 1,
            false,
        ),
        None => (String::new(), 1, true),
    };

    // Huella (formatos AEAT exactos — chain.rs) + QR.
    // ⚠️ ADR-0007: los importes llegan/persisten en CÉNTIMOS (INTEGER), pero la huella y el
    // XML/QR de la AEAT exigen EUROS con 2 decimales. Se convierte céntimos→euros SOLO en el
    // límite de formateo fiscal; las columnas (`base/tax/total_amount`) siguen en céntimos.
    let generation_timestamp = ctx.now.clone();
    let tax_amount_eur = r.tax_amount / 100.0;
    let total_amount_eur = r.total_amount / 100.0;
    let record_hash = if r.record_type == "alta" {
        chain::alta_hash(
            &r.issuer_nif,
            &r.invoice_number,
            &r.invoice_date,
            &r.invoice_type,
            tax_amount_eur,
            total_amount_eur,
            &previous_hash,
            &generation_timestamp,
        )
    } else {
        chain::anulacion_hash(
            &r.issuer_nif,
            &r.invoice_number,
            &r.invoice_date,
            &previous_hash,
            &generation_timestamp,
        )
    };
    let config = read_config(host, &ctx.hub_id).await?;
    // El host del QR depende del entorno (testing vs producción) → leer la config antes de generarlo.
    let environment = config
        .as_ref()
        .map(environment_of)
        .unwrap_or_else(|| "testing".to_string());
    let qr_url = chain::qr_url(
        &r.issuer_nif,
        &r.invoice_number,
        &r.invoice_date,
        total_amount_eur,
        &environment,
    );
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
                "record_type": r.record_type,
                "sequence_number": sequence_number,
                "invoice_id": r.invoice_id,
                "issuer_nif": r.issuer_nif,
                "issuer_name": r.issuer_name,
                "invoice_number": r.invoice_number,
                "invoice_date": r.invoice_date,
                "invoice_type": r.invoice_type,
                "description": r.description,
                "base_amount": r.base_amount,
                "tax_rate": r.tax_rate,
                "tax_breakdown": r.tax_breakdown,
                "tax_amount": r.tax_amount,
                "total_amount": r.total_amount,
                "previous_hash": previous_hash,
                "record_hash": record_hash,
                "is_first_record": if is_first { 1 } else { 0 },
                "generation_timestamp": generation_timestamp,
                "qr_url": qr_url,
                // F3 → FacturasSustituidas (ADR-0140): snapshot de la F2 sustituida para reconstruir
                // el XML en contingencia/reintento sin releer la factura. Vacíos si no es sustitución.
                "substitutes_number": r.substitutes_number,
                "substitutes_date": r.substitutes_date,
                "substitutes_nif": r.substitutes_nif,
            }),
        ))
        .with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ids[1],
                "record_id": record_id,
                "event_type": "record_created",
                "severity": "info",
                "message": format!("Registro {} #{sequence_number} de {} creado", r.record_type, r.invoice_number),
                "details": json!({
                    "sequence_number": sequence_number,
                    "record_hash": record_hash,
                    "is_first_record": is_first,
                }).to_string(),
                "timestamp": ctx.now,
            }),
        ));

    if !auto_transmit {
        // Sin auto-transmisión: el registro queda encolado en contingencia para envío diferido.
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
    } else if let Some(cfg) = config.as_ref() {
        // Auto-transmisión a la AEAT al emitir (como el Cloud). Reutiliza `transmit_one`, que aplica
        // el resultado al registro (accepted/rejected + CSV) y, ante fallo de red, lo encola en
        // contingencia con backoff. Sin certificado configurado → se deja `pending` (envío manual
        // posterior). Las intenciones se aplican DESPUÉS del INSERT del registro (orden del Output).
        if has_certificate(cfg) {
            let record_json = json!({
                "id": record_id,
                "record_type": r.record_type,
                "sequence_number": sequence_number,
                "issuer_nif": r.issuer_nif,
                "issuer_name": r.issuer_name,
                "invoice_number": r.invoice_number,
                "invoice_date": r.invoice_date,
                "invoice_type": r.invoice_type,
                "description": r.description,
                "tax_rate": r.tax_rate,
                "tax_breakdown": r.tax_breakdown,
                "base_amount": r.base_amount,
                "tax_amount": r.tax_amount,
                "total_amount": r.total_amount,
                "record_hash": record_hash,
                "previous_hash": previous_hash,
                "is_first_record": if is_first { 1 } else { 0 },
                "generation_timestamp": generation_timestamp,
                "recipient_nif": r.recipient_nif,
                "recipient_name": r.recipient_name,
                "substitutes_number": r.substitutes_number,
                "substitutes_date": r.substitutes_date,
                "substitutes_nif": r.substitutes_nif,
            });
            if let Ok((ops, _success)) =
                transmit_one(host, ctx, &record_json, cfg, &ids[3], &ids[4]).await
            {
                for o in ops {
                    output = output.with_operation(o);
                }
            }
        }
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
        return Err(RuntimeError::Native(
            "el registro ya fue aceptado por la AEAT".into(),
        ));
    }

    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;
    // Gate: sin certificado (ni core ni legacy) no se puede transmitir.
    if !has_certificate(&config) {
        return Err(VerifactuError::Certificate(
            "certificado PKCS#12 no configurado (sube el .p12 en Ajustes → Negocio)".into(),
        )
        .into());
    }

    let (ops, _success) = transmit_one(
        host,
        &ctx,
        &record,
        &config,
        &ctx.new_ids[0],
        &ctx.new_ids[1],
    )
    .await?;
    let mut out = Output::new();
    for o in ops {
        out = out.with_operation(o);
    }
    // El evento `verifactu.record.transmitted` lo emite el `emit` declarado del command.
    Ok(out)
}

/// Núcleo de transmisión de **un** registro: lee el registro anterior (encadenamiento), construye
/// el XML SOAP, firma con el PKCS#12 y hace POST TLS-mutua a la AEAT. Devuelve las intenciones
/// (UPDATE registro + evento + resolver/encolar contingencia) y `true` si la AEAT lo aceptó.
/// Reutilizado por `transmit_record` (uno) y `process_contingency_queue` (lote).
#[allow(clippy::too_many_arguments)]
async fn transmit_one(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record: &Json,
    config: &Json,
    event_id: &str,
    queue_id: &str,
) -> Result<(Vec<Operation>, bool)> {
    let record_id = str_field(record, "id");
    let is_first = int_field(record, "is_first_record", 0) != 0;
    let prev = if is_first {
        None
    } else {
        host.read(
            "SELECT issuer_nif, invoice_number, invoice_date, record_hash FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif AND sequence_number = :prev_seq \
             AND is_deleted = 0 LIMIT 1",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": str_field(record, "issuer_nif"),
                "prev_seq": int_field(record, "sequence_number", 1) - 1,
            })),
        )
        .await?
        .into_iter()
        .next()
    };

    // En un reintento se usa EXACTAMENTE el XML del intento anterior (si ya quedó en BD), no se
    // regenera con una configuración que podría haber cambiado mientras la AEAT estaba caída.
    let xml = record
        .get("xml_content")
        .and_then(Json::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToString::to_string)
        .unwrap_or_else(|| aeat::build_soap(record, config, prev.as_ref(), &ctx.hub_id));
    // Archivo duradero ANTES de tocar la red. Si el backend Local/S3 no confirma la escritura, no
    // se envía: nunca aceptamos una transmisión fiscal sin conservar su XML para auditoría/reenvío.
    let xml_storage_path = archive_transmission_xml(host, &record_id, &xml).await?;
    let environment = environment_of(config);
    // Identity mTLS: cert del core (opaca, bytes en el core) o legacy. Ver `build_identity`.
    let identity = build_identity(host, &ctx.hub_id, config).await?;

    match aeat::post_soap(aeat::endpoint(&environment), identity, &xml).await {
        Ok(body) => {
            let resp = aeat::parse_response(&body);
            let status = match resp.estado_registro.as_str() {
                "Correcto" | "AceptadoConErrores" => "accepted",
                "Incorrecto" => "rejected",
                _ if resp.estado_envio == "Correcto" => "accepted",
                _ => "error",
            };
            let success = status == "accepted";
            let (code, message) = if success {
                (resp.estado_registro.clone(), resp.estado_envio.clone())
            } else {
                (resp.codigo_error.clone(), resp.descripcion_error.clone())
            };
            let event_type = if success {
                "transmission_success"
            } else {
                "transmission_failure"
            };
            let severity = if success { "info" } else { "error" };
            let mut ops = vec![
                apply_transmission(
                    &record_id,
                    status,
                    &code,
                    &message,
                    &resp.csv,
                    &xml,
                    &xml_storage_path,
                    0,
                ),
                op(
                    "verifactu._insert_event",
                    json!({
                        "event_id": event_id,
                        "record_id": record_id.clone(),
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
                ),
            ];
            if success {
                // Si el registro estaba en la cola de contingencia, sale de ella.
                ops.push(op(
                    "verifactu._resolve_contingency",
                    json!({ "record_id": record_id }),
                ));
            }
            Ok((ops, success))
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
            let attempts = queue
                .first()
                .map(|q| int_field(q, "attempts", 0))
                .unwrap_or(0)
                + 1;
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
            let ops = vec![
                apply_transmission(
                    &record_id,
                    "error",
                    "",
                    &reason,
                    "",
                    &xml,
                    &xml_storage_path,
                    1,
                ),
                op(
                    "verifactu._insert_event",
                    json!({
                        "event_id": event_id,
                        "record_id": record_id.clone(),
                        "event_type": "transmission_failure",
                        "severity": "error",
                        "message": format!("Fallo de transmisión AEAT ({environment}); reintento en {backoff_minutes} min"),
                        "details": json!({ "error": reason.clone(), "attempts": attempts }).to_string(),
                        "timestamp": ctx.now,
                    }),
                ),
                op(
                    "verifactu._enqueue_contingency",
                    json!({
                        "queue_id": queue_id,
                        "record_id": record_id,
                        "priority": 2,
                        "attempts": attempts,
                        "last_attempt_at": ctx.now,
                        "last_error": reason,
                        "next_attempt_at": next_attempt_at,
                        "queue_status": "retrying",
                    }),
                ),
            ];
            Ok((ops, false))
        }
    }
}

/// Guarda el XML con una clave estable por registro. Los reintentos sobrescriben atómicamente el
/// mismo objeto con el mismo contenido; el estado/contador de intentos vive en la BD.
async fn archive_transmission_xml(
    host: &dyn NativeHost,
    record_id: &str,
    xml: &str,
) -> Result<String> {
    if record_id.is_empty()
        || !record_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err(RuntimeError::Storage(
            "id de registro no válido para archivar XML".to_string(),
        ));
    }
    host.write_static_file(
        &format!("xml/{record_id}.xml"),
        xml.as_bytes(),
        "application/xml",
    )
    .await
}

/// Intención UPDATE del registro tras un intento de transmisión.
fn apply_transmission(
    record_id: &str,
    status: &str,
    code: &str,
    message: &str,
    csv: &str,
    xml: &str,
    xml_storage_path: &str,
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
            "xml_storage_path": xml_storage_path,
            "retry_increment": retry_increment,
        }),
    )
}

// ── process_contingency_queue (issue verifactu#7) ─────────────────────────────

/// Procesa por lotes la cola de contingencia (tarea programada cada 5 min o trigger manual):
/// lee las entradas elegibles (`pending`/`retrying` con `next_attempt_at <= now`) por prioridad y
/// antigüedad, y reintenta la transmisión de cada una vía [`transmit_one`]. Éxito → sale de la
/// cola; fallo → backoff. Devuelve un evento resumen `{successful, failed}`.
async fn process_contingency_queue(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let limit = int_field(&payload, "limit", 100).clamp(1, 500);

    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;
    // Gate: sin certificado no hay nada que transmitir; deja la cola como está.
    if !has_certificate(&config) {
        return Ok(Output::new());
    }

    let eligible = host
        .read(
            "SELECT record_id FROM verifactu_contingencyqueue \
             WHERE hub_id = :hub_id AND is_deleted = 0 AND status IN ('pending','retrying') \
             AND (next_attempt_at IS NULL OR next_attempt_at <= :now) \
             ORDER BY priority ASC, queued_at ASC LIMIT :limit",
            &params(json!({ "hub_id": ctx.hub_id, "now": ctx.now, "limit": limit })),
        )
        .await?;

    // 2 ids por registro (evento + cola); reservamos 1 para el evento resumen.
    let max_records = (ctx.new_ids.len().saturating_sub(1)) / 2;
    let mut out = Output::new();
    let mut id_idx = 0usize;
    let (mut successful, mut failed) = (0i64, 0i64);

    for q in eligible.iter().take(max_records) {
        let rid = str_field(q, "record_id");
        let rec = host
            .read(
                "SELECT * FROM verifactu_record WHERE id = :rid AND hub_id = :hub_id AND is_deleted = 0 LIMIT 1",
                &params(json!({ "rid": rid, "hub_id": ctx.hub_id })),
            )
            .await?
            .into_iter()
            .next();
        let rec = match rec {
            Some(r) => r,
            None => continue, // registro borrado: ignorar la entrada huérfana
        };
        if str_field(&rec, "status") == "accepted" {
            // Ya aceptado: limpiar la entrada de cola obsoleta.
            out = out.with_operation(op(
                "verifactu._resolve_contingency",
                json!({ "record_id": rid }),
            ));
            continue;
        }
        let event_id = ctx.new_ids[id_idx].clone();
        let queue_id = ctx.new_ids[id_idx + 1].clone();
        id_idx += 2;
        let (ops, success) = transmit_one(host, &ctx, &rec, &config, &event_id, &queue_id).await?;
        for o in ops {
            out = out.with_operation(o);
        }
        if success {
            successful += 1;
        } else {
            failed += 1;
        }
    }

    let summary_id = ctx.new_ids.get(id_idx).cloned().unwrap_or_default();
    out = out.with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": summary_id,
            "record_id": Json::Null,
            "event_type": "contingency_processed",
            "severity": if failed > 0 { "warning" } else { "info" },
            "message": format!("Cola de contingencia procesada: {successful} enviados, {failed} con error"),
            "details": json!({ "successful": successful, "failed": failed }).to_string(),
            "timestamp": ctx.now,
        }),
    ));
    Ok(out)
}

// ── run_diagnostics: prueba en vivo (cert + huella + QR + envío AEAT) ──────────

/// Prueba de extremo a extremo SIN tocar la cadena: verifica que el certificado carga con su
/// contraseña, genera una huella + QR de un registro de **muestra** y (si el cert es válido) hace
/// un envío de prueba a la AEAT, devolviendo la respuesta. Persiste SOLO un evento `diagnostic`
/// (no inserta ningún `verifactu_record`); la UI lo lee con `verifactu.diagnostics.last`.
async fn run_diagnostics(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;

    // OBLIGADO tributario (emisor) = el NIF que la AEAT valida y que representa el certificado.
    // NO es el productor del software (software_*). Para la prueba viene de la config (issuer_*).
    let issuer_nif = str_field(&config, "issuer_nif");
    let issuer_name = {
        let n = str_field(&config, "issuer_name");
        if n.is_empty() {
            issuer_nif.clone()
        } else {
            n
        }
    };
    let environment = environment_of(&config);
    let gen_ts = chain::format_timestamp(&ctx.now);
    let sample_date: String = ctx.now.chars().take(10).collect();
    let sample_number = format!("PRUEBA-{sample_date}");

    // Tipo de factura de la prueba (lo elige la UI). Default **F2** = tiquet simplificado, que NO
    // requiere destinatario. F1/F3/R1-R4 SÍ exigen el bloque Destinatarios (error AEAT 1189): para
    // esos tipos se usa un cliente de muestra si la UI no manda uno.
    let invoice_type = {
        let t = str_field(&payload, "invoice_type");
        if INVOICE_TYPES.contains(&t.as_str()) {
            t
        } else {
            "F2".to_string()
        }
    };
    let needs_recipient = matches!(
        invoice_type.as_str(),
        "F1" | "F3" | "R1" | "R2" | "R3" | "R4"
    );
    let recipient_nif = {
        let n = str_field(&payload, "recipient_nif");
        if !n.is_empty() {
            n
        } else if needs_recipient {
            "12345678Z".to_string()
        } else {
            String::new()
        }
    };
    let recipient_name = {
        let n = str_field(&payload, "recipient_name");
        if !n.is_empty() {
            n
        } else if needs_recipient {
            "Cliente de Prueba".to_string()
        } else {
            String::new()
        }
    };

    // Importes de muestra (céntimos): base 100,00 € · IVA 21% · total 121,00 €.
    let huella = chain::alta_hash(
        &issuer_nif,
        &sample_number,
        &sample_date,
        &invoice_type,
        21.0,
        121.0,
        "",
        &gen_ts,
    );
    let qr_url = chain::qr_url(
        &issuer_nif,
        &sample_number,
        &sample_date,
        121.0,
        &environment,
    );

    let mut cert_ok = false;
    let cert_message;
    let mut aeat = Json::Null;

    // Identity mTLS vía `build_identity`: cert del core (opaca, la cripto vive en el core) o
    // legacy. Para el cert del core NO se cargan los bytes del `.p12` en el módulo (ADR-0079).
    match build_identity(host, &ctx.hub_id, &config).await {
        Ok(identity) => {
            cert_ok = true;
            cert_message = "Certificado cargado correctamente.".into();
            if issuer_nif.is_empty() {
                // Sin NIF del obligado no se puede enviar (la AEAT lo rechazaría por formato).
                aeat = json!({ "ok": false, "error": "Configura el NIF del obligado tributario (emisor) antes de enviar la prueba." });
            } else {
                // Envío de prueba real al endpoint AEAT del entorno configurado.
                let sample = json!({
                    "record_type": "alta",
                    "issuer_nif": issuer_nif,
                    "issuer_name": issuer_name,
                    "invoice_number": sample_number,
                    "invoice_date": sample_date,
                    "invoice_type": invoice_type,
                    "description": "Factura de PRUEBA (diagnóstico VeriFactu)",
                    "tax_rate": 21,
                    "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
                    "base_amount": 10000,
                    "tax_amount": 2100,
                    "total_amount": 12100,
                    "recipient_nif": recipient_nif,
                    "recipient_name": recipient_name,
                    "record_hash": huella,
                    "is_first_record": 1,
                    "generation_timestamp": gen_ts,
                });
                let xml = aeat::build_soap(&sample, &config, None, &ctx.hub_id);
                match aeat::post_soap(aeat::endpoint(&environment), identity, &xml).await {
                    Ok(body) => {
                        let r = aeat::parse_response(&body);
                        let accepted = r.estado_registro == "Correcto"
                            || r.estado_registro == "AceptadoConErrores"
                            || r.estado_envio == "Correcto";
                        aeat = json!({
                            "ok": accepted,
                            "estado_envio": r.estado_envio,
                            "estado_registro": r.estado_registro,
                            "csv": r.csv,
                            "codigo_error": r.codigo_error,
                            "descripcion_error": r.descripcion_error,
                        });
                    }
                    Err(e) => {
                        aeat = json!({ "ok": false, "error": e.to_string() });
                    }
                }
            }
        }
        Err(e) => {
            cert_message = format!("El certificado no carga o no está configurado: {e}");
        }
    }

    let details = json!({
        "cert_ok": cert_ok,
        "cert_message": cert_message,
        "issuer_nif": issuer_nif,
        "invoice_type": invoice_type,
        "recipient_nif": recipient_nif,
        "environment": environment,
        "sample_number": sample_number,
        "huella": huella,
        "qr_url": qr_url,
        "aeat": aeat,
    });
    Ok(Output::new().with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": ctx.new_ids.first().cloned().unwrap_or_default(),
            "record_id": Json::Null,
            "event_type": "diagnostic",
            "severity": if cert_ok { "info" } else { "warning" },
            "message": if cert_ok {
                format!("Prueba VeriFactu ejecutada ({environment})")
            } else {
                "Prueba VeriFactu: certificado no válido".to_string()
            },
            "details": details.to_string(),
            "timestamp": ctx.now,
        }),
    )))
}

// ── helpers de recuperación / consulta ────────────────────────────────────────

/// NIF del emisor a usar: el del payload o, si falta, `software_nif` de la config.
fn resolve_nif(payload: &Json, config: Option<&Json>) -> String {
    let n = str_field(payload, "issuer_nif");
    if !n.is_empty() {
        return n;
    }
    // El NIF del OBLIGADO (issuer_nif); software_nif es el productor, solo fallback legacy.
    match config {
        Some(c) => {
            let iss = str_field(c, "issuer_nif");
            if iss.is_empty() {
                str_field(c, "software_nif")
            } else {
                iss
            }
        }
        None => String::new(),
    }
}

/// Entorno AEAT efectivo (`testing` por defecto).
fn environment_of(config: &Json) -> String {
    let e = str_field(config, "environment");
    if e.is_empty() {
        "testing".to_string()
    } else {
        e
    }
}

/// (Ejercicio=YYYY, Periodo=MM) del `now` RFC3339 para el filtro de consulta AEAT.
fn year_month(now: &str) -> (String, String) {
    match chrono::DateTime::parse_from_rfc3339(now) {
        Ok(dt) => (dt.format("%Y").to_string(), dt.format("%m").to_string()),
        Err(_) => (String::new(), String::new()),
    }
}

/// AEAT devuelve fechas en `DD-MM-YYYY`; la BD usa ISO `YYYY-MM-DD`.
fn iso_date(aeat_date: &str) -> String {
    let p: Vec<&str> = aeat_date.split('-').collect();
    if p.len() == 3 && p[0].len() == 2 {
        format!("{}-{}-{}", p[2], p[1], p[0])
    } else {
        aeat_date.to_string()
    }
}

/// Primeros 8 caracteres de una huella (para mensajes).
fn short(hash: &str) -> String {
    hash.chars().take(8).collect()
}

/// Siguiente número de secuencia interno para `(hub_id, issuer_nif)` = max + 1.
async fn next_sequence(host: &dyn NativeHost, hub_id: &str, issuer_nif: &str) -> Result<i64> {
    let rows = host
        .read(
            "SELECT sequence_number FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif AND is_deleted = 0 \
             ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({ "hub_id": hub_id, "issuer_nif": issuer_nif })),
        )
        .await?;
    Ok(rows
        .first()
        .map(|r| int_field(r, "sequence_number", 0))
        .unwrap_or(0)
        + 1)
}

/// Consulta a la AEAT (TLS mutua con el cert de la config) los registros del emisor en el
/// periodo actual y los parsea. Red real — sin cert/red devuelve error (no silencioso).
async fn run_consult(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
    issuer_nif: &str,
    now: &str,
) -> Result<Vec<aeat::ConsultRecord>> {
    // Identity mTLS vía `build_identity`: cert del core (opaca) o legacy. Ver ADR-0079.
    let identity = build_identity(host, hub_id, config).await?;
    let issuer_name = str_field(config, "software_name");
    let (ejercicio, periodo) = year_month(now);
    let xml = aeat::build_consult_soap(issuer_nif, &issuer_name, &ejercicio, &periodo);
    let body = aeat::post_soap(
        aeat::consult_endpoint(&environment_of(config)),
        identity,
        &xml,
    )
    .await?;
    Ok(aeat::parse_consult_response(&body))
}

/// Intenciones para volcar el snapshot de consulta AEAT: limpia el anterior de este emisor +
/// inserta hasta 10 registros (usa `ctx.new_ids[0..N]`). Devuelve (ops, nº insertados).
fn aeat_snapshot_ops(
    ctx: &Ctx,
    issuer_nif: &str,
    records: &[aeat::ConsultRecord],
) -> (Vec<Operation>, usize) {
    let mut ops = vec![op(
        "verifactu._clear_aeat_records",
        json!({ "issuer_nif": issuer_nif.to_string() }),
    )];
    let limit = records.len().min(10);
    for (i, r) in records.iter().take(limit).enumerate() {
        let nif_val = if r.issuer_nif.is_empty() {
            issuer_nif.to_string()
        } else {
            r.issuer_nif.clone()
        };
        ops.push(op(
            "verifactu._insert_aeat_record",
            json!({
                "rec_id": ctx.new_ids.get(i).cloned().unwrap_or_default(),
                "issuer_nif": nif_val,
                "invoice_number": r.invoice_number.clone(),
                "invoice_date": iso_date(&r.invoice_date),
                "record_type": "alta",
                "record_hash": chain::normalize_hash(&r.record_hash),
                "aeat_csv": r.csv.clone(),
                "estado": r.estado.clone(),
                "query_timestamp": ctx.now.clone(),
            }),
        ));
    }
    (ops, limit)
}

// ── validate_chain (issue verifactu#4) ────────────────────────────────────────

/// Relee la cadena de `(hub_id, issuer_nif)` ordenada por secuencia, recomputa cada huella y
/// verifica el encadenamiento (`previous_hash` == huella anterior). Las filas `recovery` son
/// anclas de confianza (no se recomputan; su huella es el enlace para la siguiente). El
/// resultado se persiste como `verifactu_event` (`chain_validated`/`chain_error`) que la UI lee.
async fn validate_chain(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?;
    let issuer_nif = resolve_nif(&payload, config.as_ref());
    if issuer_nif.is_empty() {
        return Err(
            VerifactuError::Payload("falta issuer_nif (o software_nif en config)".into()).into(),
        );
    }

    let rows = host
        .read(
            "SELECT id, record_type, sequence_number, issuer_nif, invoice_number, invoice_date, \
             invoice_type, tax_amount, total_amount, previous_hash, record_hash, is_first_record, \
             generation_timestamp FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif AND is_deleted = 0 \
             ORDER BY sequence_number ASC",
            &params(json!({ "hub_id": ctx.hub_id, "issuer_nif": issuer_nif })),
        )
        .await?;

    let mut prev_hash = String::new();
    let mut first_invalid: Option<(i64, String)> = None;
    for (idx, r) in rows.iter().enumerate() {
        let rtype = str_field(r, "record_type");
        let stored = str_field(r, "record_hash");
        if rtype == "recovery" {
            // Ancla de confianza: no se recomputa; su huella enlaza con la siguiente.
            prev_hash = stored;
            continue;
        }
        let rec_prev = str_field(r, "previous_hash");
        let is_first = int_field(r, "is_first_record", 0) != 0;
        let link_ok = if is_first && prev_hash.is_empty() {
            rec_prev.is_empty()
        } else {
            rec_prev == prev_hash
        };
        let computed = if rtype == "anulacion" {
            chain::anulacion_hash(
                &str_field(r, "issuer_nif"),
                &str_field(r, "invoice_number"),
                &str_field(r, "invoice_date"),
                &rec_prev,
                &str_field(r, "generation_timestamp"),
            )
        } else {
            chain::alta_hash(
                &str_field(r, "issuer_nif"),
                &str_field(r, "invoice_number"),
                &str_field(r, "invoice_date"),
                &str_field(r, "invoice_type"),
                num_field(r, "tax_amount", 0.0) / 100.0,
                num_field(r, "total_amount", 0.0) / 100.0,
                &rec_prev,
                &str_field(r, "generation_timestamp"),
            )
        };
        if (computed != stored || !link_ok) && first_invalid.is_none() {
            first_invalid = Some((
                int_field(r, "sequence_number", idx as i64),
                str_field(r, "id"),
            ));
        }
        prev_hash = stored;
    }

    let valid = first_invalid.is_none();
    let total = rows.len();
    let (severity, event_type) = if valid {
        ("info", "chain_validated")
    } else {
        ("error", "chain_error")
    };
    let message = if valid {
        format!("Cadena íntegra: {total} registro(s) verificados ({issuer_nif})")
    } else {
        let seq = first_invalid.as_ref().map(|x| x.0).unwrap_or(0);
        format!("Cadena ROTA en la secuencia {seq} ({issuer_nif})")
    };
    let details = json!({
        "valid": valid,
        "total": total,
        "issuer_nif": issuer_nif,
        "first_invalid_seq": first_invalid.as_ref().map(|x| x.0),
        "first_invalid_id": first_invalid.as_ref().map(|x| x.1.clone()),
    });
    let record_id = first_invalid
        .as_ref()
        .map(|x| Json::String(x.1.clone()))
        .unwrap_or(Json::Null);
    Ok(Output::new().with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": ctx.new_ids.first().cloned().unwrap_or_default(),
            "record_id": record_id,
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "details": details.to_string(),
            "timestamp": ctx.now,
        }),
    )))
}

// ── query_aeat_records (issue verifactu#3) ────────────────────────────────────

/// Consulta a la AEAT los últimos registros del emisor y vuelca un snapshot en
/// `verifactu_aeat_record` (lo que la UI muestra como "últimos N de la Agencia Tributaria").
/// No toca la cadena local — solo trae lo que la AEAT tiene confirmado.
async fn query_aeat_records(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;
    let issuer_nif = resolve_nif(&payload, Some(&config));
    if issuer_nif.is_empty() {
        return Err(
            VerifactuError::Payload("falta issuer_nif (o software_nif en config)".into()).into(),
        );
    }
    let records = run_consult(host, &ctx.hub_id, &config, &issuer_nif, &ctx.now).await?;
    let (ops, limit) = aeat_snapshot_ops(&ctx, &issuer_nif, &records);
    let mut out = Output::new();
    for o in ops {
        out = out.with_operation(o);
    }
    out = out.with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": ctx.new_ids.get(limit).cloned().unwrap_or_default(),
            "record_id": Json::Null,
            "event_type": "aeat_queried",
            "severity": "info",
            "message": format!("Consulta AEAT: {limit} registro(s) recuperados para {issuer_nif}"),
            "details": json!({ "count": limit, "issuer_nif": issuer_nif }).to_string(),
            "timestamp": ctx.now,
        }),
    ));
    Ok(out)
}

// ── recuperación de cadena (WASM-TODO §9) ─────────────────────────────────────

/// Recupera la cadena consultando a la AEAT: vuelca el snapshot e inserta un **ancla de
/// recuperación** con la huella del registro más reciente confirmado, para que el siguiente
/// `create_record` encadene desde ahí. Operación sensible (admin) — emite `chain_recovered`.
async fn recover_from_aeat(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;
    let issuer_nif = resolve_nif(&payload, Some(&config));
    if issuer_nif.is_empty() {
        return Err(
            VerifactuError::Payload("falta issuer_nif (o software_nif en config)".into()).into(),
        );
    }
    let records = run_consult(host, &ctx.hub_id, &config, &issuer_nif, &ctx.now).await?;
    if records.is_empty() {
        return Err(RuntimeError::Native(
            "la AEAT no devolvió registros para este emisor/periodo; nada que recuperar".into(),
        ));
    }
    let (ops, limit) = aeat_snapshot_ops(&ctx, &issuer_nif, &records);
    // Ancla = registro más reciente devuelto (la lista viene best-effort; se asume el primero).
    let latest = &records[0];
    let seq = next_sequence(host, &ctx.hub_id, &issuer_nif).await?;
    let record_hash = chain::normalize_hash(&latest.record_hash);
    let anchor_id = ctx.new_ids.get(limit).cloned().unwrap_or_default();
    let invoice_number = if latest.invoice_number.is_empty() {
        format!("AEAT-{}", short(&record_hash))
    } else {
        latest.invoice_number.clone()
    };

    let mut out = Output::new();
    for o in ops {
        out = out.with_operation(o);
    }
    out = out
        .with_operation(op(
            "verifactu._insert_recovery",
            json!({
                "record_id": anchor_id.clone(),
                "sequence_number": seq,
                "issuer_nif": issuer_nif.clone(),
                "issuer_name": str_field(&config, "software_name"),
                "invoice_number": invoice_number,
                "invoice_date": iso_date(&latest.invoice_date),
                "description": "Ancla recuperada desde la AEAT (ConsultaFactuSistemaFacturacion)",
                "record_hash": record_hash.clone(),
                "aeat_csv": latest.csv.clone(),
            }),
        ))
        .with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ctx.new_ids.get(limit + 1).cloned().unwrap_or_default(),
                "record_id": anchor_id,
                "event_type": "chain_recovered",
                "severity": "warning",
                "message": format!("Cadena recuperada desde la AEAT para {issuer_nif}: huella {}…", short(&record_hash)),
                "details": json!({
                    "source": "aeat",
                    "record_hash": record_hash,
                    "sequence_number": seq,
                    "found": limit,
                }).to_string(),
                "timestamp": ctx.now,
            }),
        ));
    Ok(out)
}

/// Continúa la cadena a partir de una huella aportada manualmente (migración de otra app):
/// valida que sea 64-hex, calcula el siguiente número de secuencia e inserta el ancla de
/// recuperación. El siguiente `create_record` encadenará desde esta huella. Emite `chain_recovered`.
async fn recover_manual(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?;
    let issuer_nif = resolve_nif(&payload, config.as_ref());
    if issuer_nif.is_empty() {
        return Err(VerifactuError::Payload("falta issuer_nif".into()).into());
    }
    let raw_hash = str_field(&payload, "record_hash");
    if !chain::is_valid_hash(raw_hash.trim()) {
        return Err(VerifactuError::Payload(
            "record_hash debe ser 64 caracteres hexadecimales (SHA-256)".into(),
        )
        .into());
    }
    let record_hash = chain::normalize_hash(&raw_hash);
    let seq = next_sequence(host, &ctx.hub_id, &issuer_nif).await?;
    let invoice_number = {
        let n = str_field(&payload, "invoice_number");
        if n.is_empty() {
            format!("RECOVERY-{}", short(&record_hash))
        } else {
            n
        }
    };
    let invoice_date = {
        let d = str_field(&payload, "invoice_date");
        if d.is_empty() {
            ctx.now.chars().take(10).collect::<String>()
        } else {
            d
        }
    };
    let issuer_name = config
        .as_ref()
        .map(|c| str_field(c, "software_name"))
        .unwrap_or_default();
    let anchor_id = ctx.new_ids.first().cloned().unwrap_or_default();

    Ok(Output::new()
        .with_operation(op(
            "verifactu._insert_recovery",
            json!({
                "record_id": anchor_id.clone(),
                "sequence_number": seq,
                "issuer_nif": issuer_nif.clone(),
                "issuer_name": issuer_name,
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "description": "Ancla importada manualmente (migración de otra aplicación)",
                "record_hash": record_hash.clone(),
                "aeat_csv": "",
            }),
        ))
        .with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ctx.new_ids.get(1).cloned().unwrap_or_default(),
                "record_id": anchor_id,
                "event_type": "chain_recovered",
                "severity": "warning",
                "message": format!("Cadena continuada manualmente para {issuer_nif}: huella {}…", short(&record_hash)),
                "details": json!({
                    "source": "manual",
                    "record_hash": record_hash,
                    "sequence_number": seq,
                }).to_string(),
                "timestamp": ctx.now,
            }),
        )))
}

#[cfg(test)]
mod tests {
    use super::{archive_transmission_xml, derive_tax_rate, NativeHost, Params, Result};
    use serde_json::Value as Json;
    use std::sync::Mutex;

    #[derive(Default)]
    struct ArchiveHost {
        writes: Mutex<Vec<(String, Vec<u8>, String)>>,
    }

    #[async_trait::async_trait]
    impl NativeHost for ArchiveHost {
        async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
            Ok(vec![])
        }

        async fn write_static_file(
            &self,
            relative_path: &str,
            bytes: &[u8],
            content_type: &str,
        ) -> Result<String> {
            self.writes.lock().unwrap().push((
                relative_path.to_string(),
                bytes.to_vec(),
                content_type.to_string(),
            ));
            Ok(format!("modules/verifactu/{relative_path}"))
        }
    }

    #[tokio::test]
    async fn xml_is_archived_before_transmission_under_a_stable_record_path() {
        let host = ArchiveHost::default();
        let path = archive_transmission_xml(&host, "record-123", "<soap />")
            .await
            .unwrap();

        assert_eq!(path, "modules/verifactu/xml/record-123.xml");
        assert_eq!(
            host.writes.lock().unwrap().as_slice(),
            &[(
                "xml/record-123.xml".to_string(),
                b"<soap />".to_vec(),
                "application/xml".to_string()
            )]
        );
    }

    #[test]
    fn tipo_unico_se_toma_del_desglose() {
        // Factura a 10% (peluquería/restaurante): el desglose tiene un único tipo → 10, no 21.
        let tb = r#"{"10.00":{"base":1100,"tax":110}}"#;
        assert_eq!(derive_tax_rate(tb, 1100.0, 110.0), 10.0);
        // Factura a 21% estándar.
        let tb21 = r#"{"21.00":{"base":10000,"tax":2100}}"#;
        assert_eq!(derive_tax_rate(tb21, 10000.0, 2100.0), 21.0);
        // Tipo reducido 4% (libros/alimentos).
        let tb4 = r#"{"4.00":{"base":500,"tax":20}}"#;
        assert_eq!(derive_tax_rate(tb4, 500.0, 20.0), 4.0);
    }

    #[test]
    fn mixto_o_vacio_cae_al_tipo_efectivo() {
        // Mixto 21%+10%: el registro es de tipo único → efectivo (no es un tipo real, limitación
        // documentada; el desglose multi-línea queda para el humano).
        let mixto = r#"{"21.00":{"base":10000,"tax":2100},"10.00":{"base":1000,"tax":100}}"#;
        let r = derive_tax_rate(mixto, 11000.0, 2200.0); // 2200/11000 = 20%
        assert_eq!(r, 20.0);
        // Desglose vacío (facturas antiguas '{}'): efectivo desde base/cuota.
        assert_eq!(derive_tax_rate("{}", 1000.0, 100.0), 10.0);
        // JSON inválido → efectivo.
        assert_eq!(derive_tax_rate("", 1000.0, 210.0), 21.0);
    }

    #[test]
    fn base_cero_no_divide_por_cero() {
        assert_eq!(derive_tax_rate("{}", 0.0, 0.0), 0.0);
    }

    #[test]
    fn rectificativa_negativa_conserva_signo_del_tipo() {
        // R1 con importes negativos: 2100/10000 = 21% (positivo), el desglose de tipo único manda.
        let tb = r#"{"21.00":{"base":-10000,"tax":-2100}}"#;
        assert_eq!(derive_tax_rate(tb, -10000.0, -2100.0), 21.0);
        // Sin desglose, efectivo de negativos: (-210)/(-1000) → 21%.
        assert_eq!(derive_tax_rate("{}", -1000.0, -210.0), 21.0);
    }
}

#[cfg(test)]
mod cert_source_tests {
    use super::*;

    /// Host que simula un hub con certificado del negocio en el core (`_hub_certificate`).
    struct CoreCertHost;
    #[async_trait::async_trait]
    impl NativeHost for CoreCertHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            if sql.contains("_hub_certificate") {
                Ok(vec![json!({ "pkcs12_b64": "QUJD", "password": "secret" })])
            } else if sql.contains("verifactu_config") {
                Ok(vec![json!({ "hub_id": "h1", "environment": "testing" })])
            } else {
                Ok(vec![])
            }
        }
    }

    /// ADR-0079/0081: el `.p12` del negocio es del CORE. `read_config` debe **marcar** su presencia
    /// (`certificate_source = "core"`) pero NUNCA copiar los bytes del `.p12` ni la contraseña a la
    /// config del módulo — se quedan en el core; la firma usa la capability opaca
    /// `certificate_identity(hub_id)` (ver `build_identity`), no `certificate_identity_from`.
    #[tokio::test]
    async fn read_config_marks_core_cert_without_leaking_bytes() {
        let cfg = read_config(&CoreCertHost, "h1").await.unwrap().unwrap();
        assert_eq!(
            cfg.get("certificate_source").and_then(|v| v.as_str()),
            Some("core"),
            "debe marcar que el cert es del core"
        );
        assert!(
            cfg.get("certificate_pkcs12").is_none(),
            "los bytes del .p12 NO deben entrar en la config del módulo (ADR-0079)"
        );
        assert!(
            cfg.get("certificate_password").is_none(),
            "la contraseña del cert NO debe entrar en la config del módulo (ADR-0079)"
        );
    }
}

#[cfg(test)]
mod ingest_tests {
    use super::*;

    /// Host que devuelve UNA factura con `issuer_nif` vacío (identidad fiscal global sin configurar).
    struct NoIssuerHost;
    #[async_trait::async_trait]
    impl NativeHost for NoIssuerHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            if sql.contains("FROM invoice_invoice") {
                Ok(vec![json!({
                    "invoice_type": "F2", "number": "TICKET-2026-000001",
                    "issue_date": "2026-07-31", "issuer_nif": "", "issuer_name": "",
                    "customer_tax_id": "", "customer_name": "Cliente",
                    "description": "Venta", "base_amount": 100, "tax_amount": 21, "total_amount": 121,
                    "tax_breakdown": "", "substitutes_number": "", "substitutes_date": "",
                    "substitutes_nif": ""
                })])
            } else {
                Ok(vec![])
            }
        }
    }

    /// verifactu#109: una factura SIN issuer_nif debe RECHAZAR (antes devolvía OK/0-operaciones en
    /// silencio y no generaba registro fiscal — falsa sensación de cumplimiento).
    #[tokio::test]
    async fn ingest_invoice_rejects_missing_issuer_nif() {
        let input = json!({
            "payload": { "invoice_id": "inv-1" },
            "context": { "hub_id": "h1", "now": "2026-07-31T10:00:00Z", "current_user_id": "u1" }
        });
        let res = ingest_invoice(&input, &NoIssuerHost).await;
        let err = res.unwrap_err().to_string();
        assert!(
            err.contains("missing_issuer_nif"),
            "esperaba rechazo por issuer_nif vacío, llegó: {err}"
        );
    }
}
