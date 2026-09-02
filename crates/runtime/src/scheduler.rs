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
//! El cron es un parser propio de 5 campos con la gramática de `crontab(5)` (rangos `1-5`, listas
//! `1,15`, pasos `*/N`/`a-b/N` y nombres `MON`/`JAN`; ver [`cron`], hub#730). **Estas tareas se
//! interpretan en UTC** y eso NO cambia (hub#731): el `cron` de una `scheduled_task` lo escribe un
//! programador en el manifest, meses antes de saber en qué país vive el hub. El reloj del negocio
//! es cosa de los flujos, que sí los escribe el dueño — ver `flows/triggers.rs`.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::commands;
use crate::errors::Result;
use crate::manifest::{CatchUp, ScheduledTaskDef};
use crate::registry::{now_rfc3339, Registry, RequestContext};

/// Tamaño de lote por ciclo del barrido (acota el lock del runtime, como el outbox).
const BATCH: i64 = 50;

/// Cuánto tiempo una tarea reclamada queda invisible a otras instancias (hub#570). Lo bastante largo
/// para cubrir la ejecución del command (incluida su tx); lo bastante corto para que un runtime que
/// muere a media tarea no la deje bloqueada hasta el siguiente reinicio. Cuando el lease expira, la
/// condición del `WHERE` del claim la vuelve a ver y otra instancia la reclama.
const LEASE_SECONDS: i64 = 300;

/// Dónde va a parar una tarea cuyo cron el motor no sabe leer (hub#730). `next_run` es `NOT NULL`,
/// así que no se puede "desprogramar" una fila: se manda tan lejos que no vuelve. Es un caso
/// inalcanzable desde el manifest (`seed_module_tasks` ya lo rechaza) — esto cubre las filas
/// escritas antes del gate.
const PARKED_FOREVER: &str = "9999-12-31T00:00:00+00:00";

const ENSURE_TABLE: &str = "\
CREATE TABLE IF NOT EXISTS _scheduled_tasks (\
  module_id TEXT NOT NULL, name TEXT NOT NULL, command TEXT NOT NULL, \
  cron TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', catch_up TEXT NOT NULL DEFAULT 'collapse', \
  next_run TEXT NOT NULL, last_run TEXT, claim_expires_at TEXT, \
  PRIMARY KEY (module_id, name));\
CREATE INDEX IF NOT EXISTS ix_sched_due ON _scheduled_tasks (next_run);\
ALTER TABLE _scheduled_tasks ADD COLUMN IF NOT EXISTS claim_expires_at TEXT;";

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
        // hub#730: el fallback era `unwrap_or_else(|| now)`, o sea que un cron que el motor NO
        // sabe leer quedaba **vencido en cada tick** — un bucle caliente disfrazado de tarea. Una
        // tarea que no se puede programar NO se programa, y se grita: la tabla es el registro de
        // lo que va a correr, y una fila que miente es peor que una fila que falta.
        let Some(next_run) = cron::next_after(&t.cron, &now) else {
            eprintln!(
                "scheduler: {}.{}: `{}` is not a cron this hub can run, task NOT scheduled — {}",
                module_id,
                t.name,
                t.cron,
                cron::validate(&t.cron).err().unwrap_or_default()
            );
            continue;
        };
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
pub async fn delete_obsolete(
    db: &dyn DatabaseAdapter,
    module_id: &str,
    keep: &[String],
) -> Result<()> {
    // Trae los nombres actuales y borra los que no se conservan (sin construir IN dinámico).
    let mut q = Params::new();
    q.insert("module_id".into(), json!(module_id));
    let rows = db
        .query(
            "SELECT name FROM _scheduled_tasks WHERE module_id = :module_id",
            &q,
        )
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
pub async fn process_once(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
) -> Result<usize> {
    sweep(db, registry, hub_id, false).await
}

/// Barrido de arranque (Tauri/local): catch-up **collapse**. Ejecuta una sola vez cada tarea
/// con backlog vencido (las `catch_up=skip` solo se reprograman). Lo llama el host al arrancar.
pub async fn catch_up_on_boot(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
) -> Result<usize> {
    sweep(db, registry, hub_id, true).await
}

/// Barrido común. `on_boot=false`: barrido normal del relay (cada tarea vencida corre y avanza al
/// siguiente vencimiento). `on_boot=true`: catch-up — `collapse` corre una vez y salta el backlog;
/// `skip` no corre, solo reprograma.
///
/// **Reclamo atómico (hub#570).** El modelo de actualización es `start-first`: la tarea nueva
/// arranca mientras la vieja sigue sirviendo, así que durante el solape hay **dos** runtimes del
/// mismo hub contra la misma BD corriendo el scheduler. Un `SELECT … WHERE next_run <= :now` seguido
/// de `UPDATE next_run` en la transacción del command deja una ventana en la que las dos instancias
/// leen la misma fila vencida y la ejecutan las dos. Lo cerramos **a nivel BD**: cada vuelta del
/// bucle **reclama una tarea** con un `UPDATE … (SELECT … FOR UPDATE SKIP LOCKED) … RETURNING` que
/// la marca en vuelo (`claim_expires_at`) — mismo patrón que `print_queue::claim_next`.
/// `FOR UPDATE SKIP LOCKED` garantiza que dos instancias que compiten se llevan tareas **distintas**:
/// nunca la misma dos veces. El `next_run` real (calculado en Rust, pues el cron se parsea aquí) se
/// escribe al **resolver** la tarea, junto a los efectos del command, en la MISMA transacción; si el
/// proceso muere a media tarea, el lease expira y otra instancia la reclama.
async fn sweep(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    on_boot: bool,
) -> Result<usize> {
    let now = now_rfc3339();
    let mut ran = 0usize;
    for _ in 0..BATCH {
        match claim_next_due(db, &now).await? {
            Some(row) => {
                if run_task(db, registry, &row, &now, hub_id, on_boot).await? {
                    ran += 1;
                }
            }
            // Ninguna tarea vencida y sin dueño: fin del barrido.
            None => break,
        }
    }
    Ok(ran)
}

/// Reclama **una** tarea vencida de forma atómica y devuelve la fila reclamada. El `UPDATE` toma la
/// fila con `FOR UPDATE SKIP LOCKED` y le pone `claim_expires_at` al futuro, **en el mismo
/// enunciado**: así la fila deja de ser "reclamable" para cualquier otra instancia (la condición del
/// `WHERE` exige `claim_expires_at IS NULL OR claim_expires_at <= :now`) antes de que esta ejecute el
/// command. La fila sigue teniendo su `next_run` original (aún no avanzado): `run_task` lo avanza al
/// resolver la tarea, dentro de la transacción del command.
async fn claim_next_due(db: &dyn DatabaseAdapter, now: &str) -> Result<Option<Json>> {
    let lease = (chrono::Utc::now() + chrono::Duration::seconds(LEASE_SECONDS)).to_rfc3339();
    let mut p = Params::new();
    p.insert("now".into(), json!(now));
    p.insert("lease".into(), json!(lease));
    let sql = "UPDATE _scheduled_tasks SET claim_expires_at = :lease \
               WHERE (module_id, name) = ( \
                 SELECT module_id, name FROM _scheduled_tasks \
                 WHERE next_run <= :now \
                   AND (claim_expires_at IS NULL OR claim_expires_at <= :now) \
                 ORDER BY next_run LIMIT 1 FOR UPDATE SKIP LOCKED) \
               RETURNING module_id, name, command, cron, payload, catch_up, next_run";
    let res = db.query(sql, &p).await?;
    Ok(res.rows.into_iter().next())
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
    // hub#730: si el cron no se puede leer, la fila se APARCA (no se pone a `now`, que la dejaba
    // vencida en cada tick). Solo es alcanzable con una fila anterior al gate de `seed_module_tasks`
    // — el manifest es la fuente de verdad y ahí ya se rechaza —, así que se grita una vez y no
    // vuelve a molestar en lugar de repetir el aviso cada segundo.
    let next_run = cron::next_after(&cron, now).unwrap_or_else(|| {
        eprintln!(
            "scheduler: {module_id}.{name}: `{cron}` is not a cron this hub can run; the task is \
             parked instead of being due on every tick. Reinstall the module with a valid cron."
        );
        PARKED_FOREVER.to_string()
    });

    // ¿Ejecutamos el command en este barrido?
    //  - barrido normal del relay: sí (la fila está vencida).
    //  - arranque con catch_up=skip: no (solo reprograma).
    let should_run = !(on_boot && catch_up == "skip");

    // El command pertenece al propio módulo; solo se ejecuta si su módulo está activo.
    let runnable = should_run
        && registry
            .get_command(&command)
            .map(|c| c.module_id == module_id)
            .unwrap_or(false);

    if runnable {
        let payload = parse_payload(row);
        let ctx = system_ctx(hub_id);
        // Efectos del command (+ sus eventos en el outbox) y el avance de `next_run`/`last_run`
        // de ESTA tarea en UNA transacción → idempotencia estructural (sin doble-disparo): si el
        // command commitea, `next_run` avanza sí o sí; si revierte, la tarea se reintenta.
        let advance = advance_op(&module_id, &name, &next_run, now);
        // Origin::Internal (hub#131, hub#145): la tarea corre sin usuario, disparada por el
        // propio Hub (§4.2). El `runnable` de arriba YA exige que `command` pertenezca al MISMO
        // `module_id` que declaró la scheduled task en su manifest — así que aunque el command sea
        // `internal`/`_`-prefijado, esto NO abre una puerta cruzada: sigue siendo "el módulo se
        // dispara a sí mismo", el mismo aislamiento que ya tenía el handler WASM (§5.3).
        commands::execute_at(
            db,
            registry,
            &command,
            &payload,
            &ctx,
            0,
            &[advance],
            commands::Origin::Internal,
            // A scheduled task runs with nobody at the till (hub#361): no approval to spend.
            None,
        )
        .await?;
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

/// `UPDATE` que resuelve una tarea reclamada: avanza `next_run` al siguiente vencimiento, marca
/// `last_run = now` y **libera el lease** (`claim_expires_at = NULL`). Se añade a la transacción del
/// command (vía `extra_ops` de `commands::execute_at`) para que el disparo y el avance sean atómicos:
/// si el command commitea, la tarea queda reprogramada y libre; si revierte, el lease sigue vivo y la
/// tarea se reintenta (su `next_run` no avanzó). En el path no-runnable (skip en arranque, o command
/// no resoluble) se ejecuta suelta: la tarea queda reprogramada sin disparar nada.
fn advance_op(module_id: &str, name: &str, next_run: &str, now: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    p.insert("name".into(), json!(name));
    p.insert("next_run".into(), json!(next_run));
    p.insert("last_run".into(), json!(now));
    let sql = "UPDATE _scheduled_tasks SET next_run = :next_run, last_run = :last_run, \
               claim_expires_at = NULL WHERE module_id = :module_id AND name = :name";
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

/// Cron of 5 fields (`minute hour day-of-month month day-of-week`) + the `@` shortcuts, with the
/// grammar of `crontab(5)`: `*`, a value, a range `a-b`, a list `a,b`, a step `*/N` or `a-b/N`, and
/// names for month and day-of-week (`JAN…DEC`, `SUN…SAT`).
///
/// **Why it grew (hub#730).** It used to understand only `*`, `*/N` and a fixed number, and
/// [`parse`] returned `None` for everything else — which the callers turned into a trigger that is
/// armed and never fires. Rejecting `1-5` at the door was the floor; understanding it is what
/// anybody who has ever written a crontab (or used Zapier/n8n) expects on the first day. The
/// parser now returns a **message saying what is wrong**, and that message is what the API hands
/// back, so a cron the engine cannot run can no longer be saved.
///
/// **Which clock (hub#731).** [`next_after`] resolves the expression in **UTC** — that is the
/// contract of `_scheduled_tasks`, written by a module programmer in a manifest, and it does not
/// move. [`next_after_in_tz`] resolves it in the **business** zone, and that is what a flow's cron
/// uses: the owner writes «cierra la caja a las 21:00» and means 21:00 in the shop. Both return the
/// instant in UTC, because `next_run` is a TEXT column compared with `<=` in SQL and a `+02:00` in
/// the string would sort as a different instant.
pub mod cron {
    use chrono::{
        DateTime, Datelike, Duration, LocalResult, NaiveDate, NaiveDateTime, TimeZone, Utc,
    };
    pub use chrono_tz::Tz;

    /// What a person is allowed to write, in one line. It is appended to every refusal: the whole
    /// point of hub#730 is that the author is told what to type instead.
    pub const SYNTAX_HELP: &str = "Accepted per field: `*`, a value, a range `a-b`, a list `a,b`, \
        a step `*/N` or `a-b/N`; month and day-of-week also take names (JAN…DEC, SUN…SAT, e.g. \
        `0 9 * * MON-FRI`). Shortcuts: @hourly, @daily, @weekly, @monthly, @yearly.";

    /// How far ahead the search goes. Eight years, not one: `0 0 29 2 *` is legal and the next 29
    /// February can be four years away (eight across a non-leap century year). The old 366-day
    /// window returned `None` for it, and `None` is exactly what the callers mistranslated into
    /// "never" (flows) or "due on every tick" (scheduler).
    const SEARCH_DAYS: i32 = 8 * 366;

    const MONTH_NAMES: &[(&str, u32)] = &[
        ("JAN", 1),
        ("FEB", 2),
        ("MAR", 3),
        ("APR", 4),
        ("MAY", 5),
        ("JUN", 6),
        ("JUL", 7),
        ("AUG", 8),
        ("SEP", 9),
        ("OCT", 10),
        ("NOV", 11),
        ("DEC", 12),
    ];
    const DAY_NAMES: &[(&str, u32)] = &[
        ("SUN", 0),
        ("MON", 1),
        ("TUE", 2),
        ("WED", 3),
        ("THU", 4),
        ("FRI", 5),
        ("SAT", 6),
    ];

    /// Next instant (RFC-3339, UTC) matching `expr` **strictly after** `after`, resolved on the
    /// UTC clock. `None` if `expr` is not runnable or `after` is not an instant. The catch-up
    /// "collapse" is free: the search always goes forward from `now`, so no backlog accumulates.
    pub fn next_after(expr: &str, after: &str) -> Option<String> {
        next_after_in_tz(expr, after, Tz::UTC)
    }

    /// Same, resolved on the clock of `tz` — the **business** clock. The returned instant is still
    /// UTC; only the reading of the expression changes.
    ///
    /// ## The two days a year this is not arithmetic
    ///
    /// - **The hour that does not exist** (spring forward: Madrid goes 02:00 → 03:00). A `0 2 * * *`
    ///   has no instant that day. It fires **at the moment the clock jumps over it** — i.e. 03:00
    ///   local, the first real instant at or after the one that was asked for. A cash close is not
    ///   silently dropped because the calendar skipped an hour.
    /// - **The hour that happens twice** (autumn: 03:00 → 02:00, so local 02:xx runs twice). The
    ///   **first** (pre-transition) occurrence is taken and the second is never produced, so the
    ///   close is booked once. The cost is that a sub-hourly cron loses that repeated hour — which
    ///   is what `crontab` and `systemd` timers do too, and is the right side to err on: skipping
    ///   an interval tick is recoverable, booking a day twice is not.
    pub fn next_after_in_tz(expr: &str, after: &str, tz: Tz) -> Option<String> {
        let cron = parse(expr).ok()?;
        let from: DateTime<Utc> = DateTime::parse_from_rfc3339(after)
            .ok()?
            .with_timezone(&Utc);

        let hours = values(cron.hour);
        let minutes = values(cron.minute);
        // Walk LOCAL days, not UTC minutes: the expression is written on the wall clock, and this
        // also makes a rare date (29 February) cheap instead of two million minute steps.
        let mut date = from.with_timezone(&tz).date_naive();
        for _ in 0..SEARCH_DAYS {
            if cron.matches_date(&date) {
                for hour in &hours {
                    for minute in &minutes {
                        let naive = date.and_hms_opt(*hour, *minute, 0)?;
                        let utc = local_to_utc(&naive, tz);
                        // Strictly after: on both DST days the local→UTC map is only
                        // non-decreasing, so this is what keeps a fired trigger from firing again.
                        if utc > from {
                            return Some(utc.to_rfc3339());
                        }
                    }
                }
            }
            date = date.succ_opt()?;
        }
        None
    }

    /// `Ok(())` if this hub can actually run `expr`, `Err(what is wrong)` otherwise. This is the
    /// gate the API calls before storing a trigger (hub#730).
    pub fn validate(expr: &str) -> std::result::Result<(), String> {
        parse(expr).map(|_| ())
    }

    /// One local wall-clock time as an instant, with the two DST cases decided (see
    /// [`next_after_in_tz`]).
    fn local_to_utc(naive: &NaiveDateTime, tz: Tz) -> DateTime<Utc> {
        match tz.from_local_datetime(naive) {
            LocalResult::Single(dt) => dt.with_timezone(&Utc),
            // Twice: the earlier one, once.
            LocalResult::Ambiguous(earliest, _) => earliest.with_timezone(&Utc),
            // Never: the instant the clock jumped over it. Found by bisection rather than by
            // assuming the jump is one hour — it is 30 minutes in Lord Howe, and a hard-coded
            // hour is how a "should be fine everywhere" rule becomes a wrong close somewhere.
            LocalResult::None => gap_end(naive, tz),
        }
    }

    /// The first instant whose local time has reached `naive`, when `naive` itself never happens.
    fn gap_end(naive: &NaiveDateTime, tz: Tz) -> DateTime<Utc> {
        // A 60 h window around the wall-clock time brackets any real transition (the largest UTC
        // offset in the tz database is ±14 h), so the predicate is false at `lo` and true at `hi`.
        let base = *naive - Duration::hours(30);
        let (mut lo, mut hi) = (0i64, 60 * 60i64);
        while lo < hi {
            let mid = (lo + hi) / 2;
            let candidate = Utc.from_utc_datetime(&(base + Duration::minutes(mid)));
            if candidate.with_timezone(&tz).naive_local() >= *naive {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        Utc.from_utc_datetime(&(base + Duration::minutes(lo)))
    }

    /// A parsed cron. Each field is a bitmask of the values it matches, which makes "is this
    /// minute in the set?" one instruction and "which minutes?" one iteration.
    #[derive(Debug)]
    pub struct Cron {
        minute: u64,
        hour: u64,
        dom: u64,
        month: u64,
        dow: u64,
        /// Whether the author restricted the field (i.e. did not write `*`). Only used to pick
        /// between AND and OR on the two day fields — see [`Cron::matches_date`].
        dom_restricted: bool,
        dow_restricted: bool,
    }

    impl Cron {
        fn matches_date(&self, date: &NaiveDate) -> bool {
            if self.month & bit(date.month()) == 0 {
                return false;
            }
            let by_dom = self.dom & bit(date.day()) != 0;
            let by_dow = self.dow & bit(date.weekday().num_days_from_sunday()) != 0;
            // `crontab(5)`: when BOTH day fields are restricted they are ORed — `0 9 1 * MON` is
            // "the 1st, and every Monday". When only one is, the other is `*` and ANDing is the
            // same thing. (The old parser ANDed always, which quietly meant "the 1st, but only if
            // it is a Monday" — eleven months of the year that is no run at all.)
            if self.dom_restricted && self.dow_restricted {
                by_dom || by_dow
            } else {
                by_dom && by_dow
            }
        }

        /// Is there any (month, day) this can ever land on? `0 0 30 2 *` parses field by field and
        /// then never happens; refusing it here is the difference between "saved and silent" and
        /// "told at save time".
        fn is_reachable(&self) -> bool {
            if self.dow_restricted {
                // Any weekday recurs in every month, so a non-empty month set is enough.
                return self.month != 0 && self.dow != 0;
            }
            (1..=12).any(|m| {
                self.month & bit(m) != 0 && (1..=days_in_month(m)).any(|d| self.dom & bit(d) != 0)
            })
        }
    }

    /// Longest this month can ever be (February counted as a leap year).
    fn days_in_month(month: u32) -> u32 {
        match month {
            2 => 29,
            4 | 6 | 9 | 11 => 30,
            _ => 31,
        }
    }

    fn bit(value: u32) -> u64 {
        1u64 << value
    }

    fn values(mask: u64) -> Vec<u32> {
        (0..64).filter(|v| mask & bit(*v) != 0).collect()
    }

    /// Parses `expr`, or says what is wrong with it in a sentence the author can act on.
    pub fn parse(expr: &str) -> std::result::Result<Cron, String> {
        let raw = expr.trim();
        let expanded = match raw.to_ascii_lowercase().as_str() {
            "@yearly" | "@annually" => "0 0 1 1 *",
            "@monthly" => "0 0 1 * *",
            "@weekly" => "0 0 * * 0",
            "@daily" | "@midnight" => "0 0 * * *",
            "@hourly" => "0 * * * *",
            _ => raw,
        };
        if expanded.starts_with('@') {
            // `@reboot` is the usual one, and it is not a schedule — it is an event this hub does
            // not have. Saying so beats parsing it into a trigger that never fires.
            return Err(format!(
                "`{raw}` is not a shortcut this hub knows. {SYNTAX_HELP}"
            ));
        }
        let parts: Vec<&str> = expanded.split_whitespace().collect();
        if parts.len() != 5 {
            return Err(format!(
                "`{raw}`: a cron has 5 fields — `minute hour day-of-month month day-of-week` — \
                 and this has {}. {SYNTAX_HELP}",
                parts.len()
            ));
        }

        // Left to right, so the complaint is about the FIRST field that is wrong — which is the
        // one the author's eye goes to. (`esto no es un cron` happens to be five words; reporting
        // the last field would tell them about `cron` instead of about `esto`.)
        let minute = field(parts[0], 0, 59, "minute", &[])?;
        let hour = field(parts[1], 0, 23, "hour", &[])?;
        let dom = field(parts[2], 1, 31, "day-of-month", &[])?;
        let month = field(parts[3], 1, 12, "month", MONTH_NAMES)?;
        let dow_raw = field(parts[4], 0, 7, "day-of-week", DAY_NAMES)?;
        let cron = Cron {
            minute,
            hour,
            dom,
            month,
            // Both 0 and 7 mean Sunday in crontab, and somebody will write each of them.
            dow: if dow_raw & bit(7) != 0 {
                (dow_raw | 1) & !bit(7)
            } else {
                dow_raw
            },
            dom_restricted: parts[2] != "*",
            dow_restricted: parts[4] != "*",
        };
        if !cron.is_reachable() {
            return Err(format!(
                "`{raw}`: that day never happens (day {} of month {}), so the schedule would \
                 never fire. {SYNTAX_HELP}",
                parts[2], parts[3]
            ));
        }
        Ok(cron)
    }

    /// One field → the set of values it matches. `names` is the alias table for the two fields
    /// that have one (month, day-of-week); empty elsewhere.
    fn field(
        spec: &str,
        min: u32,
        max: u32,
        name: &str,
        names: &[(&str, u32)],
    ) -> std::result::Result<u64, String> {
        let mut mask = 0u64;
        for item in spec.split(',') {
            let item = item.trim();
            if item.is_empty() {
                return Err(format!(
                    "{name} `{spec}`: an empty item in the list. {SYNTAX_HELP}"
                ));
            }
            let (range, step) = match item.split_once('/') {
                Some((range, step)) => {
                    let n: u32 = step.trim().parse().map_err(|_| {
                        format!("{name} `{item}`: the step after `/` must be a whole number. {SYNTAX_HELP}")
                    })?;
                    if n == 0 {
                        return Err(format!(
                            "{name} `{item}`: a step of 0 matches nothing. {SYNTAX_HELP}"
                        ));
                    }
                    (range.trim(), n)
                }
                None => (item, 1),
            };
            let (lo, hi) = if range == "*" {
                (min, max)
            } else if let Some((from, to)) = range.split_once('-') {
                let (from, to) = (
                    value(from, min, max, name, names)?,
                    value(to, min, max, name, names)?,
                );
                if from > to {
                    return Err(format!(
                        "{name} `{item}`: the range runs backwards ({from} is after {to}). {SYNTAX_HELP}"
                    ));
                }
                (from, to)
            } else {
                let v = value(range, min, max, name, names)?;
                // `a/N` is `a` through the end of the field, every N — the crontab reading.
                if step == 1 {
                    (v, v)
                } else {
                    (v, max)
                }
            };
            let mut v = lo;
            while v <= hi {
                mask |= bit(v);
                v += step;
            }
        }
        Ok(mask)
    }

    fn value(
        token: &str,
        min: u32,
        max: u32,
        name: &str,
        names: &[(&str, u32)],
    ) -> std::result::Result<u32, String> {
        let token = token.trim();
        if let Some((_, v)) = names.iter().find(|(n, _)| n.eq_ignore_ascii_case(token)) {
            return Ok(*v);
        }
        let parsed: u32 = token.parse().map_err(|_| {
            format!("{name} `{token}`: expected a number {min}-{max}. {SYNTAX_HELP}")
        })?;
        if parsed < min || parsed > max {
            return Err(format!(
                "{name} `{token}`: out of range, it has to be {min}-{max}. {SYNTAX_HELP}"
            ));
        }
        Ok(parsed)
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

        // ── The grammar a person actually writes (hub#730) ────────────────────────────────────
        //
        // Before this, `1-5`, `1,15` and `MON` parsed to `None`, which the callers turned into
        // "armed and never fires". Refusing them at the gate is the floor; understanding them is
        // what anybody coming from crontab/Zapier/n8n expects the first day.

        #[test]
        fn a_range_fires_on_every_minute_of_the_range() {
            let mut at = "2026-06-13T10:00:30+00:00".to_string();
            let mut got = Vec::new();
            for _ in 0..5 {
                at = next_after("1-5 * * * *", &at).unwrap();
                got.push(at[11..16].to_string());
            }
            assert_eq!(got, ["10:01", "10:02", "10:03", "10:04", "10:05"]);
            // …and then jumps the hour instead of matching :06.
            let n = next_after("1-5 * * * *", &at).unwrap();
            assert!(n.starts_with("2026-06-13T11:01:00"), "got {n}");
        }

        #[test]
        fn a_list_fires_on_each_listed_value() {
            let a = next_after("1,15 * * * *", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(a.starts_with("2026-06-13T10:01:00"), "got {a}");
            let b = next_after("1,15 * * * *", &a).unwrap();
            assert!(b.starts_with("2026-06-13T10:15:00"), "got {b}");
            let c = next_after("1,15 * * * *", &b).unwrap();
            assert!(c.starts_with("2026-06-13T11:01:00"), "got {c}");
        }

        #[test]
        fn a_step_over_a_range_stays_inside_the_range() {
            let mut at = "2026-06-13T09:59:00+00:00".to_string();
            let mut got = Vec::new();
            for _ in 0..5 {
                at = next_after("0-30/10 * * * *", &at).unwrap();
                got.push(at[11..16].to_string());
            }
            assert_eq!(got, ["10:00", "10:10", "10:20", "10:30", "11:00"]);
        }

        #[test]
        fn day_and_month_names_are_understood() {
            // 2026-06-13 is a Saturday; the next Monday is the 15th.
            let n = next_after("0 9 * * MON", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-15T09:00:00"), "got {n}");
            // Case does not matter, and a range of names works too (Mon..Fri → Monday the 15th).
            let n = next_after("0 9 * * mon-fri", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-15T09:00:00"), "got {n}");
            let n = next_after("0 0 1 JAN *", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(n.starts_with("2027-01-01T00:00:00"), "got {n}");
        }

        #[test]
        fn sunday_is_both_zero_and_seven() {
            // 2026-06-13 Saturday → Sunday the 14th, whichever number the author wrote.
            for expr in ["0 9 * * 0", "0 9 * * 7", "0 9 * * SUN"] {
                let n = next_after(expr, "2026-06-13T10:00:00+00:00").unwrap();
                assert!(n.starts_with("2026-06-14T09:00:00"), "{expr} got {n}");
            }
        }

        #[test]
        fn day_of_month_and_day_of_week_are_ored_like_crontab() {
            // `0 9 1 * MON`: the 1st OR any Monday — crontab's rule when BOTH are restricted.
            // From Sat 2026-06-13: Monday the 15th comes before the 1st of July.
            let a = next_after("0 9 1 * MON", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(a.starts_with("2026-06-15T09:00:00"), "got {a}");
            // …and the 1st of July (a Wednesday) still fires, even though it is not a Monday.
            let b = next_after("0 9 1 * MON", "2026-06-30T10:00:00+00:00").unwrap();
            assert!(b.starts_with("2026-07-01T09:00:00"), "got {b}");
        }

        #[test]
        fn a_step_counts_from_the_start_of_the_field_range() {
            // Day-of-month starts at 1, so `*/5` is 1,6,11,… — the crontab meaning. (The old
            // parser did `day % 5`, i.e. 5,10,15…, which is a different calendar.)
            let n = next_after("0 0 */5 * *", "2026-06-02T00:00:00+00:00").unwrap();
            assert!(n.starts_with("2026-06-06T00:00:00"), "got {n}");
        }

        #[test]
        fn a_rare_date_further_than_a_year_away_is_still_found() {
            // 29 February only exists on a leap year: the old 366-day window returned `None`,
            // and `None` is exactly what the callers turned into "never" or "every tick".
            let n = next_after("0 0 29 2 *", "2026-06-13T10:00:00+00:00").unwrap();
            assert!(n.starts_with("2028-02-29T00:00:00"), "got {n}");
        }

        // ── What the engine refuses, and why it says so (hub#730) ─────────────────────────────

        #[test]
        fn every_shape_the_engine_cannot_run_is_refused_by_name() {
            for (expr, needle) in [
                ("esto no es un cron", "esto"),
                ("0 0 9 * * *", "5 fields"),
                ("* * *", "5 fields"),
                ("", "5 fields"),
                ("70 * * * *", "70"),
                ("0 25 * * *", "25"),
                ("0 9 * * FUNDAY", "FUNDAY"),
                ("0 9 * 13 *", "13"),
                ("*/0 * * * *", "step"),
                ("5-1 * * * *", "5-1"),
                ("1,,2 * * * *", "empty"),
                ("@reboot", "@reboot"),
                ("0 0 30 2 *", "never"),
                ("0 0 31 4 *", "never"),
            ] {
                let err = parse(expr).expect_err("`{expr}` is not runnable and must be refused");
                assert!(
                    err.contains(needle),
                    "`{expr}`: the message has to say WHAT is wrong; expected `{needle}` in `{err}`"
                );
                assert!(
                    next_after(expr, "2026-06-13T10:00:00+00:00").is_none(),
                    "{expr}"
                );
            }
        }

        #[test]
        fn the_help_text_lists_what_is_accepted() {
            // The message a person reads is the whole fix for hub#730: it has to be actionable.
            for shape in ["*/N", "a-b", "a,b", "@daily", "MON"] {
                assert!(
                    SYNTAX_HELP.contains(shape),
                    "`{shape}` missing from {SYNTAX_HELP}"
                );
            }
        }

        // ── The business clock (hub#731) ──────────────────────────────────────────────────────

        const MADRID: chrono_tz::Tz = chrono_tz::Europe::Madrid;

        #[test]
        fn nine_in_the_morning_is_nine_on_the_business_clock() {
            // Summer (CEST, +02:00): 09:00 in the shop is 07:00 UTC.
            let n = next_after_in_tz("0 9 * * *", "2026-08-10T00:00:00+00:00", MADRID).unwrap();
            assert_eq!(n, "2026-08-10T07:00:00+00:00");
            // Winter (CET, +01:00): the SAME expression is 08:00 UTC. Nobody edited the flow.
            let n = next_after_in_tz("0 9 * * *", "2026-01-10T00:00:00+00:00", MADRID).unwrap();
            assert_eq!(n, "2026-01-10T08:00:00+00:00");
        }

        #[test]
        fn the_stored_instant_is_always_utc() {
            // `next_run` is a TEXT column compared with `<=` in SQL: a `+02:00` string would sort
            // as if it were two hours later and the trigger would be claimed late (or early).
            let n = next_after_in_tz("0 21 * * *", "2026-08-10T00:00:00+00:00", MADRID).unwrap();
            assert!(n.ends_with("+00:00"), "got {n}");
            assert_eq!(n, "2026-08-10T19:00:00+00:00");
        }

        #[test]
        fn spring_forward_does_not_lose_the_run() {
            // 2026-03-29 Madrid: 02:00 CET → 03:00 CEST. Local 02:00 NEVER HAPPENS that day, and
            // a cash close at 02:00 that is simply skipped is a day of takings unaccounted for.
            // The rule: fire at the instant the clock jumps over it (01:00 UTC = 03:00 local).
            let n = next_after_in_tz("0 2 * * *", "2026-03-28T12:00:00+00:00", MADRID).unwrap();
            assert_eq!(n, "2026-03-29T01:00:00+00:00");
            // …once, not once per minute of the hour that does not exist.
            let n2 = next_after_in_tz("0 2 * * *", &n, MADRID).unwrap();
            assert_eq!(n2, "2026-03-30T00:00:00+00:00");
        }

        #[test]
        fn fall_back_does_not_run_it_twice() {
            // 2026-10-25 Madrid: 03:00 CEST → 02:00 CET. Local 02:00 HAPPENS TWICE (00:00 UTC and
            // 01:00 UTC). A cash close that runs twice books the day twice.
            let n = next_after_in_tz("0 2 * * *", "2026-10-24T12:00:00+00:00", MADRID).unwrap();
            assert_eq!(n, "2026-10-25T00:00:00+00:00", "the first 02:00 fires");
            let n2 = next_after_in_tz("0 2 * * *", &n, MADRID).unwrap();
            assert_eq!(
                n2, "2026-10-26T01:00:00+00:00",
                "the SECOND 02:00 (01:00 UTC) must be skipped; next is the following day"
            );
        }

        #[test]
        fn utc_is_still_utc_when_no_zone_is_given() {
            // `next_after` is what `_scheduled_tasks` calls, and its contract does not move.
            assert_eq!(
                next_after("0 9 * * *", "2026-08-10T00:00:00+00:00").unwrap(),
                "2026-08-10T09:00:00+00:00"
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::CommandDef;
    use crate::registry::{ModuleStatus, RegisteredCommand};
    use erplora_db::{
        testutil::{fresh_db, TestDb},
        PgAdapter,
    };

    fn cmd(module: &str, sql: &str) -> RegisteredCommand {
        RegisteredCommand {
            module_id: module.to_string(),
            def: CommandDef {
                permission: String::new(),
                reads: Vec::new(),
                transaction: true,
                sql: vec![sql.to_string()],
                emit: vec![],
                min_affected_rows: None,
                expect_rows: None,
                handler: None,
                ai: None,
                schema: None,
                expose_api: false,
                internal: false,
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

    async fn count(db: &PgAdapter, sql: &str) -> i64 {
        let r = db.query(sql, &Params::new()).await.unwrap();
        r.rows[0]["c"]
            .as_i64()
            .or_else(|| r.rows[0]["c"].as_f64().map(|f| f as i64))
            .unwrap_or(-1)
    }

    /// hub#131/#145: el `command` de una scheduled task puede ser interno (prefijo `_`, como
    /// `verifactu._check_certificate_expiry`) — la tarea la dispara el propio Hub sin usuario
    /// (§4.2), así que corre con `Origin::Internal` y el gate no la bloquea.
    #[tokio::test]
    async fn due_task_with_internal_command_runs_via_origin_internal() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        crate::outbox::ensure_tables(&db).await.unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("verifactu".into(), ModuleStatus::Active);
        reg.commands.insert(
            "verifactu._check_certificate_expiry".into(),
            cmd("verifactu", "INSERT INTO t (n) VALUES (1);"),
        );

        let mut p = Params::new();
        p.insert("module_id".into(), json!("verifactu"));
        p.insert("name".into(), json!("check_cert"));
        p.insert(
            "command".into(),
            json!("verifactu._check_certificate_expiry"),
        );
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
        assert_eq!(
            ran, 1,
            "el gate de origen NO bloquea una scheduled task interna"
        );
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1);
    }

    /// Una tarea vencida ejecuta su command y avanza `next_run` al futuro en la misma tx; un
    /// segundo barrido inmediato NO la vuelve a disparar (sin doble-disparo).
    #[tokio::test]
    async fn due_task_runs_once_and_reschedules() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        crate::outbox::ensure_tables(&db).await.unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        reg.commands
            .insert("m.tick".into(), cmd("m", "INSERT INTO t (n) VALUES (1);"));

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
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();
        let tasks = vec![task("tick", "m.tick", "*/5 * * * *", CatchUp::Collapse)];

        seed_module_tasks(&db, "m", &tasks).await.unwrap();
        let r = db
            .query(
                "SELECT next_run FROM _scheduled_tasks WHERE module_id='m' AND name='tick'",
                &Params::new(),
            )
            .await
            .unwrap();
        let first = r.rows[0]["next_run"].as_str().unwrap().to_string();

        // Forzamos un next_run "antiguo" como si la tarea llevara tiempo corriendo.
        let mut p = Params::new();
        p.insert("nr".into(), json!("2099-01-01T00:00:00+00:00"));
        db.execute(
            "UPDATE _scheduled_tasks SET next_run = :nr WHERE name='tick'",
            &p,
        )
        .await
        .unwrap();

        // Re-sembrar (reinstalación) NO debe pisar next_run.
        seed_module_tasks(&db, "m", &tasks).await.unwrap();
        let r = db
            .query(
                "SELECT next_run FROM _scheduled_tasks WHERE name='tick'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            r.rows[0]["next_run"].as_str().unwrap(),
            "2099-01-01T00:00:00+00:00"
        );
        assert_ne!(first, "2099-01-01T00:00:00+00:00");

        // Una tarea retirada del manifest se borra.
        seed_module_tasks(&db, "m", &[]).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _scheduled_tasks").await,
            0
        );
    }

    /// hub#731: **the module contract does NOT move.** A flow's cron is the business clock because
    /// the owner writes it; a `scheduled_tasks` cron is written by a module programmer in a
    /// manifest, months before anybody knows where the hub is, and it means UTC. Reinterpreting it
    /// would silently shift `verifactu.process_contingency` and every other task in production for
    /// no gain — the ones that exist are intervals (`*/5`, `*/15`), where a zone means nothing.
    #[tokio::test]
    async fn a_module_task_stays_on_utc_whatever_zone_the_business_is_in() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();
        db.execute_batch(
            "CREATE TABLE hub_settings (\
              hub_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, \
              updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
              PRIMARY KEY (hub_id, key));",
        )
        .await
        .unwrap();
        let mut updates = serde_json::Map::new();
        updates.insert("timezone".into(), json!("Asia/Kolkata"));
        crate::settings::set_many(&db, "hub-1", &updates, "hub_user:1", false)
            .await
            .unwrap();

        seed_module_tasks(
            &db,
            "m",
            &[task("nine", "m.nine", "0 9 * * *", CatchUp::Collapse)],
        )
        .await
        .unwrap();
        let r = db
            .query(
                "SELECT next_run FROM _scheduled_tasks WHERE name='nine'",
                &Params::new(),
            )
            .await
            .unwrap();
        let next = r.rows[0]["next_run"].as_str().unwrap();
        assert!(
            next.ends_with("T09:00:00+00:00"),
            "09:00 UTC, not 03:30: {next}"
        );
    }

    /// The opposite fallback of the flows one, and the more dangerous: `unwrap_or_else(|| now)`
    /// made an unrunnable cron **due on every tick**. A task the engine cannot schedule is left
    /// unscheduled and shouted about — never turned into a hot loop.
    #[tokio::test]
    async fn a_task_whose_cron_cannot_run_is_not_scheduled_for_right_now() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();
        seed_module_tasks(
            &db,
            "m",
            &[task("bad", "m.bad", "1-5 9 * * FUNDAY", CatchUp::Collapse)],
        )
        .await
        .unwrap();
        let r = db
            .query(
                "SELECT next_run FROM _scheduled_tasks WHERE name='bad'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert!(
            r.rows.is_empty() || r.rows[0]["next_run"].as_str().is_none(),
            "an unrunnable cron must not become a task that is due forever: {:?}",
            r.rows
        );
    }

    /// Catch-up en arranque: `collapse` ejecuta una sola vez el backlog; `skip` no ejecuta, solo
    /// reprograma.
    #[tokio::test]
    async fn boot_catch_up_collapse_vs_skip() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        crate::outbox::ensure_tables(&db).await.unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        reg.commands.insert(
            "m.collapse".into(),
            cmd("m", "INSERT INTO t (n) VALUES (1);"),
        );
        reg.commands
            .insert("m.skip".into(), cmd("m", "INSERT INTO t (n) VALUES (2);"));

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
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "collapse corrió una vez"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=2").await,
            0,
            "skip no corrió"
        );
        // Ambas quedan reprogramadas al futuro (no se vuelven a tomar).
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _scheduled_tasks WHERE next_run <= '2025-01-01'"
            )
            .await,
            0
        );
    }

    /// hub#570: con `start-first` hay dos runtimes del mismo hub contra la misma BD corriendo el
    /// scheduler a la vez. El reclamo atómico (`FOR UPDATE SKIP LOCKED` + lease) garantiza que una
    /// tarea reclamada por una instancia es **invisible** a la otra mientras se ejecuta, y que al
    /// resolvar queda reprogramada. Este test reproduce la carrera de forma determinista, en el
    /// eslabón que la decide — el claim:
    ///
    /// 1. La instancia A reclama la tarea vencida → devuelve la fila y la marca `claim_expires_at`
    ///    al futuro (leased). Aún no ha resuelto (`next_run` sigue vencido).
    /// 2. La instancia B reclama a continuación: su `WHERE` exige
    ///    `claim_expires_at IS NULL OR <= now`, así que la fila leased **no la ve** → `None`.
    ///
    /// Sin el lease (o su condición del `WHERE`), B vería la misma fila vencida y la reclamaría
    /// también → ambos ejecutarían el command. El test **falla** si se quita el lease del claim.
    #[tokio::test]
    async fn two_instances_do_not_double_fire_a_due_task() {
        let tdb = TestDb::new().await;
        let db_a = tdb.adapter().await;
        let db_b = tdb.adapter().await;
        ensure_tables(&db_a).await.unwrap();

        let mut p = Params::new();
        p.insert("module_id".into(), json!("m"));
        p.insert("name".into(), json!("tick"));
        p.insert("command".into(), json!("m.tick"));
        p.insert("cron".into(), json!("*/5 * * * *"));
        p.insert("next_run".into(), json!("2020-01-01T00:00:00+00:00"));
        db_a.execute(
            "INSERT INTO _scheduled_tasks (module_id, name, command, cron, payload, catch_up, next_run) \
             VALUES (:module_id, :name, :command, :cron, '{}', 'collapse', :next_run)",
            &p,
        )
        .await
        .unwrap();

        let now = "2026-01-01T00:00:00+00:00";

        // A reclama la tarea vencida → la gana (queda leased, aún sin resolver).
        let claimed_a = claim_next_due(&db_a, now).await.unwrap();
        assert!(claimed_a.is_some(), "A reclama la tarea vencida");
        assert_eq!(
            claimed_a.as_ref().unwrap()["name"].as_str(),
            Some("tick"),
            "A se llevó la tarea correcta"
        );

        // B reclama la misma tarea mientras A la tiene leased → no la ve (None). Sin lease, B la
        // vería vencida y la reclamaría de nuevo → doble ejecución al correr ambas su command.
        let claimed_b = claim_next_due(&db_b, now).await.unwrap();
        assert!(
            claimed_b.is_none(),
            "B no puede reclamar una tarea que A tiene leased"
        );

        // Mientras tanto, la fila sigue vencida (next_run no avanzó): A aún no ha resuelto. Esto
        // confirma que la invisibilidad para B viene del LEASE, no de un next_run ya adelantado.
        let still_due = db_b
            .query(
                "SELECT next_run FROM _scheduled_tasks WHERE module_id='m' AND name='tick'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            still_due.rows[0]["next_run"].as_str(),
            Some("2020-01-01T00:00:00+00:00"),
            "next_run no avanza hasta resolver (la guarda es el lease, no el next_run)"
        );
    }
}
