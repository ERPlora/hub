//! Scheduler de módulo (ADR-0011): tareas idempotentes periódicas que ejecuta **el Hub**, no
//! Cloud. **Espejo de `outbox.rs`**: tabla de sistema `_scheduled_tasks` (poblada desde el
//! manifest al instalar, idempotente) + barrido en el loop del relay (`crates/server`).
//!
//! Decisiones (ADR-0011, columna del humano — aquí solo se implementan):
//!  - El `command` de una tarea pertenece al **propio módulo** (mismo aislamiento que el handler
//!    WASM); se ejecuta **sin usuario** (contexto de sistema), igual que el relay del outbox
//!    reconstruye el contexto del emisor: `user_id = ""` + permiso comodín `*`.
//!  - Barrido: `SELECT` tareas vencidas (`next_run <= now`) → `execute_command` → `UPDATE
//!    next_run` atómico **en la misma transacción** (sin doble-disparo). Los efectos del command
//!    y el avance de `next_run` van juntos: si el command revierte, `next_run` no avanza y la
//!    tarea se reintenta el siguiente ciclo.
//!  - Tauri/local al arrancar: catch-up **collapse** — si la tarea estuvo vencida durante un
//!    apagado, se ejecuta **una sola vez** y se reprograma al siguiente vencimiento futuro (no se
//!    corre el backlog acumulado). `catch_up=skip` no ejecuta el backlog, solo reprograma.
//!
//! El cron es un parser mínimo de 5 campos (sin dependencia nueva; ver [`cron`]). TODO humano:
//! decidir si se adopta el crate `cron`/`croner` para soportar la gramática completa (rangos
//! `1-5`, listas `1,15`, `L`/`#`); hoy se cubren los casos del ADR (`*/5`, `@daily`, `@hourly`).
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::commands;
use crate::errors::Result;
use crate::manifest::{CatchUp, ScheduledTaskDef};
use crate::registry::{now_rfc3339, Registry, RequestContext};

/// Tamaño de lote por ciclo del barrido (acota el lock del runtime, como el outbox).
const BATCH: i64 = 50;

const ENSURE_TABLE: &str = "\
CREATE TABLE IF NOT EXISTS _scheduled_tasks (\
  module_id TEXT NOT NULL, name TEXT NOT NULL, command TEXT NOT NULL, \
  cron TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', catch_up TEXT NOT NULL DEFAULT 'collapse', \
  next_run TEXT NOT NULL, last_run TEXT, \
  PRIMARY KEY (module_id, name));\
CREATE INDEX IF NOT EXISTS ix_sched_due ON _scheduled_tasks (next_run);";

/// Crea la tabla de sistema del scheduler (idempotente), como `outbox::ensure_tables`.
pub async fn ensure_tables(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_TABLE).await?;
    Ok(())
}

/// Vuelca las `scheduled_tasks` del manifest de un módulo a `_scheduled_tasks`. **Idempotente**:
/// se llama en cada instalación/reinstalación. Conserva el `next_run`/`last_run` de una tarea ya
/// existente (no resetea el reloj al reinstalar/actualizar) y solo refresca `command/cron/payload/
/// catch_up`; calcula `next_run` a partir de `now` solo para tareas nuevas. Las tareas del módulo
/// que ya no estén en el manifest se borran (capacidad retirada).
pub async fn seed_module_tasks(
    db: &dyn DatabaseAdapter,
    module_id: &str,
    tasks: &[ScheduledTaskDef],
) -> Result<()> {
    ensure_tables(db).await?;
    let now = now_rfc3339();

    // 1) Upsert de cada tarea declarada (preserva next_run/last_run si ya existía).
    for t in tasks {
        let next_run = cron::next_after(&t.cron, &now).unwrap_or_else(|| now.clone());
        let payload = t
            .payload
            .as_ref()
            .map(|p| serde_json::to_string(p).unwrap_or_else(|_| "{}".into()))
            .unwrap_or_else(|| "{}".into());
        let catch_up = match t.catch_up {
            CatchUp::Collapse => "collapse",
            CatchUp::Skip => "skip",
        };
        let mut p = Params::new();
        p.insert("module_id".into(), json!(module_id));
        p.insert("name".into(), json!(t.name));
        p.insert("command".into(), json!(t.command));
        p.insert("cron".into(), json!(t.cron));
        p.insert("payload".into(), json!(payload));
        p.insert("catch_up".into(), json!(catch_up));
        p.insert("next_run".into(), json!(next_run));
        // upsert por PK (module_id,name): si ya existe, NO tocamos next_run/last_run.
        db.execute(
            "INSERT INTO _scheduled_tasks \
               (module_id, name, command, cron, payload, catch_up, next_run, last_run) \
             VALUES (:module_id, :name, :command, :cron, :payload, :catch_up, :next_run, NULL) \
             ON CONFLICT(module_id, name) DO UPDATE SET \
               command = :command, cron = :cron, payload = :payload, catch_up = :catch_up",
            &p,
        )
        .await?;
    }

    // 2) Borra las tareas del módulo que ya no están en el manifest (capacidad retirada).
    let names: Vec<String> = tasks.iter().map(|t| t.name.clone()).collect();
    delete_obsolete(db, module_id, &names).await?;
    Ok(())
}

/// Borra del registro las tareas de `module_id` cuyo `name` no está en `keep` (las del manifest
/// actual). Si `keep` está vacío, borra todas las del módulo. Se ejecuta al reinstalar y al
/// desinstalar (con `keep = []`).
pub async fn delete_obsolete(db: &dyn DatabaseAdapter, module_id: &str, keep: &[String]) -> Result<()> {
    // Trae los nombres actuales y borra los que no se conservan (sin construir IN dinámico).
    let mut q = Params::new();
    q.insert("module_id".into(), json!(module_id));
    let rows = db
        .query("SELECT name FROM _scheduled_tasks WHERE module_id = :module_id", &q)
        .await?;
    for row in &rows.rows {
        let name = row["name"].as_str().unwrap_or_default().to_string();
        if keep.iter().any(|k| k == &name) {
            continue;
        }
        let mut p = Params::new();
        p.insert("module_id".into(), json!(module_id));
        p.insert("name".into(), json!(name));
        db.execute(
            "DELETE FROM _scheduled_tasks WHERE module_id = :module_id AND name = :name",
            &p,
        )
        .await?;
    }
    Ok(())
}

/// Borra TODAS las tareas de un módulo (lo llama el desinstalador). Atajo de [`delete_obsolete`].
pub async fn remove_module_tasks(db: &dyn DatabaseAdapter, module_id: &str) -> Result<()> {
    delete_obsolete(db, module_id, &[]).await
}

/// Un ciclo del barrido: ejecuta hasta [`BATCH`] tareas vencidas. Devuelve cuántas corrió.
/// Lo llama el loop del relay en `crates/server` (junto al `process_outbox`). `hub_id` es el del
/// despliegue (un ECS container por hub, §2.5): se inyecta en el contexto de sistema de la tarea.
pub async fn process_once(db: &dyn DatabaseAdapter, registry: &Registry, hub_id: &str) -> Result<usize> {
    sweep(db, registry, hub_id, false).await
}

/// Barrido de arranque (Tauri/local): catch-up **collapse**. Ejecuta una sola vez cada tarea
/// con backlog vencido (las `catch_up=skip` solo se reprograman). Lo llama el host al arrancar.
pub async fn catch_up_on_boot(db: &dyn DatabaseAdapter, registry: &Registry, hub_id: &str) -> Result<usize> {
    sweep(db, registry, hub_id, true).await
}

/// Barrido común. `on_boot=false`: barrido normal del relay (cada tarea vencida corre y avanza al
/// siguiente vencimiento). `on_boot=true`: catch-up — `collapse` corre una vez y salta el backlog;
/// `skip` no corre, solo reprograma. En ambos casos el avance de `next_run` va en la MISMA
/// transacción que los efectos del command (sin doble-disparo).
async fn sweep(db: &dyn DatabaseAdapter, registry: &Registry, hub_id: &str, on_boot: bool) -> Result<usize> {
    let now = now_rfc3339();
    let mut q = Params::new();
    q.insert("now".into(), json!(now));
    q.insert("lim".into(), json!(BATCH));
    let due = db
        .query(
            "SELECT module_id, name, command, cron, payload, catch_up, next_run \
             FROM _scheduled_tasks WHERE next_run <= :now ORDER BY next_run LIMIT :lim",
            &q,
        )
        .await?;

    let mut ran = 0usize;
    for row in &due.rows {
        if run_task(db, registry, row, &now, hub_id, on_boot).await? {
            ran += 1;
        }
    }
    Ok(ran)
}

/// Procesa una fila vencida: decide si ejecutar el command (según `on_boot`/`catch_up`), calcula el
/// próximo `next_run` y lo persiste atómicamente con los efectos del command. Devuelve `true` si
/// ejecutó el command. Una tarea cuyo command no exista (módulo inactivo/desinstalado a medias) se
/// reprograma sin ejecutar (no es un error duro del barrido).
async fn run_task(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    row: &Json,
    now: &str,
    hub_id: &str,
    on_boot: bool,
) -> Result<bool> {
    let module_id = row["module_id"].as_str().unwrap_or_default().to_string();
    let name = row["name"].as_str().unwrap_or_default().to_string();
    let command = row["command"].as_str().unwrap_or_default().to_string();
    let cron = row["cron"].as_str().unwrap_or_default().to_string();
    let catch_up = row["catch_up"].as_str().unwrap_or("collapse");

    // Próximo vencimiento estrictamente posterior a `now` (collapse del backlog acumulado).
    let next_run = cron::next_after(&cron, now).unwrap_or_else(|| now.to_string());

    // ¿Ejecutamos el command en este barrido?
    //  - barrido normal del relay: sí (la fila está vencida).
    //  - arranque con catch_up=skip: no (solo reprograma).
    let should_run = !(on_boot && catch_up == "skip");

    // El command pertenece al propio módulo; solo se ejecuta si su módulo está activo.
    let runnable = should_run && registry.get_command(&command).map(|c| c.module_id == module_id).unwrap_or(false);

    if runnable {
        let payload = parse_payload(row);
        let ctx = system_ctx(hub_id);
        // Efectos del command (+ sus eventos en el outbox) y el avance de `next_run`/`last_run`
        // de ESTA tarea en UNA transacción → idempotencia estructural (sin doble-disparo): si el
        // command commitea, `next_run` avanza sí o sí; si revierte, la tarea se reintenta.
        let advance = advance_op(&module_id, &name, &next_run, now);
        commands::execute_at(db, registry, &command, &payload, &ctx, 0, &[advance]).await?;
        Ok(true)
    } else {
        // No se ejecuta (skip en arranque, o command no resoluble): solo reprograma `next_run`.
        let (sql, p) = advance_op(&module_id, &name, &next_run, now);
        let p = if should_run {
            // command no resoluble: reprograma pero NO marca last_run (no corrió).
            let mut p2 = p;
            p2.insert("last_run".into(), Json::Null);
            p2
        } else {
            p
        };
        db.execute(&sql, &p).await?;
        Ok(false)
    }
}

/// `UPDATE` que avanza `next_run` y marca `last_run = now`. Se añade a la transacción del command
/// (vía `extra_ops` de `commands::execute_at`) para que el disparo y el avance sean atómicos.
fn advance_op(module_id: &str, name: &str, next_run: &str, now: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    p.insert("name".into(), json!(name));
    p.insert("next_run".into(), json!(next_run));
    p.insert("last_run".into(), json!(now));
    let sql = "UPDATE _scheduled_tasks SET next_run = :next_run, last_run = :last_run \
               WHERE module_id = :module_id AND name = :name";
    (sql.to_string(), p)
}

/// Contexto **de sistema** (sin usuario) con el que corre la tarea: el `hub_id` del despliegue
/// (un ECS container por hub, §2.5), `user_id` vacío y permiso comodín `*`. Es el equivalente al
/// contexto que el relay del outbox reconstruye para el emisor, pero sin usuario (ADR-0011: las
/// scheduled tasks ejecutan sin usuario).
fn system_ctx(hub_id: &str) -> RequestContext {
    RequestContext::new(hub_id.to_string(), String::new(), ["*".to_string()])
}

fn parse_payload(row: &Json) -> Params {
    row["payload"]
        .as_str()
        .and_then(|s| serde_json::from_str::<Json>(s).ok())
        .and_then(|v| match v {
            Json::Object(m) => Some(m),
            _ => None,
        })
        .unwrap_or_default()
}

/// Parser de cron mínimo (5 campos `min hora dom mes dow` + atajos), **sin dependencia nueva**.
/// Soporta lo que pide el ADR-0011: `*` (cualquiera), `*/N` (cada N), un entero fijo, y los atajos
/// `@hourly`/`@daily`/`@weekly`/`@monthly`/`@yearly`. NO soporta rangos (`1-5`) ni listas (`1,15`)
/// — TODO humano: adoptar un crate de cron si se necesita la gramática completa.
pub mod cron {
    use chrono::{DateTime, Datelike, Duration, Timelike, Utc};

    /// Devuelve el siguiente instante (RFC3339) que cumple `expr` **estrictamente posterior** a
    /// `after` (RFC3339). `None` si la expresión es inválida o `after` no parsea. El "collapse" del
    /// catch-up sale gratis: siempre se busca hacia adelante desde `now`, nunca se acumula backlog.
    pub fn next_after(expr: &str, after: &str) -> Option<String> {
        let parsed = parse(expr)?;
        let from: DateTime<Utc> = DateTime::parse_from_rfc3339(after).ok()?.with_timezone(&Utc);
        // Empieza en el siguiente minuto (resolución mínima del cron) y avanza minuto a minuto
        // hasta encontrar coincidencia. Tope de búsqueda: ~366 días (cubre @yearly) por seguridad.
        let mut t = (from + Duration::minutes(1))
            .with_second(0)?
            .with_nanosecond(0)?;
        for _ in 0..(366 * 24 * 60) {
            if parsed.matches(&t) {
                return Some(t.to_rfc3339());
            }
            t += Duration::minutes(1);
        }
        None
    }

    /// Cron parseado: por campo, `None` = comodín (`*`), `Some((step, fixed))`.
    struct Cron {
        minute: Field,
        hour: Field,
        dom: Field,
        month: Field,
        dow: Field,
    }

    /// Un campo de cron: comodín, "cada N" (`*/N`) o valor fijo.
    enum Field {
        Any,
        Step(u32),
        Fixed(u32),
    }

    impl Field {
        fn matches(&self, value: u32) -> bool {
            match self {
                Field::Any => true,
                Field::Step(n) if *n == 0 => false,
                Field::Step(n) => value % n == 0,
                Field::Fixed(v) => value == *v,
            }
        }
    }

    impl Cron {
        fn matches(&self, t: &DateTime<Utc>) -> bool {
            self.minute.matches(t.minute())
                && self.hour.matches(t.hour())
                && self.dom.matches(t.day())
                && self.month.matches(t.month())
                // chrono: lunes=0..domingo=6; cron: domingo=0..sábado=6. Normalizamos a cron.
                && self.dow.matches(t.weekday().num_days_from_sunday())
        }
    }

    fn parse_field(s: &str) -> Option<Field> {
        if s == "*" {
            return Some(Field::Any);
        }
        if let Some(rest) = s.strip_prefix("*/") {
            return rest.parse::<u32>().ok().map(Field::Step);
        }
        s.parse::<u32>().ok().map(Field::Fixed)
    }

    fn parse(expr: &str) -> Option<Cron> {
        let expr = expr.trim();
        // Atajos comunes → expansión a 5 campos.
        let expanded = match expr {
            "@yearly" | "@annually" => "0 0 1 1 *".to_string(),
            "@monthly" => "0 0 1 * *".to_string(),
            "@weekly" => "0 0 * * 0".to_string(),
            "@daily" | "@midnight" => "0 0 * * *".to_string(),
            "@hourly" => "0 * * * *".to_string(),
            other => other.to_string(),
        };
        let parts: Vec<&str> = expanded.split_whitespace().collect();
        if parts.len() != 5 {
            return None;
        }
        Some(Cron {
            minute: parse_field(parts[0])?,
            hour: parse_field(parts[1])?,
            dom: parse_field(parts[2])?,
            month: parse_field(parts[3])?,
            dow: parse_field(parts[4])?,
        })
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn every_five_minutes() {
            // `*/5` desde 10:02 → 10:05.
            let n = next_after("*/5 * * * *", "2026-06-13T10:02:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-13T10:05:00"), "got {n}");
        }

        #[test]
        fn daily_shortcut() {
            // `@daily` desde las 10:00 → medianoche del día siguiente.
            let n = next_after("@daily", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-14T00:00:00"), "got {n}");
        }

        #[test]
        fn hourly_shortcut() {
            let n = next_after("@hourly", "2026-06-13T10:30:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-13T11:00:00"), "got {n}");
        }

        #[test]
        fn fixed_minute_hour() {
            // `30 9 * * *` (9:30 cada día) desde las 10:00 → mañana 9:30.
            let n = next_after("30 9 * * *", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-14T09:30:00"), "got {n}");
        }

        #[test]
        fn invalid_expr_is_none() {
            assert!(next_after("not a cron", "2026-06-13T10:00:00+00:00").is_none());
            assert!(next_after("* * *", "2026-06-13T10:00:00+00:00").is_none());
        }

        #[test]
        fn collapse_skips_backlog() {
            // Aunque la tarea estuviera vencida hace días, `next_after(now)` salta hacia adelante:
            // no se acumula backlog (catch-up collapse estructural).
            let n = next_after("*/5 * * * *", "2026-06-13T10:02:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-13T10:05:00"), "got {n}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::CommandDef;
    use crate::registry::{ModuleStatus, RegisteredCommand};
    use erplora_db::SqliteAdapter;

    fn cmd(module: &str, sql: &str) -> RegisteredCommand {
        RegisteredCommand {
            module_id: module.to_string(),
            def: CommandDef {
                permission: String::new(),
                transaction: true,
                sql: vec![sql.to_string()],
                emit: vec![],
                handler: None,
                ai: None,
                schema: None,
                expose_api: false,
            },
            sql: vec![sql.to_string()],
            wasm: None,
            schema: None,
        }
    }

    fn task(name: &str, command: &str, cron: &str, catch_up: CatchUp) -> ScheduledTaskDef {
        ScheduledTaskDef {
            name: name.to_string(),
            command: command.to_string(),
            cron: cron.to_string(),
            payload: None,
            catch_up,
        }
    }

    async fn count(db: &SqliteAdapter, sql: &str) -> i64 {
        let r = db.query(sql, &Params::new()).await.unwrap();
        r.rows[0]["c"].as_i64().or_else(|| r.rows[0]["c"].as_f64().map(|f| f as i64)).unwrap_or(-1)
    }

    /// Una tarea vencida ejecuta su command y avanza `next_run` al futuro en la misma tx; un
    /// segundo barrido inmediato NO la vuelve a disparar (sin doble-disparo).
    #[tokio::test]
    async fn due_task_runs_once_and_reschedules() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        crate::outbox::ensure_tables(&db).await.unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        reg.commands.insert("m.tick".into(), cmd("m", "INSERT INTO t (n) VALUES (1);"));

        // Tarea ya vencida: next_run en el pasado.
        let mut p = Params::new();
        p.insert("module_id".into(), json!("m"));
        p.insert("name".into(), json!("tick"));
        p.insert("command".into(), json!("m.tick"));
        p.insert("cron".into(), json!("*/5 * * * *"));
        p.insert("next_run".into(), json!("2020-01-01T00:00:00+00:00"));
        db.execute(
            "INSERT INTO _scheduled_tasks (module_id, name, command, cron, payload, catch_up, next_run) \
             VALUES (:module_id, :name, :command, :cron, '{}', 'collapse', :next_run)",
            &p,
        )
        .await
        .unwrap();

        let ran = process_once(&db, &reg, "h1").await.unwrap();
        assert_eq!(ran, 1, "ejecuta la tarea vencida");
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1);

        // Segundo barrido inmediato: next_run ya está en el futuro → no re-dispara.
        let ran2 = process_once(&db, &reg, "h1").await.unwrap();
        assert_eq!(ran2, 0, "no doble-disparo");
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1);
    }

    /// `seed_module_tasks` es idempotente: re-sembrar la misma tarea NO resetea `next_run`.
    #[tokio::test]
    async fn seed_is_idempotent_and_preserves_clock() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_tables(&db).await.unwrap();
        let tasks = vec![task("tick", "m.tick", "*/5 * * * *", CatchUp::Collapse)];

        seed_module_tasks(&db, "m", &tasks).await.unwrap();
        let r = db
            .query("SELECT next_run FROM _scheduled_tasks WHERE module_id='m' AND name='tick'", &Params::new())
            .await
            .unwrap();
        let first = r.rows[0]["next_run"].as_str().unwrap().to_string();

        // Forzamos un next_run "antiguo" como si la tarea llevara tiempo corriendo.
        let mut p = Params::new();
        p.insert("nr".into(), json!("2099-01-01T00:00:00+00:00"));
        db.execute("UPDATE _scheduled_tasks SET next_run = :nr WHERE name='tick'", &p).await.unwrap();

        // Re-sembrar (reinstalación) NO debe pisar next_run.
        seed_module_tasks(&db, "m", &tasks).await.unwrap();
        let r = db
            .query("SELECT next_run FROM _scheduled_tasks WHERE name='tick'", &Params::new())
            .await
            .unwrap();
        assert_eq!(r.rows[0]["next_run"].as_str().unwrap(), "2099-01-01T00:00:00+00:00");
        assert_ne!(first, "2099-01-01T00:00:00+00:00");

        // Una tarea retirada del manifest se borra.
        seed_module_tasks(&db, "m", &[]).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM _scheduled_tasks").await, 0);
    }

    /// Catch-up en arranque: `collapse` ejecuta una sola vez el backlog; `skip` no ejecuta, solo
    /// reprograma.
    #[tokio::test]
    async fn boot_catch_up_collapse_vs_skip() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        crate::outbox::ensure_tables(&db).await.unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        reg.commands.insert("m.collapse".into(), cmd("m", "INSERT INTO t (n) VALUES (1);"));
        reg.commands.insert("m.skip".into(), cmd("m", "INSERT INTO t (n) VALUES (2);"));

        for (name, command, cu) in [("c", "m.collapse", "collapse"), ("s", "m.skip", "skip")] {
            let mut p = Params::new();
            p.insert("module_id".into(), json!("m"));
            p.insert("name".into(), json!(name));
            p.insert("command".into(), json!(command));
            p.insert("cron".into(), json!("*/5 * * * *"));
            p.insert("catch_up".into(), json!(cu));
            p.insert("next_run".into(), json!("2020-01-01T00:00:00+00:00"));
            db.execute(
                "INSERT INTO _scheduled_tasks (module_id, name, command, cron, payload, catch_up, next_run) \
                 VALUES (:module_id, :name, :command, :cron, '{}', :catch_up, :next_run)",
                &p,
            )
            .await
            .unwrap();
        }

        let ran = catch_up_on_boot(&db, &reg, "h1").await.unwrap();
        assert_eq!(ran, 1, "solo la collapse corre en arranque");
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1, "collapse corrió una vez");
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=2").await, 0, "skip no corrió");
        // Ambas quedan reprogramadas al futuro (no se vuelven a tomar).
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _scheduled_tasks WHERE next_run <= '2025-01-01'").await,
            0
        );
    }
}
