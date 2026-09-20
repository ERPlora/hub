//! Query/command dispatch, system tables and system params — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

/// Cuánto espera un arranque por el lock de migración antes de rendirse.
///
/// 120 s por defecto: el que espera es el arranque NUEVO del solape blue/green, y lo que espera es
/// a que el viejo —o el otro nuevo— termine de migrar. Las migraciones son aditivas por contrato
/// (ADR-0269), así que duran segundos; el margen es para un backfill lento, no para una espera
/// normal. Ajustable con `HUB_MIGRATION_LOCK_TIMEOUT_MS` por si algún hub tiene un histórico gordo.
fn migration_lock_timeout_ms() -> u64 {
    std::env::var("HUB_MIGRATION_LOCK_TIMEOUT_MS")
        .ok()
        .and_then(|raw| raw.trim().parse().ok())
        .unwrap_or(120_000)
}

impl Runtime {
    /// Ejecuta una query declarativa (solo si su módulo está activo) y devuelve filas JSON.
    /// Para queries de lista devuelve solo las filas de la página (compat); usa
    /// [`Runtime::execute_query_page`] si necesitas el total para paginar.
    pub async fn execute_query(
        &self,
        name: &str,
        params: &Params,
        ctx: &RequestContext,
    ) -> Result<Vec<Json>> {
        let r = queries::execute(self.db.as_ref(), &self.registry, name, params, ctx).await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "query", name, params);
        }
        r
    }

    /// Ejecuta una query devolviendo la página completa (`rows` + `total` + `limit`/`offset`).
    /// Lo usa el server para queries de lista; el total alimenta el pager del `<data-table>`.
    pub async fn execute_query_page(
        &self,
        name: &str,
        params: &Params,
        ctx: &RequestContext,
    ) -> Result<queries::QueryPage> {
        let r = queries::execute_page(self.db.as_ref(), &self.registry, name, params, ctx).await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "query", name, params);
        }
        r
    }

    /// ¿La query (de un módulo activo — o del core, hub#884) declara bloque `list` (es paginada)?
    /// Lo usa el server para decidir la forma del `data` que devuelve por el wire.
    pub fn is_list_query(&self, name: &str) -> bool {
        hub_users::is_core_list_query(name)
            || self
                .registry
                .get_query(name)
                .map(|q| q.def.list.is_some())
                .unwrap_or(false)
    }

    /// Ejecuta un command declarativo (solo si su módulo está activo). Los eventos emitidos se
    /// persisten en el outbox en la misma transacción; sus listeners los entrega el relay (§5.4).
    pub async fn execute_command(
        &self,
        name: &str,
        payload: &Params,
        ctx: &RequestContext,
    ) -> Result<Json> {
        let r = commands::execute(
            self.db.as_ref(),
            &self.registry,
            name,
            payload,
            ctx,
            &self.elevation,
        )
        .await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "command", name, payload);
        }
        // What the people of the business DO here (saas#2129), recorded at the one funnel every
        // external command goes through. Only on success — a refund that was refused is not a
        // refund — and only for the PUBLIC doors (`activity_log::kind_for_command`): the internal
        // relays one sale fans out into run inside this same call and would count it four times.
        if r.is_ok() {
            if let Some(kind) = crate::activity_log::kind_for_command(name) {
                crate::activity_log::record_best_effort(self.db(), self.hub_id(), kind, ctx).await;
            }
        }
        r
    }

    /// Como [`Runtime::execute_command`] pero con **origen INTERNO** (hub#131, hub#145): ejecuta
    /// también commands marcados internos (prefijo `_` en el último segmento, o `internal: true`),
    /// con el mismo `Origin::Internal` que el relay del Outbox y el scheduler.
    ///
    /// SOLO para el **host embebedor** del runtime (código Rust de confianza que ya tiene [`Runtime::db`]
    /// con acceso crudo): siembras de tests e2e que suplen un handler nativo/WASM no enlazado con la
    /// intención declarativa exacta que ese motor emitiría (`verifactu._insert_record`,
    /// `appointments._insert_appointment`). NINGUNA superficie externa (rutas HTTP, API pública de
    /// API keys, asistente/SDK) debe enrutar por aquí: esas pasan por [`Runtime::execute_command`],
    /// que gatea los internos con `internal_command`.
    #[doc(hidden)]
    pub async fn execute_command_internal(
        &self,
        name: &str,
        payload: &Params,
        ctx: &RequestContext,
    ) -> Result<Json> {
        let r = commands::execute_at(
            self.db.as_ref(),
            &self.registry,
            name,
            payload,
            ctx,
            0,
            &[],
            commands::Origin::Internal,
            // The embedder seeding e2e data is the runtime calling itself: no approval to spend.
            None,
        )
        .await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "command", name, payload);
        }
        r
    }

    /// **Embudo único** de errores del dispatcher (§ error-registry). Reporta el `RuntimeError` de un
    /// `execute_command`/`execute_query` al registro global, etiquetándolo con `source="module"` +
    /// `module_id` cuando el nombre resuelve a un módulo registrado, o `source="hub"` si no (core /
    /// capacidad inexistente). Capturamos aquí — no (solo) en la capa HTTP — para cubrir también los
    /// errores de caminos no-HTTP (scheduler, relay del outbox, Tauri). Best-effort: no falla nunca.
    ///
    /// El contexto incluye el `kind`/`name` de la capacidad y las **claves** del payload (no los
    /// valores, para no arrastrar PII). El `module_id` se resuelve del registry sin filtrar por
    /// estado activo: un error sobre un command/query de un módulo desactivado igual se atribuye a él.
    pub(crate) fn report_dispatch_error(
        &self,
        err: &RuntimeError,
        kind: &str,
        name: &str,
        payload: &Params,
    ) {
        let module_id = self
            .registry
            .commands
            .get(name)
            .map(|c| c.module_id.clone())
            .or_else(|| self.registry.queries.get(name).map(|q| q.module_id.clone()));
        let source = if module_id.is_some() {
            error_registry::source::MODULE
        } else {
            error_registry::source::HUB
        };
        let payload_keys: Vec<&String> = payload.keys().collect();
        let context = serde_json::json!({ kind: name, "payload_keys": payload_keys });
        error_registry::report_runtime_error(err, source, module_id, context);
    }

    /// Asegura + migra el **esquema de sistema** del runtime (hub#37). Dos fases:
    ///  1. **ensure baseline (v0):** los `CREATE TABLE IF NOT EXISTS` de las tablas de sistema
    ///     (`hub_module`, outbox `_event_outbox`/`_event_delivery`, scheduler `_scheduled_tasks`,
    ///     identidad `hub_user`/`hub_session`). Cubre el hub vacío (BD nueva sin módulos).
    ///  2. **migrate (≥ v1):** aplica en orden las migraciones de sistema versionadas que aún no
    ///     estén registradas en `_hub_system_migrations`, **scoped por el `hub_id` del despliegue**.
    ///     Así un cambio de esquema de sistema llega también a un `erplora.db` ya existente (un
    ///     `CREATE IF NOT EXISTS` no altera tablas previas — ver `system_migrations.rs`).
    ///
    /// Idempotente: re-arrancar no reaplica. El server la llama al arrancar.
    pub async fn ensure_system_tables(&self) -> Result<()> {
        // 🔒 UN solo arranque toca el esquema a la vez (hub#539).
        //
        // Con `order: start-first` (ADR-0269) hay **dos procesos del mismo hub contra la misma
        // base** en cada actualización, y los dos corren esto entero. Sin lock pueden leer el mismo
        // `max_applied_version` y aplicar la misma migración a la vez: `CREATE TABLE` sin
        // `IF NOT EXISTS` da 42P07, un `ALTER` deja el esquema a medias y el `INSERT` de control
        // choca contra la PK. El segundo espera, entra, y se encuentra el trabajo hecho —
        // todo lo de abajo es idempotente.
        //
        // Envuelve la función ENTERA y no solo `system_migrations::apply`: el baseline v0, el
        // marcador monetario y los backfills de más abajo escriben esquema y datos igual.
        //
        // Si no lo consigue, **falla el arranque**. Es deliberado: seguir sin él es migrar en
        // paralelo, y con `/readyz` de verdad (hub#538) un arranque fallido dispara el rollback en
        // vez de matar a la tarea que sí funcionaba.
        let _migration_lock = self
            .db
            .migration_lock(&self.hub_id, migration_lock_timeout_ms())
            .await
            .map_err(|error| RuntimeError::Domain {
                code: "hub.migration_lock_timeout".into(),
                message: error.to_string(),
            })?;

        // 1) Baseline v0 (idempotente).
        installer::ensure_hub_module_table(self.db.as_ref()).await?;
        // El ledger de migraciones de MÓDULO nace AQUÍ, no con la primera migración: el readiness
        // (`/readyz`, hub#538) lo consulta en cada latido, y en un hub RECIÉN NACIDO —cero
        // módulos— «relation _hub_migrations does not exist» era DOWN → 503 → el healthcheck de
        // Swarm mataba la tarea → `deployment_status=error`. Ningún hub nuevo podía aprovisionarse
        // (2026-08-09); los tests no lo veían porque su fixture creaba la tabla A MANO, cosa que
        // el boot real no hacía.
        migrations::ensure_table(self.db.as_ref()).await?;
        outbox::ensure_tables(self.db.as_ref()).await?;
        scheduler::ensure_tables(self.db.as_ref()).await?;
        identity::ensure_tables(self.db.as_ref()).await?;
        // 2) Migraciones de sistema versionadas (≥ v1), scoped por hub_id del despliegue.
        system_migrations::apply(self.db.as_ref(), &self.hub_id).await?;
        // 2a) Índices de las tablas de flujo que su migración creadora no podía prever (hub#666).
        // Va DESPUÉS de `apply` porque las tablas tienen que existir. No es migración numerada a
        // propósito: un índice no cambia la forma del dato y `IF NOT EXISTS` no cuesta nada en el
        // segundo arranque — mismo criterio que las columnas del outbox por su `ENSURE_TABLES`.
        flows::store::ensure_indexes(self.db.as_ref()).await?;
        // 2a-bis) The `wake_at` of the runs parked before hub#970, re-written in UTC. Same
        // criterion as 2b below: an invariant over data, not a schema change — the write side is
        // already fixed, but a run that is ALREADY asleep is only ever read by the very comparison
        // the offset breaks, so nothing else would reach it. Re-running it is a no-op.
        flows::store::normalize_wake_at(self.db.as_ref(), &self.hub_id).await?;
        // 2b) The device row an id that names the HUB left behind (hub#454). Not a versioned
        // migration on purpose: it is an invariant, not a schema change — it must also clean a
        // database restored from a backup taken before the fix, and re-running it is a no-op.
        identity::forget_hub_id_as_device(self.db.as_ref(), &self.hub_id).await?;
        // 2c) The hub's FISCAL PROFILE (ADR-0273, hub#549): what this hub owes, resolved from its
        // country and persisted by the core. It runs here — on the boot path every hub takes —
        // precisely so that owing VeriFactu is never a consequence of having installed something.
        // It only resolves and records; nothing rejects anything yet (hub#550/#556).
        fiscal_profile::ensure(self.db.as_ref(), &self.hub_id).await?;
        // 3) Marcador de unidad monetaria (ADR-0007): una instalación NUEVA (esquema ya en
        // céntimos) se auto-marca `money_unit=cents` para que el backfill jamás la convierta. Un
        // hub VIEJO en euros NO se auto-marca aquí — espera a `--backfill-money` (que convierte).
        money_backfill::seed_marker_if_cents(self.db.as_ref()).await?;
        // 4) Lo que el backfill de la v19 NO pudo decidir (hub#436): filas cuyo email vive solo en
        // el perfil y choca con otra identidad, así que su baja **no revoca** nada. No se adivina
        // —fusionar dos personas es peor que dejar una fila señalada—: se imprime en cada arranque
        // para que alguien lo mire. Consulta VIVA, no una foto: se calla sola al resolverse.
        //
        // **No aborta el arranque.** Es un aviso, no un paso del bootstrap: un hub que no abre es
        // una tienda que no cobra, y eso es mucho peor que un aviso que falta. Si la consulta
        // revienta se dice y se sigue.
        if let Err(e) = access_email::report_unresolved(self.db.as_ref(), &self.hub_id).await {
            eprintln!("[access-email] no se pudo comprobar los emails de acceso (hub#436): {e}");
        }
        // 5) The owner's rules, from `_policy` into the in-memory index the gate reads from
        // (hub#1701, ADR-0476). It goes here — on the boot path EVERY hub walks — because an empty
        // index is a rule that forbids nothing: the most expensive fail-open of all, because it is
        // not noticed until someone slips through the discount the rule existed to stop.
        //
        // It does not depend on the modules being re-hydrated already: the index is filled with
        // ROWS, and who gates which command is resolved by the Registry at apply time.
        self.reload_policies().await?;
        Ok(())
    }

    /// Backfill **idempotente** euros→céntimos para hubs ya desplegados (ADR-0007). No-op en
    /// instalaciones nuevas (esquema ya en céntimos) y en hubs ya convertidos (marcador
    /// `_hub_meta.money_unit=cents`). Lo invoca el subcomando `--backfill-money` del binario.
    /// SEGURO de re-ejecutar. Ver [`money_backfill`].
    pub async fn backfill_money(&self) -> Result<money_backfill::BackfillReport> {
        money_backfill::run_logged(self.db.as_ref()).await
    }

    /// Aplica un **seed de configuración inicial** (SQL idempotente) sobre la conexión del runtime,
    /// **después** de [`Runtime::ensure_system_tables`] (hub#36). Mecanismo genérico de carga de
    /// config (no es "modo demo"); la idempotencia la garantiza el propio SQL. Devuelve cuántas
    /// sentencias aplicó. Lo llama el host al arrancar si hay `HUB_SEED_SQL`/`HUB_SEED_SQL_PATH`.
    pub async fn apply_seed(&self, sql: &str) -> Result<usize> {
        seed::apply(self.db.as_ref(), sql, &self.hub_id).await
    }

    // ── Print queue of the hub (ADR-0196 §6, hub#341) ──────────────────────────────────────────
}

/// Inyecta los parámetros del sistema en el payload del llamador: `hub_id`, `current_user_id`,
/// `now` y `new_id`. Siempre disponibles para el SQL del módulo y no falsificables desde la UI
/// (ARQUITECTURA.md §2.5, §2.9).
///
/// `pub` porque **es contrato del kernel** (hub#1235): los nombres que devuelve son los `:name`
/// contra los que está escrito el SQL de los 27 módulos publicados, y
/// `tests/kernel_contract_engine.rs` los congela llamando a esta misma función — nunca a una copia
/// de su lista, que es como se desincronizaría.
pub fn system_params(base: &Params, ctx: &RequestContext) -> Params {
    let mut p = base.clone();
    p.insert("hub_id".into(), Json::String(ctx.hub_id.clone()));
    p.insert("current_user_id".into(), Json::String(ctx.user_id.clone()));
    p.insert("now".into(), Json::String(registry::now_rfc3339()));
    p.insert("new_id".into(), Json::String(registry::new_id()));
    // Identidad de NEGOCIO GLOBAL del hub (fuente única país-agnóstica, hub_settings — ADR-0061) —
    // disponible como `:business_tax_id`/`:business_legal_name`/`:business_address` en TODO el SQL de
    // comandos (incl. operaciones de handlers WASM/nativos), para que los módulos resuelvan el emisor
    // sin que el caller lo pase.
    p.insert(
        "business_tax_id".into(),
        Json::String(ctx.business_tax_id.clone()),
    );
    p.insert(
        "business_legal_name".into(),
        Json::String(ctx.business_legal_name.clone()),
    );
    p.insert(
        "business_address".into(),
        Json::String(ctx.business_address.clone()),
    );
    // Presencia del certificado fiscal del negocio (`_hub_certificate`, core — ADR-0081), como 0/1
    // para que el SQL del módulo lo use sin leer la tabla de sistema (p.ej. verifactu.config.get →
    // has_certificate / gate de "Probar" / setup.configured_when).
    p.insert(
        "has_certificate".into(),
        Json::from(if ctx.has_certificate { 1 } else { 0 }),
    );
    // The hub's EPHEMERAL DEMO mark (ADR-0197, hub#1135), as 0/1 — SAME pattern as
    // `:has_certificate` right above: a hub condition a module needs in order to paint
    // (verifactu#40 — do not offer "Production" in a demo that the fiscal close is always going
    // to deny), sounded by the runtime, never guessed by the module. It is not a setting and is
    // not writable by payload: `ctx.is_demo_hub` overwrites it here, AFTER cloning `base`, so a
    // caller that stuffs it into its own payload loses it exactly like it loses `:hub_id`.
    p.insert(
        "is_demo_hub".into(),
        Json::from(if ctx.is_demo_hub { 1 } else { 0 }),
    );
    // ¿Están CONCEDIDAS todas las capabilities que declara el módulo LLAMANTE? (ADR-0079,
    // hub#1425), como 0/1 — MISMO patrón que `:has_certificate` y `:is_demo_hub`: una condición
    // que el módulo necesita para PINTAR («estás activado y no puedes firmar», verifactu#62),
    // sonada por el runtime y nunca leída por el módulo de `_module_capability_grants`, que es
    // tabla de sistema. El valor lo sella el dispatcher llamando a `capabilities::all_granted`
    // —que ES `capabilities::enforce`—, así que la pantalla y el gate no pueden discrepar. No es
    // falsificable por payload: se escribe aquí, DESPUÉS de clonar `base`.
    p.insert(
        "capabilities_granted".into(),
        Json::from(if ctx.capabilities_granted { 1 } else { 0 }),
    );
    // LA ZONA HORARIA DEL NEGOCIO (hub#731, hub#1022), como nombre IANA ya RESUELTO
    // (`settings::timezone_of`: la declarada o la deducida del país/región). Disponible como
    // `:timezone` en TODO el SQL de queries y comandos — «mañana a las 09:00» son las 09:00 de la
    // TIENDA. Degrada a `UTC` si el dispatcher no la llegó a resolver (mismo fallback que el boot
    // del server), nunca a una cadena vacía que nadie podría interpretar.
    p.insert(
        "timezone".into(),
        Json::String(ctx.timezone_name().to_string()),
    );
    // EL IDIOMA EFECTIVO DE QUIEN LLAMA (hub#1098), con la precedencia del shell
    // (`bootHubLanguage`): override personal (`hub_user_pref.language`) → setting del hub
    // (`hub_settings.language`) → default del core (`es`). Hasta aquí cada módulo que proyectaba
    // texto traducido reimplementaba esto en SQL leyendo tablas del CORE (taxes#38) — y adivinaba
    // el default, mal (taxes#40). Degrada a `es`, el default del core, nunca a vacío.
    p.insert(
        "caller_lang".into(),
        Json::String(ctx.caller_lang().to_string()),
    );
    // Who APPROVED this command, when it only ran because a manager stepped up (hub#361). Empty
    // for everything else, which is almost everything. It sits next to `:current_user_id` on
    // purpose: together they are the double attribution rule 3 asks for — `created_by` is the
    // cashier who was at the till, `approved_by` the manager who authorised. **This exposes it;
    // hub#362 owns the row contract** (which columns every module table carries, and the
    // migration that adds them). Never settable by a caller: the dispatcher writes it only after
    // spending a grant.
    p.insert(
        "approved_by".into(),
        Json::String(ctx.approved_by.clone().unwrap_or_default()),
    );
    p
}

/// El idioma EFECTIVO de quien llama (hub#1098), con la MISMA precedencia que el shell
/// (`apps/web/src/i18n → bootHubLanguage`) y que taxes#38 reimplementaba a mano en el SQL de cada
/// módulo:
///
/// 1. el override personal (`hub_user_pref.language`, si no está vacío);
/// 2. el setting del hub (`hub_settings.language`, cuyo default `es` YA aplica la capa de
///    settings — `settings::get_all` lo mezcla);
/// 3. `es`, el default del CORE (taxes#40: no `en`; ADR-0055 sigue mandando para la fuente y el
///    fallback de una TRADUCCIÓN faltante, que es cosa del módulo, no de esta función).
///
/// Tolerante a propósito: sin fila de preferencia, sin tabla o sin settings legibles no hay error
/// que el caller pueda arreglar — es el caso normal (casi nadie elige idioma) y se degrada al
/// setting/default. `settings` es el mapa de [`settings::get_all`], que el dispatcher YA leyó para
/// la identidad de negocio: no se vuelve a pagar ese viaje.
pub(crate) async fn effective_caller_lang(
    db: &dyn DatabaseAdapter,
    settings: &Json,
    hub_id: &str,
    user_id: &str,
) -> String {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("user_id".into(), json!(user_id));
    if let Ok(rows) = db
        .query(
            "SELECT TRIM(language) AS language FROM hub_user_pref \
             WHERE hub_id = :hub_id AND user_id = :user_id",
            &p,
        )
        .await
    {
        if let Some(lang) = rows.rows.first().and_then(|r| r["language"].as_str()) {
            if !lang.is_empty() {
                return lang.to_string();
            }
        }
    }
    settings
        .get("language")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .unwrap_or("es")
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registry::{ModuleStatus, RegisteredCommand, RequestContext};
    use erplora_db::testutil::fresh_db;

    fn underscore_cmd(module: &str, sql: &str) -> RegisteredCommand {
        RegisteredCommand {
            module_id: module.to_string(),
            def: manifest::CommandDef {
                permission: format!("{module}.write"),
                reads: Vec::new(),
                transaction: false,
                sql: vec![],
                schema: None,
                emit: vec![],
                min_affected_rows: None,
                expect_rows: None,
                handler: None,
                ai: None,
                expose_api: false,
                internal: false,
            },
            sql: vec![sql.to_string()],
            wasm: None,
            schema: None,
        }
    }

    /// hub#1403: the split moved `system_params` into this module, but its crate-root path is
    /// kernel contract — `tests/kernel_contract_engine.rs` freezes the `:name` binds of the 27
    /// published modules by calling `erplora_runtime::system_params` directly. This pins the
    /// re-export: if a future cleanup drops it, this fails to compile/behave instead of the
    /// contract test silently testing a copy.
    #[test]
    fn hub1403_system_params_stays_reachable_at_the_crate_root() {
        let ctx = RequestContext::new("h1", "u1", Vec::<String>::new());
        let p = crate::system_params(&Params::new(), &ctx);
        assert_eq!(p["hub_id"], json!("h1"));
        assert_eq!(p["timezone"], json!("UTC"));
    }

    /// hub#1022/hub#1098: `:timezone`/`:caller_lang` llegan SIEMPRE con un valor bindeable — el
    /// resuelto por el dispatcher si pasó por ahí, y si no, los fallbacks DOCUMENTADOS (`UTC`, el
    /// reloj que correrá de todos modos; `es`, el default del core que taxes#40 fijó como tal).
    /// Una cadena vacía sería «no lo sé», y un bind vacío en SQL es un bug a las 3 de la mañana.
    #[test]
    fn system_params_timezone_and_caller_lang_never_arrive_empty() {
        let ctx = RequestContext::new("h1", "u1", Vec::<String>::new());
        let p = system_params(&Params::new(), &ctx);
        assert_eq!(p["timezone"], json!("UTC"));
        assert_eq!(p["caller_lang"], json!("es"));

        let ctx = ctx.with_timezone("Atlantic/Canary").with_caller_lang("en");
        let p = system_params(&Params::new(), &ctx);
        assert_eq!(p["timezone"], json!("Atlantic/Canary"));
        assert_eq!(p["caller_lang"], json!("en"));
    }

    /// hub#1135: a module cannot know today that its hub is an ephemeral DEMO (ADR-0197) — the
    /// mark is sealed on `Registry::demo_hub` from `HUB_DEMO` but never reached `system_params`,
    /// so the SQL every module writes had no `:is_demo_hub` to bind, unlike the sibling gate
    /// `:has_certificate` that already exists for the same shape of question (a hub condition a
    /// module needs to paint, sounded by the runtime, exposed as 0/1 so the SQL never reads a
    /// system table). Asserted BOTH ways, not just the positive: a normal hub must keep reading
    /// `0` — the failure mode of a demo mark is a REAL hub mislabelled as a demo, which would
    /// freeze its fiscal identity in silence (see `RequestContext::is_demo_hub` doc comment).
    #[test]
    fn hub1135_system_params_expose_the_demo_mark_both_ways() {
        let ctx = RequestContext::new("h1", "u1", Vec::<String>::new());
        let p = system_params(&Params::new(), &ctx);
        assert_eq!(
            p["is_demo_hub"],
            json!(0),
            "a normal hub reads 0, never absent"
        );

        let ctx = ctx.with_demo_hub(true);
        let p = system_params(&Params::new(), &ctx);
        assert_eq!(p["is_demo_hub"], json!(1), "a demo hub reads 1");
    }

    /// hub#1135: «no es un setting y no debe poder escribirse» — the same non-negotiable the
    /// issue states for `is_demo_hub` that `being_a_demo_is_not_something_a_hub_can_switch_on`
    /// (settings.rs) already enforces for `hub_settings`. Here the door is the PAYLOAD: whatever
    /// a caller stuffs into its own params under `is_demo_hub` must be overwritten by the value
    /// `system_params` computes from `ctx` — exactly like `hub_id`/`has_certificate`/every other
    /// system param, none of which a caller can forge by pre-filling the same key.
    #[test]
    fn hub1135_the_demo_mark_is_not_writable_by_payload() {
        let normal_ctx = RequestContext::new("h1", "u1", Vec::<String>::new());
        let mut forged_true = Params::new();
        forged_true.insert("is_demo_hub".into(), json!(1));
        let p = system_params(&forged_true, &normal_ctx);
        assert_eq!(
            p["is_demo_hub"],
            json!(0),
            "a normal hub cannot be talked into claiming demo=1 via payload"
        );

        let demo_ctx = normal_ctx.with_demo_hub(true);
        let mut forged_false = Params::new();
        forged_false.insert("is_demo_hub".into(), json!(0));
        let p = system_params(&forged_false, &demo_ctx);
        assert_eq!(
            p["is_demo_hub"],
            json!(1),
            "a demo hub cannot be talked out of its own mark via payload"
        );
    }

    /// hub#1425: a module cannot tell whether the owner GRANTED the capabilities it declares, so
    /// it cannot say so on its own screen — which is where the owner is standing when they switch
    /// on the feature that needs them. The core already does its half (`invoice.created` dies with
    /// `module.capability_denied`, `setup_status` does not call it configured); what was missing
    /// was the module's half, at the point of use.
    ///
    /// Same shape as `:has_certificate`/`:is_demo_hub` right above: a hub condition a module needs
    /// in order to PAINT, sounded by the runtime as 0/1 so no module reads the system table
    /// `_module_capability_grants` (which `migration_guard` forbids it anyway).
    #[test]
    fn hub1425_system_params_expose_whether_the_capabilities_are_granted() {
        let ctx = RequestContext::new("h1", "u1", Vec::<String>::new());
        let p = system_params(&Params::new(), &ctx);
        assert_eq!(
            p["capabilities_granted"],
            json!(0),
            "unresolved reads as «not granted»: a screen that over-warns is recoverable, one that \
             stays silent while the module cannot sign is the bug this closes"
        );

        let ctx = ctx.with_capabilities_granted(true);
        let p = system_params(&Params::new(), &ctx);
        assert_eq!(p["capabilities_granted"], json!(1));
    }

    /// And it is not forgeable: written AFTER cloning `base`, exactly like `:hub_id`. Otherwise a
    /// module could paint itself «all permissions granted» by stuffing the key into its own
    /// payload — the shape of hole `hub1135_the_demo_mark_is_not_writable_by_payload` pins for the
    /// demo mark.
    #[test]
    fn hub1425_capabilities_granted_is_not_writable_by_payload() {
        let denied_ctx = RequestContext::new("h1", "u1", Vec::<String>::new());
        let mut forged_true = Params::new();
        forged_true.insert("capabilities_granted".into(), json!(1));
        assert_eq!(
            system_params(&forged_true, &denied_ctx)["capabilities_granted"],
            json!(0)
        );

        let granted_ctx = denied_ctx.with_capabilities_granted(true);
        let mut forged_false = Params::new();
        forged_false.insert("capabilities_granted".into(), json!(0));
        assert_eq!(
            system_params(&forged_false, &granted_ctx)["capabilities_granted"],
            json!(1)
        );
    }

    /// hub#131/#145: [`Runtime::execute_command`] (la puerta PÚBLICA del embedder, la única que
    /// exponen las rutas HTTP/API keys) rechaza un command interno `_` con `InternalCommand`;
    /// [`Runtime::execute_command_internal`] (host embebedor de confianza: siembras de e2e que
    /// suplen un handler nativo/WASM no enlazado) SÍ lo ejecuta — mismo `Origin::Internal` que el
    /// relay del Outbox y el scheduler — y el SQL declarativo del command corre de verdad.
    #[tokio::test]
    async fn public_gate_rejects_underscore_but_internal_entrypoint_runs_it() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();

        let mut rt = Runtime::new(Box::new(db));
        rt.registry
            .status
            .insert("appointments".to_string(), ModuleStatus::Active);
        rt.registry.commands.insert(
            "appointments._insert_appointment".to_string(),
            underscore_cmd("appointments", "INSERT INTO t (n) VALUES (1);"),
        );
        // Identidad de negocio ya rellena → `execute_at` no re-lee `hub_settings` (mismo patrón
        // que `ctx_admin()` en los tests del gate de `commands.rs`).
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]).with_business(
            "B00000000",
            "ACME Test",
            "Calle Falsa 123",
        );

        let err = rt
            .execute_command("appointments._insert_appointment", &Params::new(), &ctx)
            .await
            .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InternalCommand(_)),
            "la puerta pública del embedder debe rechazar el command `_`: {err:?}"
        );

        rt.execute_command_internal("appointments._insert_appointment", &Params::new(), &ctx)
            .await
            .expect("la puerta interna del embedder debe ejecutar el command `_`");
        let r = rt
            .db()
            .query("SELECT COUNT(*) AS c FROM t WHERE n = 1", &Params::new())
            .await
            .unwrap();
        let c = r.rows[0]["c"]
            .as_i64()
            .or_else(|| r.rows[0]["c"].as_f64().map(|f| f as i64))
            .unwrap_or(-1);
        assert_eq!(c, 1, "el SQL del command interno debe haberse ejecutado");
    }
}
