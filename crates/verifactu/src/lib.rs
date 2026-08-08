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
use erplora_wasm_host::{Operation, Output};
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
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        let rows = host
            .read(
                "SELECT COUNT(*) AS pending_count FROM verifactu_record \
                 WHERE hub_id = :hub_id AND is_deleted = 0 \
                   AND status IN ('pending', 'retry', 'error', 'rejected')",
                &p,
            )
            .await?;
        let count = rows
            .first()
            .map(|r| int_field(r, "pending_count", 0))
            .unwrap_or(0)
            .max(0) as u64;
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
fn resolve_invoice_type(declared: &str, recipient_nif: &str) -> String {
    if !recipient_nif.trim().is_empty() || !TYPES_REQUIRING_RECIPIENT.contains(&declared) {
        return declared.to_string();
    }
    match declared {
        "R1" | "R2" | "R3" | "R4" => "R5".to_string(),
        _ => "F2".to_string(),
    }
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

    // Destinatario de la factura: decide el TIPO antes de encadenar nada.
    let recipient_nif = str_field(&inv, "customer_tax_id");
    let invoice_type = {
        let t = str_field(&inv, "invoice_type");
        let declared = if INVOICE_TYPES.contains(&t.as_str()) {
            t
        } else {
            "F1".to_string()
        };
        // Sin NIF de cliente, una F1 sale sin `Destinatarios` y la AEAT la rechaza con 1189 —
        // ya con el número de cadena gastado. El tipo entra en la huella, así que se resuelve
        // AQUÍ, antes de calcularla (`resolve_invoice_type`).
        resolve_invoice_type(&declared, &recipient_nif)
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
            recipient_nif,
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
            });
            if let Ok((ops, _success)) =
                transmit_one(host, ctx, &record_json, cfg, &ids[3], &ids[4], &ids[5]).await
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
        // Id reservado para el ancla si la AEAT rechaza por encadenamiento y hay que re-anclar.
        &ctx.new_ids[2],
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
    recovery_id: &str,
) -> Result<(Vec<Operation>, bool)> {
    let record_id = str_field(record, "id");
    // WHERE this goes is settled BEFORE anything else happens — before the chain read, before
    // the XML, before the archive (hub#471). If the record cannot say which of the two tax
    // agencies owns it, nothing is built and nothing is sent.
    let destination = match destination_of(record, config) {
        Ok(destination) => destination,
        Err(reason) => {
            return refuse_transmission(host, ctx, &record_id, event_id, queue_id, config, &reason)
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
    let xml = record
        .get("xml_content")
        .and_then(Json::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToString::to_string)
        .unwrap_or_else(|| aeat::build_soap(record, config, prev.as_ref(), &ctx.hub_id));

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
                            &record_id,
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
                &record_id,
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
            Ok((ops, false))
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
    record_id: &str,
    event_id: &str,
    queue_id: &str,
    config: &Json,
    reason: &str,
) -> Result<(Vec<Operation>, bool)> {
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
                        "reason": "record_environment_unknown",
                        "error": reason,
                        "attempts": retry.attempts,
                    })
                    .to_string(),
                    "timestamp": ctx.now,
                }),
            ),
            retry.operation,
        ],
        false,
    ))
}

/// Intenciones que aplican una respuesta de la AEAT sobre el registro: UPDATE + evento (+ salida
/// de la cola de contingencia si fue aceptado). Compartido por el primer intento y por el
/// reintento tras re-anclar.
#[allow(clippy::too_many_arguments)]
fn response_ops(
    record_id: &str,
    resp: &aeat::AeatResponse,
    destination: &Destination,
    xml: &str,
    xml_storage_path: &str,
    event_id: &str,
    now: &str,
    note: Option<&str>,
) -> (Vec<Operation>, bool) {
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
    (ops, success)
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
) -> Result<Option<(Vec<Operation>, bool)>> {
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
    );
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
    let (mut ops, success) = response_ops(
        &record_id,
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
    Ok(Some((ops, success)))
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
        let (ops, success) = transmit_one(
            host,
            &ctx,
            &rec,
            &config,
            &event_id,
            &queue_id,
            &recovery_id,
        )
        .await?;
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
                // Mismo gate que la transmisión real: la prueba tiene que fallar donde falla el
                // envío de verdad, no ir a la AEAT a que lo diga con un 4102.
                if let Err(e) = xsd::validate_registro(&xml) {
                    aeat =
                        json!({ "ok": false, "error": format!("XML no conforme al esquema: {e}") });
                } else {
                    match aeat::post_soap(transmission_endpoint(&config), identity, &xml).await {
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
        "environment": environment,
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
    }

    impl ChainHost {
        fn new(config: Json, records: Vec<Json>) -> Self {
            ChainHost {
                config,
                records,
                queue: Vec::new(),
                has_core_certificate: false,
                reads: Mutex::new(Vec::new()),
            }
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

        async fn write_static_file(
            &self,
            relative_path: &str,
            _bytes: &[u8],
            _content_type: &str,
        ) -> Result<String> {
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

        let (ops, _) = response_ops(
            "rec-2",
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

        let (ops, _) = response_ops(
            "rec-2",
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

        let (ops, success) = response_ops(
            "rec-2",
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

        let (ops, _) = response_ops(
            "rec-2",
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
