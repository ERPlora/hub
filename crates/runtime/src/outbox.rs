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
use crate::errors::Result;
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

const ENSURE_TABLES: &str = "\
CREATE TABLE IF NOT EXISTS _event_outbox (\
  id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, user_id TEXT NOT NULL, \
  permissions TEXT NOT NULL, event_name TEXT NOT NULL, payload TEXT NOT NULL, \
  depth INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', \
  attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL, \
  last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, delivered_at TEXT);\
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
pub(crate) fn insert_op(ctx: &RequestContext, event: &str, payload: &Params, depth: u32) -> (String, Params) {
    let perms: Vec<&String> = ctx.permissions.iter().collect();
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(new_id()));
    p.insert("hub_id".into(), json!(ctx.hub_id));
    p.insert("user_id".into(), json!(ctx.user_id));
    p.insert("permissions".into(), json!(serde_json::to_string(&perms).unwrap_or_else(|_| "[]".into())));
    p.insert("event_name".into(), json!(event));
    p.insert(
        "payload".into(),
        json!(serde_json::to_string(&Json::Object(payload.clone())).unwrap_or_else(|_| "{}".into())),
    );
    p.insert("depth".into(), json!(depth));
    p.insert("now".into(), json!(now));
    let sql = "INSERT INTO _event_outbox \
        (id, hub_id, user_id, permissions, event_name, payload, depth, status, attempts, next_attempt_at, last_error, created_at) \
        VALUES (:id, :hub_id, :user_id, :permissions, :event_name, :payload, :depth, 'pending', 0, :now, '', :now)";
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
pub async fn process_once(db: &dyn DatabaseAdapter, registry: &Registry) -> Result<usize> {
    let now = now_rfc3339();
    let mut q = Params::new();
    q.insert("now".into(), json!(now));
    q.insert("lim".into(), json!(BATCH));
    let due = db
        .query(
            "SELECT id, hub_id, user_id, permissions, event_name, payload, depth, attempts \
             FROM _event_outbox WHERE status = 'pending' AND next_attempt_at <= :now \
             ORDER BY created_at LIMIT :lim",
            &q,
        )
        .await?;

    let count = due.rows.len();
    for row in &due.rows {
        process_row(db, registry, row).await?;
    }
    Ok(count)
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
    let listeners = registry.listeners_for(&event_name);
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
        )
        .await
        {
            return defer_or_dead(db, &id, attempts, &format!("{listener}: {e}")).await;
        }
    }

    // ── Listener-host de `host.notify` (ADR-0012) ───────────────────────────────────────────
    // Un evento `*.reminder.due` además dispara el envío externo (email/sms/whatsapp) por el
    // transporte del runtime. Reusa la MISMA infra del outbox: idempotencia por `_event_delivery`
    // (listener sintético `host.notify`) y, si el transporte falla, reintento/backoff/dead-letter.
    if event_name.ends_with(REMINDER_DUE_SUFFIX) {
        if let Err(e) = deliver_host_notify(db, registry, &id, &payload).await {
            return defer_or_dead(db, &id, attempts, &format!("{HOST_NOTIFY_LISTENER}: {e}")).await;
        }
    }

    mark_delivered(db, &id).await
}

/// Entrega un evento `*.reminder.due` al transporte de `host.notify` (ADR-0012), con idempotencia
/// por `_event_delivery` (listener sintético [`HOST_NOTIFY_LISTENER`]). Sin transporte configurado
/// es no-op (la capacidad no está disponible en este host). El marcador de entrega se escribe SOLO
/// tras un envío con éxito → un fallo deja la fila para reintento (no marca entregado).
async fn deliver_host_notify(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    event_id: &str,
    payload: &Params,
) -> Result<()> {
    let Some(transport) = &registry.notify_transport else {
        return Ok(()); // capacidad no disponible: no se envía nada (ni se reintenta).
    };
    if delivery_exists(db, event_id, HOST_NOTIFY_LISTENER).await? {
        return Ok(()); // ya enviado en un intento previo (idempotencia)
    }
    let intent = NotifyIntent::from_event_payload(payload)?;
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
        "UPDATE _event_outbox SET status = 'delivered', delivered_at = :now WHERE id = :id",
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
        "UPDATE _event_outbox SET status = 'dead', last_error = :err WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

/// Reintento: incrementa `attempts`, reprograma con backoff; si supera `MAX_ATTEMPTS` → dead.
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
        "UPDATE _event_outbox SET attempts = :attempts, next_attempt_at = :next_at, last_error = :err WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
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
        crate::commands::execute(&db, &reg, "m.fire", &Params::new(), &ctx).await.unwrap();
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
        crate::commands::execute(&db, &reg, "sales.void", &Params::new(), &ctx).await.unwrap();

        drain(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "el listener interno `_reverse_sale` SÍ corre entregado por el relay (Origin::Internal)"
        );
    }

    /// Un evento `*.reminder.due` dispara el **listener-host** de `host.notify` (ADR-0012) por el
    /// relay: el transporte recibe la intención exactamente una vez y queda marcado en
    /// `_event_delivery` (idempotente al re-drenar). Es el camino que pasa por el Outbox.
    #[tokio::test]
    async fn reminder_due_event_delivers_to_notify_transport_once() {
        use crate::host_notify::{Channel, MockTransport, Routing};
        use serde_json::json;

        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        ensure_tables(&db).await.unwrap();

        // Módulo "appt" activo: "appt.remind" emite "appt.reminder.due" con la intención.
        let mut reg = Registry::new();
        reg.status.insert("appt".into(), ModuleStatus::Active);
        reg.commands.insert(
            "appt.remind".into(),
            cmd("appt", "INSERT INTO t (n) VALUES (1);", vec!["appt.reminder.due".into()]),
        );
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());

        // La intención viaja en el payload del command (que el outbox guarda como payload del evento).
        let mut payload = Params::new();
        payload.insert("channel".into(), json!("email"));
        payload.insert("to".into(), json!("cliente@x.com"));
        payload.insert("template".into(), json!("appointment_reminder"));
        payload.insert("vars".into(), json!({ "when": "10:00" }));

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "appt.remind", &payload, &ctx).await.unwrap();
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

    /// Un transporte que falla deja el evento `*.reminder.due` para reintento (backoff) y, tras
    /// `MAX_ATTEMPTS`, lo manda a dead-letter — reusa la misma máquina del Outbox (sin código nuevo).
    #[tokio::test]
    async fn failing_notify_transport_retries_then_dead_letters() {
        use crate::host_notify::MockTransport;
        use serde_json::json;

        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);").await.unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("appt".into(), ModuleStatus::Active);
        reg.commands.insert(
            "appt.remind".into(),
            cmd("appt", "INSERT INTO t (n) VALUES (1);", vec!["appt.reminder.due".into()]),
        );
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::failing()));

        let mut payload = Params::new();
        payload.insert("channel".into(), json!("sms"));
        payload.insert("to".into(), json!("+34600000000"));
        payload.insert("template".into(), json!("reminder"));

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "appt.remind", &payload, &ctx).await.unwrap();

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
}
