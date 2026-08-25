//! # erplora-verifactu
//!
//! Motor fiscal **VeriFactu** (RD 1007/2023) como **plugin nativo first-party**
//! ([ADR-0009]): cadena de hash SHA-256 encadenada por `(hub_id, issuer_nif, environment)`
//! (ADR-0202 guarda R4: `production` y `testing` son dos cadenas paralelas independientes),
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
use erplora_runtime::certificate_refetch::RefetchSignal;
use erplora_runtime::native::{NativeHandler, NativeHost, PendingObligation};
use erplora_runtime::{Result, RuntimeError};
use erplora_wasm_host::{Event, Operation, Output};
use serde_json::{json, Value as Json};

pub mod aeat;
pub mod chain;
pub mod xsd;

/// Errores internos del motor (se aplanan a [`RuntimeError::Native`]).
#[derive(Debug, thiserror::Error)]
pub enum VerifactuError {
    #[error("payload inválido: {0}")]
    Payload(String),
    #[error("certificado: {0}")]
    Certificate(String),
    #[error("transmisión AEAT: {0}")]
    Transmission(String),
    /// El canal TLS con la AEAT falló: nuestro certificado de cliente fue rechazado, caducó, fue
    /// revocado, o el handshake no llegó a cerrarse (`aeat::is_tls_failure`).
    ///
    /// Variante propia porque **es el tercer disparador de refetch** (ADR-0202 §2 punto 4): si el
    /// certificado con el que nos identificamos dejó de valer, la respuesta es pedir el vigente al
    /// plano de control, no reintentar el mismo. Un fallo de red se reintenta; este se **arregla**.
    #[error("transmisión AEAT (TLS): {0}")]
    Tls(String),
    /// La AEAT respondió a la **consulta** con un fallo (SOAP Fault). Es un error propio y no
    /// una lista vacía: «0 registros» se leería como «no hay nada que recuperar», que es la
    /// lectura que rompe la recuperación de la cadena (hub#287).
    #[error("consulta AEAT: {0}")]
    Consult(String),
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

    /// **Retention gate (hub#314, ADR-0202 guard R2).** Records the AEAT does NOT have yet.
    /// While this is non-zero the runtime refuses to deactivate or uninstall the module: those
    /// records are the only proof pending for invoices already issued, and nothing outside this
    /// module can transmit them (VeriFactu FAQ §5).
    ///
    /// The counted states are exactly the module's own `compliance_summary` KPI —
    /// `pending`/`retry`/`error`/`rejected`, everything short of `accepted` — so the number in
    /// the refusal is the same one the operator already sees on the dashboard, and clearing the
    /// KPI is literally the way out. `rejected` counts too: the AEAT rejected the record, so the
    /// invoice is still unregistered and needs a corrected one before the module may go
    /// (`is_chainable_status`: a rejected link is not in the chain either).
    async fn pending_obligations(
        &self,
        hub_id: &str,
        host: &dyn NativeHost,
    ) -> Result<Option<PendingObligation>> {
        let count = contingency_queue(hub_id, host).await?.depth;
        if count == 0 {
            return Ok(None);
        }
        Ok(Some(PendingObligation {
            count,
            code: "verifactu.unsent_records".to_string(),
            // English source string; the UI translates against the stable code (ADR-0055).
            message: format!(
                "{count} VeriFactu record(s) have not reached the AEAT yet: send them before disabling or removing the module"
            ),
        }))
    }
}

/// How much work the AEAT is still waiting for, and since when (hub#326).
///
/// It is the **same** set of records the retention gate counts
/// (`NativeHandler::pending_obligations`) — everything short of `accepted` — read with the same
/// query, so the number the SaaS alerts on and the number that blocks an uninstall can never
/// disagree.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContingencyQueue {
    /// Records this hub has not handed over yet. **`0` is a fact**, not an absence: it means the
    /// chain is fully remitted. «I could not count it» is the `Err` of [`contingency_queue`].
    pub depth: u64,
    /// `created_at` of the oldest entry still waiting, or `None` when the queue is empty.
    ///
    /// The hub reports the wait it can measure and **does not decide what «stuck» means**: a
    /// threshold belongs where the alert is raised (the SaaS), not baked into every hub in the
    /// fleet — a restaurant mid-service and a hub whose certificate expired last week both have a
    /// non-empty queue, and only the age tells them apart.
    pub oldest_pending_at: Option<String>,
}

/// Measure the contingency queue for `hub_id`: depth plus the wait of its oldest entry.
///
/// One query for both numbers, and the same one the retention gate uses. An `Err` means the read
/// itself failed (no `verifactu` module installed, so no table) — callers must report that as
/// «unknown», never as a zero: a fabricated `0` tells the fleet panel that a queue nobody could
/// read is under control, which is exactly the blindness hub#326 exists to remove.
pub async fn contingency_queue(hub_id: &str, host: &dyn NativeHost) -> Result<ContingencyQueue> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let rows = host
        .read(
            "SELECT COUNT(*) AS pending_count, MIN(created_at) AS oldest_pending_at \
             FROM verifactu_record \
             WHERE hub_id = :hub_id AND is_deleted = 0 \
               AND status IN ('pending', 'retry', 'error', 'rejected')",
            &p,
        )
        .await?;
    let row = rows.first();
    let depth = row
        .map(|r| int_field(r, "pending_count", 0))
        .unwrap_or(0)
        .max(0) as u64;
    let oldest_pending_at = row
        .and_then(|r| r.get("oldest_pending_at"))
        .and_then(|v| v.as_str())
        .map(str::to_owned);
    Ok(ContingencyQueue {
        depth,
        oldest_pending_at,
    })
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
/// **Certificado (ADR-0079/0081, ADR-0202 §2.1):** el PKCS#12 vive en el core (`_hub_certificate`),
/// NO en `verifactu_config`, y el hub tiene DOS slots — el `own` del negocio (subido en Ajustes →
/// Negocio) y el `delegated` de ERPlora, que el plano de control reparte y rota. Aquí solo se marca
/// **qué dice el core**: `certificate_source = "core"` (hay con qué firmar) y `certificate_kind`
/// (con cuál). **Los bytes del `.p12` y la contraseña NUNCA se copian a la config del módulo** —
/// ni se consultan siquiera: la firma/transmisión usa la capability opaca
/// `certificate_identity(hub_id)` (el core hace la cripto; ver `build_identity`). El acceso está
/// gateado por la capability `certificate` (el dispatcher la exige antes del handler nativo),
/// así que llegar aquí implica que el usuario la concedió.
///
/// **Quién firma lo decide el CORE, no este módulo** (hub#319). Antes se sondeaba
/// `SELECT pkcs12_b64, password FROM _hub_certificate … LIMIT 1`: sin `kind` (con dos filas, la que
/// devolviese la BD), contando filas que el core se niega a seleccionar, y arrastrando la contraseña
/// del certificado a la memoria del módulo solo para comprobar que no estaba vacía. La regla de
/// selección (`own` si está, si no `delegated`) tiene un dueño y no se reimplementa aquí.
async fn read_config(host: &dyn NativeHost, hub_id: &str) -> Result<Option<Json>> {
    let rows = host
        .read(
            "SELECT * FROM verifactu_config WHERE hub_id = :hub_id AND is_deleted = 0 LIMIT 1",
            &params(json!({ "hub_id": hub_id })),
        )
        .await?;
    let mut config = rows.into_iter().next();

    // Tolerante: un host sin la capacidad (o un hub sin la migración de sistema) responde `None` y
    // el módulo se queda sin marcador — que es «no puedo transmitir», el lado seguro.
    if let Some(kind) = host
        .certificate_signing_kind(hub_id)
        .await
        .unwrap_or_default()
    {
        // **Y QUÉ es**, que es otra pregunta (hub#470): el slot dice de quién es el certificado, el
        // tipo dice por qué puerta de la AEAT entra. Se lee del MISMO sitio y en la misma pasada que
        // el slot —el core— para que no haya dos lecturas de «con qué firmo» que puedan contestar
        // distinto: ese desdoblamiento es exactamente cómo se estropearon #317, #318 y #319.
        // `None` (el core no puede jurarlo, o un host sin la capacidad) deja el marcador vacío, que
        // es la puerta del titular.
        let certificate_type = host
            .certificate_signing_type(hub_id)
            .await
            .unwrap_or_default()
            .unwrap_or_default();
        let obj = config.get_or_insert_with(|| json!({}));
        if let Some(m) = obj.as_object_mut() {
            m.insert("certificate_source".into(), json!("core"));
            m.insert("certificate_kind".into(), json!(kind));
            m.insert("certificate_type".into(), json!(certificate_type));
        }
    }

    // Los hechos del productor (hub#323): identidad del fabricante + `IndicadorMultiplesOT`, que
    // el hub NO puede saber y que el plano de control sirve en el latido. Viajan pegados a la
    // config —igual que los marcadores del certificado— para que el constructor del XML lea UN
    // objeto y no sepa que existe un Cloud. Ausentes = ausentes: no hay defaults para una
    // declaración legal, y `sistema_informatico` se niega a construir el registro.
    //
    // Se ADJUNTAN a la config, nunca la CREAN: «este hub no tiene config de VeriFactu» tiene que
    // seguir contestando `None` a quien pregunta. Los hechos del productor son de la flota, no de
    // este hub, y no convierten un módulo sin configurar en uno configurado.
    if let Some(obj) = config.as_mut().and_then(Json::as_object_mut) {
        if let Some(facts) = host.producer_facts().await.unwrap_or_default() {
            obj.insert("producer_facts".into(), facts);
        }
    }
    Ok(config)
}

/// Construye la **Identity mTLS** para firmar/transmitir a la AEAT.
///
/// El certificado fiscal (.p12) es un recurso del NEGOCIO/hub (ADR-0079/0081) y desde ADR-0202 §2.1
/// hay dos: el **propio** del negocio y el **delegado** de ERPlora. `host.certificate_identity`
/// resuelve el fallback (`own` si está subido, si no `delegated`) y hace TODA la cripto PKCS#12;
/// **los bytes del `.p12` y la contraseña NUNCA entran al módulo**.
///
/// Error **solo si no hay ninguno de los dos** (hub#319): un hub cuyo único certificado es el
/// delegado transmite perfectamente — ERPlora firma en su nombre.
async fn build_identity(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
) -> Result<reqwest::Identity> {
    if !has_certificate(config) {
        return Err(VerifactuError::Certificate(
            "no hay certificado con el que firmar: ni el del negocio (súbelo en Ajustes → Negocio) \
             ni uno delegado de ERPlora"
                .into(),
        )
        .into());
    }
    host.certificate_identity(hub_id).await
}

/// ¿Hay un certificado del core con el que transmitir — propio **o** delegado? Gate barato que NO
/// carga los bytes del `.p12`: basta el marcador `certificate_source` que `read_config` pone con lo
/// que respondió el core.
fn has_certificate(config: &Json) -> bool {
    str_field(config, "certificate_source") == "core"
}

/// **¿Puede este motor firmar por `hub_id` ahora mismo?** — exactamente el predicado con el que
/// [`build_identity`] deja pasar o rechaza.
///
/// `pub` a propósito (hub#319): «¿puede este hub facturar?» la contestan TRES sitios —el gate fiscal
/// del dispatcher (ADR-0203), el brazo ⛔ de la checklist (hub#370) y este motor— y tienen que
/// contestar lo mismo. Un ⛔ que bloquea una pantalla mientras el runtime acepta la venta, o al
/// revés, es la checklist mintiendo. Con el predicado del motor accesible, esa coherencia se
/// comprueba en UN test junto a los otros dos, en vez de confiarla a tres tests separados que
/// pueden separarse sin que nada avise.
pub async fn can_sign(host: &dyn NativeHost, hub_id: &str) -> Result<bool> {
    Ok(read_config(host, hub_id)
        .await?
        .as_ref()
        .is_some_and(has_certificate))
}

/// Con **cuál** de los dos se firma: `"own"`, `"delegated"`, o `""` si no hay ninguno
/// (ADR-0202 §2.1 — hub#319).
///
/// ⚠️ **Esta es la respuesta que lee el endpoint AEAT (`www1` vs `www10`, hub#320) y la que tiene
/// que leer [hub#321] (bloque `Representante`), NO una segunda consulta a `_hub_certificate`.** La
/// selección arrastra el endpoint y el `Representante`, así que resolverla otra vez por su cuenta
/// es cómo vuelve el defecto que hub#317 y hub#318 ya arreglaron dos veces: dos lecturas de la
/// misma pregunta que pueden contestar distinto. Hasta que hub#321 aterrice, un hub que firme con
/// el delegado transmite por el endpoint correcto pero **sin `Representante`**.
///
/// [hub#321]: https://github.com/ERPlora/hub/issues/321
fn signing_kind(config: &Json) -> String {
    str_field(config, "certificate_kind")
}

/// **QUÉ es** el certificado que firma: `"seal"`, `"representative"`, o `""` si el core no puede
/// jurarlo (ADR-0202 §2.1 — hub#470).
///
/// El gemelo de [`signing_kind`], y la distinción es el fondo de hub#470: el slot dice **de quién**
/// es el certificado —lo que decide el fallback y lo que necesitará el bloque `Representante` de
/// hub#321— y el tipo dice **qué** es, que es lo único por lo que la AEAT segrega la puerta. Leer
/// el slot como si fuera el tipo mandaba a `www10` a cualquier certificado repartido por el plano
/// de control, fuese un sello o no.
///
/// Lo pone [`read_config`] con lo que contestó el core. El motor no vuelve a preguntar a
/// `_hub_certificate`: una sola lectura, un solo dueño.
fn signing_type(config: &Json) -> String {
    str_field(config, "certificate_type")
}

/// **El endpoint AEAT de este hub AHORA MISMO** — los dos ejes (`environment` y certificado que
/// firma) resueltos de la MISMA lectura de la config (ADR-0202 §2.1 — hub#320).
///
/// Existe para que ningún sitio los multiplique por su cuenta. Son dos ejes y fallan distinto: un
/// certificado en la puerta equivocada se rechaza (ruidoso, recuperable a mano); un entorno
/// equivocado se **acepta** en el sistema que no era, y un registro remitido no se reenvía ni se
/// borra (ADR-0189). ⚠️ El eje del **entorno** sale de la config, no del registro, así que un
/// registro encolado en `testing` y drenado tras un go-live sale hacia la AEAT real:
/// [hub#471](https://github.com/ERPlora/hub/issues/471) (pendiente, va con la guarda R1).
///
/// **El endpoint acompaña al CERTIFICADO, no al XML.** La AEAT segrega la puerta por el certificado
/// que se presenta en el handshake TLS, así que un registro que lleva días en contingencia se
/// transmite por la puerta del certificado que firma **hoy**, no por la del que firmaba cuando se
/// generó: presentar el sello de ERPlora en `www1` falla siempre, diga lo que diga el XML
/// archivado. ⚠️ La otra mitad de esa pareja —el `Representante`, que sí viaja DENTRO del
/// `xml_content` congelado del reintento— es de [hub#321](https://github.com/ERPlora/hub/issues/321):
/// si el hub cambió de certificado mientras el registro esperaba en la cola, ese XML describe al
/// firmante anterior y habrá que reconstruirlo.
fn transmission_endpoint(config: &Json) -> &'static str {
    aeat::endpoint(&environment_of(config), &signing_type(config))
}

/// **Por qué puerta de la AEAT transmite este hub AHORA MISMO**, resuelto desde el host — los dos
/// ejes de la MISMA lectura de la config, sin que el llamante los multiplique por su cuenta.
///
/// `pub` a propósito, por el mismo motivo que [`can_sign`] (hub#319): la cadena core → `read_config`
/// → tipo de certificado → URL cruza dos crates, y la familia de defectos de #317/#318/#319/#470 es
/// justamente la de un dato de certificado que se lee distinto a cada lado. Con la cadena entera
/// accesible se comprueba en UN test de punta a punta, en vez de en dos tests que pueden
/// separarse sin que nada avise.
pub async fn transmission_endpoint_for(
    host: &dyn NativeHost,
    hub_id: &str,
) -> Result<&'static str> {
    let config = read_config(host, hub_id).await?.unwrap_or_else(|| json!({}));
    Ok(transmission_endpoint(&config))
}

/// El endpoint de **consulta** de este hub ahora mismo. Es el mismo que el de alta (el WSDL publica
/// las dos operaciones en `VerifactuSOAP`, hub#287) y por eso se deriva igual, con los dos ejes de
/// la misma lectura: recuperar la cadena tiene que hablar con la misma puerta que la emitió.
fn consult_endpoint_of(config: &Json) -> &'static str {
    aeat::consult_endpoint(&environment_of(config), &signing_type(config))
}

/// **Where ONE record's transmission is going** — resolved once and then shared by the POST, by
/// the audit event and by the drift warning, so the wire and the paper trail cannot say
/// different things about the same send (hub#471).
#[derive(Debug)]
struct Destination {
    /// The AEAT environment that must receive this record: the one its CHAIN lives in.
    environment: String,
    /// `environment` × the certificate signing TODAY. Still ONE multiplication (hub#320).
    endpoint: &'static str,
    /// The hub's CURRENT environment, and only when it is NOT the record's.
    hub_environment: Option<String>,
}

impl Destination {
    /// What the owner reads in the fiscal event log when a record left for an environment that
    /// is no longer the hub's — the visible half of hub#471. Nothing is wrong here, but nothing
    /// about it is routine either: it means the contingency queue outlived a go-live.
    fn drift_note(&self) -> Option<String> {
        self.hub_environment.as_ref().map(|hub_environment| {
            format!(
                "remitido a «{}» —el entorno de la CADENA de este registro— aunque el hub está \
                 ahora en «{hub_environment}»: las dos cadenas no se mezclan (ADR-0202 §3)",
                self.environment
            )
        })
    }
}

/// The AEAT environment stamped on the record when it was created (guard R4, hub#313) — the one
/// its hash chain lives in, and never re-derived from the config afterwards.
///
/// `None` is NOT «testing». A row that does not carry the column predates migration 008 and its
/// chain could belong to either system; both guesses are unrecoverable — a practice record
/// **accepted** by the real AEAT, or a real invoice the real AEAT never receives — so the caller
/// refuses instead of picking one.
fn record_environment(record: &Json) -> Option<String> {
    let environment = str_field(record, "environment");
    (!environment.is_empty()).then_some(environment)
}

/// Resolves the [`Destination`] of one record, or says why it cannot.
///
/// The two axes answer to different owners **on purpose** (hub#471, hub#320):
///
/// - the **environment** belongs to the RECORD. `production` and `testing` are two parallel
///   chains that never mix (guard R4), and the previous link, the frozen `xml_content` and the
///   QR host of a queued record already all say the same one. Reading the URL from the config
///   made those four disagree the moment the operator went live with a non-empty queue;
/// - the **certificate** belongs to TODAY'S config. The AEAT segregates the door by the
///   certificate presented in the TLS handshake, so a record that waited days in contingency
///   goes through the door of whatever signs now.
///
/// And they fail in opposite ways, which is why one is worth refusing over: the wrong door is
/// REJECTED — loud, and recoverable one record at a time — while the wrong environment is
/// ACCEPTED by a tax agency that was never meant to receive it, and an accepted record is
/// neither resent nor deleted (ADR-0189).
///
/// ⚠️ The certificate axis is [`signing_type`], **not** [`signing_kind`] (hub#470): the AEAT
/// segregates by what the certificate IS, and the slot only says whose it is. This function is the
/// second place in the engine that multiplies the two axes, so it is also the second place that has
/// to read the same value as [`transmission_endpoint`] — reading one from the type and the other
/// from the slot is exactly the shape of defect this whole chain keeps producing.
fn destination_of(record: &Json, config: &Json) -> std::result::Result<Destination, String> {
    let hub_environment = environment_of(config);
    let Some(environment) = record_environment(record) else {
        return Err(format!(
            "el registro no dice a qué entorno de la AEAT pertenece (fila anterior a la \
             migración 008) y el hub está en «{hub_environment}»: no se transmite a ciegas"
        ));
    };
    Ok(Destination {
        endpoint: aeat::endpoint(&environment, &signing_type(config)),
        // Only when they differ: `Some` IS the drift, so nothing downstream has to compare.
        hub_environment: (environment != hub_environment).then_some(hub_environment),
        environment,
    })
}

/// **Tercer disparador de refetch del certificado** (ADR-0202 §2 punto 4 — hub#318): un fallo del
/// canal TLS contra la AEAT pide al plano de control el certificado vigente.
///
/// El motor **no descarga nada**. No tiene la credencial de máquina del hub y no debe tenerla: la
/// clave privada delegada es de ERPlora y su única puerta de entrada vive en el server
/// (`erplora-server::fiscal_certificate`). Aquí solo se levanta la señal; quién la sirve, cuándo, y
/// con cuánto presupuesto, es decisión del server.
///
/// Solo el TLS. Un timeout o un DNS caído se reintentan por la cola de contingencia (5/10/20/40/60
/// min) y **no** se arreglan bajando otra vez una clave privada: pedirla en cada registro varado
/// agotaría el presupuesto de 20/h del endpoint justo cuando el hub más lo necesita.
///
/// **Y solo si quien se identificó fue el certificado DELEGADO** (`signing_kind`, hub#319). El
/// refetch baja el de ERPlora; si el handshake lo rompió el certificado **propio** del negocio
/// —caducado, revocado, contraseña cambiada—, bajar el delegado no arregla nada, porque el propio
/// sigue ganando el fallback (ADR-0202 §2.1) y el intento siguiente falla igual. Lo único que
/// lograría es gastar el cupo del hub en algo que no puede funcionar, y dejar sin él al disparador
/// del latido —el que sí instala una rotación real— justo cuando llegue.
///
/// El `signal` es un parámetro —y no el global directamente— para que esto sea comprobable sin
/// tocar estado de proceso compartido entre tests.
fn request_certificate_refetch_on_tls(
    error: &VerifactuError,
    signing_kind: &str,
    signal: &RefetchSignal,
) {
    if matches!(error, VerifactuError::Tls(_)) && signing_kind == DELEGATED_SLOT {
        signal.request();
    }
}

/// Nombre del slot delegado tal y como lo devuelve el core
/// (`certificate::CertificateKind::as_str`). Constante para que la comparación no se escriba a mano
/// en cada sitio y pueda equivocarse en uno.
const DELEGATED_SLOT: &str = "delegated";

/// Nombre del tipo **sello de entidad** tal y como lo devuelve el core
/// (`certificate::CertificateType::as_str`). El ÚNICO valor que abre la puerta `www10` de la AEAT
/// (`aeat::endpoint`); todo lo demás cae a la del titular.
///
/// ⚠️ Es una constante distinta de [`DELEGATED_SLOT`] a propósito, y no un alias suyo: son las dos
/// palabras que hub#470 separó —de quién es el certificado vs. qué es— y colapsarlas otra vez
/// devuelve el defecto.
pub(crate) const SEAL_TYPE: &str = "seal";

// ── create_record (issue verifactu#2) ────────────────────────────────────────

const INVOICE_TYPES: [&str; 8] = ["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"];

/// Tipos que exigen el bloque `Destinatarios` en el XML: sin destinatario identificado la AEAT
/// los rechaza con el error **1189**.
const TYPES_REQUIRING_RECIPIENT: [&str; 6] = ["F1", "F3", "R1", "R2", "R3", "R4"];

/// Estados de registro que **siguen siendo eslabón** de la cadena.
///
/// Solo `rejected` deja de serlo: la AEAT no lo tiene, así que su huella no existe para Hacienda
/// y encadenar ahí garantiza que también rechacen al siguiente — un fallo puntual se convierte
/// en una cadena que ya no avanza sola (hub#287, mismo defecto confirmado en el SaaS).
///
/// Lo que está **en vuelo** (`pending`, `retry`, `error` — encolado en contingencia con backoff)
/// sí encadena: ese registro se transmitirá con la huella que ya calculó, y saltárselo
/// bifurcaría la cadena.
pub fn is_chainable_status(status: &str) -> bool {
    status != "rejected"
}

/// Tipo de factura efectivo según haya o no **destinatario identificado**.
///
/// Una F1 exige el bloque `Destinatarios`; sin NIF de cliente el XML sale sin él y la AEAT lo
/// rechaza con **1189**, después de que el registro haya consumido su número en la cadena. Una
/// venta a consumidor final sin NIF es justo el supuesto de la **simplificada (F2)**.
///
/// Una rectificativa sin NIF **no** es una simplificada: es una rectificativa **de** simplificada
/// (**R5**). Degradarla a F2 declararía una venta donde hay una devolución.
///
/// Se resuelve **antes** de encadenar porque el tipo entra en el cálculo de la huella.
///
/// ⚠️ **Degradar es correcto; hacerlo en silencio no** (hub#1104). Esta función decide el tipo y
/// nada más — quien la llama compara el resultado con lo declarado y lleva la diferencia a
/// [`RecordInput::downgraded_from`], que es lo que hace que el hecho se vea: un evento
/// `invoice_type_downgraded` con severidad `warning` y, si la F2 fabricada rompiese el techo
/// §15.8, un rechazo antes de gastar el número de cadena.
fn resolve_invoice_type(declared: &str, recipient_nif: &str) -> String {
    if !recipient_nif.trim().is_empty() || !TYPES_REQUIRING_RECIPIENT.contains(&declared) {
        return declared.to_string();
    }
    match declared {
        "R1" | "R2" | "R3" | "R4" => "R5".to_string(),
        _ => "F2".to_string(),
    }
}

/// Tipos que **no admiten un total negativo**: F1, F2 y F3 documentan una venta. Lo negativo es
/// una RECTIFICATIVA (R1…R5), que es el camino legal de una devolución y sí puede serlo.
///
/// Espejo exacto de `invoice.NON_NEGATIVE_TYPES` y de la restricción
/// `ck_verifactu_record_ordinary_total_not_negative` del módulo: tres puertas, un solo criterio.
const NON_NEGATIVE_TYPES: [&str; 3] = ["F1", "F2", "F3"];

/// Tolerancia de redondeo al contrastar la cuota de una línea del desglose contra su propio tipo,
/// en céntimos.
///
/// Un céntimo por la regla de redondeo de `taxes` (con precios IVA incluido la cuota es
/// `bruto − base`, que difiere hasta un céntimo de `base × tipo`) y medio más porque se compara
/// contra el valor **sin redondear**. Es el mismo `1.5` que usa
/// `ck_verifactu_record_quota_matches_declared_rate`: si las dos puertas midieran distinto, una
/// factura pasaría aquí para morir con un error crudo de Postgres una línea después.
const LINE_ROUNDING_TOLERANCE_CENTS: f64 = 1.5;

/// Margen al comparar dos importes que son **enteros de céntimos** viajando en `f64`.
const CENT_EPSILON: f64 = 0.5;

/// Una línea del desglose reducida a lo único que la auditoría necesita. Importes en CÉNTIMOS.
struct AuditLine {
    rate: f64,
    base: f64,
    quota: f64,
    surcharge_rate: f64,
    surcharge_quota: f64,
    has_surcharge: bool,
}

/// Lee el `tax_breakdown` en sus DOS generaciones (el mismo par que entiende `aeat::desglose`, y
/// por el mismo motivo: las facturas ya emitidas están encadenadas en la huella y no se pueden
/// reinterpretar). Un desglose ilegible devuelve la lista vacía — ahí no hay nada declarado que
/// contrastar y juzga el `tax_rate` de la fila.
fn audit_lines(tax_breakdown: &str) -> Vec<AuditLine> {
    let mut lines = Vec::new();
    match serde_json::from_str::<Json>(tax_breakdown) {
        // Formato nuevo: una entrada por clave fiscal completa.
        Ok(Json::Array(entries)) => {
            for e in &entries {
                if !e.is_object() {
                    continue;
                }
                lines.push(AuditLine {
                    rate: num_field(e, "rate", 0.0),
                    base: num_field(e, "base", 0.0),
                    quota: num_field(e, "quota", 0.0),
                    surcharge_rate: num_field(e, "surcharge_rate", 0.0),
                    surcharge_quota: num_field(e, "surcharge_quota", 0.0),
                    has_surcharge: e.get("surcharge_rate").is_some()
                        || e.get("surcharge_quota").is_some(),
                });
            }
        }
        // Formato viejo: clave = tipo, `{base, tax}`, todo venta nacional sujeta y no exenta.
        Ok(Json::Object(map)) => {
            for (rate, amounts) in map {
                let Ok(rate) = rate.trim().parse::<f64>() else {
                    continue;
                };
                lines.push(AuditLine {
                    rate,
                    base: num_field(&amounts, "base", 0.0),
                    quota: num_field(&amounts, "tax", 0.0),
                    surcharge_rate: 0.0,
                    surcharge_quota: 0.0,
                    has_surcharge: false,
                });
            }
        }
        _ => {}
    }
    lines
}

/// **Nada aritméticamente imposible se sella** (hub#1103).
///
/// Este motor es el último eslabón antes de Hacienda: calcula la huella SHA-256, gasta un número
/// de secuencia, encadena y encola para la AEAT. Aceptaba los importes que le dieran. Una pasada
/// de QA selló un registro que declaraba `rate 21.0` con una cuota de 99,99 € sobre una base de
/// 5,45 €, y otro con base y cuota negativas en un alta ordinaria: los dos viajaron VERBATIM al
/// `CuotaTotal` y al `ImporteTotal` que se remiten.
///
/// # Por qué aquí, si el módulo ya lo comprueba en la tabla
///
/// `013_arithmetic_integrity.sql` (verifactu#53) puso tres `CHECK` en `verifactu_record`, y esa es
/// la guarda que ninguna puerta puede saltarse. Pero una violación de `CHECK` llega como un error
/// crudo de Postgres: **sin código de dominio, sin motivo legible y después** de haber leído el
/// ancla de la cadena. Este control se adelanta a ese punto y da el motivo con su código, que es
/// lo que la issue pedía dejar «en `verifactu.events.list`». *(No puede ser una FILA de evento: el
/// rechazo revierte su propia transacción y el evento se iría con ella. El motivo viaja en el
/// error, que es lo que ve el llamante y lo que registra el runtime.)*
///
/// # Qué se comprueba, y qué NO
///
///   * **la cuota contra SU tipo declarado** — sí, y es la única que caza el caso del QA:
///     `base + cuota = total` cuadra igual (545 + 9999 = 10544 es internamente consistente).
///   * **la cuota contra `quantity × unit_price`** — NO, y no es un olvido: `sales` prorratea el
///     descuento DENTRO de la línea y deja `unit_price` en el bruto. Esa comparación rechazaría
///     toda venta con descuento y toda invitación (razonado en `invoice#50`).
///   * **el desglose contra la cabecera** (`Σ bases`, `Σ cuotas`) y **`base + cuota = total`** —
///     sí. Es exactamente el cruce que hace la AEAT, y es la mitad que la tabla dejó fuera a
///     propósito porque en SQL no cabía sin una función.
///   * **`total ≤ 0`** — NO: `< 0`. Un tique 100 % invitado suma 0,00 € honestamente y sigue
///     siendo una venta que necesita su F2. El criterio de aceptación de hub#1103 pedía `≤ 0` y
///     contradecía lo ya decidido en `invoice#50`; manda lo decidido.
///
/// Devuelve `Some(mensaje)` —con el código de dominio delante— cuando el registro no se puede
/// sellar.
fn audit_amounts(r: &RecordInput) -> Option<String> {
    // Una anulación no lleva importes: no hay nada que cuadrar.
    if r.record_type != "alta" {
        return None;
    }

    let lines = audit_lines(&r.tax_breakdown);
    let mut declared_base = 0.0;
    let mut declared_quota = 0.0;

    for line in &lines {
        declared_base += line.base;
        declared_quota += line.quota + line.surcharge_quota;

        let expected = line.base * line.rate / 100.0;
        if (line.quota - expected).abs() > LINE_ROUNDING_TOLERANCE_CENTS {
            return Some(format!(
                "quota_rate_mismatch: el desglose declara {} de cuota sobre una base de {} al {} %, \
                 y ese tipo justifica {expected:.2} (tolerancia {LINE_ROUNDING_TOLERANCE_CENTS} \
                 céntimos de redondeo). Cobrar un importe y declarar otro es lo que rompe el cruce \
                 de la AEAT",
                line.quota, line.base, line.rate
            ));
        }
        if line.has_surcharge {
            let expected_surcharge = line.base * line.surcharge_rate / 100.0;
            if (line.surcharge_quota - expected_surcharge).abs() > LINE_ROUNDING_TOLERANCE_CENTS {
                return Some(format!(
                    "quota_rate_mismatch: el desglose declara {} de recargo de equivalencia sobre \
                     una base de {} al {} %, y ese tipo justifica {expected_surcharge:.2}",
                    line.surcharge_quota, line.base, line.surcharge_rate
                ));
            }
        }
    }

    if lines.is_empty() {
        // Sin desglose legible (facturas anteriores al campo, rectificativas que lo dejan vacío, o
        // un `records.create` que no lo manda) solo queda el `tax_rate` de la fila. Tolerancia: un
        // céntimo de redondeo más el error que introduce guardar el tipo EFECTIVO con dos
        // decimales — sin ese margen una factura grande se rechazaría por la precisión de su
        // propio tipo. Mismo margen que `ck_verifactu_record_quota_matches_row_rate`.
        let expected = r.base_amount * r.tax_rate / 100.0;
        let tolerance = 1.0 + (r.base_amount.abs() * 0.00005).ceil();
        if (r.tax_amount - expected).abs() > tolerance {
            return Some(format!(
                "quota_rate_mismatch: la fila declara {} de cuota sobre una base de {} al {} %, y \
                 ese tipo justifica {expected:.2} (tolerancia {tolerance} céntimos)",
                r.tax_amount, r.base_amount, r.tax_rate
            ));
        }
    } else if (declared_base - r.base_amount).abs() > CENT_EPSILON
        || (declared_quota - r.tax_amount).abs() > CENT_EPSILON
    {
        return Some(format!(
            "totals_mismatch: la cabecera declara base {} y cuota {}, y su propio desglose suma \
             base {declared_base} y cuota {declared_quota}. `CuotaTotal` tiene que ser la suma de \
             las cuotas declaradas",
            r.base_amount, r.tax_amount
        ));
    }

    if (r.base_amount + r.tax_amount - r.total_amount).abs() > CENT_EPSILON {
        return Some(format!(
            "totals_mismatch: la cabecera declara base {} + cuota {} y un total de {}, que es lo \
             que viaja como `ImporteTotal`",
            r.base_amount, r.tax_amount, r.total_amount
        ));
    }

    if NON_NEGATIVE_TYPES.contains(&r.invoice_type.as_str())
        && (r.total_amount < -CENT_EPSILON || r.base_amount + r.tax_amount < -CENT_EPSILON)
    {
        return Some(format!(
            "negative_total: una factura de tipo {} no puede totalizar {}: un importe negativo es \
             una rectificativa (R1…R5), no una ordinaria",
            r.invoice_type, r.total_amount
        ));
    }

    None
}

/// Recompone un registro **rechazado** sobre el último eslabón que la AEAT sí tiene.
///
/// Cambia `previous_hash`, el número de secuencia y —por tanto— la propia huella. Reescribir el
/// registro localmente es legítimo *precisamente* porque la AEAT lo rechazó: nunca entró en la
/// cadena oficial. Lo que no vale es reenviarlo colgando de la huella equivocada.
///
/// Devuelve el registro recompuesto (para reconstruir el XML) y la intención que lo persiste.
/// El `xml_content` se limpia: el XML archivado corresponde al eslabón viejo y un reintento
/// posterior debe regenerarlo, no reenviar el que ya rechazaron.
pub fn rechain_record(
    record: &Json,
    anchor: &aeat::ConsultRecord,
    sequence_number: i64,
) -> (Json, Operation) {
    let previous_hash = chain::normalize_hash(&anchor.record_hash);
    let mut rechained = record.clone();
    let record_hash = if str_field(record, "record_type") == "anulacion" {
        chain::anulacion_hash(
            &str_field(record, "issuer_nif"),
            &str_field(record, "invoice_number"),
            &str_field(record, "invoice_date"),
            &previous_hash,
            &str_field(record, "generation_timestamp"),
        )
    } else {
        chain::alta_hash(
            &str_field(record, "issuer_nif"),
            &str_field(record, "invoice_number"),
            &str_field(record, "invoice_date"),
            &str_field(record, "invoice_type"),
            num_field(record, "tax_amount", 0.0) / 100.0,
            num_field(record, "total_amount", 0.0) / 100.0,
            &previous_hash,
            &str_field(record, "generation_timestamp"),
        )
    };
    if let Some(m) = rechained.as_object_mut() {
        m.insert("previous_hash".into(), json!(previous_hash));
        m.insert("record_hash".into(), json!(record_hash));
        m.insert("sequence_number".into(), json!(sequence_number));
        m.insert("is_first_record".into(), json!(0));
        m.insert("xml_content".into(), json!(""));
    }
    let record_id = str_field(record, "id");
    let intent = op(
        "verifactu._rechain_record",
        json!({
            "record_id": record_id,
            "sequence_number": sequence_number,
            "previous_hash": previous_hash,
            "record_hash": record_hash,
        }),
    );
    (rechained, intent)
}

/// Generates the chained fiscal record (alta/anulación): chain anchor per
/// `(hub_id, issuer_nif, environment)`, SHA-256 fingerprint (exact AEAT formats), `qr_url`,
/// and the INSERT record(pending) + event intentions (see [`build_record_output`]).
///
/// Sequence atomicity: the anchor is read before computing, and the unique index
/// `uq_verifactu_record_hub_seq (hub_id, issuer_nif, environment, sequence_number)` closes
/// the TOCTOU window — if two creates race, the second INSERT violates the index and ITS
/// whole transaction rolls back (no chain fork).
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
            // El command público declara el tipo que quiere y no se le toca: aquí no hay
            // degradación que anotar (la resuelve `ingest_invoice`, que sí conoce al destinatario).
            downgraded_from: String::new(),
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
            // Rectificación (R1-R5, hub#1023). `rectification_type` vacío = lo deriva el XML de
            // si vienen o no los importes rectificados; explícito (`S`/`I`) manda sobre él.
            rectifies_number: str_field(&payload, "rectifies_number"),
            rectifies_date: str_field(&payload, "rectifies_date"),
            rectifies_nif: str_field(&payload, "rectifies_nif"),
            rectification_type: str_field(&payload, "rectification_type"),
            rectified_base_amount: optional_cents(&payload, "rectified_base_amount"),
            rectified_tax_amount: optional_cents(&payload, "rectified_tax_amount"),
            rectified_surcharge_amount: optional_cents(&payload, "rectified_surcharge_amount"),
        },
    )
    .await
}

/// Un importe **opcional** en céntimos, tal cual venga: `Json::Null` cuando nadie lo escribió.
///
/// No se normaliza a `0`: en el bloque `ImporteRectificacion` la diferencia entre «no hay importe»
/// y «el importe es cero» es la diferencia entre no declarar el bloque y declarar a Hacienda que
/// se rectifica una base de cero euros (hub#324). Quien decide es `aeat::importe_rectificacion`.
fn optional_cents(payload: &Json, key: &str) -> Json {
    payload.get(key).cloned().unwrap_or(Json::Null)
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

    // Lectura acotada por id de la factura (snapshot fiscal: número oficial + importes). Los dos
    // LEFT JOIN a sí misma traen, EN LA MISMA lectura (respeta la "única lectura acotada" de
    // ADR-0058), la factura enlazada de cada caso:
    //
    // - `substitutes_invoice_id` → la F2 que una F3 sustituye (bloque XML `FacturasSustituidas`);
    // - `rectifies_invoice_id`   → la factura que una R1-R5 rectifica (`FacturasRectificadas`,
    //   hub#1023) — el camino normal de una devolución en TPV.
    //
    // NULL/'' cuando la factura no enlaza nada, que es el caso de toda venta corriente.
    let rows = host
        .read(
            "SELECT i.invoice_type, i.number, i.issue_date, i.issuer_nif, i.issuer_name, \
             i.customer_tax_id, i.customer_name, i.description, \
             i.base_amount, i.tax_amount, i.total_amount, i.tax_breakdown, \
             COALESCE(sub.number, '') AS substitutes_number, \
             COALESCE(sub.issue_date, '') AS substitutes_date, \
             COALESCE(sub.issuer_nif, '') AS substitutes_nif, \
             COALESCE(rec.number, '') AS rectifies_number, \
             COALESCE(rec.issue_date, '') AS rectifies_date, \
             COALESCE(rec.issuer_nif, '') AS rectifies_nif \
             FROM invoice_invoice i \
             LEFT JOIN invoice_invoice sub \
               ON sub.id = i.substitutes_invoice_id AND sub.hub_id = i.hub_id AND sub.is_deleted = 0 \
             LEFT JOIN invoice_invoice rec \
               ON rec.id = i.rectifies_invoice_id AND rec.hub_id = i.hub_id AND rec.is_deleted = 0 \
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

    // Destinatario de la factura: decide el TIPO antes de encadenar nada.
    let recipient_nif = str_field(&inv, "customer_tax_id");
    let declared_type = {
        let t = str_field(&inv, "invoice_type");
        if INVOICE_TYPES.contains(&t.as_str()) {
            t
        } else {
            "F1".to_string()
        }
    };
    // Sin NIF de cliente, una F1 sale sin `Destinatarios` y la AEAT la rechaza con 1189 — ya con
    // el número de cadena gastado. El tipo entra en la huella, así que se resuelve AQUÍ, antes de
    // calcularla (`resolve_invoice_type`).
    let invoice_type = resolve_invoice_type(&declared_type, &recipient_nif);
    // hub#1104: y si degradó, se ANOTA. El documento que el cliente se llevó dice una cosa y el
    // registro que se declara dice otra; que las dos verdades existan es inevitable, que nadie se
    // entere no. `build_record_output` emite el hecho y comprueba el techo de la F2.
    let downgraded_from = if invoice_type == declared_type {
        String::new()
    } else {
        declared_type
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
            downgraded_from,
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
            recipient_nif,
            recipient_name: str_field(&inv, "customer_name"),
            // F3 → FacturasSustituidas: datos de la F2 sustituida (del LEFT JOIN). Vacíos si no es F3.
            substitutes_number: str_field(&inv, "substitutes_number"),
            substitutes_date: str_field(&inv, "substitutes_date"),
            substitutes_nif: str_field(&inv, "substitutes_nif"),
            // R1-R5 → FacturasRectificadas: datos de la factura rectificada (del LEFT JOIN).
            rectifies_number: str_field(&inv, "rectifies_number"),
            rectifies_date: str_field(&inv, "rectifies_date"),
            rectifies_nif: str_field(&inv, "rectifies_nif"),
            // `invoice.rectify` emite la rectificativa **negando** el original, así que los
            // importes de esta factura SON el delta: es una rectificativa por diferencias, y el
            // XML la deriva de que no haya importes rectificados (ver `aeat::rectification_type`).
            // La sustitutiva (`S`) llega por `create_record`, que sí acepta los `rectified_*`;
            // el módulo `invoice` todavía no tiene columna que distinga los dos (invoice#5).
            rectification_type: String::new(),
            rectified_base_amount: Json::Null,
            rectified_tax_amount: Json::Null,
            rectified_surcharge_amount: Json::Null,
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
    /// Tipo que **declaraba el documento** cuando `invoice_type` es el resultado de una
    /// degradación (hub#1104), y vacío cuando nadie degradó nada.
    ///
    /// No es decorativo: es lo que convierte la degradación en un hecho observable. Con él,
    /// [`build_record_output`] emite el evento `invoice_type_downgraded` y comprueba el techo
    /// §15.8 ANTES de gastar un número de cadena.
    downgraded_from: String,
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
    /// Factura RECTIFICADA (R1-R5 → la original, hub#1023): nº+serie, fecha de expedición y NIF
    /// del emisor de la factura que esta rectificativa corrige. Alimentan el bloque XML
    /// `FacturasRectificadas` (XSD `IDFacturaARType`, el mismo shape que las sustituidas). Vacíos
    /// si el registro no rectifica nada, o si la rectificativa no identifica el original (una R5
    /// de un tique puede no hacerlo: el bloque es `minOccurs="0"`).
    rectifies_number: String,
    rectifies_date: String,
    rectifies_nif: String,
    /// `TipoRectificativa`: `S` sustitutiva · `I` por diferencias. **Vacío = lo deriva el XML**
    /// de si vienen o no los importes rectificados (`aeat::rectification_type`), que es la única
    /// lectura que admite el esquema. Un valor explícito manda sobre la derivación.
    rectification_type: String,
    /// `ImporteRectificacion` (solo en una `S`): base, cuota y —opcional— recargo **rectificados**,
    /// en CÉNTIMOS. `Json::Null` cuando no vienen: ahí «no hay importe» y «el importe es cero» son
    /// cosas distintas ante Hacienda, así que no se normalizan a `0` (hub#324).
    rectified_base_amount: Json,
    rectified_tax_amount: Json,
    rectified_surcharge_amount: Json,
}

/// Chaining core: reads the `(hub_id, issuer_nif, environment)` anchor, computes the SHA-256
/// fingerprint (exact AEAT formats) + `qr_url`, and returns the INSERT record(pending) + event
/// intentions (plus the inline transmission when a certificate is available — module active =
/// always emit, ADR-0202 guard R3).
///
/// Environment scoping (ADR-0202 guard R4, hub#313): `production` and `testing` are two
/// parallel, independent chains. The anchor, the sequence and `PrimerRegistro` never cross
/// environments — switching the config toggle starts/resumes THAT environment's own chain.
///
/// Sequence atomicity: the anchor is read before computing, and the unique index
/// `uq_verifactu_record_hub_seq (hub_id, issuer_nif, environment, sequence_number)` closes the
/// TOCTOU window — if two creates race, the second INSERT violates the index and ITS whole
/// transaction rolls back (no chain fork).
async fn build_record_output(host: &dyn NativeHost, ctx: &Ctx, r: RecordInput) -> Result<Output> {
    // ADR-0202 §4.2 (phase 0, hub#312): `NumeroInstalacion` is this hub's UUID before the AEAT
    // and can never be reused — a record built under a slug or any non-UUID id would register a
    // bogus installation that Hacienda can neither reconcile nor keep unique. Hard fail, before
    // any sequence number is consumed.
    if uuid::Uuid::parse_str(&ctx.hub_id).is_err() {
        return Err(RuntimeError::Native(format!(
            "verifactu: context.hub_id {:?} is not a UUID — NumeroInstalacion must be the hub UUID",
            ctx.hub_id
        )));
    }
    // hub#1103: **nada aritméticamente imposible se sella**. Antes de leer el ancla y ANTES de
    // gastar un número de secuencia — un registro rechazado más tarde deja el hueco igual.
    if let Some(reason) = audit_amounts(&r) {
        return Err(VerifactuError::Payload(reason).into());
    }

    // hub#1104: una F1 sin destinatario se degrada a F2 para no morir con el 1189… pero una F2
    // por encima de 3.010,00 € muere con el §15.8, y esa la habríamos FABRICADO nosotros. El techo
    // se comprueba aquí, no en `xsd::validate_registro`, porque allí llega con la cadena ya gastada.
    if !r.downgraded_from.is_empty() && r.invoice_type == "F2" {
        let declared = r.base_amount + r.tax_amount;
        if declared > xsd::F2_CEILING_CENTS as f64 {
            return Err(VerifactuError::Payload(format!(
                "f2_limit_exceeded: la factura {} se declaró {} sin NIF de destinatario, y una \
                 simplificada F2 no puede pasar de {:.2} € (§15.8) sumando base y cuota; suma \
                 {:.2} €. Identifica al destinatario para poder emitirla como factura completa",
                r.invoice_number,
                r.downgraded_from,
                xsd::F2_CEILING_CENTS as f64 / 100.0,
                declared / 100.0,
            ))
            .into());
        }
    }

    // The record joins the chain of the hub's CURRENT config environment (guard R4). Read the
    // config BEFORE the anchor: the environment scopes every chain read below (and the QR host).
    let config = read_config(host, &ctx.hub_id).await?;
    let environment = config
        .as_ref()
        .map(environment_of)
        .unwrap_or_else(|| "testing".to_string());
    // Chain anchor: last CHAINABLE row for (hub_id, issuer_nif, environment). A `rejected`
    // record is not at the AEAT, so its fingerprint cannot be the next `previous_hash` —
    // chaining there guarantees another rejection and stalls the chain (`is_chainable_status`).
    let anchor = host
        .read(
            "SELECT record_hash, sequence_number FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND is_deleted = 0 \
             AND status <> 'rejected' \
             ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": r.issuer_nif,
                "environment": environment,
            })),
        )
        .await?;
    // The SEQUENCE, instead, counts ALL rows of the environment: a rejected record already
    // spent its number and the unique index `uq_verifactu_record_hub_seq` won't reuse it.
    let sequence_number = next_sequence(host, &ctx.hub_id, &r.issuer_nif, &environment).await?;
    let (previous_hash, is_first) = match anchor.first() {
        Some(row) => (str_field(row, "record_hash"), false),
        // Sin eslabón anterior que la AEAT reconozca, este SÍ es el primero: si lo único previo
        // fue un rechazo, Hacienda no tiene nada de este emisor.
        None => (String::new(), true),
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
    // The QR host depends on the environment (testing vs production), read above.
    let qr_url = chain::qr_url(
        &r.issuer_nif,
        &r.invoice_number,
        &r.invoice_date,
        total_amount_eur,
        &environment,
    );

    let ids = &ctx.new_ids;
    if ids.len() < 3 {
        return Err(RuntimeError::Native("context.new_ids insuficientes".into()));
    }
    // `ids[0..6]` ya están repartidos (registro, evento, la ranura reservada de la vieja cola y los
    // tres de la transmisión inline). El aviso de degradación estrena la séptima para no mover
    // ninguna de las anteriores de sitio.
    const DOWNGRADE_EVENT_ID_INDEX: usize = 6;
    if !r.downgraded_from.is_empty() && ids.len() <= DOWNGRADE_EVENT_ID_INDEX {
        return Err(RuntimeError::Native(
            "context.new_ids insuficientes para anotar la degradación de tipo".into(),
        ));
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
                // Guard R4 (hub#313): explicit environment — the record joins the chain whose
                // anchor/sequence were read above; the SQL COALESCE fallback is only for older
                // engines that omit the param.
                "environment": environment,
                // F3 → FacturasSustituidas (ADR-0140): snapshot de la F2 sustituida para reconstruir
                // el XML en contingencia/reintento sin releer la factura. Vacíos si no es sustitución.
                "substitutes_number": r.substitutes_number,
                "substitutes_date": r.substitutes_date,
                "substitutes_nif": r.substitutes_nif,
                // R1-R5 → bloque rectificativo (hub#1023): mismo snapshot, mismo motivo. Un envío
                // diferido (registro creado sin certificado y remitido a mano después) reconstruye
                // el XML desde ESTA fila, así que lo que no esté aquí no llega a la AEAT.
                "rectifies_number": r.rectifies_number,
                "rectifies_date": r.rectifies_date,
                "rectifies_nif": r.rectifies_nif,
                "rectification_type": r.rectification_type,
                "rectified_base_amount": r.rectified_base_amount,
                "rectified_tax_amount": r.rectified_tax_amount,
                "rectified_surcharge_amount": r.rectified_surcharge_amount,
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

    // hub#1104: **la degradación deja de ser muda.** Va como evento propio y no como un matiz del
    // `record_created` porque es un hecho distinto y con severidad distinta: quien filtre por
    // `warning` en la pantalla de eventos —o dispare un flujo con él— tiene que encontrarlo.
    if !r.downgraded_from.is_empty() {
        output = output.with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ids[DOWNGRADE_EVENT_ID_INDEX],
                "record_id": record_id,
                "event_type": EVENT_TYPE_INVOICE_TYPE_DOWNGRADED,
                "severity": "warning",
                "message": format!(
                    "La factura {} se declaró {} y se ha registrado como {}: sin NIF de \
                     destinatario la AEAT rechaza el tipo declarado (error 1189)",
                    r.invoice_number, r.downgraded_from, r.invoice_type
                ),
                "details": json!({
                    "declared": r.downgraded_from,
                    "effective": r.invoice_type,
                    "reason": REASON_MISSING_RECIPIENT,
                    "sequence_number": sequence_number,
                }).to_string(),
                "timestamp": ctx.now,
            }),
        ));
    }

    // Module active = ALWAYS emit (ADR-0202 guard R3, verifactu#26): the `auto_transmit`
    // column was dropped in verifactu v1.5.2 — there is no deferred-transmission mode.
    // `ids[2]` stays reserved (it was the contingency queue id) so the transmit ids below
    // keep their positions.
    if let Some(cfg) = config.as_ref() {
        // Inline AEAT transmission on emit. Reuses `transmit_one`, which applies the result to
        // the record (accepted/rejected + CSV) and, on network failure, enqueues it in the
        // contingency queue with backoff. Without a configured certificate → left `pending`
        // (manual send later). Intentions apply AFTER the record INSERT (Output order).
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
                // Guard R4: `transmit_one` scopes its previous-link lookup by the record's
                // environment; the freshly built record carries the one resolved above.
                "environment": environment,
                "recipient_nif": r.recipient_nif,
                "recipient_name": r.recipient_name,
                "substitutes_number": r.substitutes_number,
                "substitutes_date": r.substitutes_date,
                "substitutes_nif": r.substitutes_nif,
                "rectifies_number": r.rectifies_number,
                "rectifies_date": r.rectifies_date,
                "rectifies_nif": r.rectifies_nif,
                "rectification_type": r.rectification_type,
                "rectified_base_amount": r.rectified_base_amount,
                "rectified_tax_amount": r.rectified_tax_amount,
                "rectified_surcharge_amount": r.rectified_surcharge_amount,
            });
            if let Ok((ops, events, _success)) =
                transmit_one(
                    host,
                    ctx,
                    &record_json,
                    cfg,
                    &ids[3],
                    &ids[4],
                    &ids[5],
                    // Alta recién creada: se remite en el momento, no sale de ninguna cola.
                    Remission::Punctual,
                )
                .await
            {
                for o in ops {
                    output = output.with_operation(o);
                }
                // A sale whose invoice the AEAT refused is the case verifactu#42 exists for: it
                // happens on the till, in front of nobody, and the audit row is on a screen.
                for e in events {
                    output = output.with_event(e);
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
/// **The public event a failed outcome emits** (verifactu#42).
///
/// One name for «this invoice did not get through and somebody has to look at it», whichever way
/// it failed — the AEAT refusing it, the wire never carrying it, the record not knowing which tax
/// agency owns it, the XML not passing the schema. `reason` tells them apart.
///
/// **One and not four**, because a trigger picks ONE event: an owner who builds «warn me when
/// something fiscal fails» and gets only the AEAT half has built the silent version of the alarm
/// they asked for. An operator who wants a single flavour filters on `reason`, which is a
/// condition step; an owner who wants all of them does nothing, which is the right default for
/// the person who loses money when it goes unnoticed.
pub const EVENT_RECORD_REJECTED: &str = "verifactu.record.rejected";

/// **Registered at the AEAT, with an error noted on it** (ADR-0189) — deliberately NOT a rejection.
///
/// Resending it is a duplicate and the AEAT refuses it (3000), so calling it a failure would send
/// the owner chasing an invoice that is already filed. But nobody opens the VeriFactu screen, and
/// an accepted-with-errors that nobody reads is a latent problem — so it gets its own word.
pub const EVENT_RECORD_ACCEPTED_WITH_ERRORS: &str = "verifactu.record.accepted_with_errors";

/// The AEAT answered, and its answer was no.
pub const REASON_AEAT_REJECTED: &str = "aeat_rejected";
/// The message never reached the AEAT (TLS, DNS, the agency down). It is queued for contingency.
pub const REASON_TRANSMISSION_FAILED: &str = "transmission_failed";
/// The record cannot say which tax agency owns it, so nothing was built and nothing was sent.
/// Same key as `Refusal::environment_unknown`, and on purpose: the refusal's stable code IS the
/// event's reason, so the panel and the automation never disagree about what went wrong.
pub const REASON_ENVIRONMENT_UNKNOWN: &str = "record_environment_unknown";
/// The envelope could not be built — an amount is missing or unreadable (hub#324). Retryable: the
/// fix is upstream data, and the record keeps its place in the queue.
pub const REASON_RECORD_NOT_DECLARABLE: &str = "record_not_declarable";
/// The XML does not meet the AEAT schema; refused locally rather than burning a chain number.
pub const REASON_XSD_INVALID: &str = "xsd_invalid";

// ── hub#1104 · la degradación de tipo deja de ser muda ────────────────────────

/// `verifactu_event.event_type` of the row that records a **downgrade of the invoice type**
/// (hub#1104).
///
/// The downgrade itself is right: an `F1` with no identified recipient travels without the
/// `Destinatarios` block and the AEAT refuses it with **1189** — after the chain number has been
/// spent. Doing it in silence is not: the document the customer took away says `F1` and the record
/// filed with the tax agency says `F2`, and nothing on any screen tells the business the two
/// disagree. ADR-0140 says fiscal state is derived, never mutated without a trace.
pub const EVENT_TYPE_INVOICE_TYPE_DOWNGRADED: &str = "invoice_type_downgraded";

/// Why the type was downgraded. Stable machine code so the screen and any automation agree, and
/// so the UI can translate the sentence instead of parsing prose (ADR-0055).
pub const REASON_MISSING_RECIPIENT: &str = "missing_recipient_aeat_1189";

/// `details.scope` of the `chain_validated`/`chain_error` event (hub#1103).
///
/// `chain.validate` recomputes SHA-256 fingerprints and verifies the chaining — and **nothing
/// else**. That is deliberate: a sealed record is immutable (RD 1007/2023), so re-auditing its
/// amounts there would inform, not prevent. What WAS a defect is a verdict that read like a
/// judgement on the amounts; the scope now travels as a stable field the UI can translate
/// (the module's `ui.recChainScope`, `en` + `es`).
pub const CHAIN_VALIDATION_SCOPE: &str = "hash_chain";

/// The public payload of a failed outcome. **Closed set, and nothing fiscal in it**: it ends up in
/// somebody's task list and in a message, so it carries what is needed to say «check invoice X»
/// and no more — never the signed XML, the chain hash, the NIF, the amounts or the CSV.
fn failure_payload(
    record: &Json,
    reason: &str,
    status: &str,
    code: &str,
    message: &str,
    environment: &str,
) -> Json {
    json!({
        "record_id": str_field(record, "id"),
        "invoice_number": str_field(record, "invoice_number"),
        "status": status,
        "reason": reason,
        "error_code": code,
        "error_message": message,
        "environment": environment,
    })
}

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

    let (ops, events, _success) = transmit_one(
        host,
        &ctx,
        &record,
        &config,
        &ctx.new_ids[0],
        &ctx.new_ids[1],
        // Id reservado para el ancla si la AEAT rechaza por encadenamiento y hay que re-anclar.
        &ctx.new_ids[2],
        // Envío puntual: `verifactu.record.transmit` remite un registro, no drena la cola.
        Remission::Punctual,
    )
    .await?;
    let mut out = Output::new();
    for o in ops {
        out = out.with_operation(o);
    }
    // El evento `verifactu.record.transmitted` lo emite el `emit` declarado del command — sale
    // pase lo que pase, porque describe el INTENTO. Lo que decide el desenlace es esto (verifactu#42).
    for e in events {
        out = out.with_event(e);
    }
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
    recovery_id: &str,
    remission: Remission,
) -> Result<(Vec<Operation>, Vec<Event>, bool)> {
    let record_id = str_field(record, "id");
    // WHERE this goes is settled BEFORE anything else happens — before the chain read, before
    // the XML, before the archive (hub#471). If the record cannot say which of the two tax
    // agencies owns it, nothing is built and nothing is sent.
    let destination = match destination_of(record, config) {
        Ok(destination) => destination,
        Err(reason) => {
            return refuse_transmission(
                host,
                ctx,
                record,
                event_id,
                queue_id,
                config,
                &Refusal::environment_unknown(reason),
            )
            .await
        }
    };
    let is_first = int_field(record, "is_first_record", 0) != 0;
    let prev = if is_first {
        None
    } else {
        // Guard R4 (hub#313): sequence numbers repeat across environments, so the previous
        // link comes from the RECORD's own environment — a retried testing record must keep
        // linking inside testing even after the hub switched its config to production.
        host.read(
            "SELECT issuer_nif, invoice_number, invoice_date, record_hash FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND sequence_number = :prev_seq \
             AND is_deleted = 0 LIMIT 1",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": str_field(record, "issuer_nif"),
                "environment": str_field(record, "environment"),
                "prev_seq": int_field(record, "sequence_number", 1) - 1,
            })),
        )
        .await?
        .into_iter()
        .next()
    };

    // En un reintento se usa EXACTAMENTE el XML del intento anterior (si ya quedó en BD), no se
    // regenera con una configuración que podría haber cambiado mientras la AEAT estaba caída.
    //
    // **Si el sobre no se puede construir, no se transmite** (hub#324): un importe ausente o
    // ilegible ya no se convierte en `0,00`. Se trata como la negativa de hub#471 —evento con
    // motivo + entrada en la cola—, NO como un rechazo: el registro se queda donde está, con su
    // XML anterior intacto, y vuelve a intentarse cuando el dato esté arreglado (FAQ §5: ningún
    // RF generado puede quedarse sin remitir).
    let xml = match record
        .get("xml_content")
        .and_then(Json::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToString::to_string)
    {
        Some(previous) => previous,
        None => match aeat::build_soap(record, config, prev.as_ref(), &ctx.hub_id) {
            Ok(xml) => xml,
            Err(e) => {
                return refuse_transmission(
                    host,
                    ctx,
                    record,
                    event_id,
                    queue_id,
                    config,
                    &Refusal::undeclarable(e.to_string()),
                )
                .await
            }
        },
    };

    // `Cabecera/Incidencia=S` cuando el envío sale de la cola de contingencia (hub#322). Se
    // estampa AQUÍ, sobre el sobre ya resuelto, y no dentro del constructor: el XML reutilizado
    // de un intento anterior se construyó cuando nadie sabía todavía que este registro acabaría
    // en la cola, y ese es justamente el caso normal de la cola. Es marca del SOBRE: el bloque
    // `RegistroAlta`/`RegistroAnulacion` —el que cubre la huella— no cambia ni un byte.
    let xml = match remission {
        Remission::Punctual => xml,
        Remission::FromContingency => aeat::stamp_contingency_incidence(&xml),
    };

    // Validación contra el esquema ANTES de tocar la red (`xsd::validate_registro`). Cuando la
    // AEAT contesta 4102 el número de cadena ya está gastado, así que un XML que no cumple no
    // puede llegar a salir. No corta el proceso: marca el registro como rechazado LOCALMENTE con
    // el motivo, para que se vea en la UI y para que un fallo de configuración no bloquee la cola
    // de contingencia entera.
    if let Err(e) = xsd::validate_registro(&xml) {
        let reason = e.to_string();
        return Ok((
            vec![
                apply_transmission(&record_id, "rejected", "XSD", &reason, "", &xml, "", 0),
                op(
                    "verifactu._insert_event",
                    json!({
                        "event_id": event_id,
                        "record_id": record_id,
                        "event_type": "transmission_failure",
                        "severity": "error",
                        "message": format!("XML no conforme al esquema de la AEAT; no se ha transmitido: {reason}"),
                        "details": json!({ "validation_error": reason }).to_string(),
                        "timestamp": ctx.now,
                    }),
                ),
            ],
            vec![Event::new(
                EVENT_RECORD_REJECTED,
                failure_payload(
                    record,
                    REASON_XSD_INVALID,
                    "rejected",
                    "XSD",
                    &reason,
                    &destination.environment,
                ),
            )],
            false,
        ));
    }

    // Archivo duradero ANTES de tocar la red. Si el backend Local/S3 no confirma la escritura, no
    // se envía: nunca aceptamos una transmisión fiscal sin conservar su XML para auditoría/reenvío.
    let xml_storage_path = archive_transmission_xml(host, &record_id, &xml).await?;
    // Identity mTLS: cert del core (opaca, bytes en el core) o legacy. Ver `build_identity`.
    let identity = build_identity(host, &ctx.hub_id, config).await?;

    match aeat::post_soap(destination.endpoint, identity, &xml).await {
        Ok(body) => {
            let resp = aeat::parse_response(&body);

            // ── Recuperación automática: SOLO si la AEAT rechazó de verdad ─────────────────
            // El caso que se quería cubrir es **restaurar un backup**: la cadena local retrocede
            // y el envío sale con `PrimerRegistro=S` cuando la AEAT ya tiene registros de ese
            // obligado y sistema informático. Se asumió que eso llegaba como rechazo. El ensayo
            // contra preproducción (2026-08-02, ADR-0189) demostró que no, y que re-enviar es lo
            // peor que se puede hacer:
            //
            //   1. La AEAT contesta `EstadoRegistro=AceptadoConErrores` + `2007` — un ACEPTADO:
            //      el registro **ya está en la AEAT** con la huella que se le calculó.
            //   2. Reenviarlo re-anclado devuelve **3000 «Registro de facturación duplicado»**, y
            //      la consulta posterior sigue mostrando una sola aparición. Ni duplica ni
            //      sustituye: rechaza.
            //
            // Por eso el disparo cuelga de `should_retransmit()` —es decir, de que el registro NO
            // esté aceptado—, y no de una lista de códigos. Un 2007 se cierra abajo como aceptado
            // **con aviso**: la cadena sigue desde él, que es lo que la AEAT tiene por último.
            // Re-anclar ANTES de emitir sigue siendo una acción explícita (`recover_from_aeat`).
            let verdict = aeat::classify(&resp);
            if verdict.should_retransmit()
                && aeat::is_chaining_rejection(&resp.codigo_error, &resp.descripcion_error)
                && !recovery_id.is_empty()
            {
                match auto_rechain_and_retry(
                    host,
                    ctx,
                    record,
                    config,
                    &destination,
                    &resp,
                    recovery_id,
                    event_id,
                    remission,
                )
                .await
                {
                    // Re-anclado y reintentado: ese es el resultado que vale.
                    Ok(Some(result)) => return Ok(result),
                    // La AEAT no dio ancla utilizable → se registra el rechazo original.
                    Ok(None) => {}
                    // La recuperación falló (consulta caída, sin certificado…). El rechazo
                    // original se registra igual, con el motivo del fallo anotado: nunca se
                    // traga en silencio.
                    Err(e) => {
                        return Ok(response_ops(
                            record,
                            &resp,
                            &destination,
                            &xml,
                            &xml_storage_path,
                            event_id,
                            &ctx.now,
                            Some(&format!("recuperación automática fallida: {e}")),
                        ))
                    }
                }
            }

            Ok(response_ops(
                record,
                &resp,
                &destination,
                &xml,
                &xml_storage_path,
                event_id,
                &ctx.now,
                None,
            ))
        }
        Err(err) => {
            // **Tercer disparador de refetch del certificado** (ADR-0202 §2 punto 4): si lo que
            // falló fue el canal TLS, el certificado con el que nos identificamos es el sospechoso
            // y hay que pedirle al plano de control el vigente. El motor no lo baja —no tiene
            // credencial de máquina ni debe tenerla—: lo PIDE, y el servicio de refetch del server
            // decide. Va justo aquí, encolando la contingencia, porque el fallo ES el disparador:
            // así se converge sin polling.
            request_certificate_refetch_on_tls(&err, &signing_kind(config), RefetchSignal::global());
            // Fallo de conexión/transporte → contingencia con backoff (WASM-TODO §5).
            let reason = err.to_string();
            let retry = enqueue_retry(host, ctx, &record_id, queue_id, config, &reason).await?;
            let environment = &destination.environment;
            let backoff_minutes = retry.backoff_minutes;
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
                        "details": json!({ "error": reason.clone(), "attempts": retry.attempts }).to_string(),
                        "timestamp": ctx.now,
                    }),
                ),
                retry.operation,
            ];
            Ok((
                ops,
                // For the owner this is the same problem as a refusal — the invoice is not at the
                // AEAT. `reason` is what tells an operator that the wire failed, not the filing.
                vec![Event::new(
                    EVENT_RECORD_REJECTED,
                    failure_payload(
                        record,
                        REASON_TRANSMISSION_FAILED,
                        "error",
                        "",
                        &reason,
                        environment,
                    ),
                )],
                false,
            ))
        }
    }
}

/// Contingency entry for a record that could NOT be remitted: attempt count + the 5/10/20/40/60
/// minute backoff (WASM-TODO §5).
///
/// Shared by the transport failure and by the hub#471 refusal, so a record that cannot be sent
/// is queued the same way whatever stopped it — the FAQ §5 invariant is that no RF may stay
/// generated and never remitted, and the queue is what makes that true.
struct Retry {
    operation: Operation,
    attempts: i64,
    backoff_minutes: i64,
}

async fn enqueue_retry(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record_id: &str,
    queue_id: &str,
    config: &Json,
    reason: &str,
) -> Result<Retry> {
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
    Ok(Retry {
        operation: op(
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
        attempts,
        backoff_minutes,
    })
}

/// **Where this send comes from**, which is what decides whether the envelope declares an
/// incidence (`Cabecera/RemisionVoluntaria/Incidencia`, hub#322).
///
/// It is passed in and not derived from the record on purpose: the caller is the only one that
/// knows. `process_contingency_queue` is draining the queue; `transmit_record` and the inline
/// transmission of `create_record` are remitting an invoice as it happens.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Remission {
    /// The record is being remitted as it is generated — the ordinary sale.
    Punctual,
    /// The record waited in the contingency queue and is going out now. This is what `Incidencia`
    /// exists for, and what makes the deferred remission legal instead of merely late.
    FromContingency,
}

/// Why a record was NOT handed to the AEAT, in the two channels the operator reads: a stable code
/// the UI can program against, and the sentence a human sees.
///
/// The code used to be the literal `record_environment_unknown`, written inside the event — which
/// worked while there was exactly one way to refuse. There are two now (hub#324 added «the record
/// cannot be declared»), and two refusals wearing the same code would have the panel telling
/// somebody to fix an environment when what is broken is an amount.
struct Refusal {
    /// Stable domain key, `<what_is_wrong>` in the module's own namespace. Never translated.
    code: &'static str,
    /// The reason as a human reads it. Also what goes into `contingencyqueue.last_error`.
    reason: String,
}

impl Refusal {
    /// The record does not say which of the two tax agencies owns it (hub#471).
    fn environment_unknown(reason: String) -> Self {
        Self {
            code: REASON_ENVIRONMENT_UNKNOWN,
            reason,
        }
    }

    /// The envelope could not be built at all: an amount is missing or unreadable (hub#324).
    /// **Retryable on purpose** — the fix is upstream data, and the record must keep its place.
    fn undeclarable(reason: String) -> Self {
        Self {
            code: REASON_RECORD_NOT_DECLARABLE,
            reason,
        }
    }
}

/// **The record does not say which AEAT owns it, so nothing is transmitted** (hub#471).
///
/// The row is deliberately left UNTOUCHED: `_apply_transmission` overwrites `xml_content` and
/// `xml_storage_path` unconditionally, and the archived XML of a record that was never sent is
/// fiscal evidence. What the refusal leaves is an `error` event with a stable reason key and a
/// contingency entry, so the record is retried once the cause is fixed and never disappears.
///
/// It returns an outcome and not an `Err` on purpose: `process_contingency_queue` propagates
/// errors with `?`, so one unresolvable row would abort the whole batch and strand every other
/// record behind it.
async fn refuse_transmission(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record: &Json,
    event_id: &str,
    queue_id: &str,
    config: &Json,
    refusal: &Refusal,
) -> Result<(Vec<Operation>, Vec<Event>, bool)> {
    let reason = refusal.reason.as_str();
    let record_id = &str_field(record, "id");
    let retry = enqueue_retry(host, ctx, record_id, queue_id, config, reason).await?;
    Ok((
        vec![
            op(
                "verifactu._insert_event",
                json!({
                    "event_id": event_id,
                    "record_id": record_id,
                    "event_type": "transmission_failure",
                    "severity": "error",
                    "message": format!("No se ha transmitido a la AEAT: {reason}"),
                    "details": json!({
                        "reason": refusal.code,
                        "error": reason,
                        "attempts": retry.attempts,
                    })
                    .to_string(),
                    "timestamp": ctx.now,
                }),
            ),
            retry.operation,
        ],
        // Nothing was handed to the AEAT — the same problem for the owner as a refusal, under the
        // reason that tells an operator the two apart. The key is `Refusal::code` and not a
        // literal: hub#324 added a second way to refuse (an envelope that cannot be built), and
        // two refusals wearing the same reason would have the alarm telling somebody to fix an
        // environment when what is broken is an amount.
        vec![Event::new(
            EVENT_RECORD_REJECTED,
            failure_payload(record, refusal.code, "error", "", reason, ""),
        )],
        false,
    ))
}

/// Intenciones que aplican una respuesta de la AEAT sobre el registro: UPDATE + evento (+ salida
/// de la cola de contingencia si fue aceptado). Compartido por el primer intento y por el
/// reintento tras re-anclar.
#[allow(clippy::too_many_arguments)]
fn response_ops(
    record: &Json,
    resp: &aeat::AeatResponse,
    destination: &Destination,
    xml: &str,
    xml_storage_path: &str,
    event_id: &str,
    now: &str,
    note: Option<&str>,
) -> (Vec<Operation>, Vec<Event>, bool) {
    let record_id = &str_field(record, "id");
    let verdict = aeat::classify(resp);
    let success = verdict.status == "accepted";
    // A record whose chain is not the hub's current environment went to the OTHER tax agency.
    // That is CORRECT — the chain owns the record — but it is never routine: it is what a
    // go-live with a non-empty queue looks like, and the owner has to be able to find it
    // (hub#471). Filed as `info`, nobody would.
    let drifted = destination.hub_environment.is_some();
    // Un `AceptadoConErrores` está registrado en la AEAT (no se reenvía), pero no puede pasar por
    // un éxito limpio: se persiste el código de la AEAT y el evento sale como aviso, no como info.
    let (event_type, severity) = match (success, verdict.accepted_with_errors || drifted) {
        (true, false) => ("transmission_success", "info"),
        (true, true) => ("transmission_warning", "warning"),
        (false, _) => ("transmission_failure", "error"),
    };
    let environment = &destination.environment;
    // The note of the caller (an automatic re-anchor, a failed recovery) and the drift note
    // travel together: both are things the operator has to read next to the AEAT verdict.
    let notes: Vec<String> = note
        .map(ToString::to_string)
        .into_iter()
        .chain(destination.drift_note())
        .collect();
    let note = (!notes.is_empty()).then(|| notes.join(" · "));
    let mut ops = vec![
        apply_transmission(
            record_id,
            verdict.status,
            &verdict.code,
            &verdict.message,
            &resp.csv,
            xml,
            xml_storage_path,
            0,
        ),
        op(
            "verifactu._insert_event",
            json!({
                "event_id": event_id,
                "record_id": record_id,
                "event_type": event_type,
                "severity": severity,
                "message": match &note {
                    Some(n) => format!("AEAT ({environment}): {} {} — {n}", resp.estado_envio, resp.estado_registro),
                    None => format!("AEAT ({environment}): {} {}", resp.estado_envio, resp.estado_registro),
                },
                "details": json!({
                    "estado_envio": resp.estado_envio,
                    "estado_registro": resp.estado_registro,
                    "csv": resp.csv,
                    "codigo_error": resp.codigo_error,
                    "descripcion_error": resp.descripcion_error,
                    "note": note,
                }).to_string(),
                "timestamp": now,
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
    // ── What LEAVES the module (verifactu#42) ────────────────────────────────────────────────
    //
    // The `_insert_event` row above is the audit trail: it is on a screen somebody has to open,
    // and the bar that closes at two in the morning does not open it. This is the outbox event an
    // automation can hang off — and it is emitted only for the two outcomes a person has to act
    // on. A clean acceptance says nothing: `verifactu.record.transmitted` already covers «it went
    // out», and one more row per successful invoice would be the till's whole day in the outbox.
    //
    // The drift note is NOT one of them. A record remitted to the other tax agency is correct
    // (the chain owns it) and it is already a `warning` in the audit trail; raising it here would
    // make «something went wrong fiscally» fire on a go-live, which is the fastest way to teach
    // an owner to ignore the alarm.
    let events = if !success {
        vec![Event::new(
            EVENT_RECORD_REJECTED,
            failure_payload(
                record,
                REASON_AEAT_REJECTED,
                verdict.status,
                &verdict.code,
                &verdict.message,
                environment,
            ),
        )]
    } else if verdict.accepted_with_errors {
        vec![Event::new(
            EVENT_RECORD_ACCEPTED_WITH_ERRORS,
            failure_payload(
                record,
                REASON_AEAT_REJECTED,
                verdict.status,
                &verdict.code,
                &verdict.message,
                environment,
            ),
        )]
    } else {
        Vec::new()
    };
    (ops, events, success)
}

/// El eslabón anterior en la forma que espera `aeat::build_soap`, a partir del ancla que devolvió
/// la AEAT. `invoice_date` llega en formato AEAT (`DD-MM-YYYY`) y `build_soap` lo re-formatea, así
/// que se normaliza a ISO aquí igual que en el resto de la recuperación.
fn anchor_as_prev(anchor: &aeat::ConsultRecord) -> Json {
    json!({
        "issuer_nif": anchor.issuer_nif,
        "invoice_number": anchor.invoice_number,
        "invoice_date": iso_date(&anchor.invoice_date),
        "record_hash": chain::normalize_hash(&anchor.record_hash),
    })
}

/// Re-ancla el registro desde lo que la AEAT tiene y lo **reintenta una vez**.
///
/// Es la recuperación automática de hub#287. Devuelve `Ok(None)` si la AEAT no dio un ancla
/// utilizable (no hay de dónde recuperar → se registra el rechazo original) y `Err` si la propia
/// recuperación falló (consulta caída, sin certificado…) — nunca en silencio.
///
/// Un solo reintento, a propósito: si el segundo envío también se rechaza, el problema no era el
/// eslabón y reintentar en bucle solo quemaría números de cadena.
#[allow(clippy::too_many_arguments)]
async fn auto_rechain_and_retry(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record: &Json,
    config: &Json,
    // Passed in, never recomputed: resolving the destination twice is how the endpoint got out
    // of step with the record in the first place (hub#320's rule, hub#471's bug).
    destination: &Destination,
    rejection: &aeat::AeatResponse,
    recovery_id: &str,
    event_id: &str,
    // El re-anclado hereda el origen del envío que lo disparó (hub#322): un registro que salió
    // de la cola sigue saliendo de la cola cuando se reintenta sobre el ancla que dio la AEAT.
    remission: Remission,
) -> Result<Option<(Vec<Operation>, Vec<Event>, bool)>> {
    let issuer_nif = str_field(record, "issuer_nif");
    // Both legs of the recovery go to the record's OWN destination (hub#471): asking the wrong
    // tax agency for the anchor would re-chain this record onto a link from the other chain,
    // which is precisely the crossing that guard R4 exists to prevent.
    let records = run_consult(
        host,
        &ctx.hub_id,
        config,
        destination.endpoint,
        &issuer_nif,
        &ctx.now,
    )
    .await?;
    let Some(anchor) = aeat::pick_latest_record(&records) else {
        return Ok(None);
    };

    // The consult ran against the RECORD's environment, so the recovered anchor belongs to
    // THAT environment's chain (guard R4).
    let environment = &destination.environment;
    // The anchor takes the next number; the rechained record, the one after.
    let anchor_seq = next_sequence(host, &ctx.hub_id, &issuer_nif, environment).await?;
    let anchor_hash = chain::normalize_hash(&anchor.record_hash);
    let anchor_op = op(
        "verifactu._insert_recovery",
        json!({
            "record_id": recovery_id,
            "sequence_number": anchor_seq,
            "issuer_nif": issuer_nif,
            "issuer_name": obligado_name(config),
            "environment": environment,
            "invoice_number": if anchor.invoice_number.is_empty() {
                format!("AEAT-{}", short(&anchor_hash))
            } else {
                anchor.invoice_number.clone()
            },
            "invoice_date": iso_date(&anchor.invoice_date),
            "description": "Ancla recuperada automáticamente tras un rechazo de encadenamiento",
            "record_hash": anchor_hash,
            "aeat_csv": anchor.csv,
        }),
    );

    let (rechained, rechain_op) = rechain_record(record, anchor, anchor_seq + 1);
    let record_id = str_field(record, "id");
    let xml = aeat::build_soap(
        &rechained,
        config,
        Some(&anchor_as_prev(anchor)),
        &ctx.hub_id,
    )?;
    let xml = match remission {
        Remission::Punctual => xml,
        Remission::FromContingency => aeat::stamp_contingency_incidence(&xml),
    };
    let xml_storage_path = archive_transmission_xml(host, &record_id, &xml).await?;
    let identity = build_identity(host, &ctx.hub_id, config).await?;
    let body = aeat::post_soap(destination.endpoint, identity, &xml).await?;
    let resp = aeat::parse_response(&body);

    let note = format!(
        "re-anclado automáticamente tras {} ({}) y reintentado sobre la huella {}…",
        if rejection.codigo_error.is_empty() {
            "rechazo de encadenamiento"
        } else {
            &rejection.codigo_error
        },
        rejection.descripcion_error.trim(),
        short(&chain::normalize_hash(&anchor.record_hash)),
    );
    let (mut ops, events, success) = response_ops(
        record,
        &resp,
        destination,
        &xml,
        &xml_storage_path,
        event_id,
        &ctx.now,
        Some(&note),
    );
    // El ancla y el re-encadenado se aplican ANTES del resultado del reintento (orden del Output).
    ops.insert(0, rechain_op);
    ops.insert(0, anchor_op);
    Ok(Some((ops, events, success)))
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
#[allow(clippy::too_many_arguments)]
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

    // 3 ids por registro (evento + cola + ancla de recuperación); reservamos 1 para el resumen.
    let max_records = (ctx.new_ids.len().saturating_sub(1)) / 3;
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
        // Tercer id: el ancla de recuperación automática. La cola de contingencia es JUSTO el
        // sitio donde engancha el reintento tras restaurar un backup (hub#287).
        let recovery_id = ctx.new_ids[id_idx + 2].clone();
        id_idx += 3;
        let (ops, events, success) = transmit_one(
            host,
            &ctx,
            &rec,
            &config,
            &event_id,
            &queue_id,
            &recovery_id,
            // ESTE es el envío que declara `Incidencia=S`: sale de la cola de contingencia.
            Remission::FromContingency,
        )
        .await?;
        for e in events {
            out = out.with_event(e);
        }
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
                // Mismo gate que la transmisión real: la prueba tiene que fallar donde falla el
                // envío de verdad, no ir a la AEAT a que lo diga con un 4102. Y si el sobre ni
                // siquiera se puede construir (hub#324), el diagnóstico lo dice aquí.
                let built = aeat::build_soap(&sample, &config, None, &ctx.hub_id);
                let checked = built.as_ref().map_err(ToString::to_string).and_then(|xml| {
                    xsd::validate_registro(xml)
                        .map(|()| xml.as_str())
                        .map_err(|e| format!("XML no conforme al esquema: {e}"))
                });
                match checked {
                    Err(error) => aeat = json!({ "ok": false, "error": error }),
                    Ok(xml) => match aeat::post_soap(transmission_endpoint(&config), identity, xml).await {
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

/// NIF del **obligado tributario** a usar: el del payload o, si falta, el `issuer_nif` de la
/// config.
///
/// Ya **no** cae a `software_nif`: ese es el NIF del PRODUCTOR del software (ERPlora), y usarlo
/// como emisor anclaría la cadena de un cliente a la identidad fiscal de ERPlora. Sin NIF del
/// obligado la operación falla, que es lo correcto: no hay cadena que consultar ni recuperar.
fn resolve_nif(payload: &Json, config: Option<&Json>) -> String {
    let n = str_field(payload, "issuer_nif");
    if !n.is_empty() {
        return n;
    }
    config
        .map(|c| str_field(c, "issuer_nif"))
        .unwrap_or_default()
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

/// Next internal sequence number for `(hub_id, issuer_nif, environment)` = max + 1.
/// Scoped per AEAT environment (guard R4): each chain numbers its own records.
async fn next_sequence(
    host: &dyn NativeHost,
    hub_id: &str,
    issuer_nif: &str,
    environment: &str,
) -> Result<i64> {
    let rows = host
        .read(
            "SELECT sequence_number FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND is_deleted = 0 \
             ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({
                "hub_id": hub_id,
                "issuer_nif": issuer_nif,
                "environment": environment,
            })),
        )
        .await?;
    Ok(rows
        .first()
        .map(|r| int_field(r, "sequence_number", 0))
        .unwrap_or(0)
        + 1)
}

/// Razón social del **OBLIGADO tributario** (el negocio del hub), que es lo que la AEAT valida
/// contra el NIF del certificado.
///
/// No es `software_name`: ese es el PRODUCTOR del software (ERPlora), fijo para todos los hubs.
/// El envelope de consulta llevaba el nombre del productor junto al NIF del negocio — dos
/// identidades distintas en el mismo `ObligadoEmision`, que la AEAT rechaza.
fn obligado_name(config: &Json) -> String {
    str_field(config, "issuer_name")
}

/// Consulta a la AEAT (TLS mutua con el cert de la config) los registros del emisor en el
/// periodo actual y los parsea. Red real — sin cert/red devuelve error (no silencioso).
///
/// The `endpoint` is a parameter and not derived here: a consult on behalf of the hub asks the
/// environment the hub is in now (`consult_endpoint_of`), while a consult on behalf of ONE
/// record asks the environment that record's chain lives in (hub#471). Same call, two owners.
async fn run_consult(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
    endpoint: &str,
    issuer_nif: &str,
    now: &str,
) -> Result<Vec<aeat::ConsultRecord>> {
    // Identity mTLS vía `build_identity`: cert del core (opaca) o legacy. Ver ADR-0079.
    let identity = build_identity(host, hub_id, config).await?;
    let issuer_name = obligado_name(config);
    let (ejercicio, periodo) = year_month(now);
    // Se construye ANTES de abrir la conexión: si falta la razón social del obligado, el sobre
    // no es válido y no tiene sentido hablar con Hacienda para llevarse un 4102.
    let xml = aeat::build_consult_soap(issuer_nif, &issuer_name, &ejercicio, &periodo)?;
    let body = aeat::post_soap(endpoint, identity, &xml).await?;
    Ok(aeat::parse_consult_response(&body)?)
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

/// Relee la cadena de `(hub_id, issuer_nif, environment)` (la del entorno ACTIVO de la config —
/// guarda R4) ordenada por secuencia, recomputa cada huella y
/// verifica el encadenamiento (`previous_hash` == huella anterior). Las filas `recovery` son
/// anclas de confianza (no se recomputan; su huella es el enlace para la siguiente). El
/// resultado se persiste como `verifactu_event` (`chain_validated`/`chain_error`) que la UI lee.
async fn validate_chain(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?;
    let issuer_nif = resolve_nif(&payload, config.as_ref());
    if issuer_nif.is_empty() {
        return Err(VerifactuError::Payload(
            "falta issuer_nif del obligado (config VeriFactu → identidad fiscal)".into(),
        )
        .into());
    }

    // Guard R4 (hub#313): validate the ACTIVE environment's chain only. `production` and
    // `testing` are parallel chains with independent sequences — interleaving them by
    // sequence number would false-flag a break in two chains that are each intact.
    let environment = config
        .as_ref()
        .map(environment_of)
        .unwrap_or_else(|| "testing".to_string());
    let rows = host
        .read(
            "SELECT id, record_type, sequence_number, issuer_nif, invoice_number, invoice_date, \
             invoice_type, tax_amount, total_amount, previous_hash, record_hash, is_first_record, \
             generation_timestamp, status FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND is_deleted = 0 \
             ORDER BY sequence_number ASC",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": issuer_nif,
                "environment": environment,
            })),
        )
        .await?;

    let mut prev_hash = String::new();
    let mut first_invalid: Option<(i64, String)> = None;
    for (idx, r) in rows.iter().enumerate() {
        let rtype = str_field(r, "record_type");
        let stored = str_field(r, "record_hash");
        // Un registro rechazado no es eslabón (`is_chainable_status`): el ancla de
        // `build_record_output` ya no cuelga de él, así que contarlo aquí marcaría rota una
        // cadena que es correcta. Ni valida su huella ni mueve `prev_hash`.
        if !is_chainable_status(&str_field(r, "status")) {
            continue;
        }
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
    // hub#1103: **el veredicto dice QUÉ verificó.** «Cadena íntegra: 27 registro(s) verificados»
    // se leyó en un informe de QA como prueba de que 27 registros aritméticamente imposibles
    // estaban bien, y ante Hacienda «íntegra» significa una cosa concreta. Lo que se comprueba
    // aquí es el encadenado de HUELLAS, y eso es lo correcto: un registro ya sellado es inmutable
    // (RD 1007/2023), así que re-auditar sus importes informaría sin evitar nada — la guarda que
    // evita el daño es `audit_amounts`, antes de sellar. El alcance viaja además en
    // `details.scope` para que la UI lo diga en el idioma del usuario (ADR-0055) en vez de
    // parsear esta frase.
    let message = if valid {
        format!(
            "Cadena de huellas íntegra: {total} registro(s) con su encadenado SHA-256 verificado \
             ({issuer_nif}). No se re-auditan los importes"
        )
    } else {
        let seq = first_invalid.as_ref().map(|x| x.0).unwrap_or(0);
        format!("Cadena de huellas ROTA en la secuencia {seq} ({issuer_nif})")
    };
    let details = json!({
        "valid": valid,
        "total": total,
        "issuer_nif": issuer_nif,
        "environment": environment,
        "scope": CHAIN_VALIDATION_SCOPE,
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
        return Err(VerifactuError::Payload(
            "falta issuer_nif del obligado (config VeriFactu → identidad fiscal)".into(),
        )
        .into());
    }
    let records = run_consult(
        host,
        &ctx.hub_id,
        &config,
        consult_endpoint_of(&config),
        &issuer_nif,
        &ctx.now,
    ).await?;
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
        return Err(VerifactuError::Payload(
            "falta issuer_nif del obligado (config VeriFactu → identidad fiscal)".into(),
        )
        .into());
    }
    let records = run_consult(
        host,
        &ctx.hub_id,
        &config,
        consult_endpoint_of(&config),
        &issuer_nif,
        &ctx.now,
    ).await?;
    if records.is_empty() {
        return Err(RuntimeError::Native(
            "la AEAT no devolvió registros para este emisor/periodo; nada que recuperar".into(),
        ));
    }
    let (ops, limit) = aeat_snapshot_ops(&ctx, &issuer_nif, &records);
    // Ancla = el registro MÁS RECIENTE por `FechaHoraHusoGenRegistro`, no el que caiga en una
    // posición: la AEAT devuelve del más nuevo al más viejo y aquí se cogía `records[0]`, que
    // acertaba por casualidad. Ver `aeat::pick_latest_record`.
    let latest = aeat::pick_latest_record(&records).ok_or_else(|| {
        RuntimeError::Native(
            "la AEAT devolvió registros pero ninguno con huella; no hay ancla que recuperar".into(),
        )
    })?;
    // Guard R4: the consult ran against the config environment's endpoint — the anchor joins
    // that environment's chain, with its own scoped sequence.
    let environment = environment_of(&config);
    let seq = next_sequence(host, &ctx.hub_id, &issuer_nif, &environment).await?;
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
                "issuer_name": obligado_name(&config),
                "environment": environment,
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
    // Guard R4: the imported anchor continues the chain of the hub's ACTIVE environment.
    let environment = config
        .as_ref()
        .map(environment_of)
        .unwrap_or_else(|| "testing".to_string());
    let seq = next_sequence(host, &ctx.hub_id, &issuer_nif, &environment).await?;
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
        .as_ref()
        .map(|c| obligado_name(c))
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
                "environment": environment,
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

    /// Host que simula un hub con certificado del negocio en el core (`_hub_certificate`). El core
    /// responde el slot que firma; las filas de la tabla siguen ahí para que el test compruebe que
    /// el módulo NO las lee (ADR-0079).
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
        async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(Some("own".to_string()))
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

    // ── hub#319: which slot signs is the CORE's answer, never the module's guess ──────────────

    /// A host that answers the certificate question the way the CORE does — with the slot that
    /// signs — and that RECORDS every SQL the engine runs, so a test can assert what the module did
    /// **not** ask the database for.
    struct SlotHost {
        signing: Option<&'static str>,
        /// What the core says the signing certificate IS (hub#470) — independent of the slot, which
        /// is the whole point: `new` leaves it `None` («cannot tell»), and the tests that care set
        /// it explicitly.
        signing_type: Option<&'static str>,
        /// Rows `_hub_certificate` would return to a module that went behind the core's back.
        stored_rows: Vec<Json>,
        seen_sql: std::sync::Mutex<Vec<String>>,
    }

    impl SlotHost {
        fn new(signing: Option<&'static str>, stored_rows: Vec<Json>) -> Self {
            Self {
                signing,
                signing_type: None,
                stored_rows,
                seen_sql: std::sync::Mutex::new(Vec::new()),
            }
        }

        /// The core also knows what the container IS. Chained so a test reads as «this slot, holding
        /// this kind of certificate».
        fn holding(mut self, certificate_type: &'static str) -> Self {
            self.signing_type = Some(certificate_type);
            self
        }
        fn sql_touching_the_certificate_table(&self) -> Vec<String> {
            self.seen_sql
                .lock()
                .unwrap()
                .iter()
                .filter(|s| s.contains("_hub_certificate"))
                .cloned()
                .collect()
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for SlotHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.seen_sql.lock().unwrap().push(sql.to_string());
            if sql.contains("_hub_certificate") {
                Ok(self.stored_rows.clone())
            } else if sql.contains("verifactu_config") {
                Ok(vec![json!({ "hub_id": "h1", "environment": "testing" })])
            } else {
                Ok(vec![])
            }
        }
        async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(self.signing.map(str::to_string))
        }
        async fn certificate_signing_type(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(self.signing_type.map(str::to_string))
        }
    }

    /// **A hub whose only certificate is the DELEGATED one can transmit** (ADR-0202 §2.1 — hub#319).
    ///
    /// `build_identity` used to demand the business's own certificate and send the user to
    /// «Ajustes → Negocio». ERPlora's certificate signs on their behalf, so the engine has to accept
    /// it — and it learns that from the core, which owns the fallback.
    #[tokio::test]
    async fn a_delegated_only_hub_can_transmit() {
        let host = SlotHost::new(Some("delegated"), vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(has_certificate(&cfg), "con el delegado el motor SÍ puede transmitir");
        assert_eq!(signing_kind(&cfg), "delegated");
    }

    /// The own certificate wins — the fallback is an ORDER, not a preference, and the engine reports
    /// the slot the core actually picked.
    #[tokio::test]
    async fn the_own_certificate_is_the_one_reported_when_both_slots_are_full() {
        let host = SlotHost::new(Some("own"), vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(has_certificate(&cfg));
        assert_eq!(signing_kind(&cfg), "own");
    }

    /// No slot at all ⇒ nothing to sign with. The engine keeps failing CLOSED.
    #[tokio::test]
    async fn a_hub_with_neither_slot_cannot_transmit() {
        let host = SlotHost::new(None, vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(!has_certificate(&cfg));
        assert_eq!(signing_kind(&cfg), "");
    }

    /// **The AEAT entry point follows what the certificate IS, as the CORE read it**
    /// (ADR-0202 §2.1 — hub#320, corrected by hub#470).
    ///
    /// The whole chain in one assertion — core → `read_config` → `certificate_type` → URL — because
    /// that is the seam #317/#318/#319 kept having to repair: the answer is fetched ONCE and
    /// travels, instead of being re-derived from `_hub_certificate` by whoever needs it next. A hub
    /// POSTing to the wrong door has every record rejected, and a rejection is not a link in the
    /// chain (ADR-0189).
    #[tokio::test]
    async fn the_entry_point_follows_what_the_certificate_is() {
        let seal = read_config(&SlotHost::new(Some("delegated"), vec![]).holding("seal"), "h1")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            transmission_endpoint(&seal),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );

        let representative = read_config(
            &SlotHost::new(Some("own"), vec![]).holding("representative"),
            "h1",
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(
            transmission_endpoint(&representative),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
    }

    /// 🔴 **The bug hub#470 closes, through the whole seam.** A hub whose DELEGATED slot holds a
    /// *representative* container — which is exactly what would happen the day ERPlora's own
    /// `.p12` (`…_R_…`) were uploaded to the control plane — must transmit through the holder's
    /// door. Routing on the slot sent it to `www10`, where the AEAT would have rejected every
    /// record of every delegated hub, one at a time and with nothing to warn anybody.
    ///
    /// And the mirror: a business that uploads its OWN entity seal reaches the seal's door. The
    /// slot no longer decides in either direction.
    #[tokio::test]
    async fn the_slot_does_not_decide_the_entry_point_in_either_direction() {
        let delegated_representative = read_config(
            &SlotHost::new(Some("delegated"), vec![]).holding("representative"),
            "h1",
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(
            signing_kind(&delegated_representative),
            "delegated",
            "the slot is still reported — it is what picks the fallback and the `Representante`"
        );
        assert_eq!(
            transmission_endpoint(&delegated_representative),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
            "a representative certificate goes to the holder's door even from the delegated slot"
        );

        let own_seal = read_config(&SlotHost::new(Some("own"), vec![]).holding("seal"), "h1")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            transmission_endpoint(&own_seal),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
            "a business's own entity seal goes to the seal's door"
        );
    }

    /// **A core that cannot vouch for the type routes to the holder's door**, and it still reports
    /// that it can sign. That is the state of every hub deployed before hub#470 whose row has no
    /// type stored and whose container the classifier cannot read — and `prewww1` is where all of
    /// them already went.
    #[tokio::test]
    async fn a_certificate_the_core_cannot_classify_keeps_the_holder_entry_point() {
        let cfg = read_config(&SlotHost::new(Some("delegated"), vec![]), "h1")
            .await
            .unwrap()
            .unwrap();
        assert!(has_certificate(&cfg), "not knowing the type does not stop it signing");
        assert_eq!(signing_type(&cfg), "");
        assert_eq!(
            transmission_endpoint(&cfg),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
    }

    /// **The seam multiplies the two axes, and neither one is allowed to swallow the other.** The
    /// certificate decides the door; the environment decides the tax agency that is actually
    /// listening. Getting the door wrong is a rejection; getting the environment wrong is a real
    /// invoice accepted where it does not belong, and a remitted record is never re-sent (ADR-0189).
    #[test]
    fn the_seam_resolves_the_environment_and_the_certificate_from_the_same_config() {
        let config = |environment: &str, certificate_type: &str| {
            json!({
                "environment": environment,
                "certificate_source": "core",
                "certificate_type": certificate_type,
            })
        };
        assert_eq!(
            transmission_endpoint(&config("production", "seal")),
            "https://www10.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&config("production", "representative")),
            "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&config("testing", "seal")),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&config("testing", "representative")),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        // An unconfigured `environment` is preproduction, on BOTH doors (`environment_of`).
        assert_eq!(
            transmission_endpoint(&json!({ "certificate_type": "seal" })),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&json!({})),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        // And the SLOT is not the axis: a config carrying only `certificate_kind` says nothing
        // about the door, which is the confusion hub#470 removed.
        assert_eq!(
            transmission_endpoint(&json!({ "certificate_kind": "delegated" })),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
    }

    /// Recovering the chain has to talk to the door that issued it: the consult resolves its entry
    /// point from the same two axes as the alta, so a hub signing with a seal can also re-anchor
    /// (hub#287).
    #[test]
    fn the_consult_and_the_transmission_share_the_entry_point() {
        for environment in ["testing", "production"] {
            for certificate_type in ["representative", "seal", "", "delegated"] {
                let cfg = json!({
                    "environment": environment,
                    "certificate_type": certificate_type,
                });
                assert_eq!(
                    consult_endpoint_of(&cfg),
                    transmission_endpoint(&cfg),
                    "({environment}, {certificate_type})"
                );
            }
        }
    }

    /// **`transmission_endpoint_for` is the same answer, from the host** — the public entry the
    /// cross-crate e2e uses (`crates/runtime/tests/certificate_type_e2e.rs`). If it ever stopped
    /// agreeing with the internal one, that e2e would be pinning a second implementation instead of
    /// the real path.
    #[tokio::test]
    async fn the_public_entry_point_helper_agrees_with_the_internal_one() {
        for certificate_type in ["seal", "representative"] {
            let host = SlotHost::new(Some("delegated"), vec![]).holding(certificate_type);
            let cfg = read_config(&host, "h1").await.unwrap().unwrap();
            assert_eq!(
                transmission_endpoint_for(&host, "h1").await.unwrap(),
                transmission_endpoint(&cfg),
                "{certificate_type}"
            );
        }
    }

    /// **The engine asks the CORE which certificate signs; it does not read the table.**
    ///
    /// `read_config` used to probe `_hub_certificate` with `SELECT … LIMIT 1` and no `kind`, which
    /// re-derived a core rule from raw SQL: with two rows it picked whichever the database handed
    /// back first, and it counted rows the core deliberately refuses to select (hub#316:
    /// «a `kind` this runtime does not know is not guessed at»). Here the table holds such a row and
    /// the core says there is nothing to sign with — the engine must believe the core, or it would
    /// try to transmit with a certificate that cannot be loaded.
    #[tokio::test]
    async fn a_slot_the_core_refuses_to_select_does_not_count_as_a_certificate() {
        let host = SlotHost::new(
            None,
            vec![json!({ "kind": "some_future_slot", "pkcs12_b64": "QUJD", "password": "secret" })],
        );
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(
            !has_certificate(&cfg),
            "la fila existe en la tabla pero el core NO firma con ella: manda el core"
        );
    }

    /// **The `.p12` and its password are never even SELECTed by the module** (ADR-0079).
    ///
    /// The old probe read `pkcs12_b64, password` just to test them for emptiness. Those columns are
    /// encrypted at rest since hub#114, but legacy rows are still plaintext — so the module was
    /// pulling the business's certificate password into its own memory to answer a yes/no question
    /// the core can answer without decrypting anything.
    #[tokio::test]
    async fn the_engine_never_selects_the_certificate_bytes_or_its_password() {
        let host = SlotHost::new(Some("own"), vec![]);
        read_config(&host, "h1").await.unwrap();
        assert!(
            host.sql_touching_the_certificate_table().is_empty(),
            "el módulo no consulta `_hub_certificate`: pregunta al core. SQL visto: {:?}",
            host.sql_touching_the_certificate_table()
        );
    }

    /// **Un host que no implementa la capacidad NO puede firmar — falla CERRADO.**
    ///
    /// El default de `NativeHost::certificate_signing_kind` es `None` a propósito, y esa decisión es
    /// de seguridad, no de comodidad: `read_config` marca `certificate_source = "core"` ante
    /// **cualquier** `Some`, así que un default con nombre —vacío o inventado— le diría al motor que
    /// puede transmitir a la AEAT sobre un host que ni siquiera sabe entregarle una identidad. Lo
    /// encontró la corrida de mutación: sustituir el default por `Ok(Some(""))` o `Ok(Some("xyzzy"))`
    /// no rompía nada.
    #[tokio::test]
    async fn a_host_without_the_certificate_capability_cannot_sign() {
        /// Lo mínimo que exige el trait: `read` y nada más.
        struct BareHost;
        #[async_trait::async_trait]
        impl NativeHost for BareHost {
            async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
                if sql.contains("verifactu_config") {
                    Ok(vec![json!({ "hub_id": "h1", "environment": "testing" })])
                } else {
                    Ok(vec![])
                }
            }
        }

        assert!(
            !can_sign(&BareHost, "h1").await.unwrap(),
            "sin la capacidad no hay con qué firmar: el motor NO transmite"
        );
        let cfg = read_config(&BareHost, "h1").await.unwrap().unwrap();
        assert!(cfg.get("certificate_source").is_none(), "y no se marca un certificado que no hay");
        assert!(build_identity(&BareHost, "h1", &cfg).await.is_err());
    }

    /// **`can_sign` IS `build_identity`'s gate, and it is pinned here too.**
    ///
    /// Its only consumer is the coherence e2e of hub#319, which lives in the `erplora-runtime`
    /// package — so a mutation run scoped to THIS package leaves it alive with nothing to say. That
    /// is a hole in the evidence, not in the code: a `pub` predicate that decides whether a hub
    /// transmits to the AEAT has to be pinned where it is defined, so it survives whatever the
    /// cross-package test does later.
    #[tokio::test]
    async fn can_sign_answers_exactly_what_build_identity_gates_on() {
        for (signing, expected) in [(Some("delegated"), true), (Some("own"), true), (None, false)] {
            let host = SlotHost::new(signing, vec![]);
            assert_eq!(
                can_sign(&host, "h1").await.unwrap(),
                expected,
                "can_sign con el slot {signing:?}"
            );
            // Y es literalmente el predicado del gate sobre la misma config: si los dos pudieran
            // diferir, el motor rechazaría lo que el runtime ya dio por bueno.
            let cfg = read_config(&host, "h1").await.unwrap().unwrap();
            assert_eq!(
                can_sign(&host, "h1").await.unwrap(),
                has_certificate(&cfg),
                "can_sign y el gate de build_identity tienen que ser la MISMA respuesta ({signing:?})"
            );
        }
    }

    /// **The error names the real cause.** «Súbelo en Ajustes → Negocio» is only half the story once
    /// a delegated certificate exists: reaching here means the business uploaded none **and** the
    /// control plane never handed one down. Telling the user only about their half sends them to a
    /// screen that cannot fix an ERPlora-side gap.
    #[tokio::test]
    async fn the_error_without_any_certificate_names_both_halves() {
        let host = SlotHost::new(None, vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        let err = build_identity(&host, "h1", &cfg).await.unwrap_err().to_string();
        assert!(err.contains("Ajustes → Negocio"), "sigue diciendo dónde subir el propio: {err}");
        assert!(
            err.to_lowercase().contains("erplora"),
            "y que ERPlora tampoco entregó uno delegado: {err}"
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

    /// Host que devuelve una **rectificativa** (R5 de un tique) con los datos de la factura que
    /// rectifica, tal y como los trae el `LEFT JOIN` por `rectifies_invoice_id`. Guarda el SQL
    /// para poder comprobar que la lectura los pide.
    struct RectifyingInvoiceHost {
        reads: std::sync::Mutex<Vec<String>>,
    }
    impl RectifyingInvoiceHost {
        fn new() -> Self {
            Self { reads: std::sync::Mutex::new(Vec::new()) }
        }
    }
    #[async_trait::async_trait]
    impl NativeHost for RectifyingInvoiceHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.reads.lock().unwrap().push(sql.to_string());
            if sql.contains("FROM invoice_invoice") {
                return Ok(vec![json!({
                    "invoice_type": "R5", "number": "RECT-2026-000001",
                    "issue_date": "2026-08-20", "issuer_nif": "B27593136",
                    "issuer_name": "ERPLORA CLOUD SL",
                    "customer_tax_id": "", "customer_name": "",
                    "description": "Devolución", "base_amount": -1000,
                    "tax_amount": -210, "total_amount": -1210,
                    "tax_breakdown": r#"{"21.00":{"base":-1000,"tax":-210}}"#,
                    "substitutes_number": "", "substitutes_date": "", "substitutes_nif": "",
                    "rectifies_number": "TICKET-2026-000001",
                    "rectifies_date": "2026-08-02",
                    "rectifies_nif": "B27593136"
                })]);
            }
            Ok(vec![])
        }
    }

    /// hub#1023: una rectificativa nacida de una devolución tiene que llegar al XML con el enlace
    /// a la factura que rectifica. El dato viaja en la MISMA lectura acotada (ADR-0058), por el
    /// `LEFT JOIN` a `rectifies_invoice_id` — igual que la F3 hace con `substitutes_invoice_id`.
    #[tokio::test]
    async fn ingest_invoice_carries_the_rectified_invoice() {
        let host = RectifyingInvoiceHost::new();
        let input = json!({
            "payload": { "new_id": "inv-r1" },
            "context": {
                "hub_id": "3f2a1b4c-5d6e-4f70-8192-a3b4c5d6e7f8",
                "now": "2026-08-20T10:00:00+02:00", "current_user_id": "u1",
                "new_ids": ["id-rec", "id-evt", "id-queue", "id-t1", "id-t2", "id-t3"]
            }
        });
        let out = ingest_invoice(&input, &host).await.expect("la R5 se ingesta");

        let sql = host.reads.lock().unwrap().join("\n");
        assert!(
            sql.contains("rectifies_invoice_id"),
            "la lectura de la factura tiene que traer la rectificada: {sql}"
        );

        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        for (field, expected) in [
            ("invoice_type", json!("R5")),
            ("rectifies_number", json!("TICKET-2026-000001")),
            ("rectifies_date", json!("2026-08-02")),
            ("rectifies_nif", json!("B27593136")),
        ] {
            assert_eq!(
                insert.params.get(field),
                Some(&expected),
                "el registro tiene que llevar `{field}`"
            );
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

#[cfg(test)]
mod environment_chain_tests {
    //! ADR-0202 phase 1, guard R4 (hub#313): the hash chain is scoped by AEAT environment.
    //! `production` and `testing` are two parallel, independent chains — the anchor, the
    //! sequence and `PrimerRegistro` never cross environments, and the engine passes the
    //! explicit `:environment` param to the module's insert SQL.
    //!
    //! And the same scope reaches the WIRE (hub#471): the endpoint a record is POSTed to is
    //! the one its own chain lives in, so a record that waited in the queue across a go-live
    //! is still remitted to the tax agency that owns it.

    use super::*;
    use std::sync::Mutex;

    /// A hub UUID (the engine hard-fails on non-UUID hub ids — ADR-0202 §4.2).
    const HUB: &str = "7b2f8a44-9c1d-4e2f-8a3b-944445555666";
    const NIF: &str = "B12345678";
    /// 64-hex hashes so anything that validates hash shape accepts them.
    const HASH_TESTING_1: &str = "1111111111111111111111111111111111111111111111111111111111111111";
    const HASH_TESTING_2: &str = "2222222222222222222222222222222222222222222222222222222222222222";
    const HASH_PRODUCTION_1: &str =
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

    /// In-memory `verifactu_record` table that honours EXACTLY the WHERE clauses present in
    /// the SQL it receives — like a real database, it only filters by `environment` when the
    /// query asks for it. That is what makes the red case honest: an unscoped anchor query
    /// sees BOTH chains.
    struct ChainHost {
        config: Json,
        records: Vec<Json>,
        /// Contingency entries, so a batch drain can be driven end to end (hub#471).
        queue: Vec<Json>,
        has_core_certificate: bool,
        reads: Mutex<Vec<(String, Params)>>,
        /// Every XML this engine archived, in order.
        ///
        /// It is the honest observation point for «what was about to be transmitted»: the archive
        /// happens **after** the envelope is final and **before** the network is touched, and a
        /// transmission that cannot be archived is never sent. Asserting here needs neither a
        /// fake AEAT nor a certificate.
        archived: Mutex<Vec<String>>,
    }

    impl ChainHost {
        fn new(config: Json, records: Vec<Json>) -> Self {
            ChainHost {
                config,
                records,
                queue: Vec::new(),
                has_core_certificate: false,
                reads: Mutex::new(Vec::new()),
                archived: Mutex::new(Vec::new()),
            }
        }

        /// The XML of the FIRST transmission this host archived.
        fn first_archived(&self) -> String {
            self.archived
                .lock()
                .unwrap()
                .first()
                .cloned()
                .expect("nothing was archived, so nothing was about to be transmitted")
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for ChainHost {
        async fn read(&self, sql: &str, p: &Params) -> Result<Vec<Json>> {
            self.reads
                .lock()
                .unwrap()
                .push((sql.to_string(), p.clone()));
            if sql.contains("FROM verifactu_config") {
                return Ok(vec![self.config.clone()]);
            }
            if sql.contains("FROM verifactu_contingencyqueue") {
                return Ok(self.queue.clone());
            }
            if sql.contains("FROM verifactu_record") {
                let param = |k: &str| p.get(k).cloned().unwrap_or(Json::Null);
                let mut rows: Vec<Json> = self
                    .records
                    .iter()
                    .filter(|r| {
                        let mut keep = true;
                        if sql.contains("hub_id = :hub_id") {
                            keep &= r["hub_id"] == param("hub_id");
                        }
                        if sql.contains("issuer_nif = :issuer_nif") {
                            keep &= r["issuer_nif"] == param("issuer_nif");
                        }
                        if sql.contains("environment = :environment") {
                            keep &= r["environment"] == param("environment");
                        }
                        if sql.contains("status <> 'rejected'") {
                            keep &= r["status"] != "rejected";
                        }
                        if sql.contains("sequence_number = :prev_seq") {
                            keep &= r["sequence_number"] == param("prev_seq");
                        }
                        if sql.contains("id = :record_id") {
                            keep &= r["id"] == param("record_id");
                        }
                        keep
                    })
                    .cloned()
                    .collect();
                if sql.contains("ORDER BY sequence_number DESC") {
                    rows.sort_by_key(|r| {
                        std::cmp::Reverse(r["sequence_number"].as_i64().unwrap_or(0))
                    });
                } else if sql.contains("ORDER BY sequence_number ASC") {
                    rows.sort_by_key(|r| r["sequence_number"].as_i64().unwrap_or(0));
                }
                if sql.contains("LIMIT 1") {
                    rows.truncate(1);
                }
                return Ok(rows);
            }
            Ok(vec![])
        }

        /// The certificate question is the CORE's to answer (hub#319) — the engine no longer
        /// queries `_hub_certificate`, so the fixture stops pretending to be that table. `own`,
        /// because these tests are about the CHAIN and not about which certificate signs.
        async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(self.has_core_certificate.then(|| "own".to_string()))
        }

        /// The manufacturer's facts as the control plane serves them (hub#323). Without them no
        /// envelope can be built at all, so a fixture that transmits has to answer this.
        async fn producer_facts(&self) -> Result<Option<Json>> {
            Ok(Some(json!({
                "NombreRazon": "ERPLORA CLOUD SL",
                "NIF": "B27593136",
                "NombreSistemaInformatico": "ERPlora Hub",
                "IdSistemaInformatico": "EC",
                "TipoUsoPosibleSoloVerifactu": "S",
                "TipoUsoPosibleMultiOT": "S",
                "IndicadorMultiplesOT": "N",
            })))
        }

        async fn write_static_file(
            &self,
            relative_path: &str,
            bytes: &[u8],
            _content_type: &str,
        ) -> Result<String> {
            self.archived
                .lock()
                .unwrap()
                .push(String::from_utf8_lossy(bytes).into_owned());
            Ok(format!("modules/verifactu/{relative_path}"))
        }
    }

    fn config_row(environment: &str) -> Json {
        json!({ "hub_id": HUB, "environment": environment, "issuer_nif": NIF,
                "issuer_name": "Test Business SL" })
    }

    /// A minimal chain row as the post-008 schema stores it (every row carries `environment`).
    fn chain_row(id: &str, seq: i64, environment: &str, hash: &str, prev: &str) -> Json {
        json!({
            "id": id, "hub_id": HUB, "issuer_nif": NIF, "issuer_name": "Test Business SL",
            "environment": environment, "sequence_number": seq,
            "record_type": "alta", "invoice_number": format!("INV-{seq}"),
            "invoice_date": "2026-08-01", "invoice_type": "F2",
            "base_amount": 10000, "tax_rate": 21.0, "tax_amount": 2100, "total_amount": 12100,
            "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
            "previous_hash": prev, "record_hash": hash,
            "is_first_record": if prev.is_empty() { 1 } else { 0 },
            "generation_timestamp": "2026-08-01T10:00:00+02:00",
            "status": "accepted", "xml_content": "", "is_deleted": 0
        })
    }

    fn create_input() -> Json {
        json!({
            "payload": {
                "record_type": "alta", "issuer_nif": NIF, "issuer_name": "Test Business SL",
                "invoice_number": "F-2026-000123", "invoice_date": "2026-08-06",
                "invoice_type": "F2", "base_amount": 10000, "tax_rate": 21.0,
                "tax_amount": 2100, "total_amount": 12100,
                "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#
            },
            "context": {
                "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00", "current_user_id": "u1",
                "new_ids": ["id-rec", "id-evt", "id-queue", "id-t1", "id-t2", "id-t3"]
            }
        })
    }

    fn find_op<'a>(out: &'a Output, command: &str) -> &'a Operation {
        out.operations
            .iter()
            .find(|o| o.command == command)
            .unwrap_or_else(|| panic!("expected an `{command}` operation"))
    }

    /// TDD red case of hub#313: with records only in `testing`, the FIRST `production`
    /// record starts its OWN chain — `PrimerRegistro=S` (is_first_record=1), empty
    /// `previous_hash`, sequence 1 — and stamps the explicit `environment` param.
    #[tokio::test]
    async fn first_production_record_starts_a_new_chain_despite_testing_records() {
        let host = ChainHost::new(
            config_row("production"),
            vec![chain_row("t1", 1, "testing", HASH_TESTING_1, "")],
        );
        let out = create_record(&create_input(), &host).await.unwrap();

        let insert = find_op(&out, "verifactu._insert_record");
        assert_eq!(
            insert.params.get("is_first_record"),
            Some(&json!(1)),
            "the first production record must open its own chain (PrimerRegistro=S)"
        );
        assert_eq!(
            insert.params.get("previous_hash"),
            Some(&json!("")),
            "a testing hash must never be the previous link of a production record"
        );
        assert_eq!(
            insert.params.get("sequence_number"),
            Some(&json!(1)),
            "the production sequence starts at 1, independent of testing"
        );
        assert_eq!(
            insert.params.get("environment"),
            Some(&json!("production")),
            "the engine must pass the explicit :environment param (no COALESCE fallback)"
        );
        // R3 pin (verifactu#26): module active = always emit; the schema no longer has
        // `auto_transmit`, so nothing may enqueue a deferred-transmission entry on create.
        assert!(
            !out.operations
                .iter()
                .any(|o| o.command == "verifactu._enqueue_contingency"),
            "create must not enqueue contingency: auto_transmit is gone (R3)"
        );
    }

    /// Switching back to an environment RESUMES that environment's own chain: the anchor is
    /// the last chainable row of the ACTIVE environment, even when the other chain is longer.
    #[tokio::test]
    async fn chaining_resumes_the_active_environment_chain_and_never_crosses() {
        let host = ChainHost::new(
            config_row("production"),
            vec![
                chain_row("t1", 1, "testing", HASH_TESTING_1, ""),
                chain_row("t2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1),
                chain_row("p1", 1, "production", HASH_PRODUCTION_1, ""),
            ],
        );
        let out = create_record(&create_input(), &host).await.unwrap();

        let insert = find_op(&out, "verifactu._insert_record");
        assert_eq!(
            insert.params.get("previous_hash"),
            Some(&json!(HASH_PRODUCTION_1)),
            "the anchor must be production's last link, not testing's (longer) chain"
        );
        assert_eq!(
            insert.params.get("sequence_number"),
            Some(&json!(2)),
            "the production sequence resumes at 2 even though testing is at 2 already"
        );
        assert_eq!(insert.params.get("is_first_record"), Some(&json!(0)));
        assert_eq!(insert.params.get("environment"), Some(&json!("production")));
    }

    /// Recovery anchors join the chain of the ACTIVE environment: scoped sequence and an
    /// explicit `environment` param on `_insert_recovery`.
    #[tokio::test]
    async fn recovery_anchor_is_scoped_and_stamped_with_the_active_environment() {
        let host = ChainHost::new(
            config_row("production"),
            vec![
                chain_row("t1", 1, "testing", HASH_TESTING_1, ""),
                chain_row("t2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1),
            ],
        );
        let input = json!({
            "payload": { "record_hash": HASH_TESTING_2 },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1", "new_ids": ["id-anchor", "id-evt"] }
        });
        let out = recover_manual(&input, &host).await.unwrap();

        let recovery = find_op(&out, "verifactu._insert_recovery");
        assert_eq!(
            recovery.params.get("sequence_number"),
            Some(&json!(1)),
            "the anchor takes production's next sequence (1), not testing's (3)"
        );
        assert_eq!(
            recovery.params.get("environment"),
            Some(&json!("production")),
            "the recovery insert must carry the explicit :environment param"
        );
    }

    /// Chain validation walks ONLY the active environment's chain: with a valid chain in each
    /// environment, interleaving them by sequence number would false-flag a break.
    #[tokio::test]
    async fn validate_chain_walks_only_the_active_environment() {
        let ts1 = "2026-08-01T10:00:00+02:00";
        let ts2 = "2026-08-02T10:00:00+02:00";
        // Real hashes so the walk's recompute matches (amounts in cents → euros /100).
        let t1_hash = chain::alta_hash(NIF, "INV-1", "2026-08-01", "F2", 21.0, 121.0, "", ts1);
        let t2_hash =
            chain::alta_hash(NIF, "INV-2", "2026-08-01", "F2", 21.0, 121.0, &t1_hash, ts2);
        let mut t1 = chain_row("t1", 1, "testing", &t1_hash, "");
        t1["generation_timestamp"] = json!(ts1);
        let mut t2 = chain_row("t2", 2, "testing", &t2_hash, t1_hash.as_str());
        t2["generation_timestamp"] = json!(ts2);
        // A parallel, self-consistent production chain that would break the walk if mixed in.
        let p1 = chain_row("p1", 1, "production", HASH_PRODUCTION_1, "");

        let host = ChainHost::new(config_row("testing"), vec![t1, p1, t2]);
        let input = json!({
            "payload": {},
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1", "new_ids": ["id-evt"] }
        });
        let out = validate_chain(&input, &host).await.unwrap();

        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(
            event.params.get("event_type"),
            Some(&json!("chain_validated")),
            "both per-environment chains are valid; mixing them is what breaks"
        );
        let details: Json =
            serde_json::from_str(event.params.get("details").and_then(Json::as_str).unwrap())
                .unwrap();
        assert_eq!(details["valid"], json!(true));
        assert_eq!(
            details["total"],
            json!(2),
            "only the 2 testing rows belong to the validated chain"
        );
    }

    /// Retransmission reads the previous link from the RECORD's own environment — sequence
    /// numbers repeat across environments, so an unscoped `prev_seq` lookup can pick the
    /// other chain's row. The record's stored environment wins over the hub's current config.
    #[tokio::test]
    async fn transmit_previous_link_lookup_is_scoped_to_the_records_environment() {
        let mut record = chain_row("rec-2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1);
        record["status"] = json!("pending");
        let mut host = ChainHost::new(
            // The hub has ALREADY switched to production; the retried record is testing.
            config_row("production"),
            vec![
                // Inserted first so an UNSCOPED lookup (stable order, LIMIT 1) picks it.
                chain_row("p1", 1, "production", HASH_PRODUCTION_1, ""),
                chain_row("t1", 1, "testing", HASH_TESTING_1, ""),
                record,
            ],
        );
        host.has_core_certificate = true; // pass the certificate gate before transmit_one
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });
        // The flow errs later (no real mTLS identity in tests) — the prev-link read under
        // scrutiny happens before that, so the outcome itself is irrelevant here.
        let _ = transmit_record(&input, &host).await;

        let reads = host.reads.lock().unwrap();
        let (sql, params) = reads
            .iter()
            .find(|(sql, _)| sql.contains(":prev_seq"))
            .expect("transmit must look up the previous link");
        assert!(
            sql.contains("environment = :environment"),
            "the previous-link lookup must filter by environment: {sql}"
        );
        assert_eq!(
            params.get("environment"),
            Some(&json!("testing")),
            "the RECORD's environment scopes the lookup, not the current config's"
        );
    }

    // ── hub#471: the ENVIRONMENT travels with the RECORD, the DOOR with today's config ──────
    //
    // R4 scoped the chain by environment but the wire kept reading the config, so the three
    // things that describe one transmission disagreed: the previous link and the frozen XML
    // said `testing` and the URL said `production`. The two axes of the endpoint fail in
    // opposite ways — a wrong door is REJECTED (loud, fixable one record at a time), a wrong
    // environment is ACCEPTED by a tax agency that was never meant to receive it, and an
    // accepted record is neither resent nor deleted (ADR-0189).
    //
    // The URLs are spelled out on purpose: deriving them from `aeat::endpoint` here would make
    // these tests agree with the code by construction instead of pinning the destination.
    //
    // ⚠️ Coverage boundary, unchanged since hub#320: the four call sites that live BEHIND the
    // socket (`post_soap`/`run_consult` inside `transmit_one` and `auto_rechain_and_retry`) are
    // not reachable from a unit test — `build_identity` needs a real mTLS identity, and driving
    // them further would mean opening a connection to Hacienda from `cargo test`. What is pinned
    // here is the VALUE those call sites are handed; that they keep being handed it is review.
    const PREPRODUCTION_HOLDER: &str =
        "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
    const PRODUCTION_HOLDER: &str =
        "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
    const PREPRODUCTION_SEAL: &str =
        "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";

    /// The record that outlived a go-live: chained in `testing`, XML frozen from that attempt,
    /// still queued when the operator flipped the hub to `production`.
    fn queued_testing_record() -> Json {
        let mut record = chain_row("rec-2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1);
        record["status"] = json!("pending");
        // `DescripcionOperacion` is required and must not be empty (`xsd::REQUIRED_ALTA`).
        // Without it the XSD gate refuses the record BEFORE the envelope is archived, and a test
        // asserting on what was about to be transmitted would find nothing at all.
        record["description"] = json!("Ticket");
        record
    }

    /// 🔴 The bug of hub#471: draining that queue after the go-live POSTed a PRACTICE record to
    /// the real AEAT. Nothing undoes that — a remitted record is never resent nor deleted.
    #[test]
    fn a_record_queued_in_testing_is_never_posted_to_the_real_aeat_after_a_go_live() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        assert_eq!(
            destination.endpoint, PREPRODUCTION_HOLDER,
            "the record belongs to the testing chain, so preproduction is the tax agency that \
             must receive it — whatever the hub's config says today"
        );
        assert_eq!(destination.environment, "testing");
    }

    /// The mirror image, and the one that breaks the LAW rather than the sandbox: a real sale
    /// queued before someone flipped the toggle back must still reach the real AEAT. Sent to
    /// preproduction it would be marked accepted here and be an orphan RF there (FAQ §5).
    #[test]
    fn a_record_queued_in_production_still_reaches_the_real_aeat_after_a_rollback() {
        let mut record = chain_row("prod-2", 2, "production", HASH_TESTING_2, HASH_PRODUCTION_1);
        record["status"] = json!("pending");

        let destination = destination_of(&record, &config_row("testing"))
            .expect("a record that carries its environment resolves");

        assert_eq!(
            destination.endpoint, PRODUCTION_HOLDER,
            "a real invoice belongs to the real chain; a hub back in testing does not move it"
        );
        assert_eq!(destination.environment, "production");
    }

    /// The two axes come from different places ON PURPOSE, and both survive together: the
    /// environment from the record (its chain), the door from the certificate signing TODAY
    /// (hub#320 — the AEAT segregates by the certificate presented in the TLS handshake, so a
    /// record that waited days goes through the door of whatever signs now).
    ///
    /// The door axis is the certificate's **TYPE**, not the slot it came from (hub#470): `delegated`
    /// says the control plane handed the container down, and ERPlora's own `.p12` is a
    /// *representative* certificate — routing on the slot would have sent the whole delegated fleet
    /// to `www10` and had every record rejected.
    #[test]
    fn the_door_follows_todays_certificate_while_the_environment_follows_the_record() {
        let mut config = config_row("production");
        config["certificate_type"] = json!("seal");

        let destination = destination_of(&queued_testing_record(), &config)
            .expect("a record that carries its environment resolves");

        assert_eq!(
            destination.endpoint, PREPRODUCTION_SEAL,
            "preproduction because of the RECORD, the seal door because of TODAY's certificate"
        );

        // And the SLOT alone moves nothing: a delegated container that is not a seal keeps the
        // holder's door, on the very same record.
        let mut slot_only = config_row("production");
        slot_only["certificate_kind"] = json!("delegated");
        assert_eq!(
            destination_of(&queued_testing_record(), &slot_only)
                .expect("a record that carries its environment resolves")
                .endpoint,
            PREPRODUCTION_HOLDER,
            "the slot is not the door axis (hub#470)"
        );
    }

    /// A record that does not say which of the two tax agencies owns it is NOT sent. Both
    /// guesses are unrecoverable — a practice record accepted by the real AEAT, or a real
    /// invoice the real AEAT never receives — so the engine refuses instead of picking one.
    #[test]
    fn a_record_that_does_not_say_which_aeat_owns_it_is_never_transmitted() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");

        let refusal = destination_of(&record, &config_row("production"))
            .expect_err("an unstamped record has no provable destination");

        assert!(
            refusal.contains("production"),
            "the refusal must name the environment the hub is in, so the owner can act: {refusal}"
        );
    }

    /// The refusal is loud and LOSSLESS: an `error` event with a stable reason, the record put
    /// back in the contingency queue, and — critically — no `_apply_transmission`, which
    /// overwrites `xml_content`/`xml_storage_path` unconditionally and would erase the archived
    /// XML of a record that was never sent.
    #[tokio::test]
    async fn the_refusal_queues_the_record_and_never_touches_its_archived_xml() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");
        let mut host = ChainHost::new(config_row("production"), vec![record]);
        host.has_core_certificate = true; // clear the certificate gate: the refusal is earlier
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("the refusal is an outcome, not an error: one bad row must not abort a batch");

        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(event.params.get("severity"), Some(&json!("error")));
        let details: Json =
            serde_json::from_str(event.params.get("details").and_then(Json::as_str).unwrap())
                .unwrap();
        assert_eq!(
            details["reason"],
            json!("record_environment_unknown"),
            "a stable reason key, so the queue-depth alerting can tell this apart from an outage"
        );
        let queued = find_op(&out, "verifactu._enqueue_contingency");
        assert_eq!(
            queued.params.get("record_id"),
            Some(&json!("rec-2")),
            "the refused record has to stay in the queue: an RF may never be left generated and \
             never remitted (FAQ §5)"
        );
        assert_eq!(queued.params.get("queue_status"), Some(&json!("retrying")));
        assert!(
            !out.operations
                .iter()
                .any(|o| o.command == "verifactu._apply_transmission"),
            "nothing was transmitted, so nothing may overwrite the record's archived XML"
        );
    }

    // ── hub#322: the envelope says whether it comes out of the contingency queue ─────────────
    //
    // Both tests stop at the same place, on purpose: the envelope is archived BEFORE the network
    // is opened, and this host has no certificate to sign with, so the run dies right after the
    // archive. What was archived is exactly what was about to be handed to the AEAT — no fake
    // tax agency and no `.p12` needed to assert on it.

    fn contingency_input() -> Json {
        json!({
            "payload": {},
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor", "id-summary"] }
        })
    }

    /// 🔴 The defect: a record that spent the outage in the queue was remitted looking punctual.
    /// `Incidencia` is what legalises a deferred remission, and no envelope carried it.
    #[tokio::test]
    async fn a_record_drained_from_the_queue_declares_the_incidence() {
        let mut host = ChainHost::new(config_row("testing"), vec![queued_testing_record()]);
        host.has_core_certificate = true;
        host.queue = vec![json!({ "record_id": "rec-2" })];

        let _ = process_contingency_queue(&contingency_input(), &host).await;

        let sent = host.first_archived();
        assert!(
            sent.contains(
                "<sum1:RemisionVoluntaria><sum1:Incidencia>S</sum1:Incidencia>\
                 </sum1:RemisionVoluntaria>"
            ),
            "an envelope out of the queue declares the incidence: {sent}"
        );
    }

    /// The other half, and the one that keeps the flag meaningful: an ordinary sale is a punctual
    /// remission and declares NO incidence. Stamping every envelope would say nothing at all.
    #[tokio::test]
    async fn an_ordinary_transmission_declares_no_incidence() {
        let mut host = ChainHost::new(config_row("testing"), vec![queued_testing_record()]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let _ = transmit_record(&input, &host).await;

        let sent = host.first_archived();
        assert!(!sent.contains("Incidencia"), "{sent}");
        assert!(!sent.contains("RemisionVoluntaria"), "{sent}");
    }

    /// **The flag is the ENVELOPE's, and the record knows nothing about it** (the caveat of #322).
    ///
    /// The same invoice remitted punctually and remitted out of the queue is the SAME record —
    /// same fields, same fingerprint, same chain link — and only its envelope differs. So the
    /// incidence must live in the `Cabecera` and nowhere inside `RegistroFactura`, which is the
    /// half the fingerprint covers.
    ///
    /// (What DOES carry it afterwards is `xml_content`, and that is the point: the column is the
    /// evidence of what was actually transmitted, and the next retry reuses it verbatim.)
    #[tokio::test]
    async fn the_incidence_lives_in_the_header_and_not_in_the_record() {
        let mut host = ChainHost::new(config_row("testing"), vec![queued_testing_record()]);
        host.has_core_certificate = true;
        host.queue = vec![json!({ "record_id": "rec-2" })];

        let _ = process_contingency_queue(&contingency_input(), &host).await;

        let sent = host.first_archived();
        let registro_start = sent.find("<sum:RegistroFactura>").expect("RegistroFactura");
        assert!(
            sent[..registro_start].contains("<sum1:Incidencia>S</sum1:Incidencia>"),
            "the header declares it: {sent}"
        );
        assert!(
            !sent[registro_start..].contains("Incidencia"),
            "and the record does not — the fingerprint covers that block: {sent}"
        );
    }

    /// **A record whose amounts cannot be read is not transmitted either** (hub#324).
    ///
    /// It lands on the SAME refusal as hub#471 and for the same reason: nothing is sent, nothing
    /// overwrites the row, and the record keeps its place in the queue. What it must NOT do is
    /// what the old `unwrap_or(0.0)` did — build an envelope declaring `0,00`, hand it to the AEAT
    /// and have it accepted. That is unrecoverable: the record is remitted, fingerprinted and
    /// chained, and the AEAT neither replaces nor deletes it (ADR-0189).
    #[tokio::test]
    async fn a_record_with_an_unreadable_amount_is_refused_not_declared_as_zero() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("total_amount");
        let mut host = ChainHost::new(config_row("testing"), vec![record]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("an undeclarable record is an outcome, not an aborted batch");

        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(event.params.get("severity"), Some(&json!("error")));
        let details: Json =
            serde_json::from_str(event.params.get("details").and_then(Json::as_str).unwrap())
                .unwrap();
        assert_eq!(
            details["reason"],
            json!("record_not_declarable"),
            "its OWN key: telling this apart from an environment it cannot resolve is what \
             decides whether somebody goes to look at the invoice or at the config"
        );
        assert!(
            details["error"].as_str().unwrap_or_default().contains("total_amount"),
            "the operator has to be told WHICH amount: {details}"
        );
        assert_eq!(
            find_op(&out, "verifactu._enqueue_contingency")
                .params
                .get("record_id"),
            Some(&json!("rec-2")),
            "an RF may never be left generated and never remitted (FAQ §5)"
        );
        assert!(
            !out.operations
                .iter()
                .any(|o| o.command == "verifactu._apply_transmission"),
            "nothing was built and nothing was sent, so nothing may touch the record"
        );
    }

    /// The refusal is per-record, not per-batch: a row nobody can place must not strand every
    /// other record behind it. That is why it is an outcome and not an `Err` —
    /// `process_contingency_queue` propagates errors with `?`.
    #[tokio::test]
    async fn one_unplaceable_record_does_not_abort_the_contingency_batch() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");
        let mut host = ChainHost::new(config_row("production"), vec![record]);
        host.has_core_certificate = true;
        host.queue = vec![json!({ "record_id": "rec-2", "attempts": 2 })];
        let input = json!({
            "payload": {},
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor", "id-summary"] }
        });

        let out = process_contingency_queue(&input, &host)
            .await
            .expect("the batch must survive a record it cannot place");

        let summary = out
            .operations
            .iter()
            .find(|o| o.params.get("event_type") == Some(&json!("contingency_processed")))
            .expect("the batch must still report a summary");
        let details: Json =
            serde_json::from_str(summary.params.get("details").and_then(Json::as_str).unwrap())
                .unwrap();
        assert_eq!(
            details["failed"], json!(1),
            "a record that could not be placed counts as failed, never as sent"
        );
        assert_eq!(details["successful"], json!(0));
    }

    /// When the automatic re-anchor of hub#287 lands on a record that also outlived a go-live,
    /// the operator needs BOTH facts in the same line: what was re-chained, and which tax agency
    /// actually got it. Keeping only the first note would hide the one nobody expects.
    #[test]
    fn the_rechain_note_and_the_drift_note_travel_together() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            Some("re-anclado automáticamente tras 4102"),
        );

        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default();
        assert!(
            message.contains("re-anclado automáticamente tras 4102"),
            "the caller's note must survive: {message}"
        );
        assert!(
            message.contains("remitido a «testing»"),
            "and so must the drift note: {message}"
        );
    }

    fn accepted_response() -> aeat::AeatResponse {
        aeat::AeatResponse {
            estado_envio: "Correcto".to_string(),
            estado_registro: "Correcto".to_string(),
            ..Default::default()
        }
    }

    /// The audit trail told the truth about the chain and lied about the wire: the event said
    /// `AEAT (production)` for a record that was chained — and now sent — in testing.
    #[test]
    fn the_audit_event_names_the_environment_the_record_was_actually_sent_to() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            None,
        );

        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default();
        assert!(
            message.contains("AEAT (testing)"),
            "the event must name where the record WENT, not where the hub is: {message}"
        );
    }

    /// Draining a queue into the other tax agency is correct but never routine — it is exactly
    /// what a go-live with a non-empty queue looks like. A clean `Correcto` would otherwise be
    /// filed as `info` and the owner would never learn that their practice records left after
    /// the go-live, nor where they went.
    #[test]
    fn a_transmission_that_outlived_a_go_live_is_reported_as_a_warning() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        let (ops, _, success) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            None,
        );

        assert!(success, "the AEAT accepted it: the record IS remitted");
        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        assert_eq!(event.params.get("severity"), Some(&json!("warning")));
        assert_eq!(
            event.params.get("event_type"),
            Some(&json!("transmission_warning"))
        );
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default();
        // Both halves, and in this order: the record LEFT for testing, the hub IS in production.
        // Read the other way round it describes the disaster instead of the safe outcome.
        assert!(
            message.contains("remitido a «testing»"),
            "the warning has to say where the record went: {message}"
        );
        assert!(
            message.contains("ahora en «production»"),
            "…and which environment the hub is in now: {message}"
        );
    }

    /// A config that never set `environment` IS in testing — that is the asymmetric default
    /// hub#320 fixed in place, and it has to be the same default on both sides of the drift
    /// comparison. Reading the raw field instead would make every ordinary testing record look
    /// like a record that outlived a go-live, and a warning that cries wolf is a warning nobody
    /// reads.
    #[test]
    fn an_unconfigured_environment_is_testing_on_both_sides_of_the_comparison() {
        let config = json!({ "hub_id": HUB, "issuer_nif": NIF });

        let destination = destination_of(&queued_testing_record(), &config)
            .expect("a record that carries its environment resolves");

        assert_eq!(destination.endpoint, PREPRODUCTION_HOLDER);
        assert_eq!(
            destination.drift_note(),
            None,
            "an unset environment is testing, so a testing record has not drifted anywhere"
        );

        let mut unstamped = queued_testing_record();
        unstamped.as_object_mut().unwrap().remove("environment");
        let refusal = destination_of(&unstamped, &config)
            .expect_err("an unstamped record has no provable destination");
        assert!(
            refusal.contains("«testing»"),
            "and the refusal names that same default, not an empty string: {refusal}"
        );
    }

    /// …and the ordinary case stays ordinary: a record sent in the hub's own environment is a
    /// clean `info` success, with no warning to cry wolf with.
    #[test]
    fn a_record_sent_in_the_hubs_own_environment_is_a_plain_success() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            None,
        );

        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        assert_eq!(event.params.get("severity"), Some(&json!("info")));
        assert_eq!(
            event.params.get("message"),
            Some(&json!("AEAT (testing): Correcto Correcto")),
            "no drift, no note: the message keeps its plain shape"
        );
    }

    // ── verifactu#42 — the outcome that has to leave the module ────────────────────────────────
    //
    // Everything above writes `verifactu_event`, the module's own audit table. Nothing there
    // leaves: it is a row on a screen somebody has to open. This is the ONE part of the product
    // where not finding out has consequences before the AEAT, and a bar that closes at two in the
    // morning does not open that screen.
    //
    // So a failed outcome also emits a **public** event — the hub's outbox, the thing an
    // automation can be built on (`ERPlora/flows#18` R0 #6, «fiscal failure → tell the owner»).

    /// A real `Incorrecto` from the AEAT, as `parse_response` hands it over.
    fn rejected_response() -> aeat::AeatResponse {
        aeat::AeatResponse {
            estado_envio: "Incorrecto".to_string(),
            estado_registro: "Incorrecto".to_string(),
            codigo_error: "1189".to_string(),
            descripcion_error: "El NIF del destinatario no está identificado".to_string(),
            ..Default::default()
        }
    }

    /// `AceptadoConErrores` (ADR-0189): the AEAT REGISTERED it and noted an error on it.
    fn accepted_with_errors_response() -> aeat::AeatResponse {
        aeat::AeatResponse {
            estado_envio: "Correcto".to_string(),
            estado_registro: "AceptadoConErrores".to_string(),
            codigo_error: "2007".to_string(),
            descripcion_error: "Primer registro con obligado ya existente".to_string(),
            ..Default::default()
        }
    }

    fn emitted(events: &[Event], name: &str) -> Option<Json> {
        events
            .iter()
            .find(|e| e.name == name)
            .map(|e| e.payload.clone())
    }

    /// A rejection the AEAT really answered leaves the module, so something other than a screen
    /// can notice it.
    #[test]
    fn a_rejection_by_the_aeat_emits_a_public_event_the_owner_can_be_told_about() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing"))
            .expect("a record that carries its environment resolves");

        let (_, events, success) = response_ops(
            &queued_testing_record(),
            &rejected_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            None,
        );

        assert!(!success);
        let payload = emitted(&events, EVENT_RECORD_REJECTED)
            .expect("a rejection has to leave the module, not just the audit table");
        assert_eq!(payload["record_id"], json!("rec-2"));
        // The human reference. `record_id` is a uuid nobody can act on; «revisa la factura INV-2»
        // is the sentence an automation has to be able to write.
        assert_eq!(payload["invoice_number"], json!("INV-2"));
        assert_eq!(payload["reason"], json!(REASON_AEAT_REJECTED));
        assert_eq!(payload["error_code"], json!("1189"));
        assert_eq!(payload["environment"], json!("testing"));
        assert!(
            emitted(&events, EVENT_RECORD_ACCEPTED_WITH_ERRORS).is_none(),
            "a rejection is not an acceptance with a note on it"
        );
    }

    /// **Nothing fiscal travels.** The payload ends up in somebody's task list and in a message,
    /// and `flows#18` asks for this by name: enough to say «check invoice X», and no more.
    #[test]
    fn the_public_payload_carries_no_fiscal_content_at_all() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing")).unwrap();
        let mut response = rejected_response();
        response.csv = "CSV-SHOULD-NOT-TRAVEL".to_string();

        let (_, events, _) = response_ops(
            &queued_testing_record(),
            &response,
            &destination,
            "<xml>the signed record</xml>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            None,
        );

        let payload = emitted(&events, EVENT_RECORD_REJECTED).expect("it emits");
        let text = payload.to_string();
        for secret in [
            "<xml>",              // the signed record itself
            HASH_TESTING_2,       // the chain hash
            NIF,                  // the issuer's tax id
            "12100",              // any amount
            "CSV-SHOULD-NOT-TRAVEL",
        ] {
            assert!(
                !text.contains(secret),
                "`{secret}` must never leave in a public event: {text}"
            );
        }
        // And the keys are the closed set, so a field added later is a decision and not a slip.
        let keys: Vec<&String> = payload.as_object().expect("an object").keys().collect();
        assert_eq!(
            keys,
            vec![
                "environment",
                "error_code",
                "error_message",
                "invoice_number",
                "reason",
                "record_id",
                "status",
            ]
        );
    }

    /// **An `AceptadoConErrores` is not a rejection** (ADR-0189): the record IS at the AEAT and
    /// resending it is a duplicate. Filing it as a rejection would send the owner chasing an
    /// invoice that is already registered — but staying silent leaves a latent problem nobody
    /// sees, which is the other half of verifactu#42. So it gets its own word.
    #[test]
    fn an_acceptance_with_errors_is_told_apart_from_a_rejection() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing")).unwrap();

        let (_, events, success) = response_ops(
            &queued_testing_record(),
            &accepted_with_errors_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            None,
        );

        assert!(success, "it is registered at the AEAT: it counts as accepted");
        assert!(
            emitted(&events, EVENT_RECORD_REJECTED).is_none(),
            "never as a rejection: the invoice is filed"
        );
        let payload = emitted(&events, EVENT_RECORD_ACCEPTED_WITH_ERRORS)
            .expect("but it cannot be silent either");
        assert_eq!(payload["error_code"], json!("2007"));
        assert_eq!(payload["record_id"], json!("rec-2"));
    }

    /// A clean acceptance says nothing. `verifactu.record.transmitted` already exists for «it
    /// went out», and an outbox row per successful invoice would be the till's whole day.
    #[test]
    fn a_clean_acceptance_emits_no_failure_event() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing")).unwrap();

        let (_, events, success) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            None,
        );

        assert!(success);
        assert!(events.is_empty(), "nothing to tell anybody: {events:?}");
    }

    /// **The two refusals leave under their OWN reason** — the second one (hub#324, «the envelope
    /// cannot be built») landed after this event was written, and it must not inherit the first
    /// one's word.
    ///
    /// For the owner both are the same problem: the invoice is not at the AEAT. For whoever has to
    /// fix it they are opposite errands — one sends somebody to the config, the other to the
    /// invoice. So the event's `reason` is `Refusal::code`, the same key the audit row already
    /// carries, and never a literal written a second time next to it.
    #[tokio::test]
    async fn a_record_that_cannot_be_declared_leaves_under_its_own_reason() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("total_amount");
        let mut host = ChainHost::new(config_row("testing"), vec![record]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("an undeclarable record is an outcome, not an aborted batch");

        let payload = emitted(&out.events, EVENT_RECORD_REJECTED)
            .expect("nothing reached the AEAT: that has to leave the module");
        assert_eq!(payload["reason"], json!(REASON_RECORD_NOT_DECLARABLE));
        assert_eq!(payload["invoice_number"], json!("INV-2"));
        assert!(
            payload["error_message"]
                .as_str()
                .unwrap_or_default()
                .contains("total_amount"),
            "and it says WHICH amount, or the alarm is not actionable: {payload}"
        );
    }

    /// The other refusal — the record that cannot say which tax agency owns it (hub#471) — keeps
    /// its own key. Written as a pair with the test above: one of them alone would pass with both
    /// refusals collapsed onto a single literal.
    #[tokio::test]
    async fn a_record_with_no_environment_leaves_under_the_environment_reason() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");
        let mut host = ChainHost::new(config_row("production"), vec![record]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("an unplaceable record is an outcome, not an aborted batch");

        let payload = emitted(&out.events, EVENT_RECORD_REJECTED)
            .expect("nothing was built and nothing was sent: that has to leave the module");
        assert_eq!(payload["reason"], json!(REASON_ENVIRONMENT_UNKNOWN));
    }
}

#[cfg(test)]
mod retention_gate_tests {
    //! ADR-0202 phase 1, guard R2 (hub#314): while records are still unsent, the module cannot
    //! be disabled or uninstalled. The runtime owns the refusal; the engine owns the COUNT and
    //! the stable code, because only it knows which record states mean "the AEAT does not have
    //! this invoice yet".

    use super::*;
    use erplora_runtime::native::NativeHandler;
    use std::sync::Mutex;

    const HUB: &str = "7b2f8a44-9c1d-4e2f-8a3b-944445555666";

    /// Answers the gate's COUNT with a fixed number and records the SQL it was asked, so the
    /// test can assert WHICH records the engine considers still owed to the AEAT.
    struct CountingHost {
        pending: i64,
        reads: Mutex<Vec<String>>,
    }

    impl CountingHost {
        fn with(pending: i64) -> Self {
            CountingHost {
                pending,
                reads: Mutex::new(Vec::new()),
            }
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for CountingHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.reads.lock().unwrap().push(sql.to_string());
            Ok(vec![json!({ "pending_count": self.pending })])
        }
    }

    #[tokio::test]
    async fn unsent_records_are_reported_as_a_pending_obligation() {
        let host = CountingHost::with(4);
        let owed = VerifactuEngine
            .pending_obligations(HUB, &host)
            .await
            .expect("counting what is owed must not fail")
            .expect("4 unsent records are an obligation");

        assert_eq!(owed.count, 4, "the operator must be told how many are left");
        assert_eq!(
            owed.code, "verifactu.unsent_records",
            "the stable code lives in the module's own namespace (hub#139 ABI)"
        );
        assert!(
            owed.message.contains('4'),
            "the human fallback must carry the count, got `{}`",
            owed.message
        );

        let reads = host.reads.lock().unwrap();
        let sql = reads.first().expect("the engine must ask the database");
        assert!(
            sql.contains("verifactu_record") && sql.contains("hub_id = :hub_id"),
            "the count is scoped to this hub's records: {sql}"
        );
        for state in ["pending", "retry", "error", "rejected"] {
            assert!(
                sql.contains(state),
                "`{state}` means the AEAT does not have the invoice yet — it must be counted: {sql}"
            );
        }
        assert!(
            sql.contains("is_deleted = 0"),
            "a soft-deleted record is not an obligation: {sql}"
        );
    }

    #[tokio::test]
    async fn a_fully_handed_over_chain_owes_nothing() {
        let host = CountingHost::with(0);
        let owed = VerifactuEngine
            .pending_obligations(HUB, &host)
            .await
            .expect("counting what is owed must not fail");
        assert!(
            owed.is_none(),
            "with every record accepted by the AEAT the module is free to be removed"
        );
    }
}

#[cfg(test)]
mod certificate_refetch_trigger_tests {
    use super::{request_certificate_refetch_on_tls, VerifactuError};
    use erplora_runtime::certificate_refetch::RefetchSignal;

    /// El slot que firmaba cuando falló el handshake (ver `signing_kind`).
    const DELEGATED: &str = "delegated";
    const OWN: &str = "own";

    /// 🔒 The failure IS the trigger (ADR-0202 §2 point 4). A rejected client certificate is the
    /// one transport failure that a retry cannot fix and a refetch can.
    #[test]
    fn a_tls_failure_asks_for_the_certificate_to_be_refetched() {
        let signal = RefetchSignal::new();
        request_certificate_refetch_on_tls(
            &VerifactuError::Tls("conexión AEAT: invalid peer certificate".into()),
            DELEGATED,
            &signal,
        );
        assert!(signal.take(), "un rechazo del certificado tiene que pedir el vigente");
    }

    /// 🔒 **El certificado que falló tiene que ser el DELEGADO** (hub#319).
    ///
    /// El refetch baja el certificado de ERPlora. Si quien se identificó ante la AEAT fue el
    /// certificado **propio** del negocio —caducado, revocado, con la contraseña cambiada—, pedir el
    /// delegado no arregla nada: el propio sigue ganando el fallback (ADR-0202 §2.1) y el siguiente
    /// intento vuelve a fallar igual. Lo único que consigue es **gastar el presupuesto**: la cola de
    /// contingencia reintenta cada 5/10/20/40/60 min, así que un certificado propio roto se comería
    /// las 6/h del hub y dejaría sin cupo al disparador que sí sirve —el del latido— justo cuando el
    /// plano de control rote de verdad.
    ///
    /// Mismo defecto de frontera que hub#317 y hub#318 arreglaron dos veces: una señal que describe
    /// el slot delegado levantada desde un contexto que podía estar hablando del propio.
    #[test]
    fn a_tls_failure_of_the_businesss_own_certificate_asks_for_nothing() {
        let signal = RefetchSignal::new();
        request_certificate_refetch_on_tls(
            &VerifactuError::Tls("conexión AEAT: received fatal alert: CertificateExpired".into()),
            OWN,
            &signal,
        );
        assert!(
            !signal.take(),
            "el certificado del negocio no se arregla bajando el de ERPlora — y gastaría el cupo"
        );
    }

    /// Sin certificado no se llega a abrir el canal, pero si se llegase tampoco se pide nada: el
    /// cupo no se gasta en una pregunta cuya respuesta ya se sabe que no se está usando.
    #[test]
    fn a_tls_failure_without_a_known_signer_asks_for_nothing() {
        let signal = RefetchSignal::new();
        request_certificate_refetch_on_tls(
            &VerifactuError::Tls("conexión AEAT: invalid peer certificate".into()),
            "",
            &signal,
        );
        assert!(!signal.take());
    }

    /// 🔒 **The AEAT being down does not make the hub ask for a private key.** These arrive once
    /// per record the contingency queue drains, and asking on each one would spend the control
    /// plane's 20/h allowance on an outage that a refetch cannot fix.
    #[test]
    fn a_network_failure_does_not() {
        let signal = RefetchSignal::new();
        for error in [
            VerifactuError::Transmission("conexión AEAT: operation timed out".into()),
            VerifactuError::Transmission("AEAT HTTP 503: servicio no disponible".into()),
            VerifactuError::Certificate("certificado del negocio no configurado".into()),
            VerifactuError::Consult("SOAP Fault".into()),
        ] {
            request_certificate_refetch_on_tls(&error, DELEGATED, &signal);
        }
        assert!(
            !signal.take(),
            "solo el fallo del canal TLS dispara el refetch; los demás se reintentan por la cola \
             de contingencia"
        );
    }

    /// Many stranded records, one broken certificate, ONE refetch: the signal coalesces, which is
    /// what keeps a queue drain from emptying the hourly allowance in a single pass.
    #[test]
    fn a_whole_queue_drain_failing_the_same_handshake_asks_once() {
        let signal = RefetchSignal::new();
        for _ in 0..200 {
            request_certificate_refetch_on_tls(
                &VerifactuError::Tls("conexión AEAT: received fatal alert: CertificateRevoked".into()),
                DELEGATED,
                &signal,
            );
        }
        assert!(signal.take());
        assert!(!signal.take(), "200 registros varados piden UN refetch, no 200");
    }
}

#[cfg(test)]
mod contingency_queue_tests {
    //! hub#326: the daily heartbeat carries how deep the contingency queue is and how long its
    //! oldest entry has been waiting, so a hub that stopped remitting is visible from the SaaS
    //! instead of only from its own dashboard.

    use super::*;
    use erplora_runtime::native::NativeHandler;
    use std::sync::Mutex;

    const HUB: &str = "7b2f8a44-9c1d-4e2f-8a3b-944445555666";

    /// Answers the queue read with a fixed count and oldest timestamp, recording the SQL so the
    /// test can assert WHICH records are being counted — and that there is only ONE query.
    struct QueueHost {
        pending: i64,
        oldest: Json,
        reads: Mutex<Vec<String>>,
    }

    impl QueueHost {
        fn with(pending: i64, oldest: Json) -> Self {
            QueueHost {
                pending,
                oldest,
                reads: Mutex::new(Vec::new()),
            }
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for QueueHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.reads.lock().unwrap().push(sql.to_string());
            let mut row = json!({ "pending_count": self.pending });
            // Like a real database, a column the query did not SELECT is simply not in the row.
            // Handing back the oldest timestamp unconditionally would make this test pass against
            // a query that never asks for it — the mock would be answering, not the engine.
            if sql.contains("MIN(created_at) AS oldest_pending_at") {
                row["oldest_pending_at"] = self.oldest.clone();
            }
            Ok(vec![row])
        }
    }

    /// A host whose reads fail, like a hub where the module was never installed and the table
    /// does not exist.
    struct BrokenHost;

    #[async_trait::async_trait]
    impl NativeHost for BrokenHost {
        async fn read(&self, _sql: &str, _p: &Params) -> Result<Vec<Json>> {
            Err(RuntimeError::Native("relation does not exist".into()))
        }
    }

    #[tokio::test]
    async fn the_queue_reports_its_depth_and_the_oldest_entry_still_waiting() {
        let host = QueueHost::with(4, json!("2026-08-01T09:00:00Z"));

        let queue = contingency_queue(HUB, &host)
            .await
            .expect("measuring the queue must not fail");

        assert_eq!(queue.depth, 4);
        assert_eq!(
            queue.oldest_pending_at.as_deref(),
            Some("2026-08-01T09:00:00Z"),
            "the age of the oldest entry is what separates a busy till from a stuck hub"
        );

        let reads = host.reads.lock().unwrap();
        assert_eq!(reads.len(), 1, "depth and age are one read, not two");
        let sql = &reads[0];
        assert!(
            sql.contains("verifactu_record") && sql.contains("hub_id = :hub_id"),
            "the queue is scoped to this hub's records: {sql}"
        );
        for state in ["pending", "retry", "error", "rejected"] {
            assert!(
                sql.contains(state),
                "`{state}` means the AEAT does not have the invoice yet: {sql}"
            );
        }
        assert!(
            sql.contains("is_deleted = 0"),
            "a soft-deleted record is not queued work: {sql}"
        );
    }

    /// **An empty queue is an explicit `0`, never silence.** The heartbeat's `Option` contract
    /// reserves «absent» for «I could not count it»; a hub that has handed everything over must
    /// say zero, or the fleet panel cannot tell it apart from one that went quiet.
    #[tokio::test]
    async fn a_drained_queue_reports_zero_and_no_oldest_entry() {
        let host = QueueHost::with(0, Json::Null);

        let queue = contingency_queue(HUB, &host)
            .await
            .expect("measuring the queue must not fail");

        assert_eq!(queue.depth, 0);
        assert_eq!(queue.oldest_pending_at, None);
    }

    /// **A read failure is an error, not a zero.** The caller turns it into an absent field; if
    /// this returned `0` the SaaS would read a hub whose table it cannot even open as healthy.
    #[tokio::test]
    async fn a_read_failure_is_not_an_empty_queue() {
        assert!(
            contingency_queue(HUB, &BrokenHost).await.is_err(),
            "not being able to count is not the same as having nothing to count"
        );
    }

    /// 🔒 **One query, one truth.** The retention gate (hub#314) and the heartbeat must count the
    /// same records: if they drifted, the SaaS would raise an alert about a queue the operator's
    /// own dashboard says is empty — or, worse, stay silent about one that blocks an uninstall.
    #[tokio::test]
    async fn the_retention_gate_reads_the_very_same_query() {
        let gate_host = QueueHost::with(4, json!("2026-08-01T09:00:00Z"));
        let owed = VerifactuEngine
            .pending_obligations(HUB, &gate_host)
            .await
            .expect("the gate must not fail")
            .expect("4 unsent records are an obligation");
        assert_eq!(owed.count, 4);

        let queue_host = QueueHost::with(4, json!("2026-08-01T09:00:00Z"));
        let queue = contingency_queue(HUB, &queue_host).await.unwrap();
        assert_eq!(u64::from(owed.count), queue.depth);

        assert_eq!(
            *gate_host.reads.lock().unwrap(),
            *queue_host.reads.lock().unwrap(),
            "both answers must come from the SAME SQL — a second copy is a second truth"
        );
    }
}

#[cfg(test)]
mod ingest_integrity_tests {
    //! hub#1103 + hub#1104 — **la última puerta antes de Hacienda tiene que juzgar lo que sella**.
    //!
    //! Dos defectos distintos de la MISMA puerta (`build_record_output`, por donde pasan tanto el
    //! command público `verifactu.records.create` como el listener `ingest_invoice`):
    //!
    //!  * **hub#1103** — la aritmética no se comprobaba. Un registro con `rate 21.0` y una cuota de
    //!    99,99 € sobre una base de 5,45 € se selló, se encadenó y se remitió VERBATIM. El módulo
    //!    cerró su mitad en la TABLA (`013_arithmetic_integrity.sql`, verifactu#53), pero una
    //!    violación de `CHECK` llega como error crudo de Postgres: sin código de dominio, sin motivo
    //!    legible y DESPUÉS de haber leído el ancla. Aquí se rechaza antes, con su código.
    //!  * **hub#1104** — una F1 sin NIF de destinatario se degradaba a F2 **en silencio** (y una
    //!    R1–R4 a R5, que es un cambio de naturaleza fiscal). La degradación es correcta —sin ella
    //!    la AEAT responde 1189 con el número de cadena ya gastado—, pero muda no lo es.
    use super::*;

    const HUB: &str = "9c1d7b2f-4e2f-8a3b-9444-455566677788";
    const NIF: &str = "B27593136";

    /// Host mínimo: config de `testing`, cadena vacía y sin certificado (no se transmite nada, que
    /// es lo que estos tests quieren observar — la puerta, no la red).
    struct GateHost;
    #[async_trait::async_trait]
    impl NativeHost for GateHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            if sql.contains("FROM verifactu_config") {
                return Ok(vec![json!({
                    "hub_id": HUB, "environment": "testing",
                    "issuer_nif": NIF, "issuer_name": "Test Business SL"
                })]);
            }
            Ok(vec![])
        }
    }

    /// Host que sirve UNA factura del módulo `invoice`, tal cual la lee `ingest_invoice`.
    struct InvoiceHost(Json);
    #[async_trait::async_trait]
    impl NativeHost for InvoiceHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            if sql.contains("FROM verifactu_config") {
                return Ok(vec![json!({
                    "hub_id": HUB, "environment": "testing",
                    "issuer_nif": NIF, "issuer_name": "Test Business SL"
                })]);
            }
            if sql.contains("FROM invoice_invoice") {
                return Ok(vec![self.0.clone()]);
            }
            Ok(vec![])
        }
    }

    fn ids() -> Json {
        json!([
            "id-rec", "id-evt", "id-queue", "id-t1", "id-t2", "id-t3", "id-warn", "id-x"
        ])
    }

    fn context() -> Json {
        json!({
            "hub_id": HUB, "now": "2026-08-25T10:00:00+02:00", "current_user_id": "u1",
            "new_ids": ids()
        })
    }

    /// Payload de `verifactu.records.create` con los importes que se le pasen.
    fn create_payload(
        invoice_type: &str,
        base: i64,
        rate: f64,
        tax: i64,
        total: i64,
        breakdown: &str,
    ) -> Json {
        json!({
            "payload": {
                "record_type": "alta", "issuer_nif": NIF, "issuer_name": "Test Business SL",
                "invoice_number": "F-2026-000123", "invoice_date": "2026-08-25",
                "invoice_type": invoice_type, "base_amount": base, "tax_rate": rate,
                "tax_amount": tax, "total_amount": total, "tax_breakdown": breakdown
            },
            "context": context()
        })
    }

    /// Factura de `invoice` con los importes y el destinatario que se le pasen.
    fn invoice_row(invoice_type: &str, customer_tax_id: &str, base: i64, tax: i64, total: i64, breakdown: &str) -> Json {
        json!({
            "invoice_type": invoice_type, "number": "FACT-2026-000009",
            "issue_date": "2026-08-25", "issuer_nif": NIF, "issuer_name": "Test Business SL",
            "customer_tax_id": customer_tax_id, "customer_name": "Cliente",
            "description": "Venta", "base_amount": base, "tax_amount": tax,
            "total_amount": total, "tax_breakdown": breakdown,
            "substitutes_number": "", "substitutes_date": "", "substitutes_nif": "",
            "rectifies_number": "", "rectifies_date": "", "rectifies_nif": ""
        })
    }

    fn ingest_input() -> Json {
        json!({ "payload": { "invoice_id": "inv-1" }, "context": context() })
    }

    fn error_of(res: Result<Output>) -> String {
        match res {
            Ok(out) => panic!(
                "esperaba un RECHAZO y el registro se selló: {:?}",
                out.operations.iter().map(|o| o.command.clone()).collect::<Vec<_>>()
            ),
            Err(e) => e.to_string(),
        }
    }

    fn event_of<'a>(out: &'a Output, event_type: &str) -> Option<&'a Operation> {
        out.operations.iter().find(|o| {
            o.command == "verifactu._insert_event"
                && o.params.get("event_type") == Some(&json!(event_type))
        })
    }

    // ── hub#1103 · la aritmética ────────────────────────────────────────────────────────────

    /// El caso EXACTO del QA: 99,99 € de cuota sobre una base de 5,45 € declarando el 21 %.
    /// `base + cuota = total` cuadra (545 + 9999 = 10544), así que solo la contrastación contra el
    /// TIPO declarado lo caza.
    #[tokio::test]
    async fn a_quota_its_own_rate_cannot_justify_is_refused() {
        let input = create_payload(
            "F1",
            545,
            21.0,
            9999,
            10544,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":9999}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// Sin desglose legible solo queda el `tax_rate` de la fila, y tiene que juzgarse igual.
    #[tokio::test]
    async fn without_a_breakdown_the_row_rate_still_has_to_explain_the_quota() {
        let input = create_payload("F1", 545, 21.0, 9999, 10544, "");
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// `base + cuota ≠ total`: la cabecera se contradice a sí misma. Ninguna de las tres reglas de
    /// la tabla lo mira (`013` lo dejó fuera a propósito), así que esta es la única puerta.
    #[tokio::test]
    async fn a_header_that_contradicts_itself_is_refused() {
        let input = create_payload(
            "F1",
            545,
            21.0,
            114,
            660,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":114}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("totals_mismatch"), "código esperado, llegó: {err}");
    }

    /// El desglose tiene que sumar lo que dice la cabecera: es el cruce que hace la AEAT
    /// (`CuotaTotal` = Σ cuotas declaradas).
    #[tokio::test]
    async fn a_breakdown_that_does_not_add_up_to_the_header_is_refused() {
        let input = create_payload(
            "F1",
            10000,
            21.0,
            2100,
            12100,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":5000,"quota":1050}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("totals_mismatch"), "código esperado, llegó: {err}");
    }

    /// Una ordinaria no totaliza negativo: lo negativo es una RECTIFICATIVA.
    #[tokio::test]
    async fn an_ordinary_invoice_cannot_total_negative() {
        let input = create_payload(
            "F1",
            -500,
            21.0,
            -105,
            -605,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":-500,"quota":-105}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("negative_total"), "código esperado, llegó: {err}");
    }

    /// 🔴 **La trampa de esta issue.** El criterio escrito pedía rechazar `total ≤ 0`, y eso
    /// contradice lo decidido en `invoice#50`: un tique 100 % invitado suma 0,00 € honestamente y
    /// sigue siendo una venta que necesita su F2. Se sella.
    #[tokio::test]
    async fn a_fully_comped_ticket_still_gets_its_record() {
        let input = create_payload(
            "F2",
            0,
            21.0,
            0,
            0,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":0,"quota":0}]"#,
        );
        let out = create_record(&input, &GateHost)
            .await
            .expect("un tique invitado se sella: 0,00 € cuadra");
        assert!(
            out.operations.iter().any(|o| o.command == "verifactu._insert_record"),
            "el registro tiene que existir"
        );
    }

    /// Una rectificativa SÍ lleva importes negativos: es el camino legal de una devolución.
    #[tokio::test]
    async fn a_corrective_invoice_may_be_negative() {
        let input = create_payload(
            "R5",
            -1000,
            21.0,
            -210,
            -1210,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":-1000,"quota":-210}]"#,
        );
        create_record(&input, &GateHost)
            .await
            .expect("una R5 negativa es legítima");
    }

    /// El recargo de equivalencia va en su propio par y se contrasta contra SU tipo.
    #[tokio::test]
    async fn the_equivalence_surcharge_is_checked_against_its_own_rate() {
        let input = create_payload(
            "F1",
            10000,
            21.0,
            2620,
            12620,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100,
                 "surcharge_rate":5.2,"surcharge_quota":999}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// Un ticket de bar legítimo (21 % + 10 %, con el céntimo de redondeo por línea) pasa: la
    /// guarda no puede dejar sin facturar una venta real.
    #[tokio::test]
    async fn a_legitimate_mixed_rate_ticket_is_sealed() {
        let input = create_payload(
            "F2",
            1001,
            16.58,
            166,
            1167,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":601,"quota":126},
                {"tax":"vat","regime":"01","class":"subject","rate":10.0,"base":400,"quota":40}]"#,
        );
        create_record(&input, &GateHost)
            .await
            .expect("un ticket mixto con su redondeo se sella");
    }

    /// Y la MISMA guarda cubre el camino automático: el listener de `invoice.created`.
    #[tokio::test]
    async fn the_listener_refuses_the_same_amounts_the_public_command_refuses() {
        let host = InvoiceHost(invoice_row(
            "F1",
            "87654321X",
            545,
            9999,
            10544,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":9999}]"#,
        ));
        let err = error_of(ingest_invoice(&ingest_input(), &host).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    // ── hub#1104 · la degradación no puede ser muda ─────────────────────────────────────────

    /// Una F1 sin NIF de destinatario se sigue degradando a F2 —sin eso la AEAT responde 1189 con
    /// el número de cadena ya gastado— pero **deja constancia**: un evento propio, con severidad
    /// `warning`, que nombra el tipo declarado, el efectivo y el motivo.
    #[tokio::test]
    async fn a_silent_downgrade_leaves_a_trace() {
        let host = InvoiceHost(invoice_row(
            "F1",
            "",
            10000,
            2100,
            12100,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100}]"#,
        ));
        let out = ingest_invoice(&ingest_input(), &host)
            .await
            .expect("la factura se ingesta: degradar es correcto, callarlo no");

        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        assert_eq!(insert.params.get("invoice_type"), Some(&json!("F2")));

        let warn = event_of(&out, EVENT_TYPE_INVOICE_TYPE_DOWNGRADED)
            .expect("la degradación tiene que dejar su evento");
        assert_eq!(warn.params.get("severity"), Some(&json!("warning")));
        let details: Json = serde_json::from_str(
            warn.params.get("details").and_then(Json::as_str).unwrap_or("{}"),
        )
        .expect("los detalles son JSON");
        assert_eq!(details.get("declared"), Some(&json!("F1")));
        assert_eq!(details.get("effective"), Some(&json!("F2")));
        assert_eq!(details.get("reason"), Some(&json!(REASON_MISSING_RECIPIENT)));
    }

    /// No es solo F1→F2: una rectificativa CON destinatario degradada a R5 cambia de naturaleza
    /// fiscal (por diferencias → de simplificada) y también tiene que verse.
    #[tokio::test]
    async fn a_corrective_downgraded_to_r5_leaves_the_same_trace() {
        let host = InvoiceHost(invoice_row(
            "R1",
            "",
            -1000,
            -210,
            -1210,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":-1000,"quota":-210}]"#,
        ));
        let out = ingest_invoice(&ingest_input(), &host)
            .await
            .expect("la rectificativa se ingesta");
        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        assert_eq!(insert.params.get("invoice_type"), Some(&json!("R5")));
        let warn = event_of(&out, EVENT_TYPE_INVOICE_TYPE_DOWNGRADED)
            .expect("la degradación R1→R5 tiene que dejar su evento");
        let details: Json = serde_json::from_str(
            warn.params.get("details").and_then(Json::as_str).unwrap_or("{}"),
        )
        .unwrap();
        assert_eq!(details.get("declared"), Some(&json!("R1")));
        assert_eq!(details.get("effective"), Some(&json!("R5")));
    }

    /// Con NIF no hay degradación, así que no hay evento que emitir: un aviso que sale siempre
    /// deja de ser un aviso.
    #[tokio::test]
    async fn an_invoice_with_a_recipient_is_not_downgraded_and_warns_about_nothing() {
        let host = InvoiceHost(invoice_row(
            "F1",
            "87654321X",
            10000,
            2100,
            12100,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100}]"#,
        ));
        let out = ingest_invoice(&ingest_input(), &host).await.expect("se ingesta");
        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        assert_eq!(insert.params.get("invoice_type"), Some(&json!("F1")));
        assert!(
            event_of(&out, EVENT_TYPE_INVOICE_TYPE_DOWNGRADED).is_none(),
            "sin degradación no hay aviso"
        );
    }

    /// 🔴 §15.8: una F2 no puede pasar de 3.000,00 € (+10,00 € de tolerancia). Degradar una F1 de
    /// 4.000 € a F2 fabrica un registro que la AEAT rechaza — con el número de cadena gastado. Se
    /// para ANTES de sellar.
    #[tokio::test]
    async fn a_downgrade_that_would_break_the_f2_ceiling_is_refused() {
        let host = InvoiceHost(invoice_row(
            "F1",
            "",
            400_000,
            84_000,
            484_000,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":400000,"quota":84000}]"#,
        ));
        let err = error_of(ingest_invoice(&ingest_input(), &host).await);
        assert!(err.contains("f2_limit_exceeded"), "código esperado, llegó: {err}");
    }

    /// Y justo por debajo del techo (3.010,00 €) se sella: el margen de la AEAT es parte de la
    /// regla, no un detalle.
    #[tokio::test]
    async fn a_downgrade_right_at_the_ceiling_is_sealed() {
        let host = InvoiceHost(invoice_row(
            "F1",
            "",
            301_000,
            0,
            301_000,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":0.0,"base":301000,"quota":0}]"#,
        ));
        ingest_invoice(&ingest_input(), &host)
            .await
            .expect("3.010,00 € entra: es el techo inclusive");
    }

    // ── hub#1103 · lo que `chain.validate` AFIRMA ───────────────────────────────────────────

    /// «Cadena íntegra» se leyó en el informe de QA como veredicto sobre los importes de 27
    /// registros imposibles. El contrato criptográfico se mantiene —recalcular huellas y verificar
    /// el encadenado es lo correcto sobre filas ya inmutables—, pero el texto tiene que decir QUÉ
    /// verificó, y los detalles tienen que llevarlo en un campo que la UI pueda traducir.
    #[tokio::test]
    async fn the_chain_verdict_names_the_fingerprints_it_actually_checked() {
        let input = json!({ "payload": { "issuer_nif": NIF }, "context": context() });
        let out = validate_chain(&input, &GateHost).await.expect("valida");
        let event = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("el veredicto se persiste como evento");
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default()
            .to_string();
        assert!(
            message.to_lowercase().contains("huella"),
            "el veredicto tiene que nombrar la HUELLA, no afirmar sobre los importes: {message}"
        );
        let details: Json = serde_json::from_str(
            event.params.get("details").and_then(Json::as_str).unwrap_or("{}"),
        )
        .expect("los detalles son JSON");
        assert_eq!(
            details.get("scope"),
            Some(&json!(CHAIN_VALIDATION_SCOPE)),
            "la UI necesita el alcance en un campo estable para traducirlo (ADR-0055)"
        );
    }
}
