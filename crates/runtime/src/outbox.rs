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
use crate::permissions;
use crate::registry::{new_id, now_rfc3339, Registry, RequestContext};

/// Reintentos antes de mandar la fila a dead-letter (`status='dead'`).
pub const MAX_ATTEMPTS: i64 = 8;

/// Sufijo convencional de los eventos que el **listener-host** de `host.notify` consume (ADR-0012):
/// un command de módulo emite `<algo>.reminder.due` con la intención `{channel,to,template,vars}`.
pub const REMINDER_DUE_SUFFIX: &str = ".reminder.due";

/// Nombre del listener sintético del host en `_event_delivery` (idempotencia del envío externo).
/// No es un command de módulo: lo entrega el runtime vía el transporte de notificación.
pub const HOST_NOTIFY_LISTENER: &str = "host.notify";

/// Sufijo convencional de los eventos que el **listener-host** de `host.print` consume (hub#957,
/// decisión de Ioan del 2026-08-15): un command de módulo emite `<algo>.print.due` con la intención
/// `{jobId, role, documentType, document, format}` y el relay la encola en la cola de impresión del
/// hub (ADR-0196 §6).
///
/// El sufijo es **`.print.due`**, calcado del de arriba y por su misma razón: «due» es lo que un
/// evento del outbox significa en este hub —algo que toca hacer y que el relay se encarga de que
/// ocurra— y compartir la forma hace que el segundo listener-host se lea como lo que es, el gemelo
/// del primero, y no como un mecanismo aparte que hay que aprender.
pub const PRINT_DUE_SUFFIX: &str = ".print.due";

/// Nombre del listener sintético de impresión en `_event_delivery` (idempotencia del encolado).
/// Espejo de [`HOST_NOTIFY_LISTENER`]: tampoco es un command de módulo.
pub const HOST_PRINT_LISTENER: &str = "host.print";

/// El evento que encola un step `notify` de un flujo (hub#821). Lleva el sufijo de arriba a
/// propósito: es el MISMO camino de entrega que el de un módulo —transporte, reintentos, backoff,
/// dead-letter— y lo único que cambia es cómo se autorizó el destinatario.
pub const FLOW_NOTIFY_EVENT: &str = "flow.reminder.due";

/// **Why a row is terminal when the answer is not "it ran out of attempts"** (hub#827).
///
/// `_event_outbox.failure_kind` is `''` for every row the relay may try again — which is every row
/// there ever was until this: a failure was a failure, and the only question asked of one was how
/// many had come before it. A revoked authorisation is a different kind of no, and the column is
/// what lets the queue, the screen and the retry all say so without parsing `last_error`.
///
/// This one means: **do not retry, and do not offer to.** ⚠️ That is a property of THIS kind, not of
/// the column: since hub#1171 `failure_kind` says *why*, and whether a why can be retried is decided
/// by [`is_retryable`].
pub const FAILURE_RELEASE_REVOKED: &str = "flow.release_revoked";

/// **A listener the capability gate refused** (hub#1171). The module declares a host primitive
/// (ADR-0079) that nobody has granted, so `capabilities::enforce` turned its command away before it
/// ran — the case that left the fiscal chain dead while every screen said «Todo en orden».
///
/// Unlike [`FAILURE_RELEASE_REVOKED`] this one **is** retryable, and the distinction is the whole
/// reason the column stopped meaning «do not retry» ([`is_retryable`]): a withdrawn authorisation is
/// a decision that already happened, while an ungranted capability is a switch the owner has simply
/// not flipped yet. Flipping it is the remedy, and the row has to be there waiting when they do.
pub const FAILURE_CAPABILITY_DENIED: &str = "module.capability_denied";

/// **Can [`retry`] do anything with a row stamped like this?**
///
/// `failure_kind` used to answer two questions at once — *why* a row is terminal and *whether* to
/// offer the button — by being empty or not. That held while there was one kind, and stopped
/// holding the moment a classified failure had a remedy (hub#1171): a capability refusal needs its
/// code in the queue **and** its retry, so the two questions had to come apart. Retryability is now
/// derived here, in the one place the screen, [`retry`] and [`retry_all`] all read.
pub fn is_retryable(failure_kind: &str) -> bool {
    failure_kind.is_empty() || failure_kind == FAILURE_CAPABILITY_DENIED
}

/// The key that replaces the recipient in the payload of a row that can never be delivered — the
/// same word the run history already uses (`crate::flows::notify`), so an operator meets one
/// vocabulary and not two.
const RECIPIENT_REDACTED_KEY: &str = "recipient_redacted";

/// The recipient's key inside a `host.notify` intent.
const RECIPIENT_KEY: &str = "to";

/// Tamaño de lote por ciclo del relay (mantiene el lock del runtime acotado).
const BATCH: i64 = 50;

/// Vigencia del reclamo de una fila del outbox, en segundos. Si el proceso muere a media entrega,
/// el lease expira y otra instancia reclama la fila en el siguiente barrido (orphan recovery).
/// Mismo valor que el scheduler (hub#570): las dos colas viven el mismo modelo `start-first`.
const LEASE_SECONDS: i64 = 300;

/// The schema of the outbox, laid down idempotently at every boot.
///
/// New columns arrive here as `ALTER TABLE … ADD COLUMN IF NOT EXISTS` and **not** as a numbered
/// system migration. That is this table's own pattern (`module_id` in ADR-0168, `discarded_at/by`
/// in hub#660, `run_id`/`parent_event_id` in hub#666, `discard_reason` in hub#955) and it is
/// deliberate: these tables are created by the runtime before the migration engine runs at all — a
/// hub with zero modules still has an outbox — so their shape cannot depend on a numbered version.
/// It also keeps additive columns out of the way of the number races between parallel branches.
///
/// `ix_outbox_prune` backs the retention sweep (hub#699, `crate::retention`), which scans by
/// terminal age and not by `next_attempt_at`, so `ix_outbox_due` does not serve it. It is
/// **partial** over the two terminal statuses: a row is born `pending` and only enters this index
/// when it stops moving, so the relay's hot path pays nothing for it, and the sweep's repeated
/// bounded passes stop being a table scan each.
///
/// `ix_outbox_name` backs [`sample_payloads`] (hub#715), which reads the last few events of ONE
/// name to infer its shape. Without it that is a sequential scan of a table whose widest column is
/// the payload — ninety days of a busy till — to return five rows, every time an editor opens.
const ENSURE_TABLES: &str = "\
CREATE TABLE IF NOT EXISTS _event_outbox (\
  id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, user_id TEXT NOT NULL, \
  permissions TEXT NOT NULL, event_name TEXT NOT NULL, payload TEXT NOT NULL, \
  depth INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', \
  attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL, \
  last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, delivered_at TEXT, \
  module_id TEXT NOT NULL DEFAULT '', claim_expires_at TEXT, \
  discarded_at TEXT, discarded_by TEXT, discard_reason TEXT NOT NULL DEFAULT '', \
  run_id TEXT NOT NULL DEFAULT '', parent_event_id TEXT NOT NULL DEFAULT '', \
  client_instance TEXT NOT NULL DEFAULT '');\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS module_id TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS claim_expires_at TEXT;\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS discarded_at TEXT;\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS discarded_by TEXT;\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS discard_reason TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS run_id TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS parent_event_id TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS failure_kind TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_outbox ADD COLUMN IF NOT EXISTS client_instance TEXT NOT NULL DEFAULT '';\
CREATE INDEX IF NOT EXISTS ix_outbox_due ON _event_outbox (status, next_attempt_at);\
CREATE INDEX IF NOT EXISTS ix_outbox_run ON _event_outbox (hub_id, run_id) WHERE run_id <> '';\
CREATE INDEX IF NOT EXISTS ix_outbox_parent ON _event_outbox (hub_id, parent_event_id) \
  WHERE parent_event_id <> '';\
CREATE INDEX IF NOT EXISTS ix_outbox_prune \
  ON _event_outbox (hub_id, COALESCE(delivered_at, discarded_at, created_at)) \
  WHERE status IN ('delivered', 'discarded');\
CREATE INDEX IF NOT EXISTS ix_outbox_name ON _event_outbox (hub_id, event_name, created_at);\
CREATE TABLE IF NOT EXISTS _event_delivery (\
  event_id TEXT NOT NULL, listener_command TEXT NOT NULL, delivered_at TEXT NOT NULL, \
  hub_id TEXT NOT NULL, provider_message_id TEXT NOT NULL DEFAULT '', \
  step_id TEXT NOT NULL DEFAULT '', flow_id TEXT NOT NULL DEFAULT '', \
  PRIMARY KEY (event_id, listener_command));\
ALTER TABLE _event_delivery ADD COLUMN IF NOT EXISTS hub_id TEXT;\
ALTER TABLE _event_delivery ADD COLUMN IF NOT EXISTS provider_message_id TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_delivery ADD COLUMN IF NOT EXISTS step_id TEXT NOT NULL DEFAULT '';\
ALTER TABLE _event_delivery ADD COLUMN IF NOT EXISTS flow_id TEXT NOT NULL DEFAULT '';\
CREATE INDEX IF NOT EXISTS ix_event_delivery_hub ON _event_delivery (hub_id, event_id);\
CREATE INDEX IF NOT EXISTS ix_event_delivery_provider \
  ON _event_delivery (hub_id, provider_message_id) WHERE provider_message_id <> '';";

/// Crea las tablas de sistema del outbox (idempotente), como `migrations::ensure_table`.
pub async fn ensure_tables(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_TABLES).await?;
    Ok(())
}

/// Construye el `INSERT` de una fila de outbox para un evento emitido por un command.
/// Se añade a la MISMA transacción que el SQL del command (escritura atómica).
///
/// Guarda el contexto del emisor. `hub_id` y `user_id` los usa el relay para construir el contexto
/// del listener ([`listener_ctx`]): el tenant y **quién lo causó**, que es la atribución que acaba
/// en `created_by`. `permissions` es desde hub#686 **forense**, no autorización: queda como
/// registro de lo que el emisor podía hacer (útil en el dead-letter, hub#660), pero el listener ya
/// no corre con ello — corre con la autoridad de su propio módulo.
///
/// `module_id` = **módulo emisor**. Se persiste porque el relay necesita saber a quién exigirle la
/// capability al ejercer un primitivo de host (`*.reminder.due` → `host.notify`): sin atribución,
/// el envío externo se hacía "en nombre del hub" y cualquier módulo llegaba a él (hub#240).
///
/// `run_id` y `parent_event_id` son la **correlación** (hub#666), y salen del contexto — jamás del
/// payload. Un evento emitido dentro de un run queda sellado con ese run, y todo evento en cascada
/// nombra al evento cuya entrega lo provocó. Sin eso la cadena venta → run → command → evento hijo
/// solo se podía adivinar por marca de tiempo, que con dos ventas por segundo no es una respuesta.
///
/// `client_instance` is the shell tab that sent the request (hub#1980), kept so the listener that
/// runs one hop later still says it on the live frame (hub#2029, [`listener_ctx`]): a till fires the
/// order, `kitchen` makes the ticket in a listener, and only the till that fired it should print it.
///
/// `dedup_key` (hub#1076) is the manifest-declared field NAME (`emit[].dedup_key`, e.g.
/// `"wa_message_id"`), not a value — this function is what resolves it against `payload`. When it
/// resolves to a scalar, the row's `id` is derived from it — scoped to the hub, the module and the
/// event — instead of a fresh [`new_id`], and the `INSERT` grows an `ON CONFLICT (id) DO NOTHING`:
/// a repeated emission with the same key is absorbed, same mechanism as
/// [`insert_core_event_once`]. `None` (no key declared, or the field is absent/non-scalar) keeps
/// the field's whole history: every call emits, exactly like before hub#1076 — and a mistaken
/// manifest degrades to that rather than losing the row's writer.
pub(crate) fn insert_op(
    ctx: &RequestContext,
    module_id: &str,
    event: &str,
    payload: &Params,
    depth: u32,
    dedup_key: Option<&str>,
) -> (String, Params) {
    let dedup_id = dedup_key.and_then(|field| {
        let resolved = payload.get(field).and_then(scalar_dedup_value);
        if resolved.is_none() {
            // Visible, never silent (production-ready rule): a manifest mistake here must not
            // roll back a mutation that already committed at the SQL layer, so this degrades to
            // "emits, undeduplicated" instead of erroring the whole command.
            eprintln!(
                "⚠ outbox: a command of `{module_id}` declares `emit[].dedup_key: \"{field}\"` \
                 for `{event}` but the payload carries no such field (or it is not a scalar) — \
                 this event is emitted WITHOUT deduplication"
            );
        }
        // The hub is part of the key: `id` is the table's only primary key and a legacy database
        // is shared, so a key without the hub would let one hub absorb another hub's event.
        resolved.map(|value| format!("dedup:{hub}:{module_id}:{event}:{value}", hub = ctx.hub_id))
    });

    let perms: Vec<&String> = ctx.permissions.iter().collect();
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(dedup_id.clone().unwrap_or_else(new_id)));
    p.insert("hub_id".into(), json!(ctx.hub_id));
    p.insert("user_id".into(), json!(ctx.user_id));
    p.insert(
        "permissions".into(),
        json!(serde_json::to_string(&perms).unwrap_or_else(|_| "[]".into())),
    );
    p.insert("event_name".into(), json!(event));
    p.insert("module_id".into(), json!(module_id));
    p.insert(
        "payload".into(),
        json!(serde_json::to_string(&Json::Object(payload.clone())).unwrap_or_else(|_| "{}".into())),
    );
    p.insert("depth".into(), json!(depth));
    p.insert(
        "run_id".into(),
        json!(ctx
            .automation()
            .map(|a| a.run_id.as_str())
            .unwrap_or_default()),
    );
    p.insert("parent_event_id".into(), json!(ctx.parent_event_id()));
    p.insert(
        "client_instance".into(),
        json!(ctx.client_instance.as_deref().unwrap_or_default()),
    );
    p.insert("now".into(), json!(now));
    let conflict_clause = if dedup_id.is_some() {
        " ON CONFLICT (id) DO NOTHING"
    } else {
        ""
    };
    let sql = format!(
        "INSERT INTO _event_outbox \
        (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, run_id, parent_event_id, client_instance, status, attempts, next_attempt_at, last_error, created_at) \
        VALUES (:id, :hub_id, :user_id, :permissions, :event_name, :module_id, :payload, :depth, :run_id, :parent_event_id, :client_instance, 'pending', 0, :now, '', :now){conflict_clause}"
    );
    (sql, p)
}

/// The stable string form of a JSON value fit to key an outbox dedup id on — scalars only. Null,
/// an array or an object have no single obvious textual identity (and a manifest naming one as
/// `dedup_key` is almost certainly pointing at the wrong field), so this returns `None` and the
/// caller degrades to "emits, undeduplicated" rather than guessing.
fn scalar_dedup_value(value: &Json) -> Option<String> {
    match value {
        Json::String(s) => Some(s.clone()),
        Json::Number(n) => Some(n.to_string()),
        Json::Bool(b) => Some(b.to_string()),
        Json::Null | Json::Array(_) | Json::Object(_) => None,
    }
}

/// Writes a **core event** — one the host itself ingests from outside the hub — into the outbox
/// under an id the CALLER chooses, at most once (ADR-0283 K1c).
///
/// Every other row here gets a fresh [`new_id`] because a command emitting an event is already
/// inside its own transaction: emit twice and you meant twice. An event ingested from an external
/// source is the opposite case. The source redelivers whatever it has not seen acknowledged, so
/// the same message arrives repeatedly by design, and the only thing that can tell one delivery of
/// a message from a second message is **the source's own id**. Deriving the primary key from it
/// (`"wa-<wa_message_id>"`) turns `ON CONFLICT DO NOTHING` into the exactly-once guarantee: the
/// database refuses the second write, so no listener runs twice and no caller has to remember
/// anything across a restart.
///
/// `DO NOTHING` — never `DO UPDATE`: a duplicate must not overwrite the stored payload, and above
/// all must not reset an already-`delivered` row back to `pending`, which would re-run listeners.
///
/// Returns whether a row was actually written (`false` = the id was already there).
///
/// The row's context is the **system** one, like [`crate::scheduler`]'s: `user_id` empty because
/// nobody in this hub caused it (the message came from a customer's phone), `module_id` empty
/// because no module emitted it. Per ADR-0288 the `permissions` column is forensic only — the
/// listener runs with its own module's authority — and the wildcard recorded here is simply the
/// honest description of the host: the same one `scheduler::system_ctx` uses.
pub async fn insert_core_event_once(
    db: &dyn DatabaseAdapter,
    id: &str,
    hub_id: &str,
    event_name: &str,
    payload: &Params,
) -> Result<bool> {
    let ctx = RequestContext::new(
        hub_id.to_string(),
        String::new(),
        [permissions::WILDCARD.to_string()],
    );
    let (sql, mut params) = insert_op(&ctx, "", event_name, payload, 0, None);
    params.insert("id".into(), json!(id));
    let result = db
        .execute(&format!("{sql} ON CONFLICT (id) DO NOTHING"), &params)
        .await?;
    Ok(result.affected > 0)
}

/// `INSERT` del marcador de entrega (event_id, listener). El relay lo añade a la transacción
/// del listener → si el listener commitea, la entrega queda registrada atómicamente.
pub(crate) fn delivery_op(hub_id: &str, event_id: &str, listener: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("event_id".into(), json!(event_id));
    p.insert("listener_command".into(), json!(listener));
    p.insert("delivered_at".into(), json!(now_rfc3339()));
    p.insert("hub_id".into(), json!(hub_id));
    let sql = "INSERT INTO _event_delivery (event_id, listener_command, delivered_at, hub_id) \
        VALUES (:event_id, :listener_command, :delivered_at, :hub_id)";
    (sql.to_string(), p)
}

/// The delivery marker of a `host.notify` send, carrying **what the provider called the message
/// and which flow, and which step of it, asked it** (hub#1951, hub#1962).
///
/// A sibling of [`delivery_op`] rather than three more parameters on it: the other four callers
/// mark a listener that ran, which has no provider, no flow and no step, and would all have to say
/// so.
///
/// All three default to `''` in the schema, so an older row and a send nobody named read the same way —
/// and [`who_asked`] refuses the empty id rather than matching it.
pub(crate) fn delivery_op_sent(
    hub_id: &str,
    event_id: &str,
    listener: &str,
    provider_message_id: &str,
    flow_id: &str,
    step_id: &str,
) -> (String, Params) {
    let (_, mut p) = delivery_op(hub_id, event_id, listener);
    p.insert(
        "provider_message_id".into(),
        json!(provider_message_id),
    );
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("step_id".into(), json!(step_id));
    let sql = "INSERT INTO _event_delivery \
        (event_id, listener_command, delivered_at, hub_id, provider_message_id, flow_id, \
         step_id) \
        VALUES (:event_id, :listener_command, :delivered_at, :hub_id, :provider_message_id, \
                :flow_id, :step_id)";
    (sql.to_string(), p)
}

/// **Who asked the question a provider message id belongs to**: the automation and its step.
/// Both are `""` when nobody the hub can name did (hub#1951, hub#1962).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct AskedBy {
    pub flow_id: String,
    pub step_id: String,
}

/// **Which flow, and which step of it, asked the question a provider message id belongs to** —
/// hub#1951 (the step) and hub#1962 (the flow).
///
/// The reverse of what [`delivery_op_sent`] wrote: Meta hands a tap back naming the `wamid` of the
/// message being answered (`context.id`), and this is the only place the hub can turn that into a
/// name the person who wrote the recipe would recognise. Nothing else can: the run that asked has
/// finished by then, and the run that reads the tap is a different one, triggered by the event.
///
/// Answers `""` — never an error and never a guess — for the three ways there is no step: an id
/// this hub never sent, an id belonging to ANOTHER hub, and an empty id. The last one is the
/// dangerous one and is refused twice, here and in the `WHERE`: every email delivery records an
/// empty `provider_message_id`, so a message that answers nothing would otherwise match whichever
/// of them the planner happened to return first and name a step nobody asked about.
pub async fn who_asked(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    provider_message_id: &str,
) -> Result<AskedBy> {
    if provider_message_id.is_empty() {
        return Ok(AskedBy::default());
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("provider_message_id".into(), json!(provider_message_id));
    p.insert("listener_command".into(), json!(HOST_NOTIFY_LISTENER));
    let res = db
        .query(
            "SELECT flow_id, step_id FROM _event_delivery \
             WHERE hub_id = :hub_id AND provider_message_id = :provider_message_id \
               AND provider_message_id <> '' AND listener_command = :listener_command",
            &p,
        )
        .await?;
    let Some(row) = res.rows.first() else {
        return Ok(AskedBy::default());
    };
    let text = |column: &str| row[column].as_str().unwrap_or_default().to_string();
    Ok(AskedBy {
        flow_id: text("flow_id"),
        step_id: text("step_id"),
    })
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
                    eprintln!(
                        "relay outbox: fila {}: {e}",
                        row["id"].as_str().unwrap_or("?")
                    );
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
               RETURNING id, hub_id, user_id, permissions, event_name, module_id, payload, depth, \
                         attempts, run_id, client_instance";
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

    let ctx = listener_ctx(row);
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
    // How many things failed this pass, and whether the failure is one that can never succeed
    // (hub#827). Counting matters: a row is only killed outright when the permanent refusal is
    // the ONLY failure it had — a sibling listener that merely stumbled still deserves its ladder.
    let mut failures = 0usize;
    let mut permanent: Option<&'static str> = None;
    // …or one that will not resolve within the ladder's minutes, yet may later (hub#971, hub#1171).
    // `dead_now_kind` is the classification stamped on the row when that happens: empty for a spent
    // quota (nothing to say beyond the error), a code for a refusal with a name.
    let mut dead_now = false;
    let mut dead_now_kind = "";
    for listener in &listeners {
        if delivery_exists(db, &ctx.hub_id, &id, listener).await? {
            continue; // ya entregado en un intento previo (idempotencia)
        }
        // Efectos del listener + sus eventos en cascada + el marcador de entrega → UNA transacción.
        let extra = [delivery_op(&ctx.hub_id, &id, listener)];
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
            failures += 1;
            // **A capability nobody granted is not a stumble** (hub#1171). The gate in front of a
            // native handler (ADR-0079) is default-deny and only a HUMAN can lift it, so the eighth
            // attempt knows exactly what the first knew — and the four minutes the ladder spends
            // finding that out are four minutes in which every surface of the hub (the dead-letter
            // screen, the topbar badge) still says «Todo en orden» while the fiscal chain is dead.
            // Same treatment as a spent quota (hub#971): terminal NOW, with its payload intact and
            // still retryable — granting the capability is precisely the remedy, and the row has to
            // be there waiting when the owner flips the switch.
            if matches!(e, RuntimeError::CapabilityDenied { .. }) {
                dead_now = true;
                dead_now_kind = FAILURE_CAPABILITY_DENIED;
            }
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
        let run_id = row["run_id"].as_str().unwrap_or_default().to_string();
        if let Err(f) = deliver_host_notify(
            db,
            registry,
            &id,
            &module_id,
            &run_id,
            &ctx.hub_id,
            &payload,
        )
        .await
        {
            failures += 1;
            permanent = f.permanent;
            // The stamp travels WITH the verdict (hub#1192). Before, `dead_now` arrived as a bare
            // bool and the row was killed with whatever `dead_now_kind` happened to hold — `''` —
            // which is precisely the classification `replay_capability_denied` cannot sweep.
            if let Some(kind) = f.dead_now {
                dead_now = true;
                dead_now_kind = kind;
            }
            if first_err.is_none() {
                first_err = Some(format!("{HOST_NOTIFY_LISTENER}: {}", f.error));
            }
        }
    }

    // ── Listener-host de `host.print` (hub#957) ─────────────────────────────────────────────
    // El gemelo del de arriba. Un evento `*.print.due` además encola el documento en la cola de
    // impresión del hub (ADR-0196 §6). Reusa la MISMA infra: idempotencia por `_event_delivery`
    // (listener sintético `host.print`) y, si la cola rechaza el trabajo, reintento/backoff/
    // dead-letter — que es lo que hace que un tipo de documento equivocado se vea en vez de
    // perderse. Encolar ES la entrega: que salga papel depende del host de impresión, y si no hay
    // ninguno registrado el trabajo espera (`print_hosts.rs`), no falla.
    if event_name.ends_with(PRINT_DUE_SUFFIX) {
        let module_id = row["module_id"].as_str().unwrap_or_default().to_string();
        if let Err(e) =
            deliver_host_print(db, registry, &id, &module_id, &ctx.hub_id, &payload).await
        {
            failures += 1;
            // The twin of the gate above (hub#1192): `printer` is the same default-deny switch, so
            // a refusal here is terminal now and STAMPED — otherwise granting «Impresora» leaves
            // the ticket in the dead-letter, which is the same silent loss by another door.
            if matches!(e, RuntimeError::CapabilityDenied { .. }) {
                dead_now = true;
                dead_now_kind = FAILURE_CAPABILITY_DENIED;
            }
            if first_err.is_none() {
                first_err = Some(format!("{HOST_PRINT_LISTENER}: {e}"));
            }
        }
    }

    // ── GDPR erasure of the kernel's history (hub#2467) ────────────────────────────────────
    // A `<subject>.anonymized` event empties, in this hub, the terminal history that names its
    // subject (`crate::erasure`). No module can do it: these tables are the kernel's (ADR-0127).
    // Idempotent by construction (an emptied payload no longer holds the id), so it needs no
    // `_event_delivery` marker; a failure here defers the row like any listener's.
    if let Err(e) = crate::erasure::on_event(
        db,
        registry,
        &ctx.hub_id,
        row["module_id"].as_str().unwrap_or_default(),
        &event_name,
        &payload,
    )
    .await
    {
        failures += 1;
        if first_err.is_none() {
            first_err = Some(format!("erasure: {e}"));
        }
    }

    // ── ESPERAS de flujo (hub#951) ──────────────────────────────────────────────────────────
    // El hermano del bloque de abajo, y la única pieza del kernel que puede mover un run que YA
    // está vivo: `triggers::on_event` solo sabe INSERTAR uno. Una espera (`delay`) tenía hasta
    // ahora una sola salida —su reloj—, así que el recordatorio de una cita cancelada se mandaba
    // igual. Aquí es donde el evento que la cancela (o la que la reprograma) llega hasta ella.
    //
    // Va ANTES de los triggers a propósito: cancelar una espera viva no depende de que el mismo
    // evento arranque además flujos nuevos, y el orden inverso dejaría el trabajo caro (insertar
    // runs) por delante del barato (un UPDATE condicional sobre un índice parcial).
    //
    // Misma infra que todo lo de arriba: idempotencia por `_event_delivery` con un listener
    // sintético `_flow_wait:<id>`, y un fallo aquí NO impide entregar la fila por lo demás.
    if let Err(e) = crate::flows::waits::on_event(db, &ctx.hub_id, &id, &event_name, &payload).await
    {
        failures += 1;
        if first_err.is_none() {
            first_err = Some(format!("flow waits: {e}"));
        }
    }

    // ── Triggers de FLUJO (ADR-0283 §3, hub#661) ────────────────────────────────────────────
    // Un evento entregado puede además arrancar flujos. Aquí SOLO se inserta la fila `_flow_runs`
    // (transaccional, idempotente por `_event_delivery` con un listener sintético `_flow:<id>`):
    // ejecutar el flujo inline mantendría el lock global del runtime tomado durante todo el flujo
    // —incluidos sus delays— y congelaría los commands de todo el hub. Lo ejecuta el tick.
    //
    // Va DESPUÉS de los listeners de manifest a propósito: que un flujo reaccione a un evento no
    // cambia cuándo corren los listeners de ese mismo evento. Y un fallo aquí NO impide marcar la
    // fila entregada por lo demás: se registra como los otros (backoff/dead-letter) y los flujos
    // que sí arrancaron ya tienen su marcador.
    if let Err(e) =
        crate::flows::triggers::on_event(db, &ctx.hub_id, &id, &event_name, &payload, depth).await
    {
        failures += 1;
        if first_err.is_none() {
            first_err = Some(format!("flows: {e}"));
        }
    }

    // Si algún listener falló, la fila se difiere/dead-lettera (NO se marca entregada): el/los
    // listeners fallidos se reintentarán; los que sí se entregaron ya tienen su marcador.
    if let Some(err) = first_err {
        // …unless the only thing that failed can never succeed (hub#827): then the row is terminal
        // NOW, with its reason recorded, instead of climbing a ladder to the same answer.
        if let (1, Some(kind)) = (failures, permanent) {
            return kill_permanently(db, &id, &err, kind, &payload).await;
        }
        // Same rule for a spent quota (hub#971) and for a capability nobody granted (hub#1171):
        // the payload is left untouched and the verdict stays retryable ([`is_retryable`]), so an
        // operator still gets the row once the quota is back or the switch is on. A spent quota has
        // nothing to add beyond its error and stamps nothing; a capability refusal names itself.
        if failures == 1 && dead_now {
            return mark_dead_as(db, &id, &err, dead_now_kind).await;
        }
        return defer_or_dead(db, &id, attempts, &err).await;
    }

    mark_delivered(db, &id).await
}

/// Why a host-notify did not go out **and whether trying again could ever change that** (hub#827).
///
/// The relay used to ask one question of a failure — how many attempts had it burnt — and a revoked
/// authorisation answered it eight times. It is not a stumble: an owner took a permission away, so
/// the eighth attempt knows exactly as much as the first. Everything that is NOT that stays
/// retryable by construction (see the `From` below), so a database blip or a transport 500 keeps
/// its backoff ladder untouched.
#[derive(Debug)]
struct NotifyFailure {
    error: RuntimeError,
    /// The classification the row is stamped with when this is terminal ([`FAILURE_RELEASE_REVOKED`]).
    /// `None` = retryable.
    permanent: Option<&'static str>,
    /// Terminal for the relay but not for an operator (hub#971): the row dies on this pass, with its
    /// payload intact, so a manual retry can pick it up once the cause is gone. `None` = retryable
    /// on the ladder; `Some(kind)` = dead now, stamped with `kind` (`""` when there is nothing to
    /// say beyond the error, as for a spent quota).
    ///
    /// **It has to be the stamp and not a bool** (hub#1192): `replay_capability_denied` sweeps the
    /// dead-letter BY `failure_kind`, so a row that dies unclassified is never put back when the
    /// owner grants the capability — the reminder is lost, not delayed.
    dead_now: Option<&'static str>,
}

impl NotifyFailure {
    /// A refusal that will never resolve on its own.
    fn permanent(kind: &'static str, error: RuntimeError) -> Self {
        Self {
            error,
            permanent: Some(kind),
            dead_now: None,
        }
    }

    /// A refusal the ladder cannot outwait, that a person can (hub#971) — stamped with `kind` so
    /// whoever fixes the cause can find the row again (hub#1192).
    fn dead_now(kind: &'static str, error: RuntimeError) -> Self {
        Self {
            error,
            permanent: None,
            dead_now: Some(kind),
        }
    }
}

/// Anything reaching this through `?` — a database error, an unparseable intent, a transport that
/// blew up — is **retryable**, which is the behaviour every one of them already had. Permanence is
/// only ever claimed explicitly, at the one place that knows.
impl From<RuntimeError> for NotifyFailure {
    fn from(error: RuntimeError) -> Self {
        Self {
            error,
            permanent: None,
            dead_now: None,
        }
    }
}

/// A database error is the retryable failure par excellence — it is what the backoff ladder was
/// built for — so it reaches here the same way.
impl From<erplora_db::DbError> for NotifyFailure {
    fn from(error: erplora_db::DbError) -> Self {
        RuntimeError::from(error).into()
    }
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
///
/// **La cuarta puerta, para lo que encola un FLUJO** (hub#821). Un flujo no es un módulo, así que
/// las puertas 1 y 2 no tienen a quién preguntar; lo que ocupa su sitio son sus dos grants, y el
/// destinatario no sale de la allowlist sino de una query concedida. La fila sigue ese camino solo
/// si es **del kernel y de un run** — `module_id` vacío **y** `run_id` presente—, y eso un módulo no
/// lo puede fabricar: `run_id` lo estampa el runtime desde el contexto de automatización (hub#666),
/// jamás desde el payload, y toda fila emitida por un command lleva su `module_id`. Copiar un
/// `resolved_via` ajeno en el payload propio no abre nada: se cae por las tres puertas de siempre.
async fn deliver_host_notify(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    event_id: &str,
    module_id: &str,
    run_id: &str,
    hub_id: &str,
    payload: &Params,
) -> std::result::Result<(), NotifyFailure> {
    let Some(transport) = &registry.notify_transport else {
        return Ok(()); // capacidad no disponible: no se envía nada (ni se reintenta).
    };
    if delivery_exists(db, hub_id, event_id, HOST_NOTIFY_LISTENER).await? {
        return Ok(()); // ya enviado en un intento previo (idempotencia)
    }
    let intent = NotifyIntent::from_event_payload(payload)?;
    let released_by_flow = module_id.trim().is_empty() && !run_id.trim().is_empty();
    // The flow that asked (hub#1962), set only on the kernel's path and only from the RUN — the
    // release check reads it there, never from the payload, so a module cannot name one.
    let mut asking_flow = String::new();

    if released_by_flow {
        // Puerta 4 — la autorización del flujo, **releída ahora**: revocar cualquiera de los dos
        // grants corta un mensaje que ya estaba en la cola. La forma del destinatario se comprueba
        // igual: que salga de una query concedida no lo convierte en una dirección válida.
        let resolved_via = payload
            .get(host_notify::RESOLVED_VIA_KEY)
            .and_then(|v| v.as_str())
            .unwrap_or_default();
        // Not `?`: a release that is gone is the one refusal the relay must not retry (hub#827).
        // The owner took the permission away — the eighth attempt would know exactly what the first
        // one did, and would have spent eight more minutes holding a customer's address in a queue.
        match crate::flows::grants::check_notify_release(
            db,
            hub_id,
            run_id,
            resolved_via,
            intent.channel,
        )
        .await
        {
            Ok(flow_id) => asking_flow = flow_id,
            Err(e) => return Err(NotifyFailure::permanent(FAILURE_RELEASE_REVOKED, e)),
        }
        host_notify::check_recipient_syntax(intent.channel, &intent.to)?;
    } else {
        // Puerta 1 — capability del MÓDULO emisor (no del hub): sin `notify` concedida, no hay
        // envío. Sin `module_id` (filas anteriores a la atribución) tampoco: no se puede autorizar
        // a nadie.
        if module_id.trim().is_empty() {
            return Err(RuntimeError::Notify(
                "evento de notificación sin módulo emisor atribuido: no se puede comprobar la \
                 capability `notify` → no se envía"
                    .to_string(),
            )
            .into());
        }
        // Not `?` (hub#1192): a capability nobody granted is the same kind of no that hub#1171
        // taught the module-listener path to recognise, and the gate here is the same default-deny
        // gate (hub#240). It is NOT `permanent`: granting `notify` is literally the remedy, so the
        // row dies now — stamped, payload intact, retryable — and `replay_capability_denied` puts
        // it back the moment the owner flips the switch. Burning the ladder to reach `failure_kind
        // = ''` is what made the reminder unrecoverable instead of merely late.
        match crate::capabilities::require(
            db,
            registry,
            module_id,
            hub_id,
            crate::manifest::CapabilityKind::Notify,
        )
        .await
        {
            Ok(()) => {}
            Err(e @ RuntimeError::CapabilityDenied { .. }) => {
                return Err(NotifyFailure::dead_now(FAILURE_CAPABILITY_DENIED, e));
            }
            // Only the REFUSAL is terminal now. The gate reads the grants table, so a database
            // blip surfaces at this same call — and that one keeps the ladder every other `?`
            // keeps, or a transient error would die stamped with a remedy that does not apply.
            Err(e) => return Err(e.into()),
        }
        // Puerta 2 — el canal tiene que estar declarado por el módulo emisor.
        host_notify::assert_channel_declared(registry, module_id, intent.channel)?;
        // Puerta 3 — el destinatario sale de los datos del hub, no del payload del handler.
        host_notify::assert_recipient_allowed(db, hub_id, &intent).await?;
    }

    // ¿WhatsApp premium de ERPlora? → proxy Cloud con cuota; si no, secreto local del tenant.
    let premium = !registry.premium_whatsapp_modules.is_empty();
    let routing = host_notify::route_channel(intent.channel, premium);
    let message_id = match transport.send(&intent, routing).await? {
        host_notify::SendOutcome::Sent { message_id } => message_id,
        // A spent quota is not a stumble (hub#971): no ladder, dead now — but retryable by hand,
        // because a quota, unlike a revoked release, comes back.
        host_notify::SendOutcome::QuotaExceeded { detail } => {
            // Unstamped on purpose: a quota has nothing to add beyond its error, and no gesture
            // sweeps by it — an operator's manual retry is the way back.
            return Err(NotifyFailure::dead_now(
                "",
                RuntimeError::Notify(format!("quota exceeded: {detail}")),
            ));
        }
    };
    // **The step that asked, but only off the KERNEL's own row** (hub#1951). On the module path
    // the payload is a module's to write, so honouring the key there would let it name a step of
    // somebody else's flow; `released_by_flow` is `module_id` empty AND `run_id` present, which is
    // the one shape a module cannot produce.
    let step_id = if released_by_flow {
        payload
            .get(host_notify::FLOW_STEP_KEY)
            .and_then(|v| v.as_str())
            .unwrap_or_default()
    } else {
        ""
    };
    // Envío con éxito → marca la entrega (idempotencia ante un reinicio entre send y mark), y con
    // ella la ÚNICA pareja que existe entre el id del proveedor y quién preguntó.
    let (sql, p) = delivery_op_sent(
        hub_id,
        event_id,
        HOST_NOTIFY_LISTENER,
        &message_id,
        &asking_flow,
        step_id,
    );
    db.execute(&sql, &p).await?;
    Ok(())
}

/// Encola un evento `*.print.due` en la cola de impresión del hub (hub#957), con idempotencia por
/// `_event_delivery` (listener sintético [`HOST_PRINT_LISTENER`]). El marcador se escribe SOLO tras
/// encolar con éxito → un fallo deja la fila para reintento (no marca entregado).
///
/// **Dos puertas antes de que se encole nada** (el gemelo de las tres de `host.notify`, ver
/// [`crate::host_print`] para por qué son dos y no tres):
///  1. el evento viene **atribuido** a un módulo emisor (`_event_outbox.module_id`): sin nombre no
///     hay a quién exigirle la capability, así que no se imprime;
///  2. ese módulo tiene la capability `printer` **declarada y concedida**
///     ([`crate::capabilities::require`], default-deny). Es la que ya existía — no se inventa una
///     nueva para lo mismo.
///
/// **No hay puerta de flujo** (la cuarta de `host.notify`, hub#821) y no debe haberla: el kernel no
/// emite nada acabado en `.print.due`. Un flujo llega aquí ejecutando el command de un módulo, y lo
/// que se autoriza es ese módulo. Una fila sin `module_id` —lo único que el kernel produce— se
/// rechaza por la puerta 1.
///
/// **Un duplicado es un éxito**: `print_queue::enqueue` es idempotente por `job_id`
/// (`ON CONFLICT DO NOTHING`, sin reescribir el documento ya encolado), así que reenviar el mismo
/// trabajo marca la entrega igual y no saca un segundo tique.
///
/// **Sin host de impresión registrado el trabajo espera.** La cola no consulta el registro de hosts
/// a propósito (`print_hosts.rs`: negarse a encolar porque no hay nadie escuchando sería el fallo
/// de la cola-en-el-dispositivo otra vez), y lo que hace que la espera no sea silenciosa ya existe:
/// `print_hosts::coverage` — aviso, nunca puerta.
async fn deliver_host_print(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    event_id: &str,
    module_id: &str,
    hub_id: &str,
    payload: &Params,
) -> Result<()> {
    if delivery_exists(db, hub_id, event_id, HOST_PRINT_LISTENER).await? {
        return Ok(()); // ya encolado en un intento previo (idempotencia)
    }
    // Puerta 1 — atribución.
    if module_id.trim().is_empty() {
        return Err(RuntimeError::Print(
            "evento de impresión sin módulo emisor atribuido: no se puede comprobar la capability \
             `printer` → no se encola"
                .to_string(),
        ));
    }
    // Puerta 2 — capability del MÓDULO emisor (declarada + concedida, default-deny).
    crate::capabilities::require(
        db,
        registry,
        module_id,
        hub_id,
        crate::manifest::CapabilityKind::Printer,
    )
    .await?;

    let job = crate::host_print::PrintIntent::from_event_payload(payload)?.into_job();
    // La cola valida el resto (vocabulario del documento, forma y tamaño, papel) y es idempotente
    // por `job_id`: `Duplicate` es un éxito, no un error.
    crate::print_queue::enqueue(db, hub_id, &job).await?;
    let (sql, p) = delivery_op(hub_id, event_id, HOST_PRINT_LISTENER);
    db.execute(&sql, &p).await?;
    Ok(())
}

/// The context a listener runs with (hub#686, ADR-0288): **the module's own authority, the
/// emitter's attribution, the event's tenant.**
///
/// # What it replaced, and why that was broken
///
/// This used to rebuild the EMITTER's context verbatim — permissions included — so a listener only
/// ran if the human who triggered the event happened to hold a permission over a command of
/// ANOTHER module. In the published catalogue the cashier (`employee`) holds none of the four that
/// the sale cascade needs: closing a sale left the stock untouched, the customer's purchase
/// unrecorded and the invoice **unsent to VeriFactu** — a legal breach, arriving as eight silent
/// retries and a dead-letter. The owner selling produced one result and their employee selling
/// another, from the same button.
///
/// The confusion was of planes. The cashier asked for «close the sale»; that this implies bringing
/// stock down and filing with the tax agency is decided by the MODULE in its manifest. Demanding
/// that the human hold a permission over an internal command of a module they never named is
/// asking the wrong principal.
///
/// # The three parts, each for its own reason
///
/// 1. **`hub_id` — from the row, always.** Not negotiable in any context the runtime builds
///    (`tenancy.md`): the listener writes in the hub of the event it reacts to and in no other.
/// 2. **`user_id` — from the row.** Module SQL binds `:current_user_id` into `created_by` /
///    `updated_by`, so a stock movement caused by Ana's sale must say Ana. This is the one place
///    this context differs from [`crate::scheduler`]'s (which has no user because nobody asked
///    for anything) and it is what keeps the fix from costing traceability.
/// 3. **`*` — the module's authority, not the human's role.** The two sibling doors of the runtime
///    already work this way: a scheduled task runs on `system_ctx`, and a handler's preloaded
///    `reads` run on a system context precisely so «un empleado de POS sin `taxes.view_tax` igual
///    necesita los tipos para poder cobrar».
///
/// # Why the wildcard is bounded, and by what
///
/// It is not a skeleton key handed to whoever emits an event: it authorises exactly ONE command,
/// and that command is the listening module's own. Since hub#659 a manifest's `events.listen` may
/// only name a command inside the declaring module's namespace, and that check sits in
/// [`crate::installer::install`] — the single registration path, which
/// [`crate::Runtime::rehydrate_installed`] re-runs on every boot, so a listener pointing at
/// somebody else's command cannot be in a live registry at all. Downstream, `validate_operation`
/// keeps a Tier-2 handler's operations inside the same module. So the authority never crosses a
/// module boundary: what the wildcard opens is a door the module already owned.
///
/// Everything that does NOT key on permissions keeps refusing exactly as before — the fiscal
/// preconditions (ADR-0203), the capability grants (ADR-0079), the payload schema, `min_affected_rows`.
/// Those cover the listeners on purpose and none of them changes here.
///
/// The row's `permissions` column is kept: it is the record of what the emitter could do, which is
/// worth having in a dead-letter (hub#660). It is simply no longer what authorises anything.
fn listener_ctx(row: &Json) -> RequestContext {
    let hub_id = row["hub_id"].as_str().unwrap_or_default().to_string();
    let user_id = row["user_id"].as_str().unwrap_or_default().to_string();
    let ctx = RequestContext::new(hub_id, user_id, [permissions::WILDCARD.to_string()])
        // Whatever this listener emits is a consequence of THIS event, and says so (hub#666).
        .caused_by_event(row["id"].as_str().unwrap_or_default())
        // There is no human at the relay, so there is nobody to type a manager's PIN: the
        // step-up dialog (hub#361) must never be offered here. It cannot be today — the
        // wildcard opens the gate before elevation is ever considered — and saying so in the
        // context means it stays true if the authority is ever narrowed.
        .as_machine();
    // The shell tab whose request started the chain (hub#2029). A till fires the ORDER; the kitchen
    // ticket is made here, one hop later, and without the tab it reached the live channel as
    // nobody's — so every till printed it. It names and grants nothing, like at the door.
    match row["client_instance"].as_str() {
        Some(instance) if !instance.is_empty() => ctx.with_client_instance(instance),
        _ => ctx,
    }
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

async fn delivery_exists(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
    listener: &str,
) -> Result<bool> {
    let mut p = Params::new();
    p.insert("event_id".into(), json!(event_id));
    p.insert("listener_command".into(), json!(listener));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT 1 AS ok FROM _event_delivery WHERE event_id = :event_id \
               AND listener_command = :listener_command AND hub_id = :hub_id",
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
    mark_dead_as(db, id, err, "").await
}

/// [`mark_dead`] with a reason attached — the row dies AND says why in a word a machine can read
/// (hub#1171). It is not [`kill_permanently`]: nothing is scrubbed from the payload and the verdict
/// does not have to be a dead end ([`is_retryable`]).
async fn mark_dead_as(
    db: &dyn DatabaseAdapter,
    id: &str,
    err: &str,
    failure_kind: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("err".into(), json!(err));
    p.insert("kind".into(), json!(failure_kind));
    db.execute(
        "UPDATE _event_outbox SET status = 'dead', last_error = :err, failure_kind = :kind, \
         claim_expires_at = NULL WHERE id = :id",
        &p,
    )
    .await?;
    Ok(())
}

/// **Ends a row that can never be delivered** (hub#827), in one gesture and on the first pass.
///
/// Two things happen here that `mark_dead` does not do, and each answers a separate half of the
/// same complaint:
///
///  1. **The reason is recorded** in `failure_kind`, so the queue can show it, [`retry`] can refuse
///     with it, and neither has to read English out of `last_error`.
///  2. **The recipient is scrubbed from the stored payload.** `crate::flows::notify` puts the
///     address in the queue row and nowhere else precisely because that row «TIENE que llevarlo» —
///     the transport needs something to dial, which is why the run history shows only
///     `recipient_redacted`. A row that will never be dialled stops having to carry it, and leaving
///     it there means ninety days of the customer's contact sitting in the operator's dead-letter:
///     the very contact the owner had just decided not to use.
///
/// What stays is what the OWNER decided — the channel, the template, the copy they wrote, the
/// release that authorised it. That is what tells one row from another, and none of it is the
/// customer's. The point is not to blind the operator; it is to stop keeping one field.
async fn kill_permanently(
    db: &dyn DatabaseAdapter,
    id: &str,
    err: &str,
    failure_kind: &str,
    payload: &Params,
) -> Result<()> {
    let mut scrubbed = payload.clone();
    if scrubbed.remove(RECIPIENT_KEY).is_some() {
        // Said out loud rather than simply removed: a payload with no `to` at all would read like
        // the message never had a recipient.
        scrubbed.insert(RECIPIENT_REDACTED_KEY.into(), json!(true));
    }
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("err".into(), json!(err));
    p.insert("kind".into(), json!(failure_kind));
    p.insert("payload".into(), json!(Json::Object(scrubbed).to_string()));
    db.execute(
        "UPDATE _event_outbox SET status = 'dead', last_error = :err, failure_kind = :kind, \
         payload = :payload, claim_expires_at = NULL WHERE id = :id",
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
    let next_at =
        (chrono::Utc::now() + chrono::Duration::seconds(backoff_seconds(next))).to_rfc3339();
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
    /// Why this row is terminal, when the answer is not «it burnt its attempts» (hub#827). Empty
    /// for every ordinary dead-letter; [`FAILURE_RELEASE_REVOKED`] when a flow's authorisation was
    /// taken away while the message was queued.
    pub failure_kind: String,
    /// Whether [`retry`] can do anything with this row. **The screen must not offer a button that
    /// cannot work**: retrying a revoked release returned `200`, reset `attempts` and died again for
    /// the same reason — a loop with no exit, presented as the remedy.
    pub retryable: bool,
}

/// Dead-letters of this hub, newest first. `limit` is clamped to [`MAX_DEAD_PAGE`].
pub async fn list_dead(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    limit: i64,
) -> Result<Vec<DeadEvent>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    p.insert("lim".into(), json!(limit.clamp(1, MAX_DEAD_PAGE)));
    let res = db
        .query(
            "SELECT id, event_name, module_id, user_id, payload, last_error, attempts, depth, \
                    created_at, failure_kind \
             FROM _event_outbox WHERE hub_id = :hub_id AND status = :status \
             ORDER BY created_at DESC LIMIT :lim",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(dead_event).collect())
}

fn dead_event(row: &Json) -> DeadEvent {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    let n = |k: &str| {
        row[k]
            .as_i64()
            .or_else(|| row[k].as_f64().map(|f| f as i64))
            .unwrap_or(0)
    };
    let raw = s("payload");
    let failure_kind = s("failure_kind");
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
        retryable: is_retryable(&failure_kind),
        failure_kind,
    }
}

/// **One dead-letter an operator CLOSED**, with the whole stamp the close left behind (hub#1117).
///
/// The sibling of [`DeadEvent`], and deliberately not the same struct: the two lists answer
/// different questions. A dead-letter is a decision waiting to be made, so it travels with its
/// payload — that is what tells a lost invoice from noise. A discarded row is a decision already
/// made, and what is asked of it afterwards is «who closed this, when, and why», never «what did it
/// carry». So the payload does NOT travel here: this listing is the widest reading of the outbox
/// that a closed row needs, and no wider.
#[derive(Debug, Clone, serde::Serialize)]
pub struct DiscardedEvent {
    pub id: String,
    pub event_name: String,
    /// The **emitting** module (attribution), the same field [`DeadEvent`] carries.
    pub module_id: String,
    /// Why it died in the first place — the half of the story the hub knows on its own.
    pub last_error: String,
    pub created_at: String,
    /// When it was closed. Also the row's retention clock: ninety days from here it is pruned.
    pub discarded_at: String,
    /// `hub_user:<id>` — the session the HTTP layer resolved, never anything a caller sent.
    pub discarded_by: String,
    /// **Why a person closed it** — the half only they knew ([`clamp_discard_reason`]). Empty when
    /// the row was closed without an explanation, which stays a legitimate gesture.
    pub discard_reason: String,
}

/// Dead-letters of this hub an operator has CLOSED, newest closure first. `limit` is clamped to
/// [`MAX_DEAD_PAGE`].
///
/// The read half of [`discard`]. The stamp had been written in full since hub#955 and no surface
/// projected any of it: `list_dead` filters `status = 'dead'`, so closing a row removed it from the
/// only listing there was, and the tray's own promise —«el hub guarda quién cerró cada uno, cuándo
/// y por qué durante noventa días»— was verifiable only with `psql`. A record nobody can read is
/// not a record.
///
/// **The ninety days are respected by construction, not by a filter here.** Retention is a hard
/// `DELETE` (hub#699, [`crate::retention`]): a row past the window is gone from the table, so it
/// cannot appear in this listing and asking for it is an ordinary «not found» rather than a
/// special case. A `WHERE discarded_at > cutoff` on top of that would be a second, drifting copy of
/// the same policy.
///
/// Ordered by `COALESCE(discarded_at, created_at)` — the same terminal moment `ix_outbox_prune`
/// indexes — so a row whose stamp predates the column still sorts somewhere sane instead of
/// wherever the dialect happens to put NULLs.
pub async fn list_discarded(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    limit: i64,
) -> Result<Vec<DiscardedEvent>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DISCARDED));
    p.insert("lim".into(), json!(limit.clamp(1, MAX_DEAD_PAGE)));
    let res = db
        .query(
            "SELECT id, event_name, module_id, last_error, created_at, discarded_at, \
                    discarded_by, discard_reason \
             FROM _event_outbox WHERE hub_id = :hub_id AND status = :status \
             ORDER BY COALESCE(discarded_at, created_at) DESC LIMIT :lim",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(discarded_event).collect())
}

fn discarded_event(row: &Json) -> DiscardedEvent {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    DiscardedEvent {
        id: s("id"),
        event_name: s("event_name"),
        module_id: s("module_id"),
        last_error: s("last_error"),
        created_at: s("created_at"),
        discarded_at: s("discarded_at"),
        discarded_by: s("discarded_by"),
        discard_reason: s("discard_reason"),
    }
}

/// One stored event, reduced to what inferring a shape needs (hub#715).
#[derive(Debug, Clone)]
pub struct PayloadSample {
    pub payload: Json,
    pub created_at: String,
}

/// The last `limit` events of ONE name in this hub, newest first, with their payloads.
///
/// This is the raw material of [`crate::event_shape`], and the only caller: what leaves the hub is
/// the SHAPE, never these rows. Every status counts — `pending`, `delivered`, `dead`,
/// `discarded` — because the question is «what does this event carry», and a delivery failure does
/// not change the answer.
///
/// Backed by `ix_outbox_name`. An unparseable stored payload comes back as a JSON string rather
/// than being dropped, the same way [`list_dead`] treats it: what is in the row is what there is.
pub async fn sample_payloads(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_name: &str,
    limit: i64,
) -> Result<Vec<PayloadSample>> {
    if event_name.is_empty() {
        return Ok(Vec::new());
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(event_name));
    p.insert(
        "lim".into(),
        json!(limit.clamp(1, crate::event_shape::MAX_SAMPLES)),
    );
    let res = db
        .query(
            "SELECT payload, created_at FROM _event_outbox \
             WHERE hub_id = :hub_id AND event_name = :name \
             ORDER BY created_at DESC, id DESC LIMIT :lim",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .map(|row| {
            let raw = row["payload"].as_str().unwrap_or_default().to_string();
            PayloadSample {
                payload: serde_json::from_str(&raw).unwrap_or(Json::String(raw)),
                created_at: row["created_at"].as_str().unwrap_or_default().to_string(),
            }
        })
        .collect())
}

/// One event name this hub has really written to the outbox, with its newest sighting (hub#823).
#[derive(Debug, Clone)]
pub struct SeenEvent {
    pub name: String,
    pub last_seen_at: String,
}

/// Every DISTINCT event name in this hub's outbox with `MAX(created_at)`, the SEEN half of the
/// event catalogue (hub#823) — the declared half comes from the registry.
///
/// Every status counts, like [`sample_payloads`]: the question is «did this event ever happen
/// here», and a delivery failure does not change the answer. Names only — the payload never
/// leaves this table through this read.
///
/// Backed by `ix_outbox_name` (`hub_id, event_name, created_at`), which serves this group-by the
/// same way it serves the shape's per-name read.
pub async fn seen_event_names(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<SeenEvent>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT event_name, MAX(created_at) AS last_seen_at FROM _event_outbox \
             WHERE hub_id = :hub_id GROUP BY event_name",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .map(|row| SeenEvent {
            name: row["event_name"].as_str().unwrap_or_default().to_string(),
            last_seen_at: row["last_seen_at"].as_str().unwrap_or_default().to_string(),
        })
        .collect())
}

/// What [`retry`] did — three answers, because the caller has to tell them apart (hub#827).
///
/// It used to be a `bool`, and `false` meant «there is no such dead-letter»: a `404`. That left
/// nowhere to put the third answer — the row is right there and cannot be replayed — so the gesture
/// returned `200` and the message died again for the same reason, forever.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RetryOutcome {
    /// Back in front of the relay with a fresh budget.
    Requeued,
    /// No dead-letter with that id **in this hub** (never existed, already delivered, discarded, or
    /// another tenant's — the last two are indistinguishable on purpose).
    NotFound,
    /// The row is a dead-letter and retrying it can never work. `failure_kind` names why, so the
    /// caller can say what WOULD help instead of showing a dead end.
    NotRetryable { failure_kind: String },
}

/// Puts a dead-letter back in front of the relay: `pending`, attempts reset, due now, lease
/// cleared.
///
/// Only a `dead` row is replayable. A `delivered` one is not an operator gesture (the delivery
/// markers in `_event_delivery` already make it a no-op), and a `pending` one is the relay's.
///
/// Resetting `attempts` to 0 is what makes the retry meaningful: the row gets the full budget of
/// [`MAX_ATTEMPTS`] again, so a transient cause gets its backoff ladder back instead of dying on
/// the first stumble. If the cause is still there, it simply dies again — and is listed again.
///
/// **Unless the cause is one that cannot come back** (hub#827). A row stamped with a
/// [`FAILURE_RELEASE_REVOKED`] is refused with its reason: the address it needed is gone from the
/// payload and the permission that produced it was withdrawn, so the remedy is to grant the
/// permission again and run the flow — not to replay this row. It is the rule §13.6 already applies
/// to the rate-guard: retrying a runaway forever is the same runaway.
pub async fn retry(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<RetryOutcome> {
    // Read WHY first: the three answers are distinguishable only before the UPDATE, since a refusal
    // and a missing row would both come back as `affected = 0`.
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    let res = db
        .query(
            "SELECT failure_kind FROM _event_outbox \
             WHERE id = :id AND hub_id = :hub_id AND status = :status",
            &p,
        )
        .await?;
    let Some(failure_kind) = res
        .rows
        .first()
        .map(|r| r["failure_kind"].as_str().unwrap_or_default().to_string())
    else {
        return Ok(RetryOutcome::NotFound);
    };
    if !is_retryable(&failure_kind) {
        return Ok(RetryOutcome::NotRetryable { failure_kind });
    }

    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("kind".into(), json!(failure_kind));
    let res = db
        .execute(
            "UPDATE _event_outbox SET status = 'pending', attempts = 0, next_attempt_at = :now, \
             last_error = '', failure_kind = '', claim_expires_at = NULL \
             WHERE id = :id AND hub_id = :hub_id AND status = :status AND failure_kind = :kind",
            &p,
        )
        .await?;
    Ok(if res.affected > 0 {
        RetryOutcome::Requeued
    } else {
        RetryOutcome::NotFound
    })
}

/// Closes a dead-letter for good: status [`STATUS_DISCARDED`] + who and when. `false` if there is
/// no dead-letter with that id in this hub.
///
/// **The gesture never `DELETE`s.** The row is the only record that the event existed, and a
/// discard is a decision somebody made; both have to survive the gesture that closed them. The
/// relay cannot take it again because [`claim_next_due`] only ever claims `pending`.
///
/// What *does* eventually remove it is retention (hub#699, `crate::retention`): ninety days after
/// it was discarded it is pruned like any other terminal row. That is not a contradiction — it is
/// the difference between an operator closing a case, which must leave evidence, and history
/// ageing out long after anybody would look. `dead`, which is still waiting for that decision, has
/// no maximum age at all.
///
/// `discarded_by` is the identity the HTTP layer resolved from the session (`hub_user:<id>`), never
/// something the caller sent in the body. `reason`, on the other hand, IS the caller's — it is the
/// one thing only the person closing the row knows (see [`clamp_discard_reason`]).
pub async fn discard(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    discarded_by: &str,
    reason: &str,
) -> Result<bool> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    p.insert("discarded".into(), json!(STATUS_DISCARDED));
    p.insert("by".into(), json!(discarded_by));
    p.insert("reason".into(), json!(clamp_discard_reason(reason)));
    p.insert("now".into(), json!(now_rfc3339()));
    let res = db
        .execute(
            "UPDATE _event_outbox SET status = :discarded, discarded_at = :now, discarded_by = :by, \
             discard_reason = :reason, claim_expires_at = NULL \
             WHERE id = :id AND hub_id = :hub_id AND status = :status",
            &p,
        )
        .await?;
    Ok(res.affected > 0)
}

/// How much of a discard reason is kept, in characters.
///
/// Long enough for the sentence an operator actually writes («duplicada: la factura se registró a
/// mano»), short enough that the field cannot become a place to paste a stack trace. This text
/// arrives from a request body and lands in a row the relay scans and retention keeps for ninety
/// days: unbounded free text there is not an audit trail, it is a hole.
pub const MAX_DISCARD_REASON: usize = 500;

/// The reason as it gets STORED: trimmed and capped at [`MAX_DISCARD_REASON`] characters.
///
/// Trimmed because a text area hands back the whitespace around what was typed, and «duplicada» and
/// « duplicada » are not two different decisions. Cut on a **character** boundary and never on a
/// byte one: half an `é` is a panic in Rust and mojibake everywhere else, and this text is Spanish.
///
/// Public because the HTTP layer echoes the stored value back to the caller (hub#955): one
/// implementation, so what the tray renders and what the row holds cannot drift apart.
pub fn clamp_discard_reason(reason: &str) -> String {
    reason.trim().chars().take(MAX_DISCARD_REASON).collect()
}

/// Puts **every** dead-letter of this hub back in front of the relay at once — the bulk gesture
/// (hub#660). Returns how many rows it moved. The one-by-one [`retry`] is for the case an operator
/// inspects; this is for the other real case: a transient outage (the DB went down, a module was
/// deactivated mid-flight) burnt through `MAX_ATTEMPTS` on several events at the same time, and
/// the cause is now fixed. Telling the operator to retry thirty rows one by one is the thing this
/// exists to remove — **the hub must never be stuck behind a queue that only moves one click at a
/// time**.
///
/// Same semantics as [`retry`], applied to the set: only `dead` rows of **this hub** move
/// (`hub_id` isolation, ADR-0201), each gets `attempts = 0`, `next_attempt_at = now`, a cleared
/// lease and a wiped `last_error`. Delivered/pending/discarded rows are untouched. Idempotent: a
/// second call moves nothing (there are no `dead` rows left). If a row's cause is still there it
/// dies again and reappears in [`list_dead`]; the queue is self-healing, not magic.
///
/// Rows whose `failure_kind` is a **dead end** are skipped ([`is_retryable`]), for the reason this
/// gesture exists at all: it is for a cause that has since been fixed, and a withdrawn authorisation
/// is not one (hub#827). Sweeping them along would be the one-by-one dead end multiplied by thirty.
/// A capability refusal (hub#1171) is the opposite case and IS swept: granting the capability is
/// exactly «the cause has since been fixed».
pub async fn retry_all(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<u64> {
    requeue_dead(db, hub_id, &["", FAILURE_CAPABILITY_DENIED]).await
}

/// Puts back every dead-letter of this hub stamped with one of `kinds`, clearing the stamp so a row
/// that dies again is classified afresh. The shared engine of [`retry_all`] and
/// [`replay_capability_denied`] — two gestures, one `UPDATE`, so they can never drift on what
/// «back in front of the relay» means.
async fn requeue_dead(db: &dyn DatabaseAdapter, hub_id: &str, kinds: &[&str]) -> Result<u64> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    p.insert("now".into(), json!(now_rfc3339()));
    let mut names = Vec::with_capacity(kinds.len());
    for (i, kind) in kinds.iter().enumerate() {
        let name = format!("kind{i}");
        p.insert(name.clone(), json!(kind));
        names.push(format!(":{name}"));
    }
    let res = db
        .execute(
            &format!(
                "UPDATE _event_outbox SET status = 'pending', attempts = 0, next_attempt_at = :now, \
                 last_error = '', failure_kind = '', claim_expires_at = NULL \
                 WHERE hub_id = :hub_id AND status = :status AND failure_kind IN ({})",
                names.join(", ")
            ),
            &p,
        )
        .await?;
    Ok(res.affected)
}

/// **Puts back what an ungranted capability had refused** (hub#1171 — the recoverable half of
/// hub#1119). Called when a capability is GRANTED: the events that died because the switch was off
/// are, by construction, the ones the switch fixes, and the owner who just flipped it must not also
/// have to find System → Events and press a button per row.
///
/// Deliberately not filtered by module: the stamp is on the event, and the refused module is not on
/// the row (`module_id` is the EMITTER). Sweeping the hub's whole capability-denied set is both
/// simpler and safe — a row whose own capability is still missing dies again on the very next pass,
/// with its reason, instead of climbing a ladder.
pub async fn replay_capability_denied(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<u64> {
    requeue_dead(db, hub_id, &[FAILURE_CAPABILITY_DENIED]).await
}

/// How many dead-letters this hub has right now (hub#660). Cheap `SELECT COUNT(*)` — the listing
/// ([`list_dead`]) carries the payloads and is capped, so it is the wrong thing to poll for a badge.
/// This powers the bell in the topbar: an admin sees, without going anywhere, that something died.
///
/// Counts **only** `dead` rows: `delivered`/`pending` are not failures, and `discarded` are closed
/// failures an admin already decided to keep closed — neither is "something that needs you".
pub async fn count_dead(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<i64> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_DEAD));
    let res = db
        .query(
            "SELECT COUNT(*) AS c FROM _event_outbox WHERE hub_id = :hub_id AND status = :status",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| {
            r["c"]
                .as_i64()
                .or_else(|| r["c"].as_f64().map(|f| f as i64))
        })
        .unwrap_or(0))
}

// ─────────────────────────── Correlation (hub#666 — ADR-0283 §8) ───────────────────────────────
//
// Two columns and two queries, and between them they answer the two questions the kernel could not
// answer before: **«what did this sale set off?»** and **«why does this row exist?»**.
//
// `depth` already bounded a cascade, but it only ever said how far one had travelled — never from
// what. The link had to be guessed from timestamps, and a till closing two sales a second makes
// that guess wrong exactly when it matters. `parent_event_id` names the event whose delivery caused
// this one; `run_id` names the flow execution that emitted it. Both are written by the runtime from
// the [`RequestContext`], never by a caller.

/// How many rows one correlation query returns. A chain longer than this is a runaway, and the
/// guards in `flows::triggers` are what deal with those.
pub const MAX_CORRELATED: i64 = 200;

/// One event, seen as a link in a chain rather than as a payload to inspect. The payload is
/// deliberately absent: this shape is for walking the chain, and the door that shows payloads is
/// the dead-letter queue, where an operator is deciding whether to replay one specific row.
#[derive(Debug, Clone, serde::Serialize)]
pub struct CorrelatedEvent {
    pub id: String,
    pub event_name: String,
    pub module_id: String,
    pub status: String,
    /// The flow run that emitted it (`""` when a person's command did).
    pub run_id: String,
    /// The event whose delivery caused it (`""` when it is the root of its chain).
    pub parent_event_id: String,
    pub depth: i64,
    pub created_at: String,
}

/// The events **a flow run emitted** — the forward link from a run into everything downstream.
pub async fn events_of_run(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
) -> Result<Vec<CorrelatedEvent>> {
    // An empty `run_id` is the value of every event nobody automated: matching on it would return
    // the whole outbox for a run id that got lost on the way here.
    if run_id.is_empty() {
        return Ok(Vec::new());
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    p.insert("lim".into(), json!(MAX_CORRELATED));
    let res = db
        .query(
            "SELECT id, event_name, module_id, status, run_id, parent_event_id, depth, created_at \
             FROM _event_outbox WHERE hub_id = :hub_id AND run_id = :run_id \
             ORDER BY created_at, id LIMIT :lim",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(correlated).collect())
}

/// The events **caused by the delivery of** `event_id` — one level of the cascade, not the whole
/// transitive closure. A recursive walk in SQL would be a single query that can traverse the entire
/// outbox; one level at a time is what the caller can page and bound.
pub async fn events_caused_by(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
) -> Result<Vec<CorrelatedEvent>> {
    if event_id.is_empty() {
        return Ok(Vec::new());
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("parent".into(), json!(event_id));
    p.insert("lim".into(), json!(MAX_CORRELATED));
    let res = db
        .query(
            "SELECT id, event_name, module_id, status, run_id, parent_event_id, depth, created_at \
             FROM _event_outbox WHERE hub_id = :hub_id AND parent_event_id = :parent \
             ORDER BY created_at, id LIMIT :lim",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(correlated).collect())
}

/// One event of this hub, as a link in a chain. `None` when it is not in this hub — the tenant is
/// part of the lookup, not a filter applied afterwards.
pub async fn correlated_event(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_id: &str,
) -> Result<Option<CorrelatedEvent>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(event_id));
    let res = db
        .query(
            "SELECT id, event_name, module_id, status, run_id, parent_event_id, depth, created_at \
             FROM _event_outbox WHERE hub_id = :hub_id AND id = :id",
            &p,
        )
        .await?;
    Ok(res.rows.first().map(correlated))
}

fn correlated(row: &Json) -> CorrelatedEvent {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    CorrelatedEvent {
        id: s("id"),
        event_name: s("event_name"),
        module_id: s("module_id"),
        status: s("status"),
        run_id: s("run_id"),
        parent_event_id: s("parent_event_id"),
        depth: row["depth"]
            .as_i64()
            .or_else(|| row["depth"].as_f64().map(|f| f as i64))
            .unwrap_or(0),
        created_at: s("created_at"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::elevation::Grants;
    use crate::manifest::CommandDef;
    use crate::registry::{ModuleStatus, Principal, RegisteredCommand};
    use erplora_db::{testutil::fresh_db, PgAdapter};

    fn cmd(module: &str, sql: &str, emit: Vec<crate::manifest::EmitDef>) -> RegisteredCommand {
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
                on_unique: Default::default(),
            },
            sql: vec![sql.to_string()],
            wasm: None,
            schema: None,
        }
    }

    /// El esquema de sistema que deja un arranque REAL (`Runtime::ensure_system_tables`).
    ///
    /// Hasta hub#661 bastaba con `ensure_tables` (las dos tablas del outbox), porque el relay solo
    /// leía las suyas. Ahora, tras entregar a los listeners, además le pregunta a `_flow_triggers`
    /// si ese evento arranca algún flujo (ADR-0283 §3) — así que un fixture con MEDIO esquema deja
    /// de parecerse a ningún hub, y sus tests pasarían a hablar del fixture en vez del relay.
    /// Montarlo entero es más lento y es lo correcto: en un hub las tablas nacen juntas, bajo un
    /// único lock de migración.
    async fn system_schema(db: &PgAdapter) {
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        ensure_tables(db).await.unwrap();
        crate::system_migrations::apply(db, "h1").await.unwrap();
        crate::flows::store::ensure_indexes(db).await.unwrap();
    }

    async fn count(db: &PgAdapter, sql: &str) -> i64 {
        let r = db.query(sql, &Params::new()).await.unwrap();
        r.rows[0]["c"]
            .as_i64()
            .or_else(|| r.rows[0]["c"].as_f64().map(|f| f as i64))
            .unwrap_or(-1)
    }

    /// El command emisor NO corre el listener inline (entrega asíncrona); el relay lo entrega
    /// exactamente una vez y es idempotente al re-procesar (marcador `_event_delivery`).
    #[tokio::test]
    async fn outbox_async_delivery_is_exactly_once() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        system_schema(&db).await;

        // Módulo "m" activo: "m.fire" emite "e"; "m.append" (listener de "e") inserta n=1.
        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        reg.commands.insert(
            "m.append".into(),
            cmd("m", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "m.fire".into(),
            cmd("m", "INSERT INTO t (n) VALUES (99);", vec!["e".into()]),
        );
        reg.listeners.insert("e".into(), vec!["m.append".into()]);

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);

        // Emisor: inserta su fila (99) + persiste el evento en el outbox, pero NO corre el listener.
        crate::commands::execute(&db, &reg, "m.fire", &Params::new(), &ctx, &Grants::new())
            .await
            .unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            0,
            "listener no inline"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending'"
            )
            .await,
            1,
            "evento pendiente en outbox"
        );

        // Relay: el listener corre una vez; el evento queda 'delivered'.
        drain(&db, &reg).await.unwrap();
        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1);
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            1
        );

        // Idempotencia: re-drenar no re-ejecuta el listener.
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "idempotente"
        );
    }

    /// hub#131/#145: un listener marcado INTERNO por convención (último segmento `_`, estilo real
    /// `cash_register._reverse_sale`) SE ENTREGA con normalidad por el relay — el gate de origen
    /// (hub#131/#145) solo bloquea el camino EXTERNO (`Runtime::execute_command`); el relay del
    /// Outbox es el propio runtime, así que invoca con `Origin::Internal` y no se ve afectado.
    #[tokio::test]
    async fn relay_delivers_to_an_underscore_prefixed_internal_listener() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        system_schema(&db).await;

        // "sales.void" emite "sale.voided"; "cash_register._reverse_sale" (interno, sin
        // `expose_api`) es su listener, como en el caso real (void_reversal_e2e.rs).
        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.status
            .insert("cash_register".into(), ModuleStatus::Active);
        reg.commands.insert(
            "cash_register._reverse_sale".into(),
            cmd("cash_register", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "sales.void".into(),
            cmd(
                "sales",
                "INSERT INTO t (n) VALUES (99);",
                vec!["sale.voided".into()],
            ),
        );
        reg.listeners.insert(
            "sale.voided".into(),
            vec!["cash_register._reverse_sale".into()],
        );

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "sales.void",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();

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
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
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
            cmd(
                "appt",
                "INSERT INTO t (n) VALUES (1);",
                vec!["appt.reminder.due".into()],
            ),
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
        crate::settings::set_many(db, "h1", &s, "hub_user:admin")
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
        crate::commands::execute(
            &db,
            &reg,
            "appt.remind",
            &reminder_payload("cliente@x.com"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        assert!(
            transport.sent().is_empty(),
            "no se envía inline; va por el relay"
        );

        // Relay: entrega el evento → el transporte recibe la intención una vez.
        drain(&db, &reg).await.unwrap();
        let sent = transport.sent();
        assert_eq!(sent.len(), 1, "una entrega por el listener-host");
        assert_eq!(sent[0].0.channel, Channel::Email);
        assert_eq!(sent[0].0.to, "cliente@x.com");
        assert_eq!(
            sent[0].1,
            Routing::Tenant,
            "email = canal del tenant (secreto local)"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='host.notify'"
            )
            .await,
            1
        );

        // Idempotencia: re-drenar no re-envía.
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            transport.sent().len(),
            1,
            "idempotente (marcador host.notify)"
        );
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
        crate::commands::execute(
            &db,
            &reg,
            "appt.remind",
            &reminder_payload("cliente@x.com"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();

        assert!(
            transport.sent().is_empty(),
            "sin grant de `notify` no puede salir NADA del hub"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='host.notify'"
            )
            .await,
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
            &ctx,
            &Grants::new(),
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
        crate::commands::execute(
            &db,
            &reg,
            "appt.remind",
            &reminder_payload("cliente@x.com"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();

        // Primer ciclo: el envío falla → la fila se difiere (sigue 'pending', attempts=1, no 'dead').
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending'"
            )
            .await,
            1
        );
        assert_eq!(
            count(&db, "SELECT attempts AS c FROM _event_outbox").await,
            1,
            "1 intento fallido"
        );

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
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'"
            )
            .await,
            1,
            "dead-letter"
        );
    }

    /// Queues a message the way `flows::notify` does: **no module, a run, and the release the grant
    /// authorised**. That emptiness plus the `run_id` is what tells the relay this row carries a
    /// flow's authorisation (and is not something a module can fabricate).
    async fn seed_flow_notify(db: &PgAdapter, id: &str, run_id: &str, grant_id: &str, to: &str) {
        let mut payload = reminder_payload(to);
        payload.insert(
            crate::host_notify::RESOLVED_VIA_KEY.into(),
            json!(crate::host_notify::flow_grant_release(grant_id)),
        );
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("run_id".into(), json!(run_id));
        p.insert("name".into(), json!(FLOW_NOTIFY_EVENT));
        p.insert("payload".into(), json!(Json::Object(payload).to_string()));
        p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
        db.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, run_id, payload, status, \
              attempts, next_attempt_at, last_error, created_at) \
             VALUES (:id, 'h1', '', '[]', :name, '', :run_id, :payload, 'pending', 0, :at, '', :at)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn seed_flow_run(db: &PgAdapter, run_id: &str, flow_id: &str) {
        let mut p = Params::new();
        p.insert("id".into(), json!(run_id));
        p.insert("flow_id".into(), json!(flow_id));
        p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
        db.execute(
            "INSERT INTO _flow_runs (id, hub_id, flow_id, status, created_at, updated_at) \
             VALUES (:id, 'h1', :flow_id, 'done', :at, :at)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn one_text(db: &PgAdapter, sql: &str) -> String {
        let res = db.query(sql, &Params::new()).await.unwrap();
        res.rows
            .first()
            .and_then(|r| r["c"].as_str().map(|s| s.to_string()))
            .unwrap_or_default()
    }

    /// The twin of [`seed_flow_notify`] for a question that is going to be ANSWERED: same kernel
    /// row, plus the step that asked it, which is what `flows::notify` writes (hub#1951).
    async fn seed_flow_question(
        db: &PgAdapter,
        id: &str,
        run_id: &str,
        grant_id: &str,
        step_id: &str,
        to: &str,
    ) {
        let mut payload = reminder_payload(to);
        payload.insert(
            crate::host_notify::RESOLVED_VIA_KEY.into(),
            json!(crate::host_notify::flow_grant_release(grant_id)),
        );
        payload.insert(crate::host_notify::FLOW_STEP_KEY.into(), json!(step_id));
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("run_id".into(), json!(run_id));
        p.insert("name".into(), json!(FLOW_NOTIFY_EVENT));
        p.insert("payload".into(), json!(Json::Object(payload).to_string()));
        p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
        db.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, run_id, payload, status, \
              attempts, next_attempt_at, last_error, created_at) \
             VALUES (:id, 'h1', '', '[]', :name, '', :run_id, :payload, 'pending', 0, :at, '', :at)",
            &p,
        )
        .await
        .unwrap();
    }

    /// The two grants the release is read against, as rows — the same shape `grants::replace`
    /// writes, seeded directly here for the reason `seed_flow_run` is: this file tests the RELAY,
    /// and building a registry with a recipient query only to satisfy the grant validator would
    /// put the subject of the test one call further away.
    async fn seed_live_grants(db: &PgAdapter, flow_id: &str) -> String {
        let grant_id = format!("grant-{flow_id}");
        for (id, kind, value) in [
            (grant_id.clone(), "recipient_query", "appt.customer.get#email"),
            (format!("{grant_id}-notify"), "notify", "email"),
        ] {
            let mut p = Params::new();
            p.insert("id".into(), json!(id));
            p.insert("flow_id".into(), json!(flow_id));
            p.insert("kind".into(), json!(kind));
            p.insert("value".into(), json!(value));
            p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
            db.execute(
                "INSERT INTO _flow_grants \
                   (id, hub_id, flow_id, kind, value, payload, created_at, granted_by) \
                 VALUES (:id, 'h1', :flow_id, :kind, :value, '{}', :at, 'hub_user:1')",
                &p,
            )
            .await
            .unwrap();
        }
        grant_id
    }

    /// **hub#1951 — the delivery row is where the `wamid` and the step MEET.**
    ///
    /// At the instant of delivery the hub holds both halves for the first and only time: the id
    /// the provider just gave the message, and whose question it was. Nothing downstream can
    /// rebuild that pairing — the run that asked has finished, and the one that will read the tap
    /// is a different run altogether — so it is written down here or it is lost.
    #[tokio::test]
    async fn a_delivered_flow_question_records_the_provider_id_and_the_step_that_asked() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::naming(
            "wamid.the-question",
        )));

        seed_flow_run(&db, "run-1", "flow-1").await;
        let grant = seed_live_grants(&db, "flow-1").await;
        seed_flow_question(
            &db,
            "ev-1",
            "run-1",
            &grant,
            "confirm-appointment",
            "ana.perez@example.test",
        )
        .await;

        process_once(&db, &reg).await.unwrap();

        assert_eq!(
            one_text(
                &db,
                "SELECT provider_message_id AS c FROM _event_delivery WHERE event_id='ev-1'"
            )
            .await,
            "wamid.the-question",
            "the send has to bring its id back and the delivery has to keep it"
        );
        assert_eq!(
            who_asked(&db, "h1", "wamid.the-question")
                .await
                .unwrap()
                .step_id,
            "confirm-appointment",
            "and the lookup the poller does has to answer with the step that asked"
        );
    }

    /// **The three ways the lookup must answer NOTHING**, and the middle one is the dangerous one:
    /// every email delivery records an empty provider id, so a message that answers nothing would
    /// match the first of them and name a step nobody asked about.
    #[tokio::test]
    async fn a_question_of_another_hub_an_empty_id_and_an_unknown_id_all_name_no_step() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::naming(
            "wamid.the-question",
        )));

        seed_flow_run(&db, "run-1", "flow-1").await;
        let grant = seed_live_grants(&db, "flow-1").await;
        seed_flow_question(
            &db,
            "ev-1",
            "run-1",
            &grant,
            "confirm-appointment",
            "ana.perez@example.test",
        )
        .await;
        process_once(&db, &reg).await.unwrap();

        // **The row that makes the empty id dangerous**, and it is not hypothetical: the same
        // flow path delivered by a transport that names nothing — email, or a proxy older than
        // the field — records an empty `provider_message_id` next to a perfectly real step.
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::new()));
        seed_flow_question(
            &db,
            "ev-2",
            "run-1",
            &grant,
            "offer-reminder",
            "ana.perez@example.test",
        )
        .await;
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            one_text(
                &db,
                "SELECT step_id AS c FROM _event_delivery WHERE event_id='ev-2'"
            )
            .await,
            "offer-reminder",
            "the unnamed send really did record a step under an empty provider id"
        );

        assert_eq!(
            who_asked(&db, "h2", "wamid.the-question")
                .await
                .unwrap()
                .step_id,
            "",
            "one hub's question is not another hub's"
        );
        assert_eq!(
            who_asked(&db, "h1", "")
                .await
                .unwrap()
                .step_id,
            "",
            "a message that answers nothing names no step, and must not match the empty id every \
             email delivery writes"
        );
        assert_eq!(
            who_asked(&db, "h1", "wamid.never-sent")
                .await
                .unwrap()
                .step_id,
            "",
            "an id this hub never sent names no step"
        );
    }

    /// **A module cannot name a step it does not own** (hub#1951). `flow_step` rides in the
    /// payload, and a module's payload is a module's to write — so the relay honours the key only
    /// on the kernel's own row (`module_id` empty AND `run_id` present), which is the one shape a
    /// module cannot produce. A module writing it into its own `*.reminder.due` records nothing,
    /// and a tap on its message goes on answering no step rather than someone else's.
    #[tokio::test]
    async fn a_module_writing_the_step_key_into_its_own_payload_names_no_step() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::naming("wamid.borrowed")));
        authorize_notify(&db, &reg, "cliente@x.com").await;

        let mut payload = reminder_payload("cliente@x.com");
        payload.insert(
            crate::host_notify::FLOW_STEP_KEY.into(),
            json!("confirm-appointment"),
        );
        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "appt.remind", &payload, &ctx, &Grants::new())
            .await
            .unwrap();
        drain(&db, &reg).await.unwrap();

        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='host.notify'"
            )
            .await,
            1,
            "the message did go out — this is not about refusing the send"
        );
        assert_eq!(
            who_asked(&db, "h1", "wamid.borrowed").await.unwrap(),
            AskedBy::default(),
            "but the step a module wrote itself names nothing — and no flow either (hub#1962)"
        );
    }

    /// **hub#1962 — the step says WHICH question, the flow says WHOSE.**
    ///
    /// A step id is unique inside its flow (`def.rs` refuses the duplicate) and nowhere else: the
    /// same gallery recipe installed twice, or one flow exported and imported, asks with the very
    /// same `confirm-appointment` from two automations. The tap has to name the automation that
    /// sent the message too, or both believe the «Sí» was theirs and one confirms what the
    /// customer never confirmed.
    ///
    /// The flow is read from the RUN the kernel row carries, not from the payload — the same
    /// source the release check trusts — and one hub's question still names nothing in another.
    #[tokio::test]
    async fn two_flows_asking_with_the_same_step_id_are_told_apart_by_the_flow_that_asked() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);

        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::naming(
            "wamid.from-the-first",
        )));
        seed_flow_run(&db, "run-1", "flow-haircut").await;
        let first = seed_live_grants(&db, "flow-haircut").await;
        seed_flow_question(
            &db,
            "ev-1",
            "run-1",
            &first,
            "confirm-appointment",
            "ana.perez@example.test",
        )
        .await;
        process_once(&db, &reg).await.unwrap();

        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::naming(
            "wamid.from-the-second",
        )));
        seed_flow_run(&db, "run-2", "flow-colour").await;
        let second = seed_live_grants(&db, "flow-colour").await;
        seed_flow_question(
            &db,
            "ev-2",
            "run-2",
            &second,
            "confirm-appointment",
            "ana.perez@example.test",
        )
        .await;
        process_once(&db, &reg).await.unwrap();

        let a = who_asked(&db, "h1", "wamid.from-the-first").await.unwrap();
        let b = who_asked(&db, "h1", "wamid.from-the-second").await.unwrap();
        assert_eq!(
            (a.step_id.as_str(), b.step_id.as_str()),
            ("confirm-appointment", "confirm-appointment"),
            "the two questions really are the same step of the same recipe"
        );
        assert_eq!(
            a.flow_id, "flow-haircut",
            "the first tap belongs to the automation that sent the first message"
        );
        assert_eq!(
            b.flow_id, "flow-colour",
            "and the second to its sibling, not to whichever was installed first"
        );
        assert_eq!(
            who_asked(&db, "h2", "wamid.from-the-first").await.unwrap(),
            AskedBy::default(),
            "one hub's question names no flow of it in another hub"
        );
    }

    /// **hub#827 — a revoked authorisation is a definitive NO, not a stumble.**
    ///
    /// Revoking `recipient_query` with a message already queued stops the send, and that half is
    /// right (§5) and is not what this covers. What was wrong is everything after it: the row spent
    /// its **eight attempts** against a permission that was never coming back, and every one of
    /// them was work the hub did knowing the answer.
    ///
    /// The relay now asks a different question of a failure — *can this ever succeed?* — and a
    /// release that no longer exists answers no. The row is terminal on the first pass, with its
    /// own [`FAILURE_RELEASE_REVOKED`] so the queue can say why and the retry can refuse.
    #[tokio::test]
    async fn a_notify_whose_release_was_revoked_dies_at_once_instead_of_burning_eight_attempts() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());

        // The run exists; the grant it names does NOT — the owner revoked it while the message was
        // in the queue, which is exactly the QA's step 5.
        seed_flow_run(&db, "run-1", "flow-1").await;
        seed_flow_notify(&db, "ev-1", "run-1", "grant-gone", "ana.perez@example.test").await;

        process_once(&db, &reg).await.unwrap();

        assert!(transport.sent().is_empty(), "revoking has to stop the send");
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'"
            )
            .await,
            1,
            "a revoked release is terminal on the first pass, not after eight"
        );
        assert_eq!(
            count(
                &db,
                "SELECT attempts AS c FROM _event_outbox WHERE id='ev-1'"
            )
            .await,
            0,
            "no retry ladder was climbed against an answer that is not coming back"
        );
        assert_eq!(
            one_text(
                &db,
                "SELECT failure_kind AS c FROM _event_outbox WHERE id='ev-1'"
            )
            .await,
            FAILURE_RELEASE_REVOKED,
            "the queue records WHY, so the screen and the retry do not have to guess"
        );
    }

    /// **hub#827 — the address does not stay in the dead-letter.**
    ///
    /// `flows::notify` justifies putting the recipient in the queue row precisely because that row
    /// «TIENE que llevarlo»: the transport needs an address to dial, which is why the run history
    /// shows `recipient_redacted` and the queue does not. A row that can never be delivered stops
    /// having to carry it — and the ninety days it would otherwise sit in the operator's dead-letter
    /// are ninety days of keeping the contact the owner had just decided not to use.
    ///
    /// The rest of the payload stays: the channel, the template, the copy the owner wrote and the
    /// release that authorised it are what let an operator tell this row from noise, and none of
    /// them is the customer's.
    #[tokio::test]
    async fn the_dead_letter_of_a_revoked_notify_keeps_the_decision_and_drops_the_recipient() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::new()));
        seed_flow_run(&db, "run-1", "flow-1").await;
        seed_flow_notify(&db, "ev-1", "run-1", "grant-gone", "ana.perez@example.test").await;

        process_once(&db, &reg).await.unwrap();

        let dead = list_dead(&db, "h1", 10).await.unwrap();
        assert_eq!(dead.len(), 1);
        let payload = &dead[0].payload;
        let whole = payload.to_string();
        assert!(
            !whole.contains("ana.perez@example.test"),
            "the customer's address is still in the queue an operator reads: {whole}"
        );
        assert_eq!(payload["recipient_redacted"], json!(true), "{whole}");
        // Not blind: what the OWNER decided is all still there.
        assert_eq!(payload["channel"], json!("email"));
        assert_eq!(payload["template"], json!("appointment_reminder"));
        assert_eq!(payload["vars"]["when"], json!("10:00"));
        assert!(
            payload[crate::host_notify::RESOLVED_VIA_KEY]
                .as_str()
                .unwrap_or_default()
                .contains("grant-gone"),
            "the release that authorised it names the grant to restore: {whole}"
        );
        assert!(
            dead[0].last_error.contains("REVOC"),
            "and the reason is readable: {}",
            dead[0].last_error
        );
    }

    /// **hub#827 — the button must not lie.**
    ///
    /// `Reintentar` on a revoked row returned `200`, reset `attempts` to `0` and let the row die
    /// again for the same reason: a loop with no exit, offered by the screen as the remedy. It is
    /// the rule §13.6 already applies to the rate-guard — retrying a runaway forever is the same
    /// runaway. The refusal names its own reason, so the screen can say what to do instead
    /// (re-grant the permission and run the flow again) rather than showing a dead end.
    ///
    /// The bulk gesture skips them for the same reason: `retry-all` exists for a transient outage
    /// that is now fixed, and this is not one.
    #[tokio::test]
    async fn a_revoked_dead_letter_refuses_the_retry_instead_of_promising_one() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        reg.notify_transport = Some(std::sync::Arc::new(MockTransport::new()));
        seed_flow_run(&db, "run-1", "flow-1").await;
        seed_flow_notify(&db, "ev-1", "run-1", "grant-gone", "ana.perez@example.test").await;
        process_once(&db, &reg).await.unwrap();

        match retry(&db, "h1", "ev-1").await.unwrap() {
            RetryOutcome::NotRetryable { failure_kind } => {
                assert_eq!(failure_kind, FAILURE_RELEASE_REVOKED)
            }
            other => panic!("a retry that can never work must be refused, got {other:?}"),
        }
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'"
            )
            .await,
            1,
            "and the row stays where it was, not back on the relay"
        );

        assert_eq!(
            retry_all(&db, "h1").await.unwrap(),
            0,
            "the bulk gesture is for a cause that got fixed; a revocation is not one"
        );

        // A dead-letter that CAN be retried still is: the refusal is about this failure, not about
        // the gesture.
        seed_row(&db, "d1", "h1", STATUS_DEAD).await;
        assert!(matches!(
            retry(&db, "h1", "d1").await.unwrap(),
            RetryOutcome::Requeued
        ));
        assert!(matches!(
            retry(&db, "h1", "nope").await.unwrap(),
            RetryOutcome::NotFound
        ));
    }

    /// **hub#142 — un listener que falla NO bloquea a sus hermanos.** Antes, `process_row`
    /// hacía `return defer_or_dead(...)` al primer fallo: si `cash_register._reverse_sale`
    /// reventaba, `inventory._restock_on_void` (otro listener del MISMO `sale.voided`) no corría
    /// ni ese ciclo ni hasta que el primero tuviera éxito en su reintento. Ahora cada listener es
    /// independiente: el que falla se difiere (backoff) y los demás se entregan igual.
    #[tokio::test]
    async fn one_failing_listener_does_not_block_sibling_listeners() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        system_schema(&db).await;

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
            cmd(
                "sales",
                "INSERT INTO t (n) VALUES (99);",
                vec!["sale.voided".into()],
            ),
        );
        reg.listeners.insert(
            "sale.voided".into(),
            vec!["bad.listener".into(), "good.listener".into()],
        );

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "sales.void",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();

        // Un solo ciclo del relay: "good.listener" se entrega AUNQUE "bad.listener" falla antes.
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "el listener bueno corre aunque su hermano falle (hub#142)"
        );
        // La entrega del bueno queda marcada (idempotente); la del malo, no.
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='good.listener'"
            )
            .await,
            1,
            "el listener bueno quedó marcado como entregado"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='bad.listener'"
            )
            .await,
            0,
            "el listener malo NO se marcó (falló) → se reintenta"
        );
        // La fila NO se marca 'delivered' (un listener falló): queda diferida para reintento.
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending'"
            )
            .await,
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
        db.execute("UPDATE _event_outbox SET next_attempt_at = :a", &p)
            .await
            .unwrap();
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
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        system_schema(&db).await;

        // "poison.fire" emite "poison.e" cuyo ÚNICO listener revienta (columna inexistente).
        // "ok.fire" emite "ok.e" cuyo listener inserta n=1. Disparamos "poison" ANTES para que su
        // fila quede ORDENADA PRIMERO por created_at → si el bug siguiera vivo, "ok.e" no se entregaría.
        let mut reg = Registry::new();
        for m in ["poison", "ok"] {
            reg.status.insert(m.into(), ModuleStatus::Active);
        }
        reg.commands.insert(
            "poison.listener".into(),
            cmd(
                "poison",
                "INSERT INTO t (no_such_column) VALUES (1);",
                vec![],
            ),
        );
        reg.commands.insert(
            "ok.listener".into(),
            cmd("ok", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "poison.fire".into(),
            cmd(
                "poison",
                "INSERT INTO t (n) VALUES (99);",
                vec!["poison.e".into()],
            ),
        );
        reg.commands.insert(
            "ok.fire".into(),
            cmd("ok", "INSERT INTO t (n) VALUES (99);", vec!["ok.e".into()]),
        );
        reg.listeners
            .insert("poison.e".into(), vec!["poison.listener".into()]);
        reg.listeners
            .insert("ok.e".into(), vec!["ok.listener".into()]);

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "poison.fire",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        crate::commands::execute(&db, &reg, "ok.fire", &Params::new(), &ctx, &Grants::new())
            .await
            .unwrap();

        // Un solo ciclo del relay procesa AMBAS filas (BATCH=50). La venenosa falla y se difiere;
        // la sana se entrega igual. Sin el fix, "ok.listener" no correría (n=1 sería 0 aquí).
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            1,
            "la fila sana se entrega aunque la venenosa (anterior en el lote) falle (hub#142)"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='ok.listener'"
            )
            .await,
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
        system_schema(&db_a).await;

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
        system_schema(&db).await;

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
        assert!(
            claimed.is_some(),
            "an expired lease is reclaimed (orphan recovery)"
        );
        assert_eq!(claimed.as_ref().unwrap()["id"].as_str(), Some("evt-1"));
    }

    // ── Operable dead-letter (hub#660 — ADR-0127 phase 2 · ADR-0283 K6a) ───────────────────────

    /// A hub holding exactly one dead-letter. `m.fire` emits `e`, whose only listener `m.apply`
    /// explodes on every attempt, so the row burns [`MAX_ATTEMPTS`] and lands in `dead`.
    ///
    /// The shape this was written for — an employee closes a sale, `verifactu.records.ingest_invoice`
    /// demands a permission the emitter does not carry, eight attempts later the invoice is dead —
    /// is gone at the source (hub#686: a listener runs with its module's authority, not the
    /// cashier's role). What is left is what will always be left: a listener that is simply broken.
    async fn hub_with_a_dead_letter() -> (PgAdapter, Registry) {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        system_schema(&db).await;

        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        // Listener that always fails (unknown column) — from the relay's point of view a refused
        // listener and a broken one are the same thing: `execute_at` returns `Err`.
        reg.commands.insert(
            "m.apply".into(),
            cmd("m", "INSERT INTO t (no_such_column) VALUES (1);", vec![]),
        );
        reg.commands.insert(
            "m.fire".into(),
            cmd("m", "INSERT INTO t (n) VALUES (99);", vec!["e".into()]),
        );
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
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'"
            )
            .await,
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
        reg.commands.insert(
            "m.apply".into(),
            cmd("m", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        assert_eq!(
            retry(&db, "h1", &dead_id(&db).await).await.unwrap(),
            RetryOutcome::Requeued,
            "the row was requeued"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending' AND attempts=0"
            )
            .await,
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
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            1
        );

        // Only a dead-letter is replayable: replaying a delivered row is not an operator gesture.
        assert_eq!(
            retry(&db, "h1", &id_of(&db, "delivered").await)
                .await
                .unwrap(),
            RetryOutcome::NotFound
        );
    }

    /// `discard` closes a dead-letter without deleting it: the row STAYS, stamped with who
    /// discarded it and when, and the relay never touches it again. Deleting would destroy the only
    /// record that the event existed at all — the audit trail is the point.
    #[tokio::test]
    async fn discard_keeps_the_row_auditable_and_the_relay_never_takes_it_again() {
        let (db, mut reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;

        assert!(discard(&db, "h1", &id, "hub_user:admin-1", "")
            .await
            .unwrap());

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
        assert!(rows[0]["discarded_at"]
            .as_str()
            .is_some_and(|s| !s.is_empty()));
        assert!(
            rows[0]["payload"]
                .as_str()
                .is_some_and(|s| s.contains("F2-1")),
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
            claim_next_due(&db, "2026-01-01T00:00:00+00:00")
                .await
                .unwrap()
                .is_none(),
            "the relay never claims a discarded row"
        );
        reg.commands.insert(
            "m.apply".into(),
            cmd("m", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await,
            0,
            "a discarded event is never delivered"
        );

        // And it drops off the operator's list: discarding is what makes the queue drainable.
        assert!(list_dead(&db, "h1", 50).await.unwrap().is_empty());
    }

    /// Reads back the stored `discard_reason` of one row.
    async fn reason_of(db: &dyn DatabaseAdapter, id: &str) -> String {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        let rows = db
            .query(
                "SELECT discard_reason FROM _event_outbox WHERE id = :id",
                &p,
            )
            .await
            .unwrap()
            .rows;
        rows[0]["discard_reason"]
            .as_str()
            .unwrap_or_default()
            .to_string()
    }

    /// **A decision that does not say WHY is half a record** (hub#955).
    ///
    /// The row already survived the gesture stamped with who closed it and when. What it could not
    /// answer was the only question anybody asks six months later: why. Without it the sole reading
    /// left of a closed dead-letter is «somebody discarded this», which is the half that needed no
    /// storing. The reason is stored TRIMMED — a text area hands back the whitespace the operator
    /// typed around it, and «duplicada» and « duplicada » are not two different decisions.
    #[tokio::test]
    async fn discard_records_why_it_was_closed() {
        let (db, _reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;

        assert!(discard(
            &db,
            "h1",
            &id,
            "hub_user:admin-1",
            "  duplicada: la factura se registró a mano  "
        )
        .await
        .unwrap());

        assert_eq!(
            reason_of(&db, &id).await,
            "duplicada: la factura se registró a mano",
            "the reason survives the click, trimmed"
        );
    }

    /// The reason is **optional** and **bounded**. Optional because the gesture existed before it
    /// did and demanding an essay to close a row is how a queue stops being drained; bounded
    /// because this text arrives from a request body and the row is kept for ninety days —
    /// unbounded free text on a table the relay scans is not an audit trail, it is a hole. Absent
    /// reads back as the empty string, never NULL: every other additive column of this table
    /// carries a `NOT NULL DEFAULT ''` and a reader should not have to know which.
    #[tokio::test]
    async fn a_discard_reason_is_optional_and_bounded() {
        let (db, _reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;
        assert!(discard(&db, "h1", &id, "hub_user:admin-1", "   ")
            .await
            .unwrap());
        assert_eq!(
            reason_of(&db, &id).await,
            "",
            "no reason given is the empty string — the row is closed all the same"
        );

        // A caller that pastes a log into the field gets a bounded column, cut on a CHARACTER
        // boundary: truncating «é» in the middle is a panic in Rust and mojibake everywhere else.
        let (db2, _reg2) = hub_with_a_dead_letter().await;
        let id2 = dead_id(&db2).await;
        let essay = "é".repeat(MAX_DISCARD_REASON + 50);
        assert!(discard(&db2, "h1", &id2, "hub_user:admin-1", &essay)
            .await
            .unwrap());
        let stored = reason_of(&db2, &id2).await;
        assert_eq!(
            stored.chars().count(),
            MAX_DISCARD_REASON,
            "the stored reason is capped at {MAX_DISCARD_REASON} characters"
        );
        assert!(
            stored.chars().all(|c| c == 'é'),
            "and cut where a character ends"
        );
    }

    /// Neither gesture crosses hubs, and neither invents a row: an unknown id is simply `false`.
    #[tokio::test]
    async fn retry_and_discard_are_scoped_to_the_hub() {
        let (db, _reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;

        assert_eq!(
            retry(&db, "other-hub", &id).await.unwrap(),
            RetryOutcome::NotFound,
            "another hub cannot replay it"
        );
        assert!(!discard(&db, "other-hub", &id, "hub_user:x", "")
            .await
            .unwrap());
        assert_eq!(
            retry(&db, "h1", "no-such-event").await.unwrap(),
            RetryOutcome::NotFound
        );
        assert!(!discard(&db, "h1", "no-such-event", "hub_user:x", "")
            .await
            .unwrap());
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'"
            )
            .await,
            1,
            "the dead-letter is untouched"
        );
    }

    // ───────────── hub#1117 — a discard reason nobody can read is not an audit trail ─────────────
    //
    // `discard` has stamped the row with who, when and WHY since hub#955, and every one of the
    // three was write-only: `list_dead` filters `status = 'dead'`, so the moment a row is closed it
    // leaves the only listing there was, and `trace_event` projects none of the three columns. The
    // tray promises on screen «el hub guarda quién cerró cada uno, cuándo y por qué durante noventa
    // días» and the only way to check that sentence was `psql`.
    //
    // [`list_discarded`] is the reading half of the gesture, and it is deliberately the sibling of
    // [`list_dead`] and not a filter parameter on it: the two lists answer different questions —
    // «what needs me» versus «what did we decide» — and a queue that mixes the closed rows into the
    // work is a queue that stops being drained.

    /// Seeds a row that a NEIGHBOUR hub closed by hand: same table, another tenant, a reason of its
    /// own. Written straight to the row because that is the state `discard` leaves behind, and the
    /// point of the test is what the listing does with it, not how it got there.
    async fn seed_foreign_discarded(db: &PgAdapter, hub_id: &str, id: &str, reason: &str) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("reason".into(), json!(reason));
        p.insert("status".into(), json!(STATUS_DISCARDED));
        db.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, status, \
              attempts, next_attempt_at, last_error, created_at, discarded_at, discarded_by, \
              discard_reason) \
             VALUES (:id, :hub_id, 'u9', '[]', 'flow.reminder.due', 'flows', '{}', 0, :status, \
                     7, '2026-08-20T09:00:00+00:00', 'host.notify: the hub is not enrolled', \
                     '2026-08-20T09:00:00+00:00', '2026-08-21T09:00:00+00:00', \
                     'hub_user:neighbour-admin', :reason)",
            &p,
        )
        .await
        .unwrap();
    }

    /// **The whole point of hub#1117**: after the row is closed, the three parts of the stamp —
    /// who, when and why — come back over an ordinary read, without opening the database.
    ///
    /// The reason is the half that only the person closing the row knows, so losing it is losing
    /// the decision itself. The other two travel WITH it because an audit trail is the three
    /// together: «somebody closed this» and «closed because duplicada» answer different halves of
    /// the same question six months later.
    #[tokio::test]
    async fn the_discard_reason_survives_the_close_and_is_readable_hub1117() {
        let (db, _reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;

        assert!(
            list_discarded(&db, "h1", 50).await.unwrap().is_empty(),
            "nothing closed yet"
        );

        assert!(discard(
            &db,
            "h1",
            &id,
            "hub_user:admin-1",
            "  duplicada: la factura se registró a mano  "
        )
        .await
        .unwrap());

        // It left the queue of what needs attention — that is what closing it means…
        assert!(list_dead(&db, "h1", 50).await.unwrap().is_empty());

        // …and it is READABLE in the closed listing, with the whole stamp.
        let closed = list_discarded(&db, "h1", 50).await.unwrap();
        assert_eq!(closed.len(), 1, "the closed row is listed");
        let row = &closed[0];
        assert_eq!(row.id, id);
        assert_eq!(row.event_name, "e");
        assert_eq!(row.module_id, "m", "the EMITTING module, as in `list_dead`");
        assert_eq!(
            row.discard_reason, "duplicada: la factura se registró a mano",
            "the reason is readable over the API, not only in psql"
        );
        assert_eq!(row.discarded_by, "hub_user:admin-1", "WHO closed it");
        assert!(!row.discarded_at.is_empty(), "WHEN it was closed");
        assert!(
            row.last_error.contains("m.apply"),
            "why it died in the first place travels too: {}",
            row.last_error
        );
        assert!(!row.created_at.is_empty());
    }

    /// A neighbour's closed rows are not ours. This seeds a REAL discarded row of another tenant —
    /// asking for a hub that has nothing in it proves nothing at all — and checks both directions:
    /// ours never shows theirs, and theirs IS there when its own hub asks, so a listing that
    /// returned nothing by accident could not pass this.
    #[tokio::test]
    async fn discarded_list_is_scoped_to_this_hub_hub1117() {
        let (db, _reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;
        assert!(discard(&db, "h1", &id, "hub_user:admin-1", "nuestra")
            .await
            .unwrap());
        seed_foreign_discarded(&db, "other-hub", "evt-neighbour", "la del vecino").await;

        let ours = list_discarded(&db, "h1", 50).await.unwrap();
        assert_eq!(ours.len(), 1, "only our own closed row");
        assert_eq!(ours[0].id, id);
        assert!(
            !ours.iter().any(|r| r.discard_reason.contains("vecino")),
            "a neighbour's reason never reaches this hub's audit listing"
        );

        // The control detects the positive: the row IS there, and its own hub sees it.
        let theirs = list_discarded(&db, "other-hub", 50).await.unwrap();
        assert_eq!(theirs.len(), 1, "the seeded neighbour row exists");
        assert_eq!(theirs[0].discard_reason, "la del vecino");
    }

    /// The listing is newest-closed first and bounded, like [`list_dead`]: it feeds a tray that
    /// renders a page, and «ninety days of a busy hub» is not a page.
    #[tokio::test]
    async fn the_discarded_listing_is_newest_first_and_capped_hub1117() {
        let (db, _reg) = hub_with_a_dead_letter().await;
        let id = dead_id(&db).await;
        assert!(discard(&db, "h1", &id, "hub_user:admin-1", "la reciente")
            .await
            .unwrap());
        // An older closure of THIS hub, stamped a month before the one above.
        seed_foreign_discarded(&db, "h1", "evt-older", "la antigua").await;

        let closed = list_discarded(&db, "h1", 50).await.unwrap();
        assert_eq!(closed.len(), 2);
        assert_eq!(
            closed[0].discard_reason, "la reciente",
            "newest closure first"
        );
        assert_eq!(closed[1].discard_reason, "la antigua");

        assert_eq!(
            list_discarded(&db, "h1", 1).await.unwrap().len(),
            1,
            "the limit is honoured"
        );
        assert_eq!(
            list_discarded(&db, "h1", i64::MAX).await.unwrap().len(),
            2,
            "an absurd limit is clamped, never a table dump"
        );
    }

    // ───────────── hub#686 — with WHOSE authority does a listener run? ─────────────
    //
    // The relay used to rebuild the EMITTER's `RequestContext` — permissions included — and run
    // the listener under it. So the reaction to an event only happened if the human who triggered
    // it happened to hold a permission over a command of ANOTHER module. In the catalogue as
    // published, the cashier (`employee`) holds none of them: they close a sale and the stock does
    // not come down, the customer's purchase is not recorded, and the invoice is not sent to the
    // AEAT. Eight retries later the event is a dead-letter, and until hub#660 that was invisible.
    //
    // The reaction to an event is a decision of the MODULE, in its manifest — not an action of the
    // user. So the listener runs with the module's own authority, keeping the emitter's `user_id`
    // for the audit trail and the `hub_id`, which is never negotiable.

    /// A command that actually demands a permission (the base [`cmd`] helper declares none).
    fn gated_cmd(
        module: &str,
        permission: &str,
        sql: &str,
        emit: Vec<crate::manifest::EmitDef>,
    ) -> RegisteredCommand {
        let mut c = cmd(module, sql, emit);
        c.def.permission = permission.to_string();
        c
    }

    /// The cast of the real bug: `sales` emits `sale.completed`, `inventory` reacts with a command
    /// of its OWN gated on `inventory.change_product` — a permission the cashier deliberately does
    /// not have, because editing the catalogue is not their job.
    async fn till_with_a_cashier() -> (PgAdapter, Registry, RequestContext) {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE sales_log (id TEXT);\
             CREATE TABLE stock_moves (hub_id TEXT NOT NULL, created_by TEXT NOT NULL);",
        )
        .await
        .unwrap();
        system_schema(&db).await;

        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.status.insert("inventory".into(), ModuleStatus::Active);
        reg.commands.insert(
            "sales.complete_sale".into(),
            gated_cmd(
                "sales",
                "sales.add_sale",
                "INSERT INTO sales_log (id) VALUES (:new_id);",
                vec!["sale.completed".into()],
            ),
        );
        reg.commands.insert(
            "inventory.stock.decrease_on_sale".into(),
            gated_cmd(
                "inventory",
                "inventory.change_product",
                "INSERT INTO stock_moves (hub_id, created_by) VALUES (:hub_id, :current_user_id);",
                vec![],
            ),
        );
        reg.listeners.insert(
            "sale.completed".into(),
            vec!["inventory.stock.decrease_on_sale".into()],
        );

        // The cashier: may sell, may look at the catalogue, may not edit it.
        let cashier = RequestContext::new(
            "h1",
            "hub_user:ana",
            [
                "sales.add_sale".to_string(),
                "inventory.view_product".to_string(),
            ],
        );
        (db, reg, cashier)
    }

    /// **The bug.** A cashier closes a sale and the stock comes down — the same as when the owner
    /// is at the till. Before hub#686 this listener died with `PermissionDenied` on every single
    /// sale an `employee` made, and the hub's inventory diverged from reality from sale one.
    #[tokio::test]
    async fn a_listener_runs_even_when_the_cashier_lacks_its_permission() {
        let (db, reg, cashier) = till_with_a_cashier().await;

        crate::commands::execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &cashier,
            &Grants::new(),
        )
        .await
        .expect("selling is what a cashier is FOR");
        drain(&db, &reg).await.unwrap();

        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM stock_moves").await,
            1,
            "the stock came down: reacting to the sale is the MODULE's decision, not the cashier's"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            1,
            "the event is delivered, not deferred"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'"
            )
            .await,
            0,
            "no dead-letter: this was the structural one that hid a fiscal breach"
        );
    }

    /// The `hub_id` is NOT part of what gets relaxed (tenancy.md): the listener writes in the hub
    /// of the event it is reacting to, and in no other. It is the one thing the relay may never
    /// take from anywhere but the row.
    #[tokio::test]
    async fn a_listener_stays_in_the_hub_that_emitted_the_event() {
        let (db, reg, cashier) = till_with_a_cashier().await;

        crate::commands::execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &cashier,
            &Grants::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();

        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM stock_moves WHERE hub_id = 'h1'"
            )
            .await,
            1,
            "the tenant of the emitter, never a system-wide or empty hub_id"
        );
    }

    /// Running with the module's authority must not cost the audit trail. `:current_user_id` — what
    /// every module binds into `created_by`/`updated_by` — stays the human who caused the event: a
    /// stock movement stamped "system" when Ana's sale produced it is a traceability regression,
    /// and the whole reason this is not simply `scheduler::system_ctx` (which has no user at all).
    #[tokio::test]
    async fn a_listener_credits_the_user_whose_action_caused_it() {
        let (db, reg, cashier) = till_with_a_cashier().await;

        crate::commands::execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &cashier,
            &Grants::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();

        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM stock_moves WHERE created_by = 'hub_user:ana'"
            )
            .await,
            1,
            "the cashier who sold is who the row is attributed to, not the runtime"
        );
        // And the row of the event keeps the same attribution, so the dead-letter queue (hub#660)
        // and any forensics can still answer «who caused this».
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE user_id = 'hub_user:ana'"
            )
            .await,
            1
        );
    }

    /// **What does NOT come down with the permission gate.** The fiscal preconditions (ADR-0203)
    /// cover listeners on purpose — `invoice.create_from_sale` and `verifactu.records.ingest_invoice`
    /// run here — and they key on the hub's identity, never on a permission. A listener that stamps
    /// the issuer into a document still refuses while that identity is missing: the alternative is
    /// an invoice with a BLANK issuer that VeriFactu then chains from (ADR-0189).
    #[tokio::test]
    async fn the_fiscal_precondition_still_stops_a_listener_that_stamps_the_issuer() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE sales_log (id TEXT);\
             CREATE TABLE fiscal_records (issuer TEXT);",
        )
        .await
        .unwrap();
        ensure_tables(&db).await.unwrap();

        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.status.insert("verifactu".into(), ModuleStatus::Active);
        reg.commands.insert(
            "sales.complete_sale".into(),
            gated_cmd(
                "sales",
                "sales.add_sale",
                "INSERT INTO sales_log (id) VALUES (:new_id);",
                vec!["invoice.created".into()],
            ),
        );
        reg.commands.insert(
            "verifactu.records.ingest_invoice".into(),
            gated_cmd(
                "verifactu",
                "verifactu.manage_verifactu",
                "INSERT INTO fiscal_records (issuer) VALUES (:business_tax_id);",
                vec![],
            ),
        );
        reg.listeners.insert(
            "invoice.created".into(),
            vec!["verifactu.records.ingest_invoice".into()],
        );

        // No business identity configured in this hub — the precondition the gate exists for.
        let cashier = RequestContext::new("h1", "hub_user:ana", ["sales.add_sale".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "sales.complete_sale",
            &Params::new(),
            &cashier,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();

        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM fiscal_records").await,
            0,
            "no fiscal record is written without the hub's identity, whatever the authority"
        );
        let last_error = db
            .query("SELECT last_error FROM _event_outbox", &Params::new())
            .await
            .unwrap()
            .rows[0]["last_error"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        assert!(
            last_error.contains("fiscal precondition"),
            "the refusal is the fiscal gate, not a permission: {last_error}"
        );
    }

    /// The context itself, stated once. Everything above is this in motion.
    #[test]
    fn the_listener_context_carries_the_hub_and_the_user_but_the_modules_authority() {
        let row = json!({
            "hub_id": "h1",
            "user_id": "hub_user:ana",
            // What the emitter could do. Kept in the row for forensics; no longer what authorises
            // the listener, which is the whole of hub#686.
            "permissions": r#"["sales.add_sale"]"#,
        });

        let ctx = listener_ctx(&row);

        assert_eq!(ctx.hub_id, "h1", "the tenant is never negotiable");
        assert_eq!(
            ctx.user_id, "hub_user:ana",
            "who caused it survives, for `created_by` and for the dead-letter queue"
        );
        assert!(
            ctx.permissions.contains("*"),
            "the module's own authority, not the cashier's role"
        );
        assert!(
            !ctx.permissions.contains("sales.add_sale"),
            "the emitter's permissions are not what the listener runs on any more"
        );
        assert_eq!(
            ctx.principal,
            Principal::Machine,
            "nobody is standing at the relay: it must never be offered a manager's PIN (hub#361)"
        );
    }

    /// A core event ingested from OUTSIDE the hub (ADR-0283 K1c: an inbound WhatsApp message)
    /// carries an id the caller chose, so the source's own message id becomes the primary key.
    /// Written once, it is a normal outbox row: `pending`, with the hub's tenant on it.
    #[tokio::test]
    async fn a_core_event_lands_in_the_outbox_under_the_caller_s_id() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();

        let mut payload = Params::new();
        payload.insert("from".into(), json!("34600999888"));
        let fresh = insert_core_event_once(
            &db,
            "wa-wamid.1",
            "hub-7",
            "hub.whatsapp.message_received",
            &payload,
        )
        .await
        .unwrap();
        assert!(fresh, "the first write of an id is a new event");

        let rows = db
            .query("SELECT * FROM _event_outbox", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["id"], json!("wa-wamid.1"));
        assert_eq!(rows[0]["hub_id"], json!("hub-7"));
        assert_eq!(
            rows[0]["event_name"],
            json!("hub.whatsapp.message_received")
        );
        assert_eq!(rows[0]["status"], json!("pending"));
        assert_eq!(
            rows[0]["payload"].as_str().unwrap(),
            r#"{"from":"34600999888"}"#
        );
    }

    /// **The primary key IS the exactly-once guarantee.** The source redelivers whatever it has
    /// not seen acked, so the same message arrives more than once by design; the second write must
    /// be a no-op that says so, not an error and not a second event.
    #[tokio::test]
    async fn the_same_id_twice_is_one_event_and_the_second_write_says_it_was_already_there() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();

        let mut first = Params::new();
        first.insert("text".into(), json!("is the table free?"));
        assert!(insert_core_event_once(&db, "wa-wamid.1", "h", "e", &first)
            .await
            .unwrap());

        // A redelivery of the SAME message: different payload on purpose — the id decides, and the
        // row that is already there must not be overwritten either.
        let mut second = Params::new();
        second.insert("text".into(), json!("tampered"));
        let fresh = insert_core_event_once(&db, "wa-wamid.1", "h", "e", &second)
            .await
            .unwrap();
        assert!(!fresh, "a duplicate id is not a new event");

        let rows = db
            .query("SELECT payload FROM _event_outbox", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(
            rows.len(),
            1,
            "exactly one event, however many times it arrives"
        );
        assert_eq!(
            rows[0]["payload"].as_str().unwrap(),
            r#"{"text":"is the table free?"}"#
        );
    }

    /// A duplicate must not resurrect an event the relay already delivered: `ON CONFLICT DO
    /// NOTHING` leaves the row exactly as it was, so a listener does not run twice.
    #[tokio::test]
    async fn a_duplicate_does_not_reopen_an_already_delivered_event() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();

        insert_core_event_once(&db, "wa-1", "h", "e", &Params::new())
            .await
            .unwrap();
        mark_delivered(&db, "wa-1").await.unwrap();

        insert_core_event_once(&db, "wa-1", "h", "e", &Params::new())
            .await
            .unwrap();
        let rows = db
            .query("SELECT status FROM _event_outbox", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1);
        assert_eq!(
            rows[0]["status"],
            json!("delivered"),
            "still delivered, not pending again"
        );
    }

    /// Delivery contract of a host-emitted event (ADR-0288): it reaches the listening module's
    /// command and that command runs with ITS OWN module's authority. There is no emitting user —
    /// the message came from a customer's phone — so `user_id` is empty, exactly as the
    /// scheduler's system context does.
    #[tokio::test]
    async fn a_core_event_is_delivered_to_its_listeners_with_no_emitting_user() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        // The WHOLE system schema, not just the outbox's two tables: this test DRAINS, and since
        // hub#661 the relay asks `_flow_triggers` whether the event it just delivered starts a
        // flow. With half a schema that question errors, the row is deferred instead of delivered,
        // and the test says "pending" for a reason that has nothing to do with what it is about.
        system_schema(&db).await;

        let mut reg = Registry::new();
        reg.status.insert("wa".into(), ModuleStatus::Active);
        reg.commands.insert(
            "wa.on_message".into(),
            cmd("wa", "INSERT INTO t (n) VALUES (1);", vec![]),
        );
        reg.listeners.insert(
            "hub.whatsapp.message_received".into(),
            vec!["wa.on_message".into()],
        );

        insert_core_event_once(
            &db,
            "wa-1",
            "h",
            "hub.whatsapp.message_received",
            &Params::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();

        assert_eq!(count(&db, "SELECT COUNT(*) AS c FROM t WHERE n=1").await, 1);
        let rows = db
            .query("SELECT user_id, status FROM _event_outbox", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(
            rows[0]["user_id"],
            json!(""),
            "nobody in this hub caused it"
        );
        assert_eq!(rows[0]["status"], json!("delivered"));
    }

    // ── Correlation (hub#666) ─────────────────────────────────────────────────────────────────

    /// A cascade event names the event whose delivery caused it.
    ///
    /// `depth` said how FAR a cascade had gone; it never said **from what**. On a till closing two
    /// sales a second, "the row before it in time" is not an answer, so without this column the
    /// chain that produced a row is not reconstructible at all — only guessable.
    #[tokio::test]
    async fn a_cascade_event_names_the_event_whose_delivery_caused_it() {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE t (n INTEGER);")
            .await
            .unwrap();
        system_schema(&db).await;

        // "m.fire" emits "e"; its listener "m.append" emits "f" — a two-link chain.
        let mut reg = Registry::new();
        reg.status.insert("m".into(), ModuleStatus::Active);
        reg.commands.insert(
            "m.append".into(),
            cmd("m", "INSERT INTO t (n) VALUES (1);", vec!["f".into()]),
        );
        reg.commands.insert(
            "m.fire".into(),
            cmd("m", "INSERT INTO t (n) VALUES (99);", vec!["e".into()]),
        );
        reg.listeners.insert("e".into(), vec!["m.append".into()]);

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "m.fire", &Params::new(), &ctx, &Grants::new())
            .await
            .unwrap();
        drain(&db, &reg).await.unwrap();

        let rows = db
            .query(
                "SELECT id, event_name, parent_event_id, run_id FROM _event_outbox",
                &Params::new(),
            )
            .await
            .unwrap()
            .rows;
        let named = |name: &str| {
            rows.iter()
                .find(|r| r["event_name"] == json!(name))
                .unwrap_or_else(|| panic!("no `{name}` row"))
                .clone()
        };
        let root = named("e");
        let cascade = named("f");
        assert_eq!(
            root["parent_event_id"],
            json!(""),
            "an event a person caused has no parent event"
        );
        assert_eq!(
            cascade["parent_event_id"], root["id"],
            "the cascade names its cause, which is the only thing that makes it a chain"
        );
        assert_eq!(
            cascade["run_id"],
            json!(""),
            "no flow was involved: the seal is empty rather than borrowed"
        );
    }

    /// The correlation columns are stamped by the RUNTIME, from the context — never by a caller.
    /// A payload that could name a run would let anybody file their event under somebody else's
    /// execution, which is exactly as useful as no correlation at all.
    #[test]
    fn the_seal_of_an_event_comes_from_the_context_and_not_from_its_payload() {
        let plain = RequestContext::new("h1", "u1", ["*".to_string()]);
        let (_, p) = insert_op(&plain, "m", "e", &Params::new(), 0, None);
        assert_eq!(p["run_id"], json!(""));
        assert_eq!(p["parent_event_id"], json!(""));

        let inside_a_run = RequestContext::new("h1", "flow:f-1", ["*".to_string()])
            .with_automation(crate::registry::AutomationCtx {
                flow_id: "f-1".into(),
                run_id: "run-7".into(),
            })
            .caused_by_event("evt-origin");
        let (_, p) = insert_op(&inside_a_run, "m", "e", &Params::new(), 0, None);
        assert_eq!(
            p["run_id"],
            json!("run-7"),
            "everything a run emits carries the run that emitted it"
        );
        assert_eq!(
            p["parent_event_id"],
            json!("evt-origin"),
            "and the event that set the whole thing off"
        );
    }

    /// hub#1076 (review): the dedup id is scoped to the HUB. `_event_outbox.id` is the only
    /// primary key of the table and the row contract keeps `hub_id` precisely because a legacy
    /// (pre-ADR-0201) database is shared: without the hub in the key, hub B ingesting the same
    /// `wa_message_id` as hub A would have its event silently absorbed by A's row.
    #[test]
    fn the_dedup_id_is_scoped_to_the_hub_hub1076() {
        let mut payload = Params::new();
        payload.insert("wa_message_id".into(), json!("wamid.X"));
        let a = RequestContext::new("hub-a", "u1", ["*".to_string()]);
        let b = RequestContext::new("hub-b", "u1", ["*".to_string()]);
        let (sql_a, p_a) = insert_op(&a, "m", "m.e", &payload, 0, Some("wa_message_id"));
        let (_, p_b) = insert_op(&b, "m", "m.e", &payload, 0, Some("wa_message_id"));
        assert!(
            sql_a.ends_with(" ON CONFLICT (id) DO NOTHING"),
            "a keyed emission is absorbed on conflict"
        );
        assert_ne!(
            p_a["id"], p_b["id"],
            "the same key in two hubs is two events, never one"
        );
        let (_, p_a2) = insert_op(&a, "m", "m.e", &payload, 0, Some("wa_message_id"));
        assert_eq!(
            p_a["id"], p_a2["id"],
            "the same key in the same hub is the same row"
        );
        assert_eq!(p_a["id"], json!("dedup:hub-a:m:m.e:wamid.X"));
    }

    /// hub#1076 (review): a `dedup_key` the payload cannot resolve — absent, `null`, an array or an
    /// object — never degrades to an EMPTY key. An empty key would dedup every emission of the
    /// command into one row; the contract is the opposite: emit, undeduplicated, and say so.
    #[test]
    fn an_unresolvable_dedup_key_never_collapses_into_one_event_hub1076() {
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        let mut payload = Params::new();
        payload.insert("nil".into(), json!(null));
        payload.insert("list".into(), json!(["a"]));
        payload.insert("obj".into(), json!({"k": "v"}));
        for field in ["absent", "nil", "list", "obj"] {
            let (sql_1, p_1) = insert_op(&ctx, "m", "m.e", &payload, 0, Some(field));
            let (_, p_2) = insert_op(&ctx, "m", "m.e", &payload, 0, Some(field));
            assert!(
                !sql_1.contains("ON CONFLICT"),
                "`{field}`: no key, no conflict clause"
            );
            assert_ne!(
                p_1["id"], p_2["id"],
                "`{field}`: each emission keeps its own fresh id"
            );
            assert!(
                !p_1["id"].as_str().unwrap_or_default().starts_with("dedup:"),
                "`{field}`: an unresolvable key derives no dedup id at all"
            );
        }
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

    /// Inserts a dead-letter row directly (skips the relay/backoff dance) so a test can stage
    /// several at once without the fixture's single-event loop. `hub_id`/`status` are parameters so
    /// the same helper builds the foreign-tenant and non-dead rows the assertions need.
    async fn seed_row(db: &PgAdapter, id: &str, hub_id: &str, status: &str) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
        p.insert("status".into(), json!(status));
        db.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, payload, status, attempts, \
              next_attempt_at, last_error, created_at) \
             VALUES (:id, :hub_id, 'u1', '[]', 'e', 'm', '{}', :status, 8, :at, 'boom', :at)",
            &p,
        )
        .await
        .unwrap();
    }

    /// `retry_all` clears the whole dead-letter queue of this hub in one gesture — the case a
    /// transient outage (the DB went down, a module was off mid-flight) killed several events at
    /// once. Every `dead` row goes back to `pending` with a fresh retry budget; the operator does
    /// not click N times. Delivered/pending/discarded rows are left alone, and it is scoped to the
    /// hub (a foreign tenant's dead-letters never move).
    #[tokio::test]
    async fn retry_all_moves_every_dead_letter_of_this_hub_back_to_the_relay() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();

        // Three dead rows in this hub, plus one in another hub, plus non-dead rows that must NOT
        // move (a delivered and a discarded one).
        seed_row(&db, "d1", "h1", STATUS_DEAD).await;
        seed_row(&db, "d2", "h1", STATUS_DEAD).await;
        seed_row(&db, "d3", "h1", STATUS_DEAD).await;
        seed_row(&db, "fx", "h2", STATUS_DEAD).await;
        seed_row(&db, "ok", "h1", "delivered").await;
        seed_row(&db, "dc", "h1", STATUS_DISCARDED).await;

        let moved = retry_all(&db, "h1").await.unwrap();
        assert_eq!(
            moved, 3,
            "only this hub's dead rows move (not h2, not delivered/discarded)"
        );

        // The three dead rows are now pending, fresh budget, lease cleared, error wiped.
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending' AND attempts=0 AND claim_expires_at IS NULL AND last_error=''").await,
            3,
            "every revived row is pending with a full retry budget and a clean lease"
        );
        // The foreign hub's dead row is untouched (tenancy).
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE id='fx' AND status='dead'"
            )
            .await,
            1,
            "another hub's dead-letter is not revived"
        );
        // The delivered/discarded rows stayed where they were.
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE id='ok' AND status='delivered'"
            )
            .await,
            1,
            "a delivered row is not an operator gesture — untouched"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE id='dc' AND status='discarded'"
            )
            .await,
            1,
            "a discarded row is a closed decision — untouched"
        );

        // Idempotent: a second call moves nothing (no dead rows left).
        let moved_again = retry_all(&db, "h1").await.unwrap();
        assert_eq!(
            moved_again, 0,
            "retry-all is idempotent — the queue is already clear"
        );
    }

    /// `count_dead` is the cheap number the topbar bell polls. It counts ONLY `dead` rows of this
    /// hub: delivered/pending are not failures, and discarded ones are failures an admin already
    /// chose to keep closed — none of those is "something that needs you".
    #[tokio::test]
    async fn count_dead_counts_only_this_hubs_dead_rows() {
        let db = fresh_db().await;
        ensure_tables(&db).await.unwrap();

        seed_row(&db, "d1", "h1", STATUS_DEAD).await;
        seed_row(&db, "d2", "h1", STATUS_DEAD).await;
        seed_row(&db, "fx", "h2", STATUS_DEAD).await; // another hub — not ours
        seed_row(&db, "ok", "h1", "delivered").await; // not a failure
        seed_row(&db, "pn", "h1", "pending").await; // still in flight, not a failure
        seed_row(&db, "dc", "h1", STATUS_DISCARDED).await; // closed by an admin, not open

        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            2,
            "only this hub's dead rows (not h2, not delivered/pending/discarded)"
        );
        assert_eq!(
            count_dead(&db, "h2").await.unwrap(),
            1,
            "the foreign hub sees its own"
        );
        assert_eq!(
            count_dead(&db, "lonely").await.unwrap(),
            0,
            "an empty hub has zero"
        );

        // The bell drops to zero once the admin clears the queue.
        retry_all(&db, "h1").await.unwrap();
        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            0,
            "the bell clears when nothing is dead"
        );
    }

    // ── Listener-host de `host.print` (hub#957) ─────────────────────────────────────────────
    //
    // El gemelo de `host.notify`. Un flujo llega a la cola de impresión por la puerta que ya
    // tiene: un step `command` ejecuta un command de módulo, el command emite `<algo>.print.due`
    // y el relay lo encola. El lenguaje del flujo no se toca (ADR-0283 D1).

    /// El mismo esquema de sistema que [`db_for_notify`]: `_print_queue` y `_print_host` los
    /// levanta `system_migrations::apply`, igual que los grants de capability y los ajustes.
    async fn db_for_print() -> PgAdapter {
        db_for_notify().await
    }

    /// Registry con el módulo `labels` instalado, su command emisor y la capability `printer`
    /// **declarada**. Declararla no es concederla: el grant va aparte ([`authorize_print`]), y el
    /// caso «ni siquiera la declara» lo cubre la puerta de emisión (`commands.rs`).
    fn registry_for_print() -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("labels".into(), ModuleStatus::Active);
        reg.installed.push(
            serde_json::from_str(
                r#"{"id":"labels","name":"Labels","version":"1.0.0",
                    "capabilities":{"printer":{}}}"#,
            )
            .unwrap(),
        );
        reg.commands.insert(
            "labels.print".into(),
            cmd(
                "labels",
                "INSERT INTO t (n) VALUES (1);",
                vec!["labels.print.due".into()],
            ),
        );
        reg
    }

    /// La intención de impresión que viaja en el payload del evento: la misma forma camelCase que
    /// `NewPrintJob` (el productor que ya existe, `apps/web/src/lib/print.ts`).
    fn print_payload(job_id: &str) -> Params {
        let mut p = Params::new();
        p.insert("jobId".into(), json!(job_id));
        p.insert("role".into(), json!("receipt"));
        p.insert("documentType".into(), json!("barcode_label"));
        p.insert("document".into(), json!({ "sku": "A-1", "name": "Cafe" }));
        p
    }

    async fn authorize_print(db: &PgAdapter, reg: &Registry) {
        crate::capabilities::set_grant(db, reg, "h1", "labels", "printer", true, "hub_user:admin")
            .await
            .unwrap();
    }

    async fn queued_jobs(db: &PgAdapter) -> Vec<crate::print_queue::PrintJob> {
        crate::print_queue::list(db, "h1", None, None, 50)
            .await
            .unwrap()
    }

    /// **El hueco de hub#957 cerrado.** Un evento `*.print.due` de un módulo con la capability
    /// `printer` concedida acaba como un trabajo en la cola de impresión del hub, exactamente una
    /// vez, con su marcador en `_event_delivery` (idempotente al re-drenar).
    #[tokio::test]
    async fn print_due_event_queues_the_document_once() {
        let db = db_for_print().await;
        let reg = registry_for_print();
        authorize_print(&db, &reg).await;

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "labels.print",
            &print_payload("job-1"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        assert!(
            queued_jobs(&db).await.is_empty(),
            "no se encola inline; va por el relay"
        );

        drain(&db, &reg).await.unwrap();
        let jobs = queued_jobs(&db).await;
        assert_eq!(jobs.len(), 1, "una entrega por el listener-host");
        assert_eq!(jobs[0].job_id, "job-1");
        assert_eq!(jobs[0].role, "receipt");
        assert_eq!(jobs[0].document_type, "barcode_label");
        assert_eq!(jobs[0].document["sku"], json!("A-1"));
        assert_eq!(
            jobs[0].format,
            crate::print_queue::FORMAT_RECEIPT,
            "formato por defecto"
        );
        assert_eq!(jobs[0].status, crate::print_queue::STATUS_PENDING);
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='host.print'"
            )
            .await,
            1
        );

        // Idempotencia del relay: re-drenar no encola un segundo tique.
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            queued_jobs(&db).await.len(),
            1,
            "idempotente (marcador host.print)"
        );
    }

    /// **Default-deny, como `notify`.** El módulo declara `printer` pero NADIE se la concede: el
    /// evento existe y se entrega a sus listeners, pero no sale papel.
    #[tokio::test]
    async fn print_due_without_a_granted_printer_capability_queues_nothing() {
        let db = db_for_print().await;
        let reg = registry_for_print();

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "labels.print",
            &print_payload("job-1"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();

        assert!(
            queued_jobs(&db).await.is_empty(),
            "sin grant de `printer` no se encola nada"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE listener_command='host.print'"
            )
            .await,
            0,
            "no hay entrega que marcar"
        );
    }

    /// **Atribución.** Una fila sin módulo emisor (lo que produce el kernel, `insert_core_event_once`
    /// o un flujo) no tiene a quién exigirle la capability, así que no imprime: la puerta de papel
    /// se abre para un MÓDULO, y un flujo llega a ella ejecutando el command de uno.
    #[tokio::test]
    async fn print_due_without_an_attributed_module_queues_nothing() {
        let db = db_for_print().await;
        let reg = registry_for_print();
        authorize_print(&db, &reg).await;

        let mut p = Params::new();
        p.insert("id".into(), json!("ev-1"));
        p.insert(
            "payload".into(),
            json!(Json::Object(print_payload("job-1")).to_string()),
        );
        p.insert("at".into(), json!("2020-01-01T00:00:00+00:00"));
        db.execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, run_id, payload, status, \
              attempts, next_attempt_at, last_error, created_at) \
             VALUES (:id, 'h1', '', '[]', 'flow.print.due', '', 'run-1', :payload, 'pending', 0, \
                     :at, '', :at)",
            &p,
        )
        .await
        .unwrap();

        process_once(&db, &reg).await.unwrap();
        assert!(
            queued_jobs(&db).await.is_empty(),
            "sin módulo atribuido no se puede comprobar la capability → no hay papel"
        );
        // Y lo NIEGA la puerta de atribución, con su motivo: sin esta aserción el test pasaría
        // igual con la puerta borrada (la de capability también rechaza un módulo vacío), y el
        // mensaje que un operador lee en el dead-letter diría otra cosa.
        assert!(
            one_text(
                &db,
                "SELECT last_error AS c FROM _event_outbox WHERE id='ev-1'"
            )
            .await
            .contains("sin módulo emisor atribuido"),
            "el error nombra la atribución que falta, no una capability de nadie"
        );
    }

    /// **`jobId` = idempotencia, y ya estaba construida** (`ON CONFLICT DO NOTHING`). Dos eventos
    /// distintos que nombran el mismo trabajo son UN tique, y el segundo no reescribe el documento
    /// que el primero encoló.
    #[tokio::test]
    async fn two_print_due_events_with_the_same_job_id_are_one_ticket() {
        let db = db_for_print().await;
        let reg = registry_for_print();
        authorize_print(&db, &reg).await;

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "labels.print",
            &print_payload("job-1"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        let mut second = print_payload("job-1");
        second.insert("document".into(), json!({ "sku": "OTRO" }));
        crate::commands::execute(&db, &reg, "labels.print", &second, &ctx, &Grants::new())
            .await
            .unwrap();
        drain(&db, &reg).await.unwrap();

        let jobs = queued_jobs(&db).await;
        assert_eq!(jobs.len(), 1, "el mismo jobId es un solo trabajo");
        assert_eq!(
            jobs[0].document["sku"],
            json!("A-1"),
            "el duplicado no reescribe el documento"
        );
        // Las DOS filas de outbox quedan entregadas: la segunda no es un fallo, es un duplicado.
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            2
        );
    }

    /// **Sin host de impresión registrado el trabajo ESPERA** — no falla, no se pierde y no
    /// inventa una alerta nueva: `print_queue::enqueue` no consulta el registro de hosts a
    /// propósito (`print_hosts.rs`), y lo que ya existe para que la espera no sea silenciosa es
    /// `print_hosts::coverage` (aviso, nunca puerta).
    #[tokio::test]
    async fn a_print_due_with_no_registered_host_waits_in_the_queue() {
        let db = db_for_print().await;
        let reg = registry_for_print();
        authorize_print(&db, &reg).await;

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "labels.print",
            &print_payload("job-1"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();

        let jobs = queued_jobs(&db).await;
        assert_eq!(jobs.len(), 1);
        assert_eq!(
            jobs[0].status,
            crate::print_queue::STATUS_PENDING,
            "espera, no muere"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            1,
            "la fila del evento queda entregada: encolar ES la entrega, imprimir es del host"
        );

        let coverage = crate::print_hosts::coverage(&db, "h1").await.unwrap();
        assert_eq!(coverage.len(), 1);
        assert_eq!(coverage[0].role, "receipt");
        assert_eq!(coverage[0].waiting, 1);
        assert_eq!(
            coverage[0].live_hosts, 0,
            "nadie imprime `receipt` y hay trabajo esperando"
        );
    }

    /// Un documento que la cola rechaza (vocabulario cerrado de `document_type`) NO se encola en
    /// silencio: el listener-host falla y la fila sigue la escalera de reintentos del relay hasta
    /// el dead-letter, donde un operador lo ve. Es el mismo trato que un transporte de `notify`
    /// que no entrega.
    #[tokio::test]
    async fn a_print_due_with_an_unknown_document_type_fails_loudly() {
        let db = db_for_print().await;
        let reg = registry_for_print();
        authorize_print(&db, &reg).await;

        let mut payload = print_payload("job-1");
        payload.insert("documentType".into(), json!("kitchn"));
        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(&db, &reg, "labels.print", &payload, &ctx, &Grants::new())
            .await
            .unwrap();

        process_once(&db, &reg).await.unwrap();
        assert!(
            queued_jobs(&db).await.is_empty(),
            "un tipo desconocido no se encola"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending' AND attempts=1"
            )
            .await,
            1,
            "la fila se difiere con su error, no se marca entregada"
        );
        assert!(
            one_text(&db, "SELECT last_error AS c FROM _event_outbox")
                .await
                .contains("host.print"),
            "el error dice qué puerta lo rechazó"
        );
    }

    // ── hub#1171: a listener refused by a CAPABILITY gate ────────────────────────────────────
    //
    // The fiscal chain is the case that destapó esto: `invoice.created` →
    // `verifactu.records.ingest_invoice`, a NATIVE handler whose module declares the `certificate`
    // capability. On a fresh hub that capability is not granted (default-deny, ADR-0079), so the
    // dispatcher refuses the command before the handler runs — and the business invoices, charges
    // and prints believing it is sealing.

    /// A first-party engine that does its job without complaint — so the ONLY thing that can stop
    /// the listener in these tests is the capability gate in front of it.
    #[derive(Debug)]
    struct SealerEngine;

    #[async_trait::async_trait]
    impl crate::native::NativeHandler for SealerEngine {
        async fn call(
            &self,
            _function: &str,
            _input: &Json,
            _host: &dyn crate::native::NativeHost,
        ) -> Result<erplora_wasm_host::Output> {
            Ok(erplora_wasm_host::Output::default())
        }
    }

    /// A hub with `invoice` (plain SQL, emits) and `sealer` (a native handler that demands the
    /// `certificate` capability, which NOBODY has granted).
    async fn hub_with_an_ungranted_capability() -> (PgAdapter, Registry) {
        let db = fresh_db().await;
        db.execute_batch("CREATE TABLE invoices (id TEXT);")
            .await
            .unwrap();
        system_schema(&db).await;

        let mut reg = Registry::new();
        reg.status.insert("invoice".into(), ModuleStatus::Active);
        reg.status.insert("sealer".into(), ModuleStatus::Active);
        reg.installed.push(
            serde_json::from_str(
                r#"{"id":"sealer","name":"Sealer","version":"1.0.0",
                    "capabilities":{"certificate":{"purpose":"fiscal-sign"}}}"#,
            )
            .unwrap(),
        );
        reg.commands.insert(
            "invoice.create_from_sale".into(),
            cmd(
                "invoice",
                "INSERT INTO invoices (id) VALUES (:new_id);",
                vec!["invoice.created".into()],
            ),
        );
        reg.native
            .insert("sealer".into(), std::sync::Arc::new(SealerEngine));
        let mut ingest = cmd("sealer", "", vec![]);
        ingest.def.sql.clear();
        ingest.sql.clear();
        ingest.def.handler = Some(crate::manifest::HandlerRef {
            kind: "native".into(),
            file: None,
            function: "ingest_invoice".into(),
        });
        reg.commands
            .insert("sealer.records.ingest_invoice".into(), ingest);
        reg.listeners.insert(
            "invoice.created".into(),
            vec!["sealer.records.ingest_invoice".into()],
        );
        (db, reg)
    }

    /// **The bug (hub#1171).** The listener is refused by the capability gate, and the relay has to
    /// treat that like any other failure: the row is NOT delivered, it carries the reason, and it
    /// ends in the dead-letter the «Eventos caídos» screen reads. Anything else turns a switch the
    /// owner never flipped into an invisible fiscal breach.
    #[tokio::test]
    async fn a_listener_refused_by_a_capability_gate_is_not_swallowed() {
        let (db, reg) = hub_with_an_ungranted_capability().await;
        let ctx = RequestContext::new("h1", "hub_user:ana", ["*".to_string()]);

        crate::commands::execute(
            &db,
            &reg,
            "invoice.create_from_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .expect("invoicing does not depend on the sealer's capability");
        process_once(&db, &reg).await.unwrap();

        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            0,
            "a refused listener must never leave the event marked delivered"
        );
        assert!(
            one_text(&db, "SELECT last_error AS c FROM _event_outbox")
                .await
                .contains("certificate"),
            "the row records WHICH capability refused it"
        );
    }

    /// …and it gets there in ONE pass, not eight. A capability nobody granted is not a stumble: the
    /// eighth attempt knows exactly what the first knew (hub#827's rule, applied to the gate that
    /// destapó hub#1171). Climbing the ladder means four minutes of a live till sealing nothing
    /// while the screen says «Todo en orden».
    #[tokio::test]
    async fn a_capability_refusal_dead_letters_at_once_instead_of_burning_eight_attempts() {
        let (db, reg) = hub_with_an_ungranted_capability().await;
        let ctx = RequestContext::new("h1", "hub_user:ana", ["*".to_string()]);

        crate::commands::execute(
            &db,
            &reg,
            "invoice.create_from_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();

        let dead = list_dead(&db, "h1", 50).await.unwrap();
        assert_eq!(dead.len(), 1, "«Eventos caídos» has to SEE it: {dead:?}");
        assert_eq!(dead[0].event_name, "invoice.created");
        assert!(
            dead[0].last_error.contains("certificate"),
            "the operator reads which permission to grant: {}",
            dead[0].last_error
        );
        assert_eq!(
            dead[0].failure_kind, FAILURE_CAPABILITY_DENIED,
            "the row carries a machine-readable reason, not English to be parsed"
        );
        assert!(
            dead[0].retryable,
            "granting the capability IS the remedy, so the retry button must work"
        );
    }

    /// A retryable classification is not a contradiction: `failure_kind` says WHY the row is
    /// terminal, and only some whys are dead ends. Retrying clears the stamp, so a row that dies
    /// again is classified afresh rather than carrying a stale verdict.
    #[tokio::test]
    async fn retrying_a_capability_refusal_clears_its_classification() {
        let (db, reg) = hub_with_an_ungranted_capability().await;
        let ctx = RequestContext::new("h1", "hub_user:ana", ["*".to_string()]);

        crate::commands::execute(
            &db,
            &reg,
            "invoice.create_from_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();
        let dead = list_dead(&db, "h1", 50).await.unwrap();
        assert!(
            matches!(
                retry(&db, "h1", &dead[0].id).await.unwrap(),
                RetryOutcome::Requeued
            ),
            "the screen's retry button is not dead for this row"
        );

        assert_eq!(
            one_text(&db, "SELECT failure_kind AS c FROM _event_outbox").await,
            "",
            "back on the relay with no verdict attached"
        );
    }

    /// «Reintentar todo» is the gesture for *a cause that has since been fixed*, and a capability
    /// the owner has just granted is the textbook one — so these rows must be swept along, unlike a
    /// revoked release (hub#827), which is a dead end whatever anybody presses.
    #[tokio::test]
    async fn retry_all_sweeps_a_capability_refusal_along_with_the_ordinary_ones() {
        let (db, reg) = hub_with_an_ungranted_capability().await;
        let ctx = RequestContext::new("h1", "hub_user:ana", ["*".to_string()]);

        crate::commands::execute(
            &db,
            &reg,
            "invoice.create_from_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();

        assert_eq!(
            retry_all(&db, "h1").await.unwrap(),
            1,
            "the row goes back to the relay"
        );
    }

    /// **The other half of hub#1119.** Making the failure visible is not the same as making it
    /// recoverable: the owner flips the switch in Ajustes → Permisos and the invoices that could not
    /// be sealed while it was off have to seal themselves. Asking them to also find System → Events
    /// and press «reintentar» is asking them to know that the first minutes of their fiscal chain
    /// are sitting in a queue.
    #[tokio::test]
    async fn granting_a_capability_replays_what_it_had_refused() {
        let (db, reg) = hub_with_an_ungranted_capability().await;
        let ctx = RequestContext::new("h1", "hub_user:ana", ["*".to_string()]);

        crate::commands::execute(
            &db,
            &reg,
            "invoice.create_from_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            1,
            "dead while the switch is off"
        );

        crate::capabilities::set_grant(
            &db,
            &reg,
            "h1",
            "sealer",
            "certificate",
            true,
            "hub_user:admin",
        )
        .await
        .unwrap();

        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            0,
            "flipping the switch put the refused events back in front of the relay"
        );
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            1,
            "and the relay delivered them"
        );
    }

    /// Revoking is not granting: taking a permission away must not stir the queue. The rows that
    /// died for it are exactly the ones that would die again, and resetting their attempts would
    /// hide how long they have been stuck.
    #[tokio::test]
    async fn revoking_a_capability_leaves_the_dead_letters_where_they_are() {
        let (db, reg) = hub_with_an_ungranted_capability().await;
        let ctx = RequestContext::new("h1", "hub_user:ana", ["*".to_string()]);

        crate::commands::execute(
            &db,
            &reg,
            "invoice.create_from_sale",
            &Params::new(),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();

        crate::capabilities::set_grant(
            &db,
            &reg,
            "h1",
            "sealer",
            "certificate",
            false,
            "hub_user:admin",
        )
        .await
        .unwrap();

        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            1,
            "still dead, still visible"
        );
    }

    // ── hub#1192: the SAME refusal, one gate further out — the host listener of `host.notify` ──
    //
    // hub#1171 taught the relay that a capability nobody granted is not a stumble, but it only
    // taught it about listeners of a MODULE. The host listener of `host.notify` (ADR-0012) has the
    // very same gate in front of it — `capabilities::require(…, Notify)`, default-deny since
    // hub#240 — and its refusal travels a different road: it reaches `NotifyFailure` through `?`,
    // which classifies everything it does not know as retryable.
    //
    // The four minutes of ladder are NOT the damage. `replay_capability_denied` sweeps **by stamp**
    // (`requeue_dead(…, &[FAILURE_CAPABILITY_DENIED])`) and `capabilities::set_grant` calls it the
    // moment the switch goes on. A row that dies with `failure_kind = ''` is therefore never put
    // back: the owner grants `notify`, every refused reminder stays dead, and the customer's
    // reminder is lost unless somebody happens to find System → Events and press retry per row.

    /// Regression test for ERPlora/hub#1192 — a hub whose `appt` module DECLARES `notify` and whom
    /// nobody has granted it (default-deny, ADR-0079): the reminder dies on the first pass and, the
    /// part that matters, dies **stamped**.
    ///
    /// Named `hub1192_…` per the merge gate (pm#177). The triage proposed a Spanish name; the
    /// repo's binding language rule keeps identifiers in English, so the stamp travels in the name.
    #[tokio::test]
    async fn hub1192_a_reminder_due_without_granted_notify_dies_on_the_first_pass_with_its_stamp() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());
        // NO `authorize_notify`: the switch is off, which is how every hub starts.

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "appt.remind",
            &reminder_payload("cliente@x.com"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();

        assert!(
            transport.sent().is_empty(),
            "sin grant no sale nada del hub (hub#240)"
        );
        let dead = list_dead(&db, "h1", 50).await.unwrap();
        assert_eq!(
            dead.len(),
            1,
            "one pass, not eight: «Eventos caídos» has to SEE it: {dead:?}"
        );
        assert_eq!(dead[0].event_name, "appt.reminder.due");
        assert!(
            dead[0].last_error.contains("notify"),
            "the operator reads which permission to grant: {}",
            dead[0].last_error
        );
        assert_eq!(
            dead[0].failure_kind, FAILURE_CAPABILITY_DENIED,
            "the stamp is what `replay_capability_denied` sweeps by — without it the row is lost"
        );
        assert!(
            dead[0].retryable,
            "granting `notify` IS the remedy, so the retry button must work"
        );
    }

    /// Regression test for ERPlora/hub#1192 — **the half that proves the fix**. Counting attempts
    /// would pass without curing anything: what was lost is the reminder, and it is lost because
    /// flipping the switch never brought it back.
    #[tokio::test]
    async fn hub1192_granting_notify_requeues_the_dead_reminder() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "appt.remind",
            &reminder_payload("cliente@x.com"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();
        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            1,
            "dead while the switch is off"
        );

        // The owner flips «Notificaciones» on in Ajustes → Permisos (and the recipient is a
        // customer of the hub, as the other three gates require).
        authorize_notify(&db, &reg, "cliente@x.com").await;

        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            0,
            "granting `notify` put the refused reminder back in front of the relay"
        );
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            transport.sent().len(),
            1,
            "…and the reminder finally reached the customer"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='delivered'"
            )
            .await,
            1,
            "the row is delivered, not sitting in a queue nobody looks at"
        );
    }

    /// Regression test for ERPlora/hub#1192 — **the twin, fixed here under the same roof.** The host
    /// listener of `host.print` (hub#957) sits behind the very same default-deny gate, and its
    /// refusal took the very same road: ladder, then `failure_kind = ''`, which
    /// `replay_capability_denied` cannot sweep. Granting «Impresora» left the ticket dead. Leaving
    /// one of two identical doors open is how a fixed bug comes back through the other one.
    #[tokio::test]
    async fn hub1192_a_print_due_without_granted_printer_dies_stamped_and_granting_it_requeues_the_ticket(
    ) {
        let db = db_for_print().await;
        let reg = registry_for_print();

        let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "labels.print",
            &print_payload("job-1"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();

        assert!(
            queued_jobs(&db).await.is_empty(),
            "sin grant de `printer` no se encola nada"
        );
        let dead = list_dead(&db, "h1", 50).await.unwrap();
        assert_eq!(dead.len(), 1, "one pass, not eight: {dead:?}");
        assert_eq!(
            dead[0].failure_kind, FAILURE_CAPABILITY_DENIED,
            "same stamp as its notify twin, or granting the capability leaves the ticket dead"
        );
        assert!(dead[0].retryable, "granting `printer` IS the remedy");

        authorize_print(&db, &reg).await;

        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            0,
            "granting `printer` put the refused ticket back in front of the relay"
        );
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            queued_jobs(&db).await.len(),
            1,
            "…and the document reached the print queue"
        );
    }

    /// Regression test for ERPlora/hub#1192 (review) — **only the refusal is terminal-now.** The gate
    /// the fix wraps reads the grants table, so a database blip surfaces at the very same call, and
    /// it must keep the ladder every other `?` keeps: stamping it `module.capability_denied` would
    /// kill it on the first pass and tell the operator to grant a capability that is already there.
    #[tokio::test]
    async fn hub1192_a_database_error_at_the_notify_gate_keeps_its_retry_ladder() {
        use crate::host_notify::MockTransport;

        let db = db_for_notify().await;
        let mut reg = registry_for_notify(true);
        let transport = std::sync::Arc::new(MockTransport::new());
        reg.notify_transport = Some(transport.clone());
        // Granted for real: what fails below is the DATABASE under the gate, not the gate.
        authorize_notify(&db, &reg, "cliente@x.com").await;

        let ctx = RequestContext::new("h1", "", ["*".to_string()]);
        crate::commands::execute(
            &db,
            &reg,
            "appt.remind",
            &reminder_payload("cliente@x.com"),
            &ctx,
            &Grants::new(),
        )
        .await
        .unwrap();
        // The grants table goes away under the relay: `capabilities::require` fails on its query.
        db.execute_batch(
            "ALTER TABLE _module_capability_grants RENAME TO _module_capability_grants_gone;",
        )
        .await
        .unwrap();
        process_once(&db, &reg).await.unwrap();

        assert_eq!(
            count_dead(&db, "h1").await.unwrap(),
            0,
            "a database error is not a refusal: no first-pass death"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending' AND attempts=1"
            )
            .await,
            1,
            "the row is deferred on the ladder with its error"
        );
        assert_eq!(
            one_text(&db, "SELECT failure_kind AS c FROM _event_outbox").await,
            "",
            "nothing stamps `module.capability_denied` on a row nobody refused"
        );

        // The database comes back and the ladder does its job: the reminder goes out.
        db.execute_batch(
            "ALTER TABLE _module_capability_grants_gone RENAME TO _module_capability_grants;",
        )
        .await
        .unwrap();
        db.execute(
            "UPDATE _event_outbox SET next_attempt_at = '2020-01-01T00:00:00+00:00'",
            &Params::new(),
        )
        .await
        .unwrap();
        drain(&db, &reg).await.unwrap();
        assert_eq!(
            transport.sent().len(),
            1,
            "…and the reminder reached the customer after the blip"
        );
    }
}
