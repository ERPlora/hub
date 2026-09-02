//! Daily business-usage heartbeat (hub#199 / saas#806).
//!
//! This reuses the entitlement's 24-hour tick. The runtime reads the canonical
//! `sales_sale` table and active local device sessions, then posts one compact
//! cumulative snapshot to the SaaS. If the sales module/table is unavailable,
//! `orders_today` is omitted: the Cloud must not turn a read failure into a
//! fabricated zero.
//!
//! The same snapshot carries what every installed **native engine still owes an external
//! authority** (hub#326 / hub#1406) — how much and since when — so a hub that stopped
//! remitting is visible from the fleet panel and not only from its own dashboard. The caller
//! asks the registry generically ([`erplora_runtime::Runtime::pending_obligations`]) — the
//! same per-engine question that blocks an uninstall (hub#314), so the alert and the refusal
//! can never disagree — and this module only shapes the answers into wire fields.

use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::native::PendingObligation;
use erplora_runtime::producer_facts::{ProducerFacts, ProducerFactsCache};
use serde::Serialize;
use serde_json::{json, Value};

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct DailyUsageHeartbeat {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub orders_today: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_sale_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub terminals: Option<u64>,
    /// Última vez que alguien **entró** en el hub (ADR-0175), si la hubo desde el último latido.
    ///
    /// Es la señal con la que el Cloud apaga (60d) y acaba borrando (120d) los hubs free que nadie
    /// usa, y va aquí — y no en un job aparte — porque este heartbeat ya viaja con la credencial
    /// de máquina y la cadencia correcta. Que sea `Option` es el contrato: **ausente = nadie ha
    /// entrado**, y el Cloud debe dejar correr el reloj. Ver `crate::activity`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_user_activity_at: Option<String>,
    /// Version of the **delegated** certificate this hub holds (ADR-0202 §2.5 — hub#318).
    ///
    /// Three states, and the Cloud stores all three differently, so they must not be conflated:
    /// an explicit **`0`** is «I hold no delegated certificate» (a fresh hub, or one that was
    /// reprovisioned and lost its `HUB_SECRETS_KEY`), a positive number is the version it really
    /// holds, and **absent** is «I am not telling you» — which the Cloud leaves as `NULL`, its
    /// «never reported» state.
    ///
    /// Absent is therefore reserved for a READ FAILURE, never for «no certificate»: the same rule
    /// `orders_today` follows above. A fabricated `0` would show up in the fleet panel as a hub
    /// that lost ERPlora's certificate, and would send somebody looking for a rotation that never
    /// broke.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cert_version: Option<i64>,
    /// `notAfter` of that same delegated container, `YYYY-MM-DD`. Absent when unknown — including
    /// when `cert_version` is `0`, which is what clears a stale expiry on the Cloud side.
    ///
    /// The Cloud compares it against the `not_after` of the `.p12` IT custodies: same version and a
    /// different date means the hub is not really running our certificate (ADR-0202 §2.5).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cert_not_after: Option<String>,
    /// The hub version this container is running, e.g. `1.0.0` (hub#515).
    ///
    /// Sin ella, «¿está este hub al día?» solo se puede contestar adivinando desde un digest — y un
    /// digest no dice si el salto de delante es un parche de seguridad o una versión nueva. Viaja
    /// en ESTE request porque el latido ya lleva la credencial de máquina con la cadencia correcta:
    /// una llamada aparte sería una cosa más que se puede romper.
    ///
    /// **No es `Option`, y eso es el contrato.** En este body «ausente» significa *no pude leerlo*
    /// (`orders_today`, `cert_version`…) y el Cloud lo guarda distinto; la versión va compilada
    /// dentro del binario, así que no existe el caso de «no la sé». Va **sin** el `v`: el prefijo
    /// es para leerlo en un panel, no para que el Cloud tenga que quitarlo antes de comparar.
    pub hub_version: String,
    /// How much every installed engine still owes its external authority (for the
    /// `verifactu` engine: records the AEAT has not received yet, hub#326).
    ///
    /// Without it a hub that stopped remitting is indistinguishable from a healthy one: the
    /// operator sees the pending KPI on their own dashboard, and nobody else does. It rides this
    /// request for the same reason everything else here does — the beat already carries the
    /// machine credential at the right cadence.
    ///
    /// Same `Option` semantics as the fields above, and it matters here more than anywhere: an
    /// explicit **`0`** is «this engine owes its authority nothing», and an ABSENT pair is «I
    /// could not count it» — the module is not installed, or its table would not read. A
    /// fabricated `0` would paint a hub nobody can measure as compliant, which is the exact
    /// blindness these fields exist to remove. And depth alone cannot raise an alert: four
    /// records queued during a lunch service are normal, four queued since last Tuesday are a
    /// hub whose certificate expired — **the hub does not decide the threshold**, it reports the
    /// wait and the SaaS decides what «stuck» means (hub#326).
    #[serde(flatten)]
    pub pending: PendingObligationFields,
    /// CPU del contenedor en %, `0..100` (hub#975). Mismas unidades que el Cloud ingiere
    /// (`cpu_pct`, que alimenta las sparklines de `HubMetricSample`).
    ///
    /// Sale de la `fraction` del sampler ÚNICO de `system_metrics` (cgroup v2) — no hay segundo
    /// lector de `/sys`. Ausente = no medible (fuera de contenedor, o cgroup sin límite de CPU:
    /// `used_cores` solo no es un porcentaje). Nunca un `0` fabricado: pintaría cada hub de
    /// escritorio como un hub muerto en el panel de flota.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cpu_pct: Option<f64>,
    /// Memoria usada del contenedor en MB (hub#975): `used_bytes` del sampler (ya sin la caché
    /// de página, como `docker stats`) convertida a MB. Ausente = fuera de contenedor.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_used_mb: Option<f64>,
    /// Techo de memoria del contenedor en MB (hub#975): `memory.max` del cgroup. Ausente cuando
    /// no hay techo (`"max"`) — el Cloud dejará su `memory_pct` a `null`, que es la verdad.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_limit_mb: Option<f64>,
    /// Pico histórico de memoria del contenedor en MB (hub#981): `memory.peak` del cgroup. Es un
    /// high-water mark, no una muestra — sobrevive al arranque, que es el momento más caro (se
    /// reinstalan todos los módulos, contrato stateless) y dura segundos: ni el muestreo del
    /// latido ni cAdvisor a 60 s lo ven. Es el dato que dimensiona el techo de RAM de un plan.
    /// Ausente donde el kernel no expone `memory.peak` (< 5.19) o fuera de contenedor.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_peak_mb: Option<f64>,
    /// Cuál de las DOS vías EXCLUYENTES (ADR-0320 §1, hub#1314) lleva los registros de este hub a
    /// la AEAT: `own` = el obligado firma y remite con su certificado —**el Anexo I no le
    /// aplica**—; `delegated` = ERPlora remite en su nombre con su Sello, que es exactamente lo
    /// que autoriza el otorgamiento firmado.
    ///
    /// Sale de [`erplora_runtime::certificate::transmission_route`], la MISMA función con la que
    /// el hub decide su go-live y pinta su propia pantalla. Que la resolviera el Cloud por su
    /// cuenta sería una segunda regla, y dos reglas separadas es como la pantalla y la puerta
    /// acaban discrepando sobre la vía de un negocio.
    ///
    /// **Ausente = no se pudo leer**, nunca «volvió a `delegated`»: misma semántica que
    /// `orders_today` y `cert_version` arriba, y aquí cuesta un documento legal de más. El Cloud
    /// deja su espejo como estaba (saas#1745) — el silencio no mueve la columna.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transmission_route: Option<&'static str>,
}

/// Un MB en bytes, para la conversión a las unidades del Cloud (1024·1024, la misma base que
/// `BYTES_PER_GIB` del contrato de BD: el ratio used/limit del Cloud es insensible a la base,
/// pero el valor absoluto que guarda `last_metrics` no).
const BYTES_PER_MB: f64 = 1024.0 * 1024.0;

/// Redondeo a 2 decimales: suficiente para una sparkline, y mantiene el payload estable
/// (un `f64` sin acotar mandaría 17 dígitos por latido).
/// Per-engine pending work, flattened into the heartbeat at its exact position:
/// `(module_id, depth, oldest_pending_at)` becomes `{module_id}_pending_depth` and —
/// only when known — `{module_id}_oldest_pending_at`.
///
/// The key names are BUILT from the registered module id (hub#1406, «the core does not
/// name countries»): for the `verifactu` engine they come out as the exact wire names
/// the SaaS already stores (`verifactu_pending_depth` / `verifactu_oldest_pending_at`,
/// hub#326) — frozen by `tests/heartbeat_payload_contract_hub1406.rs`. An engine whose
/// queue could not be read has NO entry here: absence stays «I don't know».
#[derive(Debug, Clone, PartialEq, Default)]
pub struct PendingObligationFields(pub Vec<(String, u64, Option<String>)>);

impl Serialize for PendingObligationFields {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let entries = self
            .0
            .iter()
            .map(|(_, _, oldest)| 1 + usize::from(oldest.is_some()))
            .sum();
        let mut map = serializer.serialize_map(Some(entries))?;
        for (module_id, depth, oldest) in &self.0 {
            map.serialize_entry(&format!("{module_id}_pending_depth"), depth)?;
            if let Some(at) = oldest {
                map.serialize_entry(&format!("{module_id}_oldest_pending_at"), at)?;
            }
        }
        map.end()
    }
}

impl PendingObligationFields {
    /// One wire entry per engine that ANSWERED the registry's question
    /// ([`erplora_runtime::Runtime::pending_obligations`]): `Some` = what it owes,
    /// `None` = an honest zero. Engines that could not be read never reach this list.
    pub fn from_report(report: &[(String, Option<PendingObligation>)]) -> Self {
        Self(
            report
                .iter()
                .map(|(module_id, answer)| match answer {
                    Some(owed) => (
                        module_id.clone(),
                        owed.count,
                        owed.oldest_pending_at.clone(),
                    ),
                    None => (module_id.clone(), 0, None),
                })
                .collect(),
        )
    }
}

fn round2(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

impl DailyUsageHeartbeat {
    /// Rellena la telemetría de recursos (hub#975) a partir de las métricas del sampler de
    /// `system_metrics` — conversión de UNIDADES, no una segunda lectura del cgroup.
    pub fn set_resource_metrics(
        &mut self,
        memory: crate::system_metrics::MemoryMetric,
        cpu: crate::system_metrics::CpuMetric,
    ) {
        self.memory_used_mb = memory.used_bytes.map(|b| round2(b as f64 / BYTES_PER_MB));
        self.memory_limit_mb = memory.limit_bytes.map(|b| round2(b as f64 / BYTES_PER_MB));
        self.memory_peak_mb = memory.peak_bytes.map(|b| round2(b as f64 / BYTES_PER_MB));
        self.cpu_pct = cpu.fraction.map(|f| round2(f * 100.0));
    }
}

/// Muestrea la telemetría de recursos del cgroup (hub#975) para el latido: el MISMO sampler
/// testeado de `/api/system/metrics`, envuelto en `spawn_blocking` porque duerme 100 ms para la
/// segunda muestra de CPU. Fuera de contenedor las métricas llegan «no disponibles» y los campos
/// viajan ausentes — la telemetría nunca bloquea un latido que alimenta el reloj de actividad.
pub async fn sample_resource_metrics() -> ResourceMetrics {
    let (memory, cpu) = tokio::task::spawn_blocking(|| {
        crate::system_metrics::sample_cgroup(&crate::system_metrics::SysCgroupReader)
    })
    .await
    .unwrap_or_else(|_| {
        (
            crate::system_metrics::MemoryMetric::unavailable(),
            crate::system_metrics::CpuMetric::unavailable(),
        )
    });
    ResourceMetrics { memory, cpu }
}

/// Las métricas crudas del sampler, listas para [`DailyUsageHeartbeat::set_resource_metrics`].
pub struct ResourceMetrics {
    memory: crate::system_metrics::MemoryMetric,
    cpu: crate::system_metrics::CpuMetric,
}

impl ResourceMetrics {
    /// Las vierte en el latido (ver [`DailyUsageHeartbeat::set_resource_metrics`]).
    pub fn apply_to(self, heartbeat: &mut DailyUsageHeartbeat) {
        heartbeat.set_resource_metrics(self.memory, self.cpu);
    }
}

/// What the control plane answered to a heartbeat (ADR-0202 §2.5 — hub#318).
///
/// The heartbeat is the **downstream** half of the convergence contract: the response carries the
/// version of the certificate the control plane currently serves, and a hub whose own version
/// differs refetches. It is the cheap trigger — the call already happens, with the credential it
/// already carries, so a rotation converges without a second scheduler or a push channel.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct HeartbeatResponse {
    /// `cert_version` announced by the control plane, when it announced one at all.
    ///
    /// **`None` is «nothing was announced», not «zero»**: an older SaaS answers `{"ok": true}` and
    /// a proxy can answer something that is not JSON at all. Reading either as `0` would be reading
    /// «the control plane has no certificate» out of silence.
    pub cert_version: Option<i64>,
    /// The manufacturer's half of `SistemaInformatico` (ADR-0202 §5.1 — hub#323), when the block
    /// came and was valid.
    ///
    /// It rides the beat instead of being announced: ~80 bytes of PUBLIC data, so a version
    /// number to trigger a fetch would cost more —in bytes, in state and in one more state
    /// machine on this side— than the payload it would be guarding. The certificate is versioned
    /// precisely because it is the opposite: a private key that cannot travel in a 60-second loop.
    ///
    /// `None` again means «nothing was announced», and it is NOT a set of defaults: there are
    /// none for a legal declaration. The engine refuses to build an envelope it cannot fill.
    pub producer: Option<ProducerFacts>,
}

impl HeartbeatResponse {
    /// Reads the response body **best-effort**: anything unexpected means «nothing announced».
    ///
    /// Deliberately forgiving, and it is not laziness. A 2xx heartbeat already did its real job
    /// (ADR-0175's activity clock, which is what decides whether a free hub gets switched off), so
    /// a body this hub cannot understand must not turn into an error that stops the clock. The
    /// certificate announcement is an extra that rides along, and it degrades to «no news».
    pub fn parse(body: &str) -> Self {
        let Ok(body) = serde_json::from_str::<Value>(body) else {
            return Self::default();
        };
        let announced = body
            .get("cert_version")
            .and_then(Value::as_i64)
            // A negative version cannot exist (`DelegatedCertificate.version` starts at 0 and only
            // grows). Treating it as an announcement would make the hub chase a version nobody can
            // serve, once per heartbeat, against a budgeted endpoint.
            .filter(|version| *version >= 0);
        // `ProducerFacts::parse` is the validation, and it is deliberately all-or-nothing: these
        // fields are identical across the fleet, so one bad character is AEAT error 1100 on every
        // record of every hub. A block that would be rejected is treated as no block, which keeps
        // whatever this hub already had.
        Self {
            cert_version: announced,
            producer: body.get("producer").and_then(ProducerFacts::parse),
        }
    }
}

/// Collect today's completed, non-deleted sales and the latest sale timestamp.
/// The SQL intentionally mirrors the module's canonical `sales.today` query.
pub async fn collect_daily_usage(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    now: &str,
    pending: &[(String, Option<PendingObligation>)],
) -> DailyUsageHeartbeat {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    params.insert("now".into(), json!(now));

    let sales = db
        .query(
            "SELECT COUNT(*) AS orders_today, MAX(created_at) AS last_sale_at \
             FROM sales_sale \
             WHERE hub_id = :hub_id AND is_deleted = 0 AND status = 'completed' \
             AND erp_date(created_at) = erp_date(:now)",
            &params,
        )
        .await
        .ok()
        .and_then(|result| result.rows.into_iter().next());

    let orders_today = sales
        .as_ref()
        .and_then(|row| value_as_u64(&row["orders_today"]));
    let last_sale_at = sales
        .as_ref()
        .and_then(|row| row["last_sale_at"].as_str().map(str::to_owned));

    let terminals = db
        .query(
            // Acotado por `hub_id` desde hub#497: este número viaja al SaaS y alimenta el
            // límite de dispositivos del plan. Sin el filtro, en una BD compartida un hub
            // reportaba las terminales del negocio de al lado como suyas.
            "SELECT COUNT(DISTINCT device_id) AS terminals FROM hub_session \
             WHERE hub_id = :hub_id AND expires_at > :now AND device_id IS NOT NULL",
            &params,
        )
        .await
        .ok()
        .and_then(|result| result.rows.into_iter().next())
        .and_then(|row| value_as_u64(&row["terminals"]));

    DailyUsageHeartbeat {
        orders_today,
        last_sale_at,
        terminals,
        // La actividad de usuario no se lee AQUÍ: la sirve el `ActivityState`, que la mantiene en
        // un atómico y la respalda en `_hub_activity` (hub#670). La rellena el llamador (`serve`)
        // y solo si hay algo nuevo que reportar.
        last_user_activity_at: None,
        // El certificado delegado tampoco sale de aquí: lo rellena el llamador (`serve`) con
        // `fiscal_certificate::delegated_certificate_report`, que sabe distinguir «no tengo» de
        // «no he podido leerlo».
        cert_version: None,
        cert_not_after: None,
        // No sale de la BD ni la rellena el llamador: va compilada en el binario, así que el
        // único sitio honesto para leerla es aquí.
        hub_version: crate::version::HUB_VERSION.to_string(),
        // Lo que cada motor instalado debe a su autoridad externa (hub#326/hub#1406). Lo cuenta
        // el MOTOR vía el registro genérico — la misma pregunta que bloquea una desinstalación
        // (hub#314), así que no pueden discrepar. Un motor ilegible NO tiene entrada: «no lo sé»
        // viaja como ausencia, nunca como un `0` fabricado.
        pending: PendingObligationFields::from_report(pending),
        // La telemetría de recursos (hub#975) no se lee AQUÍ: la rellena el llamador (`serve` /
        // `boot_announce`) con `sample_resource_metrics`, que muestrea el cgroup FUERA del lock
        // del runtime — el sampler duerme 100 ms y no debe sostener el lock ni la BD.
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        // La vía por la que este hub remite (hub#1441). SÍ se lee aquí, y no en el llamador como
        // el certificado delegado: es una consulta barata a las mismas tablas que las de arriba y
        // los DOS latidos —el de arranque y el tick de 24 h— la necesitan igual. Rellenarla en un
        // solo llamador dejaría al otro mandando un cuerpo sin vía, y el Cloud no distingue «este
        // latido no la trae» de «este hub no la sabe». `Err` viaja como ausencia (`.ok()`), que es
        // lo que el contrato reserva para «no pude leerlo».
        transmission_route: erplora_runtime::certificate::transmission_route(db, hub_id)
            .await
            .ok(),
    }
}

/// Send a best-effort heartbeat with the existing machine credential, and return what the control
/// plane announced back (ADR-0202 §2.5 — hub#318).
pub async fn send_heartbeat(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    body: &DailyUsageHeartbeat,
) -> Result<HeartbeatResponse, String> {
    let req = cloud_client::CloudClient::new(cloud_base_url).heartbeat(auth);
    let mut request = http.post(&req.url).json(body);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("{}: status {}", req.url, response.status()));
    }
    // A 2xx IS the success: the heartbeat's own job (ADR-0175's activity clock) is done, and the
    // caller may confirm it. The body is a bonus, so a truncated read degrades to «nothing
    // announced» rather than undoing a heartbeat that the Cloud already recorded.
    let body = response.text().await.unwrap_or_default();
    let answer = HeartbeatResponse::parse(&body);
    // The manufacturer's facts are installed HERE and not by each caller (ADR-0202 §5.1 —
    // hub#323): both the boot announce and the 60-second loop go through this function, so the
    // boot one doubles as the pull the fiscal endpoint exists for, and there is no second place
    // that can forget. Nothing below the host learns that a control plane exists — the engine
    // reads the cache through `NativeHost::producer_facts`.
    if let Some(facts) = answer.producer.clone() {
        ProducerFactsCache::global().store(facts);
    }
    Ok(answer)
}

fn value_as_u64(value: &Value) -> Option<u64> {
    match value {
        Value::Number(number) => number
            .as_u64()
            .or_else(|| number.as_i64().and_then(|n| u64::try_from(n).ok())),
        Value::String(text) => text.trim().parse().ok(),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::State;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::post;
    use axum::{Json, Router};
    use erplora_db::testutil::fresh_db;
    use std::sync::{Arc, Mutex};
    use tokio::sync::oneshot;

    #[tokio::test]
    async fn collects_only_completed_sales_for_this_hub_and_day() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE sales_sale (\
               id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, status TEXT NOT NULL, \
               is_deleted BIGINT NOT NULL DEFAULT 0, created_at TEXT NOT NULL\
             );\
             CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, hub_id TEXT NOT NULL, device_id TEXT, expires_at TEXT NOT NULL\
             );\
             INSERT INTO sales_sale VALUES\
               ('s1', 'hub-a', 'completed', 0, '2026-07-27T09:00:00Z'),\
               ('s2', 'hub-a', 'completed', 0, '2026-07-27T11:30:00Z'),\
               ('old', 'hub-a', 'completed', 0, '2026-07-26T23:59:59Z'),\
               ('void', 'hub-a', 'voided', 0, '2026-07-27T12:00:00Z'),\
               ('deleted', 'hub-a', 'completed', 1, '2026-07-27T13:00:00Z'),\
               ('other', 'hub-b', 'completed', 0, '2026-07-27T14:00:00Z');\
             INSERT INTO hub_session VALUES\
               ('a1', 'hub-a', 'device-a', '2026-07-28T00:00:00Z'),\
               ('a2', 'hub-a', 'device-a', '2026-07-28T00:00:00Z'),\
               ('b1', 'hub-a', 'device-b', '2026-07-28T00:00:00Z'),\
               ('expired', 'hub-a', 'device-c', '2026-07-27T00:00:00Z'),\
               ('unknown', 'hub-a', NULL, '2026-07-28T00:00:00Z'),\
               ('next-door', 'hub-b', 'device-z', '2026-07-28T00:00:00Z');",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z", &[]).await;
        assert_eq!(usage.orders_today, Some(2));
        assert_eq!(usage.last_sale_at.as_deref(), Some("2026-07-27T11:30:00Z"));
        assert_eq!(
            usage.terminals,
            Some(2),
            "dos terminales de ESTE hub — la del negocio de al lado (`next-door`, hub-b) no cuenta              como nuestra, y este número alimenta el límite de dispositivos del plan (hub#497)"
        );
    }

    #[tokio::test]
    async fn missing_sales_table_omits_usage_instead_of_inventing_zero() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, hub_id TEXT NOT NULL, device_id TEXT, expires_at TEXT NOT NULL\
             );",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z", &[]).await;
        assert_eq!(usage.orders_today, None);
        assert_eq!(usage.last_sale_at, None);
        assert_eq!(usage.terminals, Some(0));
        assert_eq!(
            serde_json::to_value(usage).unwrap(),
            json!({"terminals": 0, "hub_version": crate::version::HUB_VERSION})
        );
    }

    #[tokio::test]
    async fn sends_expected_json_and_machine_headers() {
        type Captured = Arc<Mutex<Option<oneshot::Sender<(HeaderMap, Value)>>>>;

        async fn capture(
            State(sender): State<Captured>,
            headers: HeaderMap,
            Json(body): Json<Value>,
        ) -> StatusCode {
            if let Some(sender) = sender.lock().unwrap().take() {
                let _ = sender.send((headers, body));
            }
            StatusCode::OK
        }

        let (sender, receiver) = oneshot::channel();
        let app = Router::new()
            .route("/api/v1/hub/device/heartbeat/", post(capture))
            .with_state(Arc::new(Mutex::new(Some(sender))));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

        let auth = cloud_client::Auth::HubToken {
            hub_id: "hub-a".into(),
            token: "machine-token".into(),
        };
        let body = DailyUsageHeartbeat {
            orders_today: Some(12),
            last_sale_at: Some("2026-07-27T11:30:00Z".into()),
            terminals: Some(3),
            last_user_activity_at: Some("2026-07-27T11:45:00Z".into()),
            cert_version: Some(4),
            cert_not_after: Some("2028-06-10".into()),
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields(vec![(
                "verifactu".into(),
                2,
                Some("2026-07-25T08:00:00Z".into()),
            )]),
            cpu_pct: Some(50.0),
            memory_used_mb: Some(10.0),
            memory_limit_mb: Some(96.0),
            memory_peak_mb: Some(192.0),
            transmission_route: None,
        };
        send_heartbeat(
            &reqwest::Client::new(),
            &format!("http://{address}"),
            &auth,
            &body,
        )
        .await
        .unwrap();

        let (headers, received) = receiver.await.unwrap();
        assert_eq!(headers["x-hub-id"], "hub-a");
        assert_eq!(headers["x-hub-token"], "machine-token");
        assert_eq!(
            received,
            json!({
                "orders_today": 12,
                "last_sale_at": "2026-07-27T11:30:00Z",
                "terminals": 3,
                "last_user_activity_at": "2026-07-27T11:45:00Z",
                "cert_version": 4,
                "cert_not_after": "2028-06-10",
                "hub_version": crate::version::HUB_VERSION,
                // hub#326: the queue the SaaS alerts on travels under these exact names.
                "verifactu_pending_depth": 2,
                "verifactu_oldest_pending_at": "2026-07-25T08:00:00Z",
                // hub#975: the resource telemetry rides the same beat, in the Cloud's units —
                // these are the names `HubMetricSample` sparklines are fed from.
                "cpu_pct": 50.0,
                "memory_used_mb": 10.0,
                "memory_limit_mb": 96.0,
                "memory_peak_mb": 192.0,
            })
        );
        server.abort();
    }

    /// ADR-0175: sin actividad de usuario el campo NO viaja. El silencio es la señal — si el
    /// Cloud recibiese una marca en cada latido, un hub encendido que nadie usa parecería usado
    /// y no vencería nunca.
    #[tokio::test]
    async fn a_hub_nobody_uses_reports_no_user_activity() {
        let usage = DailyUsageHeartbeat {
            orders_today: Some(0),
            last_sale_at: None,
            terminals: Some(0),
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };
        let body = serde_json::to_value(&usage).unwrap();
        assert!(body.get("last_user_activity_at").is_none());
        assert_eq!(
            body,
            json!({"orders_today": 0, "terminals": 0, "hub_version": crate::version::HUB_VERSION})
        );
    }

    // ── The certificate the hub REPORTS (ADR-0202 §2.5 — hub#318) ─────────────────────────────

    /// **`0` travels, silence does not.** The Cloud stores `NULL` (never reported) and `0` (holds
    /// no delegated certificate) in different states, so a hub that genuinely has none must SAY
    /// `0` — omitting it would leave the fleet panel showing a hub that never spoke, forever.
    #[test]
    fn a_hub_with_no_delegated_certificate_reports_an_explicit_zero() {
        let usage = DailyUsageHeartbeat {
            orders_today: None,
            last_sale_at: None,
            terminals: None,
            last_user_activity_at: None,
            cert_version: Some(0),
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };
        let body = serde_json::to_value(&usage).unwrap();
        assert_eq!(
            body,
            json!({"cert_version": 0, "hub_version": crate::version::HUB_VERSION})
        );
        // Y la caducidad NO viaja: es justo lo que borra en el Cloud la fecha vieja de un hub
        // reprovisionado (§2.5, «el par se escribe entero»).
        assert!(body.get("cert_not_after").is_none());
    }

    // ── Resource telemetry (hub#975): the cgroup metrics ride the same beat ────────────────────

    /// 🔴 [hub#975] The metrics `system_metrics` already reads travel in the Cloud's units.
    ///
    /// The sampler exists and `/api/system/metrics` serves it, but the heartbeat body never
    /// carried it: 0/4 production hubs had `memory_used_mb`, and `HubMetricSample` (the fleet
    /// sparklines `architecture/saas/hub-monitoring.md` documents) had zero rows. The conversion
    /// is UNITS ONLY — bytes → MB for memory, fraction → % for CPU — because the sampler stays
    /// the single reader of the cgroup (no second parser to drift).
    #[test]
    fn resource_metrics_ride_the_beat_in_cloud_units() {
        let mut usage = DailyUsageHeartbeat {
            orders_today: None,
            last_sale_at: None,
            terminals: None,
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };
        // La fixture del free tier real (system_metrics): 10 MiB usados de 96 MiB, 0,5 de 1 core.
        usage.set_resource_metrics(
            crate::system_metrics::MemoryMetric {
                used_bytes: Some(10_485_760),
                limit_bytes: Some(100_663_296),
                fraction: Some(10_485_760.0 / 100_663_296.0),
                peak_bytes: Some(201_326_592),
            },
            crate::system_metrics::CpuMetric {
                used_cores: Some(0.5),
                limit_cores: Some(1.0),
                fraction: Some(0.5),
            },
        );
        let body = serde_json::to_value(&usage).unwrap();
        assert_eq!(
            body["cpu_pct"],
            json!(50.0),
            "fracción 0..1 → porcentaje del Cloud"
        );
        assert_eq!(
            body["memory_used_mb"],
            json!(10.0),
            "bytes → MB (10 MiB exactos)"
        );
        assert_eq!(
            body["memory_limit_mb"],
            json!(96.0),
            "bytes → MB (96 MiB del plan free)"
        );
        // El PICO es lo que decide el techo de un plan: el régimen cabe de sobra en 256 MiB, y lo
        // que no se ve desde fuera es el arranque (reinstalación stateless de los módulos), que
        // dura segundos y cae entre scrapes. `memory.peak` es un high-water mark, así que el
        // latido lo lleva aunque el pico ocurriera hace horas (hub#981).
        assert_eq!(
            body["memory_peak_mb"],
            json!(192.0),
            "bytes → MB (192 MiB de pico)"
        );
    }

    /// 🔴 [hub#975] Outside a container (Tauri/desktop/dev) the cgroup does not exist: the
    /// fields stay ABSENT, never a fabricated `0` — the same rule `orders_today` already
    /// follows. A zero would paint every desktop hub as an idle one in the fleet panel.
    #[test]
    fn unmeasurable_metrics_travel_as_silence() {
        let mut usage = DailyUsageHeartbeat {
            orders_today: None,
            last_sale_at: None,
            terminals: None,
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };
        usage.set_resource_metrics(
            crate::system_metrics::MemoryMetric {
                used_bytes: None,
                limit_bytes: None,
                fraction: None,
                peak_bytes: None,
            },
            crate::system_metrics::CpuMetric {
                used_cores: None,
                limit_cores: None,
                fraction: None,
            },
        );
        let body = serde_json::to_value(&usage).unwrap();
        assert!(
            body.get("cpu_pct").is_none(),
            "sin cgroup no hay porcentaje"
        );
        assert!(
            body.get("memory_used_mb").is_none(),
            "sin cgroup no hay MB usados"
        );
        assert!(body.get("memory_limit_mb").is_none());
    }

    /// 🔴 [hub#975] CPU without a limit has no percentage either: `used_cores` alone is not a
    /// `cpu_pct`, and sending it as one would report «0,7 %» for a hub at 70% of an unlabeled
    /// machine. Memory does travel: `memory.max = "max"` still yields a real `used` against no
    /// ceiling, and the Cloud's `memory_pct` simply stays null on its side.
    #[test]
    fn cpu_without_a_limit_has_no_percentage_but_memory_still_travels() {
        let mut usage = DailyUsageHeartbeat {
            orders_today: None,
            last_sale_at: None,
            terminals: None,
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };
        usage.set_resource_metrics(
            crate::system_metrics::MemoryMetric {
                used_bytes: Some(10_485_760),
                limit_bytes: None, // `memory.max = "max"`: sin techo
                fraction: None,
                peak_bytes: None, // kernel sin `memory.peak`
            },
            crate::system_metrics::CpuMetric {
                used_cores: Some(0.7),
                limit_cores: None, // `cpu.max = "max ..."`: sin techo
                fraction: None,
            },
        );
        let body = serde_json::to_value(&usage).unwrap();
        assert!(body.get("cpu_pct").is_none(), "0,7 cores NO es un 0,7 %");
        assert_eq!(
            body["memory_used_mb"],
            json!(10.0),
            "el uso medido sí viaja"
        );
        assert!(body.get("memory_limit_mb").is_none());
    }

    /// **A read failure is silence, never a zero.** Same rule `orders_today` already follows: the
    /// Cloud must not turn a failure of ours into a fact about the fleet. A fabricated `0` would
    /// paint a healthy hub as one that lost ERPlora's certificate.
    #[test]
    fn a_hub_that_could_not_read_its_certificate_says_nothing_instead_of_zero() {
        let usage = DailyUsageHeartbeat {
            orders_today: Some(3),
            last_sale_at: None,
            terminals: Some(1),
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };
        let body = serde_json::to_value(&usage).unwrap();
        assert!(body.get("cert_version").is_none());
        assert_eq!(
            body,
            json!({"orders_today": 3, "terminals": 1, "hub_version": crate::version::HUB_VERSION})
        );
    }

    // ── What the control plane announces back (ADR-0202 §2.5) ─────────────────────────────────

    #[test]
    fn the_announced_version_is_read_from_the_response() {
        assert_eq!(
            HeartbeatResponse::parse(r#"{"ok": true, "cert_version": 4}"#),
            HeartbeatResponse {
                cert_version: Some(4),
                producer: None,
            }
        );
        // `0` es un anuncio de pleno derecho: «no he subido nada» (y el hub NO debe pedir el GET).
        assert_eq!(
            HeartbeatResponse::parse(r#"{"ok": true, "cert_version": 0}"#).cert_version,
            Some(0)
        );
    }

    /// **Silence is not zero.** A SaaS from before saas#1126 answers `{"ok": true}`; reading that
    /// as «the control plane has no certificate» would be inventing news out of an old deployment.
    #[test]
    fn an_older_control_plane_that_announces_nothing_is_not_read_as_zero() {
        assert_eq!(
            HeartbeatResponse::parse(r#"{"ok": true}"#).cert_version,
            None
        );
        assert_eq!(
            HeartbeatResponse::parse(r#"{"cert_version": null}"#).cert_version,
            None
        );
    }

    /// **A body this hub cannot parse must not become an error.** The heartbeat already succeeded
    /// (2xx) and its real job is ADR-0175's activity clock: if an edge that answers HTML turned the
    /// call into a failure, the hub would stop confirming activity and the Cloud would count it
    /// idle — and eventually switch a hub off that people are using every day.
    #[test]
    fn a_body_that_is_not_json_degrades_to_no_news() {
        assert_eq!(
            HeartbeatResponse::parse("<html>502</html>").cert_version,
            None
        );
        assert_eq!(HeartbeatResponse::parse("").cert_version, None);
        assert_eq!(HeartbeatResponse::parse("[]").cert_version, None);
    }

    // ── The manufacturer's facts ride the beat (ADR-0202 §5.1 — hub#323) ─────────────────────
    //
    // `SistemaInformatico` needs seven fields this hub cannot know: the manufacturer's identity
    // and `IndicadorMultiplesOT`, which the AEAT computes per ACCOUNT. They are ~80 bytes and
    // public, so they travel inline every minute instead of being announced by a version number
    // the hub would then have to go and fetch.

    fn served_producer_body() -> String {
        r#"{"ok": true, "producer": {
             "NombreRazon": "ERPLORA CLOUD SL", "NIF": "B27593136",
             "NombreSistemaInformatico": "ERPlora Hub", "IdSistemaInformatico": "EC",
             "TipoUsoPosibleSoloVerifactu": "S", "TipoUsoPosibleMultiOT": "S",
             "IndicadorMultiplesOT": "S"}}"#
            .to_string()
    }

    /// 🔴 hub#323: the block was served (saas#1128) and the hub threw it away, so every record
    /// kept declaring a hardcoded `IndicadorMultiplesOT = N`.
    #[test]
    fn the_beat_carries_the_manufacturer_s_facts() {
        let facts = HeartbeatResponse::parse(&served_producer_body())
            .producer
            .expect("the block the SaaS serves must be read");

        assert_eq!(facts.nombre_razon, "ERPLORA CLOUD SL");
        assert_eq!(facts.nombre_sistema_informatico, "ERPlora Hub");
        assert_eq!(
            facts.indicador_multiples_ot, "S",
            "this is the field only the control plane can compute"
        );
    }

    /// A control plane from before saas#1128 says nothing, and nothing is not a set of defaults:
    /// the hub keeps whatever it already had rather than inventing a legal declaration.
    #[test]
    fn a_beat_without_the_block_announces_no_facts() {
        assert!(HeartbeatResponse::parse(r#"{"ok": true}"#)
            .producer
            .is_none());
        assert!(HeartbeatResponse::parse("<html>502</html>")
            .producer
            .is_none());
    }

    /// A block that would be rejected by the AEAT is not installed. These facts are identical for
    /// the whole fleet, so one bad field is error 1100 on every record of every hub — keeping the
    /// previous ones beats adopting a broken identity.
    #[test]
    fn a_block_the_aeat_would_reject_is_not_adopted() {
        let broken = served_producer_body().replace(
            r#""IdSistemaInformatico": "EC""#,
            r#""IdSistemaInformatico": "ERPLORA-001""#,
        );

        assert!(HeartbeatResponse::parse(&broken).producer.is_none());
    }

    /// A version that cannot exist is not an announcement. `DelegatedCertificate.version` starts at
    /// `0` and only grows, so a negative would just make the hub chase a certificate nobody can
    /// serve — once per heartbeat, against an endpoint that is budgeted at 20/h.
    #[test]
    fn a_negative_version_is_not_an_announcement() {
        assert_eq!(
            HeartbeatResponse::parse(r#"{"cert_version": -1}"#).cert_version,
            None
        );
    }

    /// A 2xx whose body is unreadable is still a heartbeat that ARRIVED: it must come back `Ok`,
    /// because the caller confirms ADR-0175's activity mark on `Ok` and only on `Ok`.
    #[tokio::test]
    async fn an_unparseable_body_still_counts_as_a_delivered_heartbeat() {
        let app = Router::new().route(
            "/api/v1/hub/device/heartbeat/",
            post(|| async { (StatusCode::OK, "<html>hola</html>") }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

        let auth = cloud_client::Auth::HubToken {
            hub_id: "hub-a".into(),
            token: "machine-token".into(),
        };
        let response = send_heartbeat(
            &reqwest::Client::new(),
            &format!("http://{address}"),
            &auth,
            &DailyUsageHeartbeat {
                orders_today: None,
                last_sale_at: None,
                terminals: None,
                last_user_activity_at: None,
                cert_version: Some(0),
                cert_not_after: None,
                hub_version: crate::version::HUB_VERSION.to_string(),
                pending: PendingObligationFields::default(),
                cpu_pct: None,
                memory_used_mb: None,
                memory_limit_mb: None,
                memory_peak_mb: None,
                transmission_route: None,
            },
        )
        .await
        .expect("un 2xx es un latido entregado, lo que traiga el cuerpo o no");
        assert_eq!(response.cert_version, None);
        server.abort();
    }

    /// 🔒 …y lo mismo cuando el cuerpo **no se puede ni leer**: la respuesta promete 64 bytes y la
    /// conexión se corta a los 2.
    ///
    /// Es el caso que un stub HTTP normal no puede montar, y es justo el que aparece de verdad —
    /// un reset a mitad de respuesta, un edge que se rinde. Si eso convirtiera el latido en un
    /// error, el hub dejaría de confirmar la marca de actividad de ADR-0175 y el Cloud acabaría
    /// **apagando un hub que se usa a diario**. El anuncio del certificado es un extra que viaja
    /// encima; el latido ya llegó.
    #[tokio::test]
    async fn a_body_that_cannot_even_be_read_still_counts_as_a_delivered_heartbeat() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};

        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            if let Ok((mut socket, _)) = listener.accept().await {
                // Basta con drenar algo de la petición para que el cliente termine de enviarla.
                let mut buffer = [0u8; 4096];
                let _ = socket.read(&mut buffer).await;
                let _ = socket
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 64\r\n\r\nok")
                    .await;
                let _ = socket.shutdown().await;
            }
        });

        let auth = cloud_client::Auth::HubToken {
            hub_id: "hub-a".into(),
            token: "machine-token".into(),
        };
        let response = send_heartbeat(
            &reqwest::Client::new(),
            &format!("http://{address}"),
            &auth,
            &DailyUsageHeartbeat {
                orders_today: None,
                last_sale_at: None,
                terminals: None,
                last_user_activity_at: None,
                cert_version: Some(4),
                cert_not_after: None,
                hub_version: crate::version::HUB_VERSION.to_string(),
                pending: PendingObligationFields::default(),
                cpu_pct: None,
                memory_used_mb: None,
                memory_limit_mb: None,
                memory_peak_mb: None,
                transmission_route: None,
            },
        )
        .await
        .expect("un 2xx entregado no puede deshacerse porque el cuerpo se corte");
        assert_eq!(
            response.cert_version, None,
            "sin cuerpo legible, sin noticias"
        );
        server.abort();
    }

    /// The hub tells the control plane which version is running (hub#515).
    ///
    /// Without it, «is this hub up to date?» has no answer that does not involve guessing from a
    /// digest — and a digest cannot say whether the jump ahead is a security patch or a new
    /// version. It rides THIS request because the heartbeat is already the beat that carries the
    /// machine credential at the right cadence; a second call would be a second thing to break.
    ///
    /// It is the same number `/system` shows and `error_sink` stamps on every reported error
    /// ([`crate::version::HUB_VERSION`]), and it goes on the wire WITHOUT the `v` — the prefix is
    /// for humans reading a panel, not for something the Cloud will compare.
    #[test]
    fn the_heartbeat_carries_the_running_hub_version() {
        let body = DailyUsageHeartbeat {
            orders_today: Some(3),
            last_sale_at: None,
            terminals: None,
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };

        let wire = serde_json::to_value(&body).expect("el latido tiene que serializar");

        assert_eq!(wire["hub_version"], crate::version::HUB_VERSION);
        assert!(
            !wire["hub_version"].as_str().unwrap().starts_with('v'),
            "el `v` es para la pantalla, no para el cable"
        );
    }

    /// It is always there — never «absent because I could not read it».
    ///
    /// Every other optional field on this body means a READ FAILURE when missing (`orders_today`,
    /// `cert_version`…), and the Cloud stores that difference. The version is compiled in, so
    /// there is no failure mode where it is unknown: making it optional would invent a third
    /// state nobody can produce.
    #[tokio::test]
    async fn the_collected_heartbeat_already_knows_its_version() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE sales_sale (\
               id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, status TEXT NOT NULL, \
               is_deleted BIGINT NOT NULL DEFAULT 0, created_at TEXT NOT NULL\
             );\
             CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, hub_id TEXT NOT NULL, device_id TEXT, expires_at TEXT NOT NULL\
             );",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-1", "2026-08-08T10:00:00Z", &[]).await;

        assert_eq!(usage.hub_version, crate::version::HUB_VERSION);
    }
}
