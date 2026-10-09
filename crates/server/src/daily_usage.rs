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
use erplora_runtime::producer_facts::{DeclarationReference, ProducerFacts, ProducerFactsCache};
use serde::Serialize;
use serde_json::{json, Value};

/// One thing somebody of the business DID, on the wire (saas#2129).
///
/// FOUR KEYS AND NO MORE, and the Cloud reads exactly these four. Nothing about the END CUSTOMER
/// travels — not who bought, not what, not how much — and the guard is that there is nowhere to
/// put it, not a list of forbidden names somebody has to keep up to date.
///
/// `id` is minted by the hub and is the dedup key: delivery is at-least-once (the batch is
/// re-sent until a beat answers 2xx), and that id is what makes storage exactly-once on the other
/// side. `actor` is the hub's own id for that person — never a name, never an email.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ActivityEvent {
    pub id: String,
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(rename = "at")]
    pub occurred_at: String,
    pub actor: String,
}

impl From<erplora_runtime::activity_log::PendingEvent> for ActivityEvent {
    fn from(event: erplora_runtime::activity_log::PendingEvent) -> Self {
        Self {
            id: event.id,
            kind: event.kind,
            occurred_at: event.occurred_at,
            actor: event.actor,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct DailyUsageHeartbeat {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub orders_today: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_sale_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub terminals: Option<u64>,
    /// How many people hold a seat of this hub's plan right now (hub#1814) — the hub's own census,
    /// which is the only place the people who sign in with a **PIN** exist.
    ///
    /// Without it the SaaS can only see whoever has an ERPlora account, so a Free hub run by an
    /// owner and two PIN-only staff looks like a hub of one and its fourth invitation goes
    /// through (saas#2022 stores this into `Hub.reported_active_users` and the seat gate takes
    /// the larger of the two counts). It rides THIS request for the same reason as everything
    /// else here: the beat already carries the machine credential at the right cadence.
    ///
    /// The number comes from [`erplora_runtime::hub_users::count_active_users`], the SAME count
    /// that refuses the fourth user inside the hub (hub#1685) and feeds `users.active` on
    /// `/api/system/metrics` — a second way of counting the same thing is how a screen and a door
    /// end up disagreeing about who is in.
    ///
    /// Same `Option` semantics as the fields above, and here it is the whole point: an explicit
    /// **`0`** is «I counted and nobody works here», an ABSENT field is «I could not count» — the
    /// census would not read. A fabricated `0` would hand a free seat to a hub that is already
    /// full, which is the exact overflow this field exists to close.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub active_users: Option<u64>,
    /// Última vez que alguien **entró** en el hub (ADR-0175), si la hubo desde el último latido.
    ///
    /// Es la señal con la que el Cloud apaga (60d) y acaba borrando (120d) los hubs free que nadie
    /// usa, y va aquí — y no en un job aparte — porque este heartbeat ya viaja con la credencial
    /// de máquina y la cadencia correcta. Que sea `Option` es el contrato: **ausente = nadie ha
    /// entrado**, y el Cloud debe dejar correr el reloj. Ver `crate::activity`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_user_activity_at: Option<String>,
    /// What the people of the business DID since the last beat (saas#2129) — entering, leaving,
    /// selling, refunding, opening and closing the till, each with who did it and when.
    ///
    /// The sibling of `last_user_activity_at` and a step below it: that one says *somebody came*,
    /// which is enough to decide whether a free hub is abandoned and not nearly enough to answer
    /// *are they using it*. A business in its first week — entering, building the catalogue,
    /// opening the till, not charging yet — reads as dead on the sale count alone.
    ///
    /// **Empty is not news of a zero**, same absence contract as `active_users` and the
    /// `verifactu_*` pair: it is skipped when there is nothing, and the Cloud writes nothing. The
    /// events are NOT removed from the hub's buffer by being sent — only a 2xx confirms them, so
    /// a beat that never arrives keeps them for the next one.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub activity: Vec<ActivityEvent>,
    /// The binary this container is running, e.g. `1.0.0` (hub#515) — the **same number** the
    /// `verifactu` engine emits as `SistemaInformatico/Version` in every record, because both read
    /// [`erplora_runtime::CORE_VERSION`] and there is no second source.
    ///
    /// Without it, «is this hub up to date?» can only be answered by guessing from a digest — and a
    /// digest cannot say whether the jump ahead is a security patch or a new version. It rides THIS
    /// request because the beat already carries the machine credential at the right cadence: a
    /// separate call would be one more thing that can break.
    ///
    /// **The key is `core_version`, and the name is the contract** (hub#1742). The endpoint picks
    /// the *declaración responsable* that covers this binary from exactly this field (art. 13.3
    /// RRSIF: one declaration per version of the system, and there is more than one published), and
    /// it reads no other key. Until hub#1742 the number travelled as `hub_version`, which nothing on
    /// the control plane ever read — so it was emitted and dropped, and every hub was linked the
    /// declaration in force whatever it was running. It was RENAMED rather than doubled: two
    /// spellings of one number is a drift waiting to happen, and this is the number an inspector
    /// reads. A beat that omits it is answered with the declaration in force and never fails —
    /// liveness does not depend on a legal link — so old and new hubs cross over safely.
    ///
    /// **Not an `Option`, and that is the contract.** In this body «absent» means *I could not read
    /// it* (`orders_today`…) and the Cloud stores that difference; the version is compiled into the
    /// binary, so «I don't know» is not a state that exists. It travels **without** the `v`: the
    /// prefix is for reading a panel, not for something the Cloud has to strip before comparing.
    pub core_version: String,
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
/// The heartbeat used to be the **downstream** half of a convergence contract: the response carried
/// the version of the delegated certificate the control plane served, and a hub whose own version
/// differed refetched. That certificate is retired (hub#1435), and with it the announcement — the
/// SaaS stopped sending `cert_version` in saas#1435 phase 2. What still rides the beat is the
/// manufacturer's block, which is public data and needs no versioning.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct HeartbeatResponse {
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
    /// **The Cloud has the events; the hub may drop them** (review of saas#2129).
    ///
    /// A bare `200` cannot carry this. It is also the answer of a Cloud whose ingest blew up —
    /// the view swallows that on purpose, because activity may never fail a beat — and of a Cloud
    /// that predates the field entirely (deploy order, or a PRE running behind). Deleting on
    /// either would throw the events away believing they were stored, and they cannot be
    /// reconstructed afterwards.
    ///
    /// `false` is therefore the safe default in every direction: no key, an unreadable body, an
    /// older SaaS. The events simply stay for the next beat, and the Cloud deduplicates the
    /// re-send by the id the hub minted.
    pub activity_ack: bool,
    /// Which declaración responsable on the public archive covers the release this hub is
    /// running (hub#1449, ERPlora/saas#1724 — art. 13.3 RRSIF), when the control plane could
    /// compute one.
    ///
    /// Rides beside `producer`, never inside it: `producer` is the literal AEAT element set the
    /// fleet emits verbatim into the XML, and this is a different kind of fact — where the signed
    /// text lives, not something a record carries. `None` is «no news» (an older SaaS, or an
    /// archive the control plane could not read), and the caller keeps linking the root of the
    /// public archive, which already resolves to the declaration in force.
    pub declaration: Option<DeclarationReference>,
}

impl HeartbeatResponse {
    /// Reads the response body **best-effort**: anything unexpected means «nothing announced».
    ///
    /// Deliberately forgiving, and it is not laziness. A 2xx heartbeat already did its real job
    /// (ADR-0175's activity clock, which is what decides whether a free hub gets switched off), so
    /// a body this hub cannot understand must not turn into an error that stops the clock. The
    /// manufacturer's block is an extra that rides along, and it degrades to «no news».
    ///
    /// A body that still carries the retired `cert_version` is read as any other unknown field:
    /// ignored. An older SaaS is not an error.
    pub fn parse(body: &str) -> Self {
        let Ok(body) = serde_json::from_str::<Value>(body) else {
            return Self::default();
        };
        // `ProducerFacts::parse` is the validation, and it is deliberately all-or-nothing: these
        // fields are identical across the fleet, so one bad character is AEAT error 1100 on every
        // record of every hub. A block that would be rejected is treated as no block, which keeps
        // whatever this hub already had.
        Self {
            producer: body.get("producer").and_then(ProducerFacts::parse),
            declaration: body
                .get("declaration")
                .and_then(DeclarationReference::parse),
            // Strictly `true`: anything else — absent, null, `"true"`, a number — is "I cannot
            // tell", and "I cannot tell" must never delete.
            activity_ack: body.get("activity_ack") == Some(&Value::Bool(true)),
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

    // Las personas que ocupan plaza del plan (hub#1814). SÍ se lee aquí, como `terminals` y
    // `transmission_route`: es una consulta barata a la misma BD y los DOS latidos —el de arranque
    // y el tick— la necesitan igual; rellenarla en un solo llamador dejaría al otro mandando un
    // cuerpo sin censo, y el SaaS no distingue «este latido no lo trae» de «este hub no lo sabe».
    //
    // El recuento lo hace el RUNTIME, que es el dueño del censo y ya lo cuenta igual para aplicar
    // el tope (hub#1685): dos formas de contar lo mismo acabarían discrepando, y la puerta del
    // SaaS rechazaría una invitación que el hub sí admite (o al revés).
    //
    // `Err` viaja como ausencia y un recuento que no cabe en `u64` también: el contrato reserva la
    // ausencia para «no pude contar», y un `0` fabricado le regalaría una plaza libre a un hub que
    // ya está lleno — justo el desbordamiento que este campo viene a cerrar.
    let active_users = erplora_runtime::hub_users::count_active_users(db, hub_id)
        .await
        .ok()
        .and_then(|n| u64::try_from(n).ok());

    DailyUsageHeartbeat {
        orders_today,
        last_sale_at,
        terminals,
        active_users,
        // La actividad de usuario no se lee AQUÍ: la sirve el `ActivityState`, que la mantiene en
        // un atómico y la respalda en `_hub_activity` (hub#670). La rellena el llamador (`serve`)
        // y solo si hay algo nuevo que reportar.
        last_user_activity_at: None,
        // The activity EVENTS (saas#2129) ARE read here, like `terminals` and `active_users`: a
        // cheap query to the same database that BOTH beats — the boot one and the tick — need
        // alike. Reading does NOT consume: only `activity_ack` confirms, and the caller is the
        // one who confirms (`settle_activity`), because it is the only one that knows whether the
        // Cloud actually stored them.
        //
        // `Err` travels as an empty list: an unreadable buffer is "I could not count", never a
        // hub with no activity — and certainly never a failed beat.
        activity: pending_activity(db, hub_id).await,
        // No sale de la BD ni la rellena el llamador: va compilada en el binario, así que el
        // único sitio honesto para leerla es aquí.
        core_version: crate::version::HUB_VERSION.to_string(),
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
/// Reads the next beat's worth of business activity, capping the buffer on the way past.
///
/// The trim rides this read rather than the write: a hub that cannot reach the Cloud for months
/// must not fill its own disk, and checking the ceiling once per beat costs one statement instead
/// of one per sale.
async fn pending_activity(db: &dyn DatabaseAdapter, hub_id: &str) -> Vec<ActivityEvent> {
    let _ = erplora_runtime::activity_log::trim(
        db,
        hub_id,
        erplora_runtime::activity_log::MAX_BUFFERED_EVENTS,
    )
    .await;
    erplora_runtime::activity_log::pending(
        db,
        hub_id,
        erplora_runtime::activity_log::MAX_EVENTS_PER_BEAT,
    )
    .await
    .unwrap_or_default()
    .into_iter()
    .map(ActivityEvent::from)
    .collect()
}

/// How many extra beats one tick may spend emptying the buffer.
///
/// **The tick is DAILY, not per minute.** It shares `HUB_ENTITLEMENT_REVALIDATE_SECS`, whose
/// default is 86 400 and which no deployment overrides. One bite per tick therefore drains ~500
/// events A DAY, and a busy till produces more than that: the buffer climbs to its ceiling and
/// from then on the trim discards the OLDEST every day, for ever, with an `eprintln!` as the only
/// trace — precisely the loss saas#2129 exists to prevent, since this data cannot be rebuilt.
///
/// Ten rounds is the buffer's own ceiling (`MAX_BUFFERED_EVENTS / MAX_EVENTS_PER_BEAT`), so a hub
/// that is merely behind catches up inside one tick. The cap stops an enormous backlog turning a
/// tick into a storm of beats; whatever does not fit waits for the next one, which is a delay
/// rather than a loss.
pub const MAX_DRAIN_ROUNDS: usize = 10;

/// What one tick managed to settle. Returned for logging and for the tests; nobody renders it.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ActivitySettlement {
    /// Events the Cloud acknowledged and the hub dropped.
    pub confirmed: usize,
    /// Beats that carried activity, the original one included.
    pub rounds: usize,
}

/// Drops what the Cloud acknowledged and **keeps draining in the SAME tick while the bite comes
/// full** (review of saas#2129).
///
/// Two rules, both about not losing what cannot be recovered:
///
/// - **Only `activity_ack` deletes**, never a bare 2xx — see [`HeartbeatResponse::activity_ack`].
/// - **A full bite means there is more behind it.** With a daily tick, stopping here would leave
///   the surplus to the trim, which drops the oldest. A short bite means the buffer is empty and
///   nothing further is asked: otherwise every hub in the fleet would send one pointless beat a
///   day.
///
/// The drain beats carry the events and **nothing of the business**: they are the rest of the
/// batch, not a second heartbeat. Repeating `orders_today` would rewrite the day's count with the
/// same number once per round.
///
/// The runtime lock is taken per database operation and released before each network call: a tick
/// holding it across ten round trips would block every writer in the hub for as long as the Cloud
/// takes to answer.
pub async fn settle_activity(
    runtime: &crate::state::SharedRuntime,
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    sent: &[ActivityEvent],
    acked: bool,
) -> ActivitySettlement {
    if sent.is_empty() || !acked {
        return ActivitySettlement::default();
    }

    let hub_id = {
        let rt = runtime.read().await;
        rt.hub_id().to_string()
    };

    if !confirm_batch(runtime, &hub_id, sent).await {
        return ActivitySettlement::default();
    }
    let mut settled = ActivitySettlement {
        confirmed: sent.len(),
        rounds: 1,
    };

    let mut bite = sent.len();
    while bite == erplora_runtime::activity_log::MAX_EVENTS_PER_BEAT
        && settled.rounds < MAX_DRAIN_ROUNDS
    {
        // No `trim` here: the ceiling is checked once per tick, in `pending_activity`. Trimming
        // per round would discard from the old end of a buffer we are in the middle of emptying.
        let next: Vec<ActivityEvent> = {
            let rt = runtime.read().await;
            erplora_runtime::activity_log::pending(
                rt.db(),
                &hub_id,
                erplora_runtime::activity_log::MAX_EVENTS_PER_BEAT,
            )
            .await
            .unwrap_or_default()
            .into_iter()
            .map(ActivityEvent::from)
            .collect()
        };
        if next.is_empty() {
            break;
        }

        let body = activity_only(next.clone());
        match send_heartbeat(http, cloud_base_url, auth, &body).await {
            Ok(answer) if answer.activity_ack => {
                if !confirm_batch(runtime, &hub_id, &next).await {
                    break;
                }
                settled.confirmed += next.len();
                settled.rounds += 1;
                bite = next.len();
            }
            // A drain beat that failed, or that came back without the acknowledgement, leaves
            // everything where it was. The next tick tries again; nothing is lost.
            _ => break,
        }
    }

    settled
}

/// A beat that is the rest of a batch: the events and the version, nothing else.
fn activity_only(activity: Vec<ActivityEvent>) -> DailyUsageHeartbeat {
    DailyUsageHeartbeat {
        orders_today: None,
        last_sale_at: None,
        terminals: None,
        active_users: None,
        last_user_activity_at: None,
        activity,
        // Required, and honest: it is the binary that is running. Every other field is absent,
        // which the receiver already reads as "not reported" and therefore writes nowhere.
        core_version: crate::version::HUB_VERSION.to_string(),
        pending: PendingObligationFields::default(),
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        transmission_route: None,
    }
}

/// `true` if the rows really went. A failure to delete is not fatal — the next beat re-sends and
/// the Cloud deduplicates — but it does stop the drain: carrying on would re-read the same bite.
async fn confirm_batch(
    runtime: &crate::state::SharedRuntime,
    hub_id: &str,
    sent: &[ActivityEvent],
) -> bool {
    let ids: Vec<String> = sent.iter().map(|event| event.id.clone()).collect();
    let rt = runtime.read().await;
    match erplora_runtime::activity_log::confirm(rt.db(), hub_id, &ids).await {
        Ok(_) => true,
        Err(error) => {
            eprintln!(
                "[activity-log] hub={hub_id} could not confirm {} events: {error}",
                ids.len()
            );
            false
        }
    }
}

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
    // Same reasoning, same site (hub#1449): the reference travels on the same beat as the facts
    // it is about, so it is installed in the same cache and by the same caller — no second place
    // that could forget, no second cache that could fall behind.
    if let Some(declaration) = answer.declaration.clone() {
        ProducerFactsCache::global().store_declaration(declaration);
    }
    Ok(answer)
}

/// How long each step of the daily turn may take before the turn moves on without it (hub#2509).
pub const DAILY_STEP_DEADLINE: std::time::Duration = std::time::Duration::from_secs(5 * 60);

/// The daily turn (HUB-F162 + HUB-F164): every `period`, the plan check and the heartbeat.
///
/// First tick at once (seeds the entitlement as soon as possible). Without a machine credential
/// (dev/local, not enrolled) the tick is skipped WITHOUT counting a failure, so the gate stays
/// fail-open.
pub fn spawn_daily_turn(
    st: crate::AppState,
    period: std::time::Duration,
    step_deadline: std::time::Duration,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut tick = tokio::time::interval(period);
        loop {
            tick.tick().await;
            let Some(auth) = crate::auth::machine_auth(&st) else {
                continue;
            };
            daily_turn_once(&st, &auth, step_deadline).await;
        }
    })
}

async fn daily_turn_once(
    st: &crate::AppState,
    auth: &cloud_client::Auth,
    step_deadline: std::time::Duration,
) {
    // Same 24h tick, no second scheduler: report canonical daily business usage.
    // Collection happens before network I/O, then both Cloud calls run independently:
    // an entitlement failure must not suppress business-usage retention (or vice versa).
    let now = crate::entitlement::now_unix();
    let now_iso = chrono::Utc::now().to_rfc3339();
    let mut usage = {
        let runtime = st.runtime.read().await;
        // Lo que cada motor instalado debe a su autoridad (hub#326/hub#1406) — la
        // pregunta va al REGISTRO, no a un motor con nombre; mismo lock barato que
        // el resto del snapshot.
        let pending = runtime.pending_obligations().await;
        collect_daily_usage(runtime.db(), runtime.hub_id(), &now_iso, &pending).await
    };
    // ADR-0175: la actividad de usuario viaja en ESTE heartbeat, y solo si la hubo.
    // Un hub encendido que nadie toca no manda la marca — que es exactamente lo que el
    // Cloud tiene que observar para poder apagarlo.
    let pending_activity = st.activity.pending();
    usage.last_user_activity_at = pending_activity.map(crate::activity::to_iso8601);
    // hub#975: la telemetría de recursos viaja en el MISMO latido, del sampler único
    // de `system_metrics` (fuera del lock de arriba: el muestreo de CPU duerme 100 ms).
    // Best-effort: fuera de contenedor los campos viajan ausentes, nunca un 0 falso.
    sample_resource_metrics().await.apply_to(&mut usage);
    // Each step has its own deadline (hub#2509): a call erplora.com leaves hanging costs this
    // turn that step, never the next turn — the shared client already bounds every call, and this
    // holds even for a call that asks for a longer ceiling of its own.
    let entitlement_request = within(
        step_deadline,
        "entitlement",
        crate::entitlement::fetch_verified_claims(&st.http, &st.config.cloud_base_url, auth, now),
    );
    let heartbeat_request = within(
        step_deadline,
        "heartbeat",
        send_heartbeat(&st.http, &st.config.cloud_base_url, auth, &usage),
    );
    let (outcome, heartbeat_result) = tokio::join!(entitlement_request, heartbeat_request);
    // A check that never came back is a failed check: it counts towards the paid apps' cut-off.
    let outcome = outcome.unwrap_or_else(|| Err(STEP_TIMED_OUT.to_string()));
    let heartbeat_result = heartbeat_result.unwrap_or_else(|| Err(STEP_TIMED_OUT.to_string()));
    crate::entitlement::record_outcome(&st.entitlement, outcome, now);
    // La cuota del canal de WhatsApp se refleja en el medidor del módulo (hub#1089).
    // Se lee EN VIVO de `whatsapp/plan/` con esta MISMA credencial de máquina, no de
    // un claim del token: ese endpoint devuelve tier + consumo, y el consumo es un
    // contador que se mueve con cada mensaje. Si el Cloud no contesta no se escribe
    // nada — el medidor conserva lo que ya medía, porque en este canal `0` significa
    // «sin tope» y un fallo de red no es un plan. Un hub sin el módulo ni pregunta.
    match within(
        step_deadline,
        "whatsapp_quota",
        crate::whatsapp_quota::sync_once(&st.runtime, &st.http, &st.config.cloud_base_url, auth),
    )
    .await
    {
        None => {}
        Some(crate::whatsapp_quota::QuotaSync::Written {
            monthly_limit,
            monthly_usage,
        }) => {
            tracing::debug!(monthly_limit, monthly_usage, "cuota de WhatsApp al día")
        }
        // Los demás casos ya se han contado donde tocaba (o son el no-op esperado
        // en la flota que no compró el canal): aquí no se repite el ruido.
        Some(other) => tracing::trace!(?other, "sincronización de cuota de WhatsApp"),
    }
    match heartbeat_result {
        // Confirmar SOLO tras un envío correcto: si se diera por reportada una marca
        // que no llegó, el Cloud seguiría contando días y adelantaría el apagado.
        Ok(ref answer) => {
            // The beat that carried the mark is in: confirmed now, whatever the settling below
            // does with its own deadline.
            if let Some(ts) = pending_activity {
                st.activity.mark_reported(ts);
            }
            // The same, one step further down (saas#2129): the events this beat
            // carried are settled, and the buffer keeps draining in THIS tick while
            // the bite comes full — the tick is daily, so leaving the surplus for the
            // next one is how a busy till loses its oldest events for ever. Only
            // `activity_ack` deletes: a bare 2xx is also what a broken ingest answers.
            let settled = within(
                step_deadline,
                "settle_activity",
                settle_activity(
                    &st.runtime,
                    &st.http,
                    &st.config.cloud_base_url,
                    auth,
                    &usage.activity,
                    answer.activity_ack,
                ),
            )
            .await;
            if let Some(settled) = settled.filter(|settled| settled.confirmed > 0) {
                tracing::debug!(
                    confirmed = settled.confirmed,
                    rounds = settled.rounds,
                    "business activity delivered to the Cloud"
                );
            }
        }
        Err(error) => tracing::warn!(%error, "daily usage heartbeat failed"),
    }
}

/// What a step of the daily turn that ran out of time reports (hub#2509).
const STEP_TIMED_OUT: &str = "daily_turn_step_timed_out";

/// Runs one step of the daily turn within `deadline`; `None` (and a warning naming the step) if
/// it did not finish in time.
async fn within<T>(
    deadline: std::time::Duration,
    step: &'static str,
    work: impl std::future::Future<Output = T>,
) -> Option<T> {
    match tokio::time::timeout(deadline, work).await {
        Ok(done) => Some(done),
        Err(_) => {
            tracing::warn!(step, ?deadline, "daily turn step timed out (hub#2509)");
            None
        }
    }
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

    /// hub#1814: quien entra con PIN no tiene cuenta de ERPlora, así que el SaaS no lo ve — y sin
    /// este número la puerta de invitaciones cuenta solo membresías y le regala plazas a un hub
    /// lleno. El recuento es el MISMO que aplica el tope (`hub_users::count_active_users`).
    #[tokio::test]
    async fn reports_the_people_holding_a_seat_in_this_hub() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE hub_user (\
               id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, is_active BIGINT NOT NULL DEFAULT 1\
             );\
             INSERT INTO hub_user VALUES\
               ('owner', 'hub-a', 1),\
               ('pin-1', 'hub-a', 1),\
               ('pin-2', 'hub-a', 1),\
               ('left',  'hub-a', 0),\
               ('next-door', 'hub-b', 1);",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z", &[]).await;
        assert_eq!(
            usage.active_users,
            Some(3),
            "el dueño y las dos personas de PIN ocupan plaza; la baja (`left`) no, y la del negocio \
             de al lado (`next-door`, hub-b) no es nuestra — varios hubs comparten BD (hub#497)"
        );
        assert_eq!(
            serde_json::to_value(&usage).unwrap()["active_users"],
            json!(3),
            "viaja con el nombre exacto que el SaaS ingiere (saas#2022)"
        );
    }

    /// El contrato de ausencia, gemelo del de `verifactu_pending_depth`: un `0` fabricado diría
    /// «aquí no trabaja nadie» y le regalaría una plaza libre a un hub lleno, que es justo el
    /// desbordamiento que hub#1814 viene a cerrar.
    #[tokio::test]
    async fn an_uncountable_census_is_absent_never_a_fabricated_zero() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, hub_id TEXT NOT NULL, device_id TEXT, expires_at TEXT NOT NULL\
             );",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z", &[]).await;
        assert_eq!(usage.active_users, None, "sin censo legible no hay número");
        assert!(
            !serde_json::to_string(&usage).unwrap().contains("active_users"),
            "«no he podido contar» es que el campo NO esté: un cero le abriría una plaza al hub lleno"
        );
    }

    /// Y el cero HONESTO sí viaja: censo legible y vacío es `0`, no una ausencia. Es la otra mitad
    /// del contrato — si el vacío se callara, el SaaS no podría distinguirlo de un hub ilegible.
    #[tokio::test]
    async fn an_empty_census_is_an_honest_zero() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE hub_user (\
               id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, is_active BIGINT NOT NULL DEFAULT 1\
             );",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z", &[]).await;
        assert_eq!(usage.active_users, Some(0));
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
            json!({"terminals": 0, "core_version": crate::version::HUB_VERSION})
        );
    }

    /// **The four keys and nothing else** (saas#2129). This is the contract between the two
    /// repos and the privacy guard at the same time: the Cloud reads `id`, `type`, `at` and
    /// `actor`, so anything else added to this struct would either be ignored there or — the real
    /// risk — carry something about the END CUSTOMER into the control plane. Asserting the exact
    /// key set is what makes that a test failure instead of a discovery.
    #[test]
    fn an_activity_event_puts_exactly_four_keys_on_the_wire() {
        let event = ActivityEvent::from(erplora_runtime::activity_log::PendingEvent {
            id: "e-1".into(),
            kind: "cash_open".into(),
            occurred_at: "2026-10-01T09:00:00Z".into(),
            actor: "pin-42".into(),
        });

        let wire = serde_json::to_value(&event).unwrap();
        let mut keys: Vec<&str> = wire
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        keys.sort_unstable();
        assert_eq!(keys, ["actor", "at", "id", "type"]);
        assert_eq!(
            wire["type"], "cash_open",
            "the Cloud reads `type`, not `kind`"
        );
        assert_eq!(
            wire["at"], "2026-10-01T09:00:00Z",
            "and `at`, not `occurred_at`"
        );
        assert_eq!(wire["actor"], "pin-42", "the hub's own id, never a name");
    }

    /// Silence is not news of a zero — the same absence contract as `active_users` and the
    /// `verifactu_*` pair. An empty array would be a beat SAYING "nothing happened", which is a
    /// different claim from not mentioning it, and the Cloud branches on exactly that.
    #[test]
    fn a_hub_with_nothing_to_report_does_not_mention_activity_at_all() {
        let quiet = DailyUsageHeartbeat {
            orders_today: None,
            last_sale_at: None,
            terminals: None,
            active_users: None,
            last_user_activity_at: None,
            activity: Vec::new(),
            core_version: "1.0.0".into(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };

        let wire = serde_json::to_value(&quiet).unwrap();
        assert!(
            !wire.as_object().unwrap().contains_key("activity"),
            "an empty list must be omitted, not sent: {wire}"
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
            active_users: Some(4),
            last_user_activity_at: Some("2026-07-27T11:45:00Z".into()),
            activity: Vec::new(),
            core_version: crate::version::HUB_VERSION.to_string(),
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
                // hub#1814: las personas que ocupan plaza del plan, incluidas las que entran con
                // PIN y por tanto no tienen cuenta que el SaaS pueda ver.
                "active_users": 4,
                "last_user_activity_at": "2026-07-27T11:45:00Z",
                "core_version": crate::version::HUB_VERSION,
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
            active_users: None,
            last_user_activity_at: None,
            activity: Vec::new(),
            core_version: crate::version::HUB_VERSION.to_string(),
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
            json!({"orders_today": 0, "terminals": 0, "core_version": crate::version::HUB_VERSION})
        );
    }

    // 🪦 Aquí iba «el hub REPORTA qué certificado delegado tiene» (ADR-0202 §2.5 — hub#318): un
    // `0` explícito que el Cloud distinguía de un `NULL`. Se fue con el slot (hub#1435) y el SaaS
    // borró las cuatro columnas `reported_cert_*` en saas#1435 fase 2. La regla que lo motivaba
    // —«ausente» significa *no pude leerlo*, nunca «no tengo»— sigue viva en `orders_today` y en
    // `verifactu_pending_depth`, que es donde se comprueba.

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
            active_users: None,
            last_user_activity_at: None,
            activity: Vec::new(),
            core_version: crate::version::HUB_VERSION.to_string(),
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
            active_users: None,
            last_user_activity_at: None,
            activity: Vec::new(),
            core_version: crate::version::HUB_VERSION.to_string(),
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
            active_users: None,
            last_user_activity_at: None,
            activity: Vec::new(),
            core_version: crate::version::HUB_VERSION.to_string(),
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
            active_users: None,
            last_user_activity_at: None,
            activity: Vec::new(),
            core_version: crate::version::HUB_VERSION.to_string(),
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
            json!({"orders_today": 3, "terminals": 1, "core_version": crate::version::HUB_VERSION})
        );
    }

    // ── What comes back on the beat ───────────────────────────────────────────────────────────
    //
    // 🪦 Here lived «the version the control plane announces» (ADR-0202 §2.5): the response carried
    // `cert_version` and a hub whose own differed refetched the delegated certificate. Both halves
    // are retired — the slot in hub#1435, the field in saas#1435 phase 2. What must NOT be retired
    // is the forgiveness those tests also pinned, so it is asserted here on what still rides:

    /// **A body this hub cannot parse must not become an error.** The heartbeat already succeeded
    /// (2xx) and its real job is ADR-0175's activity clock: if an edge that answers HTML turned the
    /// call into a failure, the hub would stop confirming activity and the Cloud would count it
    /// idle — and eventually switch a hub off that people are using every day.
    #[test]
    fn a_body_that_is_not_json_degrades_to_no_news() {
        assert_eq!(
            HeartbeatResponse::parse("<html>502</html>"),
            HeartbeatResponse::default()
        );
        assert_eq!(HeartbeatResponse::parse(""), HeartbeatResponse::default());
        assert_eq!(HeartbeatResponse::parse("[]"), HeartbeatResponse::default());
    }

    /// A SaaS that has not been redeployed still sends the retired `cert_version`. It is read like
    /// any other unknown field — ignored — never as an error that would stop the activity clock.
    #[test]
    fn a_control_plane_still_announcing_the_retired_certificate_is_simply_ignored() {
        assert_eq!(
            HeartbeatResponse::parse(r#"{"ok": true, "cert_version": 4}"#),
            HeartbeatResponse::default()
        );
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

    // ── Which declaration covers this version rides the same beat (hub#1449, saas#1724) ──────
    //
    // The panel used to compose the archive's ROOT by hand: correct only while a single
    // declaración responsable is in force. `declaration` names the exact one that covers the
    // running release, the same way `producer` names the manufacturer — sibling key, same cycle.

    fn served_declaration_body() -> String {
        r#"{"ok": true, "producer": {
             "NombreRazon": "ERPLORA CLOUD SL", "NIF": "B27593136",
             "NombreSistemaInformatico": "ERPlora Hub", "IdSistemaInformatico": "EC",
             "TipoUsoPosibleSoloVerifactu": "S", "TipoUsoPosibleMultiOT": "S",
             "IndicadorMultiplesOT": "S"},
           "declaration": {"version": "v1",
             "url": "https://erplora.com/legal/declaracion-responsable/v1/"}}"#
            .to_string()
    }

    /// hub#1449: the exact reference the SaaS names — not a URL this hub composes — must be read
    /// off the beat, at the same level as `producer` and not nested inside it (the `producer`
    /// block is the literal AEAT element set; a stray key there would be an invented element).
    #[test]
    fn the_beat_carries_which_declaration_covers_this_release() {
        let declaration = HeartbeatResponse::parse(&served_declaration_body())
            .declaration
            .expect("the reference the SaaS serves must be read");

        assert_eq!(declaration.version, "v1");
        assert_eq!(
            declaration.url,
            "https://erplora.com/legal/declaracion-responsable/v1/"
        );
    }

    /// A control plane that has nothing to say (an older SaaS, or an unreadable archive on its
    /// side) sends no `declaration` key at all — the SaaS OMITS it, never an empty one — and that
    /// is «no news», not an error: the panel falls back to the root of the public archive.
    #[test]
    fn a_beat_without_the_key_announces_no_declaration() {
        assert!(HeartbeatResponse::parse(&served_producer_body())
            .declaration
            .is_none());
        assert!(HeartbeatResponse::parse(r#"{"ok": true}"#)
            .declaration
            .is_none());
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
                active_users: None,
                last_user_activity_at: None,
                activity: Vec::new(),
                core_version: crate::version::HUB_VERSION.to_string(),
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
        assert_eq!(
            response,
            HeartbeatResponse::default(),
            "sin cuerpo legible, sin noticias"
        );
        server.abort();
    }

    /// 🔒 …y lo mismo cuando el cuerpo **no se puede ni leer**: la respuesta promete 64 bytes y la
    /// conexión se corta a los 2.
    ///
    /// Es el caso que un stub HTTP normal no puede montar, y es justo el que aparece de verdad —
    /// un reset a mitad de respuesta, un edge que se rinde. Si eso convirtiera el latido en un
    /// error, el hub dejaría de confirmar la marca de actividad de ADR-0175 y el Cloud acabaría
    /// **apagando un hub que se usa a diario**. Los hechos del fabricante son un extra que viaja
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
                active_users: None,
                last_user_activity_at: None,
                activity: Vec::new(),
                core_version: crate::version::HUB_VERSION.to_string(),
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
            response,
            HeartbeatResponse::default(),
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
    fn the_heartbeat_carries_the_running_core_version() {
        let body = DailyUsageHeartbeat {
            orders_today: Some(3),
            last_sale_at: None,
            terminals: None,
            active_users: None,
            last_user_activity_at: None,
            activity: Vec::new(),
            core_version: crate::version::HUB_VERSION.to_string(),
            pending: PendingObligationFields::default(),
            cpu_pct: None,
            memory_used_mb: None,
            memory_limit_mb: None,
            memory_peak_mb: None,
            transmission_route: None,
        };

        let wire = serde_json::to_value(&body).expect("el latido tiene que serializar");

        assert_eq!(wire["core_version"], crate::version::HUB_VERSION);
        assert!(
            !wire["core_version"].as_str().unwrap().starts_with('v'),
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

        assert_eq!(usage.core_version, crate::version::HUB_VERSION);
    }
}
