//! Transactional Outbox del runtime: entrega **at-least-once** de eventos a sus listeners,
//! 100% asíncrona vía relay (ARQUITECTURA.md §4/§5.4). Decisiones del humano (2026-06-09):
//!  - **Entrega 100% asíncrona**: el command emisor solo PERSISTE el evento en `_event_outbox`
//!    DENTRO de su misma transacción (escritura atómica: si el command commitea, el evento
//!    queda sí o sí; si revierte, no hay evento). No ejecuta listeners inline.
//!  - **Idempotencia a nivel runtime** vía `_event_delivery (event_id, listener_command)`: el
//!    relay marca cada entrega DENTRO de la transacción del listener, así que un listener nunca
//!    corre dos veces aunque el proceso se reinicie. Los módulos no necesitan ser idempotentes.
//!
//! El **relay** (bucle en `crates/server`) llama a [`process_once`] periódicamente: lee filas
//! `pending` vencidas, resuelve los listeners actuales y ejecuta cada uno con [`commands::execute_at`]
//! (sus efectos + el marcador de entrega + los eventos en cascada que emita van en UNA transacción).
//! Fallo → backoff exponencial; tras `MAX_ATTEMPTS` → `dead` (dead-letter). La notificación al WS
//! (UI en vivo) es inline y efímera (ver `events::notify_sink`); la entrega DURABLE es esta.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::commands::{self, MAX_EVENT_DEPTH};
use crate::errors::{Result, RuntimeError};
use crate::host_notify::{self, NotifyIntent};
use crate::registry::{new_id, now_rfc3339, Registry, RequestContext};

/// Reintentos antes de mandar la fila a dead-letter (`status='dead'`).
pub const MAX_ATTEMPTS: i64 = 8;

/// Sufijo convencional de los eventos que el **listener-host** de `host.notify` consume (ADR-0012):
/// un command de módulo emite `<algo>.reminder.due` con la intención `{channel,to,template,vars}`.
pub const REMINDER_DUE_SUFFIX: &str = ".reminder.due";

/// Nombre del listener sintético del host en `_event_delivery` (idempotencia del envío externo).
/// No es un command de módulo: lo entrega el runtime vía el transporte de notificación.
pub const HOST_NOTIFY_LISTENER: &str = "host.notify";

/// Tamaño de lote por ciclo del relay (mantiene el lock del runtime acotado).
const BATCH: i64 = 50;

/// Vigencia del reclamo de una fila del outbox, en segundos. Si el proceso muere a media entrega,
/// el lease expira y otra instancia reclama la fila en el siguiente barrido (orphan recovery).
/// Mismo valor que el scheduler (hub#570): las dos colas viven el mismo modelo `start-first`.
const LEASE_SECONDS: i64 = 300;

const ENSURE_TABLES: &str = "\
CREATE TABLE IF NOT EXISTS _event_outbox (\
  id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, user_id TEXT NOT NULL, \
  permissions TEXT NOT NULL, event_name TEXT NOT NULL, payload TEXT NOT NULL, \
  depth INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', \
  attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL, \
  last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, delivered_at TEXT, \
  module_id TEXT NOT NULL DEFAULT '', claim_expires_at TEXT, \
  discarded_at TEXT, discarded_by TEXT);\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS module_id TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS claim_expires_at TEXT;\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS discarded_at TEXT;\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS discarded_by TEXT;\
CREATE INDEX IF NOT EXISTS ix_outbox_due ON _event_outbox (status, next_attempt_at);\
CREATE TABLE IF NOT EXISTS _event_delivery (\
  event_id TEXT NOT NULL, listener_command TEXT NOT NULL, delivered_at TEXT NOT NULL, \
  PRIMARY KEY (event_id, listener_command));";

/// Crea las tablas de sistema del outbox (idempotente), como `migrations::ensure_table`.
pub async fn ensure_tables(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_TABLES).await?;
    Ok(())
}

/// Construye el `INSERT` de una fila de outbox para un evento emitido por un command.
/// Se añade a la MISMA transacción que el SQL del command (escritura atómica). Guarda el
/// contexto (hub_id/user_id/permissions) para que el relay reconstruya el `RequestContext`
/// exacto del emisor — preserva la semántica de permisos del modelo síncrono.
///
/// `module_id` = **módulo emisor**. Se persiste porque el relay necesita saber a quién exigirle la
/// capability al ejercer un primitivo de host (`*.reminder.due` → `host.notify`): sin atribución,
/// el envío externo se hacía "en nombre del hub" y cualquier módulo llegaba a él (hub#240).
pub(crate) fn insert_op(
    ctx: &RequestContext,
    module_id: &str,
    event: &str,
    payload: &Params,
    depth: u32,
) -> (String, Params) {
    let perms: Vec<&String> = ctx.permissions.iter().collect();
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(new_id()));
    p.insert("hub_id".into(), json!(ctx.hub_id));
    p.insert("user_id".into(), json!(ctx.user_id));
    p.insert("permissions".into(), json!(serde_json::to_string(&perms).unwrap_or_else(|_| "[]".into())));
    p.insert("event_name".into(), json!(event));
    p.insert("module_id".into(), json!(module_id));
    p.insert(
        "payload".into(),
        json!(serde_json::to_string(&Json::Object(payload.clone())).unwrap_or_else(|_| "{}".into())),
    );
    p.insert("depth".into(), json!(depth));
    p.insert("now".into(), json!(now));
    let sql = "INSERT INTO _event_outbox \
        (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, status, attempts, next_attempt_at, last_error, created_at) \
        VALUES (:id, :hub_id, :user_id, :permissions, :event_name, :module_id, :payload, :depth, 'pending', 0, :now, '', :now)";
    (sql.to_string(), p)
}

/// `INSERT` del marcador de entrega (event_id, listener). El relay lo añade a la transacción
/// del listener → si el listener commitea, la entrega queda registrada atómicamente.
fn delivery_op(event_id: &str, listener: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("event_id".into(), json!(event_id));
    p.insert("listener_command".into(), json!(listener));
    p.insert("delivered_at".into(), json!(now_rfc3339()));
    let sql = "INSERT INTO _event_delivery (event_id, listener_command, delivered_at) \
        VALUES (:event_id, :listener_command, :delivered_at)";
    (sql.to_string(), p)
}

/// Backoff exponencial (segundos), con tope de 1h: 2^attempts acotado.
fn backoff_seconds(attempts: i64) -> i64 {
    (1i64 << attempts.clamp(0, 12)).min(3600)
}

/// Un ciclo del relay: procesa hasta [`BATCH`] eventos vencidos. Devuelve cuántas filas tomó
/// (0 = nada vencido). Las filas que fallan quedan diferidas (`next_attempt_at` futuro), así que
/// no se vuelven a tomar en este `now`; los eventos en cascada que generen las entregas con éxito
/// quedan `pending` y se toman en el siguiente ciclo.
///
/// **Cada fila es independiente (hub#142):** un error al procesar UNA fila (p.ej. un listener que
/// reventa, o un `UPDATE` del propio relay que falla) NUNCA aborta la entrega del resto del lote.
/// Antes este bucle propagaba el error con `?`, así que una sola fila "venenosa" —ordenada antes
/// por `created_at`— bloqueaba la entrega de todos los eventos posteriores del mismo ciclo. Como
/// esa fila se reintentaba ciclo tras ciclo con el mismo fallo, los eventos que llegaban después
/// se morían de hambre (starvation): `sale.voided` marcado `delivered` a medias y 25 min después
/// sin reverso de caja/stock. El síntoma era no determinista y dependía del orden/carrera del
/// relay por hub: en algunos hubs la fila venenosa no existía o llegaba al final del lote. Ahora
/// se captura el error por fila, se difiere/dead-lettera esa fila concretay el bucle sigue.
///
/// **Reclamo atómico (hub#593).** El modelo de actualización es `start-first` (ADR-0269): la
/// instancia nueva arranca mientras la vieja sigue sirviendo, así que durante el solape hay **dos**
/// runtimes del mismo hub contra la misma BD corriendo el relay del outbox. Antes este bucle hacía
/// un `SELECT … WHERE status='pending' AND next_attempt_at <= :now` **sin** `FOR UPDATE SKIP
/// LOCKED`: las dos instancias leían la misma fila vencida y la entregaban las dos. Ahora cada
/// vuelta **reclama** una fila con `UPDATE … (SELECT … FOR UPDATE SKIP LOCKED) … RETURNING` que la
/// marca en vuelo (`claim_expires_at`) — mismo patrón que el scheduler (`claim_next_due`) y la
/// cola de impresión (`print_queue::claim_next`). Si el proceso muere a media entrega, el lease
/// expira y otra instancia reclama la fila (orphan recovery).
pub async fn process_once(db: &dyn DatabaseAdapter, registry: &Registry) -> Result<usize> {
    let now = now_rfc3339();
    let mut ran = 0usize;
    for _ in 0..BATCH {
        match claim_next_due(db, &now).await? {
            Some(row) => {
                // Aislar cada fila: un fallo aquí difiere/dead-lettera SOLO esta fila (en
                // `process_row`) y el resto del lote sigue entregándose. No propagamos el error al
                // bucle del server, que solo haría `eprintln!` y dejaría todo el lote sin procesar
                // este ciclo (hub#142).
                if let Err(e) = process_row(db, registry, &row).await {
                    // `process_row` ya intentó defer/dead; si hasta eso falla (p.ej. la BD se cayó),
                    // lo dejamos para el próximo ciclo del relay y seguimos con las filas sanas.
                    eprintln!("relay outbox: fila {}: {e}", row["id"].as_str().unwrap_or("?"));
                }
                ran += 1;
            }
            // Ninguna fila vencida y sin dueño: fin del barrido.
            None => break,
        }
    }
    Ok(ran)
}

/// Reclama **una** fila vencida de forma atómica y la devuelve. El `UPDATE` toma la fila con
/// `FOR UPDATE SKIP LOCKED` y le pone `claim_expires_at` al futuro, **en el mismo enunciado**: así
/// la fila deja de ser "reclamable" para cualquier otra instancia (la condición del `WHERE` exige
/// `status='pending' AND next_attempt_at <= :now AND (claim_expires_at IS NULL OR
/// claim_expires_at <= :now)`) antes de que esta la entregue. Es el espejo de
/// `scheduler::claim_next_due` (hub#570): dos instancias que compiten se llevan filas **distintas**.
///
/// El lease se limpia al resolver la fila: `mark_delivered`, `mark_dead` y `defer_or_dead`
/// pisarían `claim_expires_at` a NULL junto al cambio de estado (de modo que una fila diferida,
/// que sigue `pending`, vuelve a ser reclamable en cuanto venza su `next_attempt_at`).
async fn claim_next_due(db: &dyn DatabaseAdapter, now: &str) -> Result<Option<Json>> {
    let lease = (chrono::Utc::now() + chrono::Duration::seconds(LEASE_SECONDS)).to_rfc3339();
    let mut p = Params::new();
    p.insert("now".into(), json!(now));
    p.insert("lease".into(), json!(lease));
    let sql = "UPDATE _event_outbox SET claim_expires_at = :lease \
               WHERE id = ( \
                 SELECT id FROM _event_outbox \
                 WHERE status = 'pending' AND next_attempt_at <= :now \
                   AND (claim_expires_at IS NULL OR claim_expires_at <= :now) \
                 ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED) \
               RETURNING id, hub_id, user_id, permissions, event_name, module_id, payload, depth, attempts";
    let res = db.query(sql, &p).await?;
    Ok(res.rows.into_iter().next())
}

/// Procesa el relay hasta drenar todo lo vencido (incluida la cascada). Para tests y arranque.
/// Tope de iteraciones como red ante un ciclo patológico (la profundidad ya está acotada por
/// [`MAX_EVENT_DEPTH`], esto es solo defensa en profundidad).
pub async fn drain(db: &dyn DatabaseAdapter, registry: &Registry) -> Result<usize> {
    let mut total = 0usize;
    for _ in 0..10_000 {
        let n = process_once(db, registry).await?;
        if n == 0 {
            break;
        }
        total += n;
    }
    Ok(total)
}

/// Entrega un evento (una fila de outbox) a todos sus listeners activos, con idempotencia por
/// `_event_delivery`. Actualiza el estado de la fila (delivered / reintento / dead).
async fn process_row(db: &dyn DatabaseAdapter, registry: &Registry, row: &Json) -> Result<()> {
    let id = row["id"].as_str().unwrap_or_default().to_string();
    let depth = row["depth"].as_u64().unwrap_or(0) as u32;
    let attempts = row["attempts"].as_i64().unwrap_or(0);
    let event_name = row["event_name"].as_str().unwrap_or_default().to_string();

    // Guarda de bucle: una cascada que supere la profundidad máxima va a dead-letter.
    if depth > MAX_EVENT_DEPTH {
        return mark_dead(db, &id, "profundidad máxima de cascada superada").await;
    }

    let ctx = reconstruct_ctx(row);
    let payload = parse_payload(row);

    // Listeners actuales (solo módulos activos). Si no hay, la entrega es trivialmente completa.
    //
    // **Cada listener es independiente (hub#142):** antes, un listener que fallaba hacía
    // `return defer_or_dead(...)` → se saltaba a los demás listeners del MISMO evento. En el caso
    // real, si `cash_register._reverse_sale` reventaba, `inventory._restock_on_void` NUNCA corría
    // (ni ese ciclo ni hasta que el primero tuviera éxito en su reintento) → el evento aparecía
    // "sin llegar" a la mitad de los listeners. Ahora registramos el primer fallo, entregamos al
    // resto y, al final, diferimos/dead-letteramos la fila una sola vez. Los listeners que sí
    // entregaron dejan su marcador en `_event_delivery`, así que en el reintento solo corre el
    // que falló (idempotencia). El contrato at-least-once + idempotencia por listener se mantiene.
    let listeners = registry.listeners_for(&event_name);
    let mut first_err: Option<String> = None;
    for listener in &listeners {
        if delivery_exists(db, &id, listener).await? {
            continue; // ya entregado en un intento previo (idempotencia)
        }
        // Efectos del listener + sus eventos en cascada + el marcador de entrega → UNA transacción.
        let extra = [delivery_op(&id, listener)];
        // Origin::Internal (hub#131, hub#145): el relay es el propio runtime entregando un
        // listener de evento — nunca un caller externo — así que un listener `_`-prefijado o
        // `internal:true` DEBE ejecutar aquí igual que uno público.
        if let Err(e) = commands::execute_at(
            db,
            registry,
            listener,
            &payload,
            &ctx,
            depth,
            &extra,
            commands::Origin::Internal,
            // The relay is the runtime delivering to itself: there is no cashier and no manager,
            // so there is no approval to spend (hub#361).
            None,
        )
        .await
        {
            // Registras el fallo y SIGUES: los hermanos se entregan igual este ciclo. El difierido
            // de la fila (backoff/dead-letter) se hace una vez al final, con el primer error.
            if first_err.is_none() {
                first_err = Some(format!("{listener}: {e}"));
            }
        }
    }

    // ── Listener-host de `host.notify` (ADR-0012) ───────────────────────────────────────────
    // Un evento `*.reminder.due` además dispara el envío externo (email/sms/whatsapp) por el
    // transporte del runtime. Reusa la MISMA infra del outbox: idempotencia por `_event_delivery`
    // (listener sintético `host.notify`) y, si el transporte falla, reintento/backoff/dead-letter.
    if event_name.ends_with(REMINDER_DUE_SUFFIX) {
        let module_id = row["module_id"].as_str().unwrap_or_default().to_string();
        if let Err(e) = deliver_host_notify(db, registry, &id, &module_id, &ctx.hub_id, &payload).await
        {
            if first_err.is_none() {
                first_err = Some(format!("{HOST_NOTIFY_LISTENER}: {e}"));
            }
        }
    }

    // Si algún listener falló, la fila se difiere/dead-lettera (NO se marca entregada): el/los
    // listeners fallidos se reintentarán; los que sí se entregaron ya tienen su marcador.
    if let Some(err) = first_err {
        return defer_or_dead(db, &id, attempts, &err).await;
    }

    mark_delivered(db, &id).await
}

/// Entrega un evento `*.reminder.due` al transporte de `host.notify` (ADR-0012), con idempotencia
/// por `_event_delivery` (listener sintético [`HOST_NOTIFY_LISTENER`]). Sin transporte configurado
/// es no-op (la capacidad no está disponible en este host). El marcador de entrega se escribe SOLO
/// tras un envío con éxito → un fallo deja la fila para reintento (no marca entregado).
///
/// **Tres puertas antes de que salga nada del hub** (hub#240 — antes no había ninguna):
///  1. el módulo emisor tiene la capability `notify` **declarada y concedida**
///     ([`crate::capabilities::require`], default-deny);
///  2. el canal es uno de los que ese módulo **declara** en `capabilities.notify.channels`;
///  3. el destinatario **se resuelve desde datos del hub** — nunca una dirección libre del payload
///     ([`host_notify::assert_recipient_allowed`]).
async fn deliver_host_notify(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    event_id: &str,
    module_id: &str,
    hub_id: &str,
    payload: &Params,
) -> Result<()> {
    let Some(transport) = &registry.notify_transport else {
        return Ok(()); // capacidad no disponible: no se envía nada (ni se reintenta).
    };
    if delivery_exists(db, event_id, HOST_NOTIFY_LISTENER).await? {
        return Ok(()); // ya enviado en un intento previo (idempotencia)
    }
    // Puerta 1 — capability del MÓDULO emisor (no del hub): sin `notify` concedida, no hay envío.
    // Sin `module_id` (filas anteriores a la atribución) tampoco: no se puede autorizar a nadie.
    if module_id.trim().is_empty() {
        return Err(RuntimeError::Notify(
            "evento de notificación sin módulo emisor atribuido: no se puede comprobar la \
             capability `notify` → no se envía"
                .to_string(),
        ));
    }
    crate::capabilities::require(
        db,
        registry,
        module_id,
        hub_id,
        crate::manifest::CapabilityKind::Notify,
    )
    .await?;

    let intent = NotifyIntent::from_event_payload(payload)?;
    // Puerta 2 — el canal tiene que estar declarado por el módulo emisor.
    host_notify::assert_channel_declared(registry, module_id, intent.channel)?;
    // Puerta 3 — el destinatario sale de los datos del hub, no del payload del handler.
    host_notify::assert_recipient_allowed(db, hub_id, &intent).await?;

    // ¿WhatsApp premium de ERPlora? → proxy Cloud con cuota; si no, secreto local del tenant.
    let premium = !registry.premium_whatsapp_modules.is_empty();
    let routing = host_notify::route_channel(intent.channel, premium);
    transport.send(&intent, routing).await?;
    // Envío con éxito → marca la entrega (idempotencia ante un reinicio entre send y mark).
    let (sql, p) = delivery_op(event_id, HOST_NOTIFY_LISTENER);
    db.execute(&sql, &p).await?;
    Ok(())
}

fn reconstruct_ctx(row: &Json) -> RequestContext {
    let hub_id = row["hub_id"].as_str().unwrap_or_default().to_string();
    let user_id = row["user_id"].as_str().unwrap_or_default().to_string();
    let perms: Vec<String> = row["permissions"]
        .as_str()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_default();
    RequestContext::new(hub_id, user_id, perms)
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

async fn delivery_exists(db: &dyn DatabaseAdapter, event_id: &str, listener: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("event_id".into(), json!(event_id));
    p.insert("listener_command".into(), json!(listener));
    let res = db
        .query(
            "SELECT 1 AS ok FROM _event_delivery WHERE event_id = :event_id AND listener_command = :listener_command",
            &p,
        )
        .await?;
    Ok(!res.rows.is_empty())
}

async fn mark_delivered(db: &dyn DatabaseAdapter, id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _event_outbox SET status = 'delivered', delivered_at = :now, claim_expires_at = NULL WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

async fn mark_dead(db: &dyn DatabaseAdapter, id: &str, err: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("err".into(), json!(err));
    db.execute(
        "UPDATE _event_outbox SET status = 'dead', last_error = :err, claim_expires_at = NULL WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

/// Reintento: incrementa `attempts`, reprograma con backoff; si supera `MAX_ATTEMPTS` → dead.
/// Limpia el lease (`claim_expires_at = NULL`) para que la fila diferida —que sigue `pending`—
/// vuelva a ser reclamable en cuanto venza su `next_attempt_at`.
async fn defer_or_dead(db: &dyn DatabaseAdapter, id: &str, attempts: i64, err: &str) -> Result<()> {
    let next = attempts + 1;
    if next >= MAX_ATTEMPTS {
        return mark_dead(db, id, err).await;
    }
    let next_at = (chrono::Utc::now() + chrono::Duration::seconds(backoff_seconds(next))).to_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("attempts".into(), json!(next));
    p.insert("next_at".into(), json!(next_at));
    p.insert("err".into(), json!(err));
    db.execute(
        "UPDATE _event_outbox SET attempts = :attempts, next_attempt_at = :next_at, last_error = :err, claim_expires_at = NULL WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

// ─────────────────────── Operable dead-letter (hub#660 — ADR-0127 phase 2) ───────────────────────
//
// `dead` used to be the end of the line: after `MAX_ATTEMPTS` the row stopped moving and the only
// window onto it was `GET /api/system`, which shows 50 rows without their payload. An event that
// died for a fixable reason — a listener demanding a permission the emitter did not carry, a module
// that was deactivated mid-flight — was lost work nobody could see, replay or close.
//
// The three gestures below are the whole of it, and they are deliberately small: LIST what died,
// RETRY one back onto the relay, DISCARD one for good. `discard` never DELETEs — the row is the
// only evidence the event ever existed, so it is kept and stamped with who closed it.

/// Terminal status of a row that burnt [`MAX_ATTEMPTS`] (dead-letter).
pub const STATUS_DEAD: &str = "dead";

/// Status of a dead-letter an admin closed by hand: it will never be delivered, and the relay —
/// which only ever claims `pending` — cannot pick it up again. The row **is kept**, auditable.
pub const STATUS_DISCARDED: &str = "discarded";

/// Hard cap on how many dead-letters one listing returns (the payloads make the rows heavy).
pub const MAX_DEAD_PAGE: i64 = 200;

/// One dead-letter, with everything an operator needs to decide between retry and discard.
#[derive(Debug, Clone, serde::Serialize)]
pub struct DeadEvent {
    pub id: String,
    pub event_name: String,
    /// The **emitting** module (attribution): who produced the event, not who refused it.
    pub module_id: String,
    /// The user whose context the emitter ran with — the cashier behind a structural dead-letter.
    pub user_id: String,
    /// The payload, parsed so it can be inspected. Unparseable stored text comes back as a string
    /// rather than being hidden: what is in the row is what the operator gets to see.
    pub payload: Json,
    pub last_error: String,
    pub attempts: i64,
    pub depth: i64,
    pub created_at: String,
}

/// Dead-letters of this hub, newest first. `limit` is clamped to [`MAX_DEAD_PAGE`].
pub async fn list_dead(db: &dyn DatabaseAdapter, hub_id: &str, limit: i64) -> Result<Vec<DeadEvent>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    p.insert("lim".into(), json!(limit.clamp(1, MAX_DEAD_PAGE)));
    let res = db
        .query(
            "SELECT id, event_name, module_id, user_id, payload, last_error, attempts, depth, created_at \
             FROM _event_outbox WHERE hub_id = :hub_id AND status = :status \
             ORDER BY created_at DESC LIMIT :lim",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(dead_event).collect())
}

fn dead_event(row: &Json) -> DeadEvent {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    let n = |k: &str| row[k].as_i64().or_else(|| row[k].as_f64().map(|f| f as i64)).unwrap_or(0);
    let raw = s("payload");
    DeadEvent {
        id: s("id"),
        event_name: s("event_name"),
        module_id: s("module_id"),
        user_id: s("user_id"),
        payload: serde_json::from_str(&raw).unwrap_or(Json::String(raw)),
        last_error: s("last_error"),
        attempts: n("attempts"),
        depth: n("depth"),
        created_at: s("created_at"),
    }
}

/// Puts a dead-letter back in front of the relay: `pending`, attempts reset, due now, lease
/// cleared. `false` if there is no dead-letter with that id in this hub.
///
/// Only a `dead` row is replayable. A `delivered` one is not an operator gesture (the delivery
/// markers in `_event_delivery` already make it a no-op), and a `pending` one is the relay's.
///
/// Resetting `attempts` to 0 is what makes the retry meaningful: the row gets the full budget of
/// [`MAX_ATTEMPTS`] again, so a transient cause gets its backoff ladder back instead of dying on
/// the first stumble. If the cause is still there, it simply dies again — and is listed again.
pub async fn retry(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    p.insert("now".into(), json!(now_rfc3339()));
    let res = db
        .execute(
            "UPDATE _event_outbox SET status = 'pending', attempts = 0, next_attempt_at = :now, \
             last_error = '', claim_expires_at = NULL \
             WHERE id = :id AND hub_id = :hub_id AND status = :status",
            &p,
        )
        .await?;
    Ok(res.affected > 0)
}

/// Closes a dead-letter for good: status [`STATUS_DISCARDED`] + who and when. `false` if there is
/// no dead-letter with that id in this hub.
///
/// **The row is CONSERVED — never `DELETE`.** It is the only record that the event existed, and a
/// discard is a decision somebody made; both have to survive it. The relay cannot take it again
/// because [`claim_next_due`] only ever claims `pending`.
///
/// `discarded_by` is the identity the HTTP layer resolved from the session (`hub_user:<id>`), never
/// something the caller sent in the body.
pub async fn discard(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    discarded_by: &str,
) -> Result<bool> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    p.insert("discarded".into(), json!(STATUS_DISCARDED));
    p.insert("by".into(), json!(discarded_by));
    p.insert("now".into(), json!(now_rfc3339()));
    let res = db
        .execute(
            "UPDATE _event_outbox SET status = :discarded, discarded_at = :now, discarded_by = :by, \
             claim_expires_at = NULL \
             WHERE id = :id AND hub_id = :hub_id AND status = :status",
            &p,
        )
        .await?;
    Ok(res.affected > 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::elevation::Grants;
    use crate::manifest::CommandDef;
    use crate::registry::{ModuleStatus, RegisteredCommand};
    use erplora_db::{testutil::fresh_db, PgAdapter};

    fn cmd(module: &str, sql: &str, emit: Vec<String>) -> RegisteredCommand {
        RegisteredCommand {
            module_id: module.to_string(),
            def: CommandDef {
                permission: String::new(),
                reads: Vec::new(),
                transaction: true,
                sql: vec![sql.to_string()],
                emit,
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

    async fn count(db: &PgAdapter, sql: &str) -> i64 {
        let r = db.query(sql, &Params::new()).await.unwrap();
        r.rows[0]["c"].as_i64().or_else(|| r.rows[0]["c"].as_f64().map(|f| f as i64)).unwrap_or(-1)
    }

    /// El command emisor NO corre el listener inline (entrega asíncrona); el relay lo entrega
    /// exactamente una vez y es idempotente al re-procesar (marcador `_event_delivery`).
    #[tokio::test]
    async fn outbox_async_delivery_is_exactly_once() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        ensure_tables(&db).await.unwrap();

        // Módulo "m" activo: "m.fire" emite "e"; "m.append" (listener de "e") inserta n=1.
        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        reg.commands.insert("m.append".into(), cmd("m", "INSERT INTO t (n) VALUES (1);", vec![]));
        reg.commands
            .insert("m.fire".into(), cmd("m", "INSERT INTO t (n) VALUES (99);", vec!["e".into()]));
        reg.listeners.insert("e".into(), vec!["m.append".into()]);

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);

        // Emisor: inserta su fila (99) + persiste el evento en el outbox, pero NO corre el listener.
        crate::commands::execute(&db, &reg, "m.fire", &Params::new(), &ctx, &Grants::new()).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 0, "listener no inline");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending'").await,
            1,
            "evento pendiente en outbox"
        );

        // Relay: el listener corre una vez; el evento queda 'delivered'.
        drain(&db, &reg).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1);
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'").await,
            1
        );

        // Idempotencia: re-drenar no re-ejecuta el listener.
        drain(&db, &reg).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1, "idempotente");
    }

    /// hub#131/#145: un listener marcado INTERNO por convención (último segmento `_`, estilo real
    /// `cash_register._reverse_sale`) SE ENTREGA con normalidad por el relay — el gate de origen
    /// (hub#131/#145) solo bloquea el camino EXTERNO (`Runtime::execute_command`); el relay del
    /// Outbox es el propio runtime, así que invoca con `Origin::Internal` y no se ve afectado.
    #[tokio::test]
    async fn relay_delivers_to_an_underscore_prefixed_internal_listener() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        ensure_tables(&db).await.unwrap();

        // "sales.void" emite "sale.voided"; "cash_register._reverse_sale" (interno, sin
        // `expose_api`) es su listener, como en el caso real (void_reversal_e2e.rs).
        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.status.insert("cash_register".into(), ModuleStatus::Active);
        reg.commands.insert(
            "cash_register._reverse_sale".into(),
            cmd("cash_register", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "sales.void".into(),
            cmd("sales", "INSERT INTO t (n) VALUES (99);", vec!["sale.voided".into()]),
        );
        reg.listeners.insert("sale.voided".into(), vec!["cash_register._reverse_sale".into()]);

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "sales.void", &Params::new(), &ctx, &Grants::new()).await.unwrap();

        drain(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "el listener interno `_reverse_sale` SÍ corre entregado por el relay (Origin::Internal)"
        );
    }

    /// Base de un hub con las tablas de sistema (grants de capability, settings, usuarios) +
    /// el outbox. Necesaria desde hub#240: `host.notify` consulta grants y ajustes del hub.
    async fn db_for_notify() -> PgAdapter {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        ensure_tables(&db).await.unwrap();
        db
    }

    /// Registry con el módulo `appt` instalado, su command emisor y (opcionalmente) la capability
    /// `notify` declarada con el canal `email`.
    fn registry_for_notify(declares_notify: bool) -> Registry {
        let manifest_json = if declares_notify {
            r#"{"id":"appt","name":"Appointments","version":"1.0.0",
                "capabilities":{"notify":{"channels":["email"]}}}"#
        } else {
            r#"{"id":"appt","name":"Appointments","version":"1.0.0"}"#
        };
        let mut reg = Registry::new();
        reg.status.insert("appt".into(), ModuleStatus::Active);
        reg.installed
            .push(serde_json::from_str(manifest_json).unwrap());
        reg.commands.insert(
            "appt.remind".into(),
            cmd("appt", "INSERT INTO t (n) VALUES (1);", vec!["appt.reminder.due".into()]),
        );
        reg
    }

    fn reminder_payload(to: &str) -> Params {
        let mut payload = Params::new();
        payload.insert("channel".into(), json!("email"));
        payload.insert("to".into(), json!(to));
        payload.insert("template".into(), json!("appointment_reminder"));
        payload.insert("vars".into(), json!({ "when": "10:00" }));
        payload
    }

    /// Autoriza a `appt` a notificar: concede la capability y mete al destinatario en la
    /// allowlist del hub (`hub_settings`).
    async fn authorize_notify(db: &PgAdapter, reg: &Registry, to: &str) {
        crate::capabilities::set_grant(db, reg, "h1", "appt", "notify", true, "hub_user:admin")
            .await
            .unwrap();
        let mut s = Params::new();
        s.insert(
            crate::host_notify::ALLOWED_RECIPIENTS_SETTING.into(),
            json!(to),
        );
        crate::settings::set_many(db, "h1", &s, "hub_user:admin", false)
            .await
            .unwrap();
    }

    /// Un evento `*.reminder.due` dispara el **listener-host** de `host.notify` (ADR-0012) por el
    /// relay: el transporte recibe la intención exactamente una vez y queda marcado en
    /// `_event_delivery` (idempotente al re-drenar). Es el camino que pasa por el Outbox.
    ///
    /// Desde hub#240 el camino exige las tres puertas: capability `notify` CONCEDIDA, canal
    /// declarado por el módulo y destinatario resuelto desde datos del hub.
    #[tokio::test]
    async fn reminder_due_event_delivers_to_notify_transport_once() {
        use crate::host_notify::{Channel, MockTransport, Routing};

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());
        authorize_notify(&db, &reg, "cliente@x.com").await;

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "appt.remind", &reminder_payload("cliente@x.com"), &ctx, &Grants::new())
            .await
            .unwrap();
        assert!(transport.sent().is_empty(), "no se envía inline; va por el relay");

        // Relay: entrega el evento → el transporte recibe la intención una vez.
        drain(&db, &reg).await.unwrap();
        let sent = transport.sent();
        assert_eq!(sent.len(), 1, "una entrega por el listener-host");
        assert_eq!(sent[0].0.channel, Channel::Email);
        assert_eq!(sent[0].0.to, "cliente@x.com");
        assert_eq!(sent[0].1, Routing::Tenant, "email = canal del tenant (secreto local)");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='host.notify'").await,
            1
        );

        // Idempotencia: re-drenar no re-envía.
        drain(&db, &reg).await.unwrap();
        assert_eq!(transport.sent().len(), 1, "idempotente (marcador host.notify)");
    }

    /// **hub#240 — el agujero.** Un módulo SIN la capability `notify` concedida emite su
    /// `*.reminder.due` igual (el evento existe), pero el listener-host **no envía nada**: el
    /// transporte no llega a ver la intención.
    #[tokio::test]
    async fn reminder_due_without_granted_notify_capability_sends_nothing() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        // Declara la capability, pero NADIE se la concede (default-deny).
        let mut reg = registry_for_notify(true);
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "appt.remind", &reminder_payload("cliente@x.com"), &ctx, &Grants::new())
            .await
            .unwrap();
        drain(&db, &reg).await.unwrap();

        assert!(
            transport.sent().is_empty(),
            "sin grant de `notify` no puede salir NADA del hub"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='host.notify'").await,
            0,
            "no hay entrega que marcar"
        );
    }

    /// **hub#240 — destinatario arbitrario.** Con la capability concedida, un destinatario que NO
    /// se resuelve desde datos del hub (ni allowlist ni usuario del hub) tampoco sale: es la vía
    /// de exfiltración que abría el `to` libre del payload.
    #[tokio::test]
    async fn reminder_due_to_an_unknown_recipient_is_not_sent() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());
        // Se autoriza al cliente legítimo… y el módulo intenta escribir a otro sitio.
        authorize_notify(&db, &reg, "cliente@x.com").await;

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "appt.remind",
            &reminder_payload("atacante@evil.com"),
            &ctx, &Grants::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();

        assert!(
            transport.sent().is_empty(),
            "el destinatario tiene que resolverse desde datos del hub"
        );
    }

    /// Un transporte que falla deja el evento `*.reminder.due` para reintento (backoff) y, tras
    /// `MAX_ATTEMPTS`, lo manda a dead-letter — reusa la misma máquina del Outbox (sin código nuevo).
    #[tokio::test]
    async fn failing_notify_transport_retries_then_dead_letters() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        // Módulo autorizado de verdad (capability concedida + destinatario del hub): lo que falla
        // aquí es el TRANSPORTE, no una de las puertas de seguridad.
        let mut reg = registry_for_notify(true);
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::failing()));
        authorize_notify(&db, &reg, "cliente@x.com").await;

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "appt.remind", &reminder_payload("cliente@x.com"), &ctx, &Grants::new())
            .await
            .unwrap();

        // Primer ciclo: el envío falla → la fila se difiere (sigue 'pending', attempts=1, no 'dead').
        process_once(&db, &reg).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending'").await, 1);
        assert_eq!(count(&db, "SELECT attempts AS c FROM _event_outbox").await, 1, "1 intento fallido");

        // Simula que ya agotó los reintentos (sin esperar el backoff real): attempts justo por
        // debajo del tope + vencido. El siguiente fallo lo manda a dead-letter.
        let mut p = Params::new();
        p.insert("a".into(), json!(MAX_ATTEMPTS - 1));
        db.execute(
            "UPDATE _event_outbox SET attempts = :a, next_attempt_at = '2020-01-01T00:00:00+00:00'",
            &p,
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'").await, 1, "dead-letter");
    }

    /// **hub#142 — un listener que falla NO bloquea a sus hermanos.** Antes, `process_row`
    /// hacía `return defer_or_dead(...)` al primer fallo: si `cash_register._reverse_sale`
    /// reventaba, `inventory._restock_on_void` (otro listener del MISMO `sale.voided`) no corría
    /// ni ese ciclo ni hasta que el primero tuviera éxito en su reintento. Ahora cada listener es
    /// independiente: el que falla se difiere (backoff) y los demás se entregan igual.
    #[tokio::test]
    async fn one_failing_listener_does_not_block_sibling_listeners() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        ensure_tables(&db).await.unwrap();

        // "sales.void" emite "sale.voided"; dos listeners: "bad" (revienta: columna inexistente)
        // y "good" (inserta n=1). El orden del registro pone "bad" PRIMERO: si el bug siguiera
        // vivo, "good" nunca correría y n=1 nunca aparecería.
        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.status.insert("bad".into(), ModuleStatus::Active);
        reg.status.insert("good".into(), ModuleStatus::Active);
        // Listener que FALLA: referencia una columna que no existe → error de BD en execute_at.
        reg.commands.insert(
            "bad.listener".into(),
            cmd("bad", "INSERT INTO t (no_such_column) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "good.listener".into(),
            cmd("good", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "sales.void".into(),
            cmd("sales", "INSERT INTO t (n) VALUES (99);", vec!["sale.voided".into()]),
        );
        reg.listeners.insert(
            "sale.voided".into(),
            vec!["bad.listener".into(), "good.listener".into()],
        );

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "sales.void", &Params::new(), &ctx, &Grants::new()).await.unwrap();

        // Un solo ciclo del relay: "good.listener" se entrega AUNQUE "bad.listener" falla antes.
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "el listener bueno corre aunque su hermano falle (hub#142)"
        );
        // La entrega del bueno queda marcada (idempotente); la del malo, no.
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='good.listener'").await,
            1,
            "el listener bueno quedó marcado como entregado"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='bad.listener'").await,
            0,
            "el listener malo NO se marcó (falló) → se reintenta"
        );
        // La fila NO se marca 'delivered' (un listener falló): queda diferida para reintento.
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending'").await,
            1,
            "la fila se difiere (no delivered) porque un listener falló"
        );
        assert_eq!(
            count(&db, "SELECT attempts AS c FROM _event_outbox").await,
            1,
            "1 intento fallido registrado"
        );

        // Reintento: "bad.listener" vuelve a fallar, pero "good.listener" NO se re-ejecuta
        // (marcador de idempotencia). El contrato at-least-once + idempotencia por listener se mantiene.
        let mut p = Params::new();
        p.insert("a".into(), json!("2020-01-01T00:00:00+00:00"));
        db.execute("UPDATE _event_outbox SET next_attempt_at = :a", &p).await.unwrap();
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "reentrega no duplica el listener bueno (idempotente)"
        );
    }

    /// **hub#142 — una fila venenosa NO bloquea el resto del lote (batch starvation).** Antes,
    /// `process_once` propagaba el error de `process_row` con `?`: una fila que fallaba al
    /// procesarse (ordenada ANTES por `created_at`) abortaba la entrega de TODAS las filas
    /// posteriores del mismo ciclo. Como esa fila se reintentaba ciclo tras ciclo con el mismo
    /// fallo, los eventos que caían después en el lote morían de hambre → `sale.voided` "sin
    /// llegar". El síntoma era no determinista (dependía del orden/carrera del relay por hub).
    /// Ahora cada fila es independiente: la venenosa se difiere y las sanas se entregan igual.
    #[tokio::test]
    async fn one_failing_row_does_not_starve_later_rows_in_the_batch() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        ensure_tables(&db).await.unwrap();

        // "poison.fire" emite "poison.e" cuyo ÚNICO listener revienta (columna inexistente).
        // "ok.fire" emite "ok.e" cuyo listener inserta n=1. Disparamos "poison" ANTES para que su
        // fila quede ORDENADA PRIMERO por created_at → si el bug siguiera vivo, "ok.e" no se entregaría.
        let mut reg = Registry::new();
        for m in ["poison", "ok"] {
            reg.status.insert(m.into(), ModuleStatus::Active);
        }
        reg.commands.insert(
            "poison.listener".into(),
            cmd("poison", "INSERT INTO t (no_such_column) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "ok.listener".into(),
            cmd("ok", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "poison.fire".into(),
            cmd("poison", "INSERT INTO t (n) VALUES (99);", vec!["poison.e".into()]),
        );
        reg.commands.insert(
            "ok.fire".into(),
            cmd("ok", "INSERT INTO t (n) VALUES (99);", vec!["ok.e".into()]),
        );
        reg.listeners.insert("poison.e".into(), vec!["poison.listener".into()]);
        reg.listeners.insert("ok.e".into(), vec!["ok.listener".into()]);

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "poison.fire", &Params::new(), &ctx, &Grants::new()).await.unwrap();
        crate::commands::execute(&db, &reg, "ok.fire", &Params::new(), &ctx, &Grants::new()).await.unwrap();

        // Un solo ciclo del relay procesa AMBAS filas (BATCH=50). La venenosa falla y se difiere;
        // la sana se entrega igual. Sin el fix, "ok.listener" no correría (n=1 sería 0 aquí).
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "la fila sana se entrega aunque la venenosa (anterior en el lote) falle (hub#142)"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='ok.listener'").await,
            1,
            "la entrega de la fila sana queda marcada"
        );
        // La fila venenosa quedó diferida (no delivered ni muerta): pendiente de reintento.
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE event_name='poison.e' AND status='pending'").await,
            1,
            "la fila venenosa sigue pendiente (diferida para reintento)"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE event_name='ok.e' AND status='delivered'").await,
            1,
            "la fila sana quedó entregada"
        );
    }

    /// hub#593: with `start-first` (ADR-0269) two runtimes of the same hub race the relay against
    /// the same DB. The atomic claim (`FOR UPDATE SKIP LOCKED` + lease) guarantees that a row
    /// claimed by one instance is **invisible** to the other while it is being delivered. This
    /// test reproduces the race deterministically, at the link that decides it — the claim:
    ///
    /// 1. Instance A claims the due event → returns the row and stamps `claim_expires_at` into the
    ///    future (leased). It has not resolved yet (`status` is still `pending`).
    /// 2. Instance B claims right after: its `WHERE` requires
    ///    `claim_expires_at IS NULL OR <= now`, so the leased row is **invisible** → `None`.
    ///
    /// Without the lease (or its `WHERE` condition), B would see the same due row and claim it too
    /// → both would deliver the event. The test **fails** if the lease is removed from the claim.
    #[tokio::test]
    async fn two_instances_do_not_double_deliver_an_event() {
        use erplora_db::testutil::TestDb;

        let tdb = TestDb::new().await;
        let db_a = tdb.adapter().await;
        let db_b = tdb.adapter().await;
        ensure_tables(&db_a).await.unwrap();

        // One due event in the outbox.
        let mut p = Params::new();
        p.insert("id".into(), json!("evt-1"));
        p.insert("hub_id".into(), json!("h1"));
        p.insert("user_id".into(), json!("u1"));
        p.insert("permissions".into(), json!("[]"));
        p.insert("event_name".into(), json!("e"));
        p.insert("payload".into(), json!("{}"));
        p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
        db_a.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, payload, status, attempts, \
              next_attempt_at, last_error, created_at) \
             VALUES (:id, :hub_id, :user_id, :permissions, :event_name, '', :payload, 'pending', 0, \
                     :at, '', :at)",
            &p,
        )
        .await
        .unwrap();

        let now = "2026-01-01T00:00:00+00:00";

        // A claims the due event → it wins (leased, not yet resolved).
        let claimed_a = claim_next_due(&db_a, now).await.unwrap();
        assert!(claimed_a.is_some(), "A claims the due event");
        assert_eq!(
            claimed_a.as_ref().unwrap()["id"].as_str(),
            Some("evt-1"),
            "A took the right row"
        );

        // B claims the same row while A has it leased → it does not see it (None). Without the
        // lease, B would see it due and claim it again → double delivery once both run their relay.
        let claimed_b = claim_next_due(&db_b, now).await.unwrap();
        assert!(claimed_b.is_none(), "B cannot claim a row A has leased");

        // Meanwhile the row is still `pending` (A has not resolved): the invisibility for B comes
        // from the LEASE, not from a status already moved to `delivered`.
        let still_pending = db_b
            .query(
                "SELECT status FROM _event_outbox WHERE id='evt-1'",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(
            still_pending.rows[0]["status"].as_str(),
            Some("pending"),
            "status does not advance until delivery (the guard is the lease, not the status)"
        );
    }

    /// hub#593: an expired lease can be reclaimed. If a runtime died mid-delivery (or the process
    /// was killed), its `claim_expires_at` is in the past by the time another sweep runs, so the
    /// orphaned row is visible again and gets retried instead of being stuck forever.
    #[tokio::test]
    async fn an_expired_lease_can_be_reclaimed() {
        use erplora_db::testutil::TestDb;

        let tdb = TestDb::new().await;
        let db = tdb.adapter().await;
        ensure_tables(&db).await.unwrap();

        let mut p = Params::new();
        p.insert("id".into(), json!("evt-1"));
        p.insert("hub_id".into(), json!("h1"));
        p.insert("user_id".into(), json!("u1"));
        p.insert("permissions".into(), json!("[]"));
        p.insert("event_name".into(), json!("e"));
        p.insert("payload".into(), json!("{}"));
        p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
        p.insert("lease".into(), json!("2020-01-01T00:05:00+00:00"));
        db.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, payload, status, attempts, \
              next_attempt_at, last_error, created_at, claim_expires_at) \
             VALUES (:id, :hub_id, :user_id, :permissions, :event_name, '', :payload, 'pending', 0, \
                     :at, '', :at, :lease)",
            &p,
        )
        .await
        .unwrap();

        // `now` is past the lease: the row is reclaimable.
        let now = "2026-01-01T00:00:00+00:00";
        let claimed = claim_next_due(&db, now).await.unwrap();
        assert!(claimed.is_some(), "an expired lease is reclaimed (orphan recovery)");
        assert_eq!(claimed.as_ref().unwrap()["id"].as_str(), Some("evt-1"));
    }

    // ── Operable dead-letter (hub#660 — ADR-0127 phase 2 · ADR-0283 K6a) ───────────────────────

    /// A hub holding exactly one dead-letter. `m.fire` emits `e`, whose only listener `m.apply`
    /// explodes on every attempt, so the row burns [`MAX_ATTEMPTS`] and lands in `dead`.
    ///
    /// This is the shape of the STRUCTURAL dead-letters production already has: an employee closes
    /// a sale, the `verifactu.records.ingest_invoice` listener demands a manager permission the
    /// emitter's reconstructed context does not carry, and eight attempts later the event is dead
    /// with nobody able to see it, let alone replay it.
    async fn hub_with_a_dead_letter() -> (PgAdapter, Registry) {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        // Listener that always fails (unknown column) — from the relay's point of view a refused
        // listener and a broken one are the same thing: `execute_at` returns `Err`.
        reg.commands.insert(
            "m.apply".into(),
            cmd("m", "INSERT INTO t (no_such_column) VALUES (1);", vec![]),
        );
        reg.commands
            .insert("m.fire".into(), cmd("m", "INSERT INTO t (n) VALUES (99);", vec!["e".into()]));
        reg.listeners.insert("e".into(), vec!["m.apply".into()]);

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let mut payload = Params::new();
        payload.insert("invoice".into(), json!("F2-1"));
        crate::commands::execute(&db, &reg, "m.fire", &payload, &ctx, &Grants::new())
            .await
            .unwrap();

        // Skip the real backoff: leave the row one attempt short of the cap and already due, so a
        // single relay cycle sends it to dead-letter.
        let mut p = Params::new();
        p.insert("a".into(), json!(MAX_ATTEMPTS - 1));
        db.execute(
            "UPDATE _event_outbox SET attempts = :a, next_attempt_at = '2020-01-01T00:00:00+00:00'",
            &p,
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'").await,
            1,
            "fixture precondition: the event is dead-lettered"
        );
        (db, reg)
    }

    /// A dead-letter is VISIBLE with everything an operator needs to decide: which event, from
    /// which module, the payload it carried, why it died and how many attempts it burnt. Before
    /// hub#660 the only window was `GET /api/system`, which shows 50 rows with no payload at all.
    #[tokio::test]
    async fn dead_letters_are_listed_with_payload_error_and_attempts() {
        let (db, _reg) = hub_with_a_dead_letter().await;

        let dead = list_dead(&db, "h1", 50).await.unwrap();
        assert_eq!(dead.len(), 1, "the dead-letter is listed");
        let row = &dead[0];
        assert_eq!(row.event_name, "e");
        assert_eq!(row.module_id, "m", "the EMITTING module, for attribution");
        // `defer_or_dead` stops counting when it gives up: the attempt that kills the row goes to
        // `mark_dead`, which changes the status without bumping the counter. So a row that burnt
        // its whole budget reads `MAX_ATTEMPTS - 1` — the last attempt it survived to record.
        assert_eq!(row.attempts, MAX_ATTEMPTS - 1, "it burnt its whole budget");
        assert!(
            row.last_error.contains("m.apply"),
            "the error names the listener that refused: {}",
            row.last_error
        );
        assert_eq!(
            row.payload["invoice"], "F2-1",
            "the payload is INSPECTABLE, not just the event name"
        );
        assert!(!row.id.is_empty() && !row.created_at.is_empty());

        // Another hub's operator never sees it (tenancy).
        assert!(list_dead(&db, "other-hub", 50).await.unwrap().is_empty());
    }

    /// `retry` puts a dead-letter back in front of the relay: `pending`, attempts reset and due
    /// now. Once whatever refused it is fixed, the delivery completes for real — the effect the
    /// event was carrying finally lands.
    #[tokio::test]
    async fn retry_returns_a_dead_letter_to_the_relay_and_it_is_delivered() {
        let (db, mut reg) = hub_with_a_dead_letter().await;

        // The relay ignores a dead row, no matter how many cycles run.
        drain(&db, &reg).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 0);

        // The operator fixes the cause (here: the listener now works) and replays the event.
        reg.commands
            .insert("m.apply".into(), cmd("m", "INSERT INTO t (n) VALUES (1);", vec![]));
        assert!(retry(&db, "h1", &dead_id(&db).await).await.unwrap(), "the row was requeued");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending' AND attempts=0").await,
            1,
            "back to pending with a fresh attempt budget"
        );

        drain(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "the listener finally runs: the retry is a real delivery, not a status change"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'").await,
            1
        );

        // Only a dead-letter is replayable: replaying a delivered row is not an operator gesture.
        assert!(!retry(&db, "h1", &id_of(&db, "delivered").await).await.unwrap());
    }

    /// `discard` closes a dead-letter without deleting it: the row STAYS, stamped with who
    /// discarded it and when, and the relay never touches it again. Deleting would destroy the only
    /// record that the event existed at all — the audit trail is the point.
    #[tokio::test]
    async fn discard_keeps_the_row_auditable_and_the_relay_never_takes_it_again() {
        let (db, mut reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;

        assert!(discard(&db, "h1", &id, "hub_user:admin-1").await.unwrap());

        // The row is conserved, with its audit stamp.
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let rows = db
            .query(
                "SELECT status, discarded_by, discarded_at, payload, last_error \
                 FROM _event_outbox WHERE id = :id",
                &p,
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1, "the row is CONSERVED, never deleted");
        assert_eq!(rows[0]["status"].as_str(), Some(STATUS_DISCARDED));
        assert_eq!(rows[0]["discarded_by"].as_str(), Some("hub_user:admin-1"));
        assert!(rows[0]["discarded_at"].as_str().is_some_and(|s| !s.is_empty()));
        assert!(
            rows[0]["payload"].as_str().is_some_and(|s| s.contains("F2-1")),
            "the payload survives for inspection"
        );

        // The relay filters by `status='pending'`, so a discarded row is not even claimable —
        // not even after making it look due, and not even if its listener starts working again.
        db.execute(
            "UPDATE _event_outbox SET next_attempt_at = '2020-01-01T00:00:00+00:00', claim_expires_at = NULL",
            &Params::new(),
        )
        .await
        .unwrap();
        assert!(
            claim_next_due(&db, "2026-01-01T00:00:00+00:00").await.unwrap().is_none(),
            "the relay never claims a discarded row"
        );
        reg.commands
            .insert("m.apply".into(), cmd("m", "INSERT INTO t (n) VALUES (1);", vec![]));
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            0,
            "a discarded event is never delivered"
        );

        // And it drops off the operator's list: discarding is what makes the queue drainable.
        assert!(list_dead(&db, "h1", 50).await.unwrap().is_empty());
    }

    /// Neither gesture crosses hubs, and neither invents a row: an unknown id is simply `false`.
    #[tokio::test]
    async fn retry_and_discard_are_scoped_to_the_hub() {
        let (db, _reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;

        assert!(!retry(&db, "other-hub", &id).await.unwrap(), "another hub cannot replay it");
        assert!(!discard(&db, "other-hub", &id, "hub_user:x").await.unwrap());
        assert!(!retry(&db, "h1", "no-such-event").await.unwrap());
        assert!(!discard(&db, "h1", "no-such-event", "hub_user:x").await.unwrap());
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'").await,
            1,
            "the dead-letter is untouched"
        );
    }

    async fn dead_id(db: &PgAdapter) -> String {
        id_of(db, STATUS_DEAD).await
    }

    async fn id_of(db: &PgAdapter, status: &str) -> String {
        let mut p = Params::new();
        p.insert("s".into(), json!(status));
        db.query("SELECT id FROM _event_outbox WHERE status = :s", &p)
            .await
            .unwrap()
            .rows[0]["id"]
            .as_str()
            .unwrap()
            .to_string()
    }
}
