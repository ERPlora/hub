//! A WhatsApp or an email that erplora.com asks the hub to slow down for WAITS and leaves on its
//! own; it is not filed as «quota exceeded» (hub#2649).
//!
//! erplora.com answers `429` for two different reasons. One is the month's quota
//! (`{"error": "quota_exceeded"}`, ERPlora/saas `whatsapp_inbox/api/notify.py`): no amount of
//! retrying brings it back, so the row goes to «Eventos caídos» at once (hub#971). The other is the
//! per-hub rate limit (DRF's `{"detail": "Request was throttled…"}` with `Retry-After`, or the email
//! door's `@quota(rate="200/h")`): it lifts on its own. A burst of reminders at opening time used to
//! hit the second and be filed as the first — every customer lost their reminder and the owner was
//! told the quota was spent when it was not.
//!
//! What a throttled delivery must do, the way Stripe, Twilio and every HTTP client that honours
//! `Retry-After` do: wait what the far end asks (bounded), try again on its own, and not spend a
//! rung of the backoff ladder doing it. The hub below is the production one — the outbox relay,
//! [`CloudNotifyTransport`] and a real Postgres — against a fake erplora.com that answers what the
//! real one answers.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex, RwLock};

use axum::extract::State;
use axum::http::{HeaderMap, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params, PgAdapter};
use erplora_runtime::elevation::Grants;
use erplora_runtime::host_notify::ALLOWED_RECIPIENTS_SETTING;
use erplora_runtime::manifest::CommandDef;
use erplora_runtime::outbox::MAX_ATTEMPTS;
use erplora_runtime::registry::{ModuleStatus, RegisteredCommand, Registry, RequestContext};
use erplora_runtime::{
    capabilities, commands, identity, installer, outbox, settings, system_migrations,
};
use erplora_server::notify_transport::CloudNotifyTransport;
use serde_json::{json, Value};

const HUB: &str = "h1";
const PHONE: &str = "+34600111222";
const EMAIL: &str = "cliente@example.com";

/// What DRF's `HubRateThrottle` answers (ERPlora/saas `config/settings.py`, 5000/h per hub).
fn throttled() -> Value {
    json!({ "detail": "Request was throttled. Expected available in 30 seconds." })
}

/// One scripted answer of the fake erplora.com: status, `Retry-After` header and body.
type Answer = (StatusCode, Option<&'static str>, Value);

#[derive(Default)]
struct Ledger {
    /// What the hub asked for next is answered from here; once empty, every send is accepted.
    script: VecDeque<Answer>,
    /// The `Idempotency-Key` of every request that reached erplora.com, in order.
    keys: Vec<Option<String>>,
    /// Sends erplora.com accepted — one per message a customer would get.
    accepted: usize,
}

struct FakeCloud {
    base_url: String,
    ledger: Arc<Mutex<Ledger>>,
    server: tokio::task::JoinHandle<()>,
}

impl FakeCloud {
    fn accepted(&self) -> usize {
        self.ledger.lock().unwrap().accepted
    }

    fn keys(&self) -> Vec<Option<String>> {
        self.ledger.lock().unwrap().keys.clone()
    }
}

impl Drop for FakeCloud {
    fn drop(&mut self) {
        self.server.abort();
    }
}

async fn fake_cloud(script: Vec<Answer>) -> FakeCloud {
    async fn notify(State(ledger): State<Arc<Mutex<Ledger>>>, headers: HeaderMap) -> Response {
        let mut ledger = ledger.lock().unwrap();
        ledger.keys.push(
            headers
                .get("idempotency-key")
                .and_then(|v| v.to_str().ok())
                .map(str::to_owned),
        );
        if let Some((status, retry_after, body)) = ledger.script.pop_front() {
            let mut response = (status, Json(body)).into_response();
            if let Some(secs) = retry_after {
                response
                    .headers_mut()
                    .insert("retry-after", HeaderValue::from_static(secs));
            }
            return response;
        }
        ledger.accepted += 1;
        let message_id = format!("wamid.{}", ledger.accepted);
        (StatusCode::OK, Json(json!({ "message_id": message_id }))).into_response()
    }

    let ledger = Arc::new(Mutex::new(Ledger {
        script: script.into(),
        ..Ledger::default()
    }));
    let app = Router::new()
        .route("/api/v1/hub/device/notify/email/", post(notify))
        .route("/api/v1/hub/device/notify/whatsapp/", post(notify))
        .with_state(ledger.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    FakeCloud {
        base_url: format!("http://{addr}"),
        ledger,
        server,
    }
}

async fn hub_db() -> PgAdapter {
    let db = fresh_db().await;
    db.execute_batch("CREATE TABLE t (n INTEGER);")
        .await
        .unwrap();
    installer::ensure_hub_module_table(&db).await.unwrap();
    identity::ensure_tables(&db).await.unwrap();
    system_migrations::apply(&db, HUB).await.unwrap();
    outbox::ensure_tables(&db).await.unwrap();
    db
}

/// The `appt` module, allowed to send WhatsApp and email, with the real cloud transport wired in.
fn registry(cloud: &FakeCloud) -> Registry {
    let manifest = json!({
        "id": "appt", "name": "Appointments", "version": "1.0.0",
        "capabilities": { "notify": { "channels": ["whatsapp", "email"] } },
    });
    let def: CommandDef = serde_json::from_value(json!({
        "permission": "",
        "transaction": true,
        "sql": ["INSERT INTO t (n) VALUES (1);"],
        "emit": ["appt.reminder.due"],
    }))
    .unwrap();

    let mut reg = Registry::new();
    reg.status.insert("appt".into(), ModuleStatus::Active);
    reg.installed
        .push(serde_json::from_value(manifest).unwrap());
    reg.commands.insert(
        "appt.remind".into(),
        RegisteredCommand {
            module_id: "appt".into(),
            def: def.clone(),
            sql: def.sql.clone(),
            wasm: None,
            schema: None,
        },
    );
    reg.notify_transport = Some(Arc::new(CloudNotifyTransport::new(
        reqwest::Client::new(),
        &cloud.base_url,
        Arc::new(RwLock::new(HUB.to_string())),
        Arc::new(RwLock::new(Some("machine-tok".to_string()))),
    )));
    reg
}

async fn authorize(db: &PgAdapter, reg: &Registry) {
    capabilities::set_grant(db, reg, HUB, "appt", "notify", true, "hub_user:admin")
        .await
        .unwrap();
    let mut s = Params::new();
    s.insert(
        ALLOWED_RECIPIENTS_SETTING.into(),
        json!(format!("{PHONE},{EMAIL}")),
    );
    settings::set_many(db, HUB, &s, "hub_user:admin")
        .await
        .unwrap();
}

/// Queues a reminder the way a module does: a command that emits it.
async fn queue_reminder(db: &PgAdapter, reg: &Registry, channel: &str) {
    let mut p = Params::new();
    p.insert("channel".into(), json!(channel));
    match channel {
        "email" => {
            p.insert("to".into(), json!(EMAIL));
            p.insert("template".into(), json!("reminder"));
            p.insert(
                "vars".into(),
                json!({ "subject": "Your appointment", "text": "Tomorrow at 10:00" }),
            );
        }
        _ => {
            p.insert("to".into(), json!(PHONE));
            p.insert("template".into(), json!(""));
            p.insert("vars".into(), json!({ "text": "Tomorrow at 10:00" }));
        }
    }
    let ctx = RequestContext::new(HUB, "", ["*".to_string()]);
    commands::execute(db, reg, "appt.remind", &p, &ctx, &Grants::new())
        .await
        .unwrap();
}

/// The row as the relay left it.
struct Row {
    status: String,
    attempts: i64,
    /// Seconds from now until the relay takes it again (negative = already due).
    due_in: i64,
}

async fn the_row(db: &PgAdapter) -> Row {
    let rows = db
        .query(
            "SELECT status, attempts, next_attempt_at FROM _event_outbox ORDER BY created_at",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(rows.len(), 1, "one reminder queued: {rows:?}");
    let row = &rows[0];
    let next = chrono::DateTime::parse_from_rfc3339(row["next_attempt_at"].as_str().unwrap())
        .unwrap()
        .with_timezone(&chrono::Utc);
    Row {
        status: row["status"].as_str().unwrap_or_default().to_owned(),
        attempts: row["attempts"].as_i64().unwrap_or(-1),
        due_in: (next - chrono::Utc::now()).num_seconds(),
    }
}

/// What the clock would do once the wait is over: the row is due again.
async fn make_due_again(db: &PgAdapter) {
    db.execute_batch(
        "UPDATE _event_outbox SET next_attempt_at = '2000-01-01T00:00:00+00:00', \
         claim_expires_at = NULL WHERE status = 'pending';",
    )
    .await
    .unwrap();
}

/// The burst at opening time: erplora.com says «slow down, try in 30 s». The reminder waits those
/// 30 s, without spending an attempt, and then leaves — once, with the same delivery key.
#[tokio::test]
async fn a_throttled_whatsapp_waits_what_erplora_asks_and_then_leaves_hub2649() {
    let cloud = fake_cloud(vec![(StatusCode::TOO_MANY_REQUESTS, Some("30"), throttled())]).await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;

    queue_reminder(&db, &reg, "whatsapp").await;
    let _ = outbox::drain(&db, &reg).await;

    let row = the_row(&db).await;
    assert_eq!(row.status, "pending", "a throttle is not a spent quota: it must not be dead");
    assert_eq!(row.attempts, 0, "waiting out a throttle spends no rung of the ladder");
    assert!(
        (25..=31).contains(&row.due_in),
        "it waits the 30 s erplora.com asked for, got {} s",
        row.due_in
    );
    assert_eq!(cloud.accepted(), 0);

    make_due_again(&db).await;
    let _ = outbox::drain(&db, &reg).await;

    assert_eq!(the_row(&db).await.status, "delivered");
    assert_eq!(cloud.accepted(), 1, "it leaves once the wait is over");
    let keys = cloud.keys();
    assert_eq!(keys.len(), 2, "{keys:?}");
    assert!(keys[0].as_deref().is_some_and(|k| !k.is_empty()), "{keys:?}");
    assert_eq!(keys[0], keys[1], "the retry is the same delivery (hub#2648): {keys:?}");
}

/// A delivery that has already climbed the ladder to its last rung (a provider outage earlier)
/// and is then throttled must still be alive afterwards: the throttle cannot be what kills it.
#[tokio::test]
async fn a_throttle_on_the_last_rung_does_not_kill_the_reminder_hub2649() {
    let cloud = fake_cloud(vec![
        (StatusCode::TOO_MANY_REQUESTS, Some("5"), throttled()),
        (StatusCode::TOO_MANY_REQUESTS, Some("5"), throttled()),
    ])
    .await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;
    queue_reminder(&db, &reg, "whatsapp").await;
    let mut p = Params::new();
    p.insert("a".into(), json!(MAX_ATTEMPTS - 1));
    db.execute("UPDATE _event_outbox SET attempts = :a", &p)
        .await
        .unwrap();

    for _ in 0..2 {
        let _ = outbox::drain(&db, &reg).await;
        let row = the_row(&db).await;
        assert_eq!(row.status, "pending", "a throttle spent the last attempt");
        assert_eq!(row.attempts, MAX_ATTEMPTS - 1);
        make_due_again(&db).await;
    }
    let _ = outbox::drain(&db, &reg).await;
    assert_eq!(the_row(&db).await.status, "delivered");
    assert_eq!(cloud.accepted(), 1);
}

/// The throttle is only free when it is the ONLY thing that went wrong. A module listener of the
/// same event that really failed keeps the row on the ladder — that failure is not waited out.
#[tokio::test]
async fn a_throttle_next_to_a_real_failure_keeps_the_ladder_hub2649() {
    let cloud = fake_cloud(vec![(StatusCode::TOO_MANY_REQUESTS, Some("30"), throttled())]).await;
    let db = hub_db().await;
    let mut reg = registry(&cloud);
    let broken: CommandDef = serde_json::from_value(json!({
        "permission": "",
        "transaction": true,
        "sql": ["INSERT INTO no_such_table (n) VALUES (1);"],
    }))
    .unwrap();
    reg.commands.insert(
        "appt.on_reminder".into(),
        RegisteredCommand {
            module_id: "appt".into(),
            def: broken.clone(),
            sql: broken.sql.clone(),
            wasm: None,
            schema: None,
        },
    );
    reg.listeners
        .insert("appt.reminder.due".into(), vec!["appt.on_reminder".into()]);
    authorize(&db, &reg).await;

    queue_reminder(&db, &reg, "whatsapp").await;
    let _ = outbox::drain(&db, &reg).await;

    let row = the_row(&db).await;
    assert_eq!(row.status, "pending");
    assert_eq!(row.attempts, 1, "the listener's failure spends its rung as always");
}

/// The email door's limit (`@quota(rate="200/h")`) answers 429 with no `Retry-After`. The hub
/// then waits a bounded default of its own — a minute — instead of hammering or giving up.
#[tokio::test]
async fn a_throttled_email_without_retry_after_waits_a_minute_hub2649() {
    let cloud = fake_cloud(vec![(
        StatusCode::TOO_MANY_REQUESTS,
        None,
        json!({ "detail": "Too many requests. Please try again later." }),
    )])
    .await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;

    queue_reminder(&db, &reg, "email").await;
    let _ = outbox::drain(&db, &reg).await;

    let row = the_row(&db).await;
    assert_eq!(row.status, "pending");
    assert_eq!(row.attempts, 0);
    assert!(
        (55..=61).contains(&row.due_in),
        "no Retry-After → the hub's own minute, got {} s",
        row.due_in
    );
}

/// A `Retry-After` beyond reason (a day) is capped at an hour: a reminder for this afternoon is
/// worth trying again within the hour, and the ladder already caps itself there.
#[tokio::test]
async fn an_absurd_retry_after_is_capped_at_an_hour_hub2649() {
    let cloud =
        fake_cloud(vec![(StatusCode::TOO_MANY_REQUESTS, Some("86400"), throttled())]).await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;

    queue_reminder(&db, &reg, "whatsapp").await;
    let _ = outbox::drain(&db, &reg).await;

    let row = the_row(&db).await;
    assert_eq!(row.status, "pending");
    assert!(
        (3595..=3601).contains(&row.due_in),
        "capped at one hour, got {} s",
        row.due_in
    );
}

/// The control: the month's quota IS what erplora.com says it is. It still goes to «Eventos
/// caídos» at once (hub#971), even if the answer also carries a `Retry-After`.
#[tokio::test]
async fn a_spent_quota_still_goes_to_dead_letters_at_once_hub2649() {
    let cloud = fake_cloud(vec![(
        StatusCode::TOO_MANY_REQUESTS,
        Some("30"),
        json!({ "error": "quota_exceeded", "detail": "WhatsApp quota exceeded" }),
    )])
    .await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;

    queue_reminder(&db, &reg, "whatsapp").await;
    let _ = outbox::drain(&db, &reg).await;

    let row = the_row(&db).await;
    assert_eq!(row.status, "dead", "a spent quota is not waited out");
    assert_eq!(row.attempts, 0, "and it does not climb the ladder either");
    assert_eq!(cloud.accepted(), 0);
}
