//! A WhatsApp or an email to a customer leaves ONCE even when the hub fails between «sent» and
//! «recorded as sent» (hub#2648).
//!
//! The relay hands the message to erplora.com and only then, in a separate write, records the
//! delivery. Whatever breaks in between — the database refusing that write, the process dying
//! while it waits for the answer, erplora.com answering an error after the message already left —
//! puts the row back in the queue and the next attempt sends it again. A send and a database row
//! cannot share a transaction, so the hub cannot close that gap by itself: what it can do is name
//! every attempt of the same delivery with the SAME `Idempotency-Key`, so the proxy recognises the
//! retry and answers what it answered the first time instead of calling Meta again (Stripe, Twilio
//! and SendGrid work the same way; the proxy's half is ERPlora/saas#2633).
//!
//! The fake erplora.com below keeps that contract — a key it has already sent answers with the
//! stored result and costs no second send — and counts what really reached the provider. The hub
//! is the production one: the outbox relay, [`CloudNotifyTransport`] and a real Postgres, with the
//! failure injected where it happens in production (the database refusing the mark, the relay
//! dropped mid-call, a 500 after the send).

use std::collections::HashMap;
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::Duration;

use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params, PgAdapter};
use erplora_runtime::elevation::Grants;
use erplora_runtime::host_notify::ALLOWED_RECIPIENTS_SETTING;
use erplora_runtime::manifest::CommandDef;
use erplora_runtime::outbox::HOST_NOTIFY_LISTENER;
use erplora_runtime::registry::{ModuleStatus, RegisteredCommand, Registry, RequestContext};
use erplora_runtime::{
    capabilities, commands, identity, installer, outbox, settings, system_migrations,
};
use erplora_server::notify_transport::CloudNotifyTransport;
use serde_json::{json, Value};
use tokio::sync::Notify;

const HUB: &str = "h1";
const CUSTOMER: &str = "+34600111222";

/// How the fake erplora.com answers AFTER it has handed a message to the provider.
const ANSWER: u8 = 0;
/// Never answers: the hub is left waiting, as when it dies mid-call.
const HANG: u8 = 1;
/// Answers 500 once (the quota bookkeeping failing after Meta accepted), then normally.
const FAIL_ONCE: u8 = 2;

#[derive(Default)]
struct Ledger {
    /// The `Idempotency-Key` of every request, in arrival order (`None` = the hub sent none).
    keys: Vec<Option<String>>,
    /// What really reached the provider — one entry per message a customer's phone would show.
    provider_sends: Vec<Value>,
    /// The answer stored per key, replayed to a retry instead of sending again (saas#2633).
    answered: HashMap<(String, String), String>,
}

#[derive(Clone)]
struct Proxy {
    ledger: Arc<Mutex<Ledger>>,
    mode: Arc<AtomicU8>,
    sent: Arc<Notify>,
}

struct FakeCloud {
    base_url: String,
    proxy: Proxy,
    server: tokio::task::JoinHandle<()>,
}

impl FakeCloud {
    fn provider_sends(&self) -> usize {
        self.proxy.ledger.lock().unwrap().provider_sends.len()
    }

    fn keys(&self) -> Vec<Option<String>> {
        self.proxy.ledger.lock().unwrap().keys.clone()
    }

    fn set_mode(&self, mode: u8) {
        self.proxy.mode.store(mode, Ordering::SeqCst);
    }
}

impl Drop for FakeCloud {
    fn drop(&mut self) {
        self.server.abort();
    }
}

async fn fake_cloud(mode: u8) -> FakeCloud {
    async fn notify(
        State(proxy): State<Proxy>,
        headers: HeaderMap,
        body: String,
    ) -> (StatusCode, Json<Value>) {
        let key = headers
            .get("idempotency-key")
            .and_then(|v| v.to_str().ok())
            .map(str::to_owned);
        let hub = headers
            .get("x-hub-id")
            .and_then(|v| v.to_str().ok())
            .unwrap_or_default()
            .to_owned();
        let message_id = {
            let mut ledger = proxy.ledger.lock().unwrap();
            ledger.keys.push(key.clone());
            // A key already sent for this hub is a retry: the stored answer, no second send.
            if let Some(stored) = key
                .as_ref()
                .and_then(|k| ledger.answered.get(&(hub.clone(), k.clone())).cloned())
            {
                return (StatusCode::OK, Json(json!({ "message_id": stored })));
            }
            ledger
                .provider_sends
                .push(serde_json::from_str(&body).unwrap_or(Value::Null));
            let message_id = format!("wamid.{}", ledger.provider_sends.len());
            if let Some(k) = key {
                ledger.answered.insert((hub, k), message_id.clone());
            }
            message_id
        };
        proxy.sent.notify_one();
        match proxy.mode.load(Ordering::SeqCst) {
            HANG => std::future::pending().await,
            FAIL_ONCE => {
                proxy.mode.store(ANSWER, Ordering::SeqCst);
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({ "error": "internal" })),
                )
            }
            _ => (StatusCode::OK, Json(json!({ "message_id": message_id }))),
        }
    }

    let proxy = Proxy {
        ledger: Arc::default(),
        mode: Arc::new(AtomicU8::new(mode)),
        sent: Arc::new(Notify::new()),
    };
    let app = Router::new()
        .route("/api/v1/hub/device/notify/email/", post(notify))
        .route("/api/v1/hub/device/notify/whatsapp/", post(notify))
        .with_state(proxy.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    FakeCloud {
        base_url: format!("http://{addr}"),
        proxy,
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
    s.insert(ALLOWED_RECIPIENTS_SETTING.into(), json!(CUSTOMER));
    settings::set_many(db, HUB, &s, "hub_user:admin")
        .await
        .unwrap();
}

/// Queues the appointment confirmation the way a module does: a command that emits it.
async fn queue_confirmation(db: &PgAdapter, reg: &Registry, text: &str) {
    let mut p = Params::new();
    p.insert("channel".into(), json!("whatsapp"));
    p.insert("to".into(), json!(CUSTOMER));
    p.insert("template".into(), json!(""));
    p.insert("vars".into(), json!({ "text": text }));
    let ctx = RequestContext::new(HUB, "", ["*".to_string()]);
    commands::execute(db, reg, "appt.remind", &p, &ctx, &Grants::new())
        .await
        .unwrap();
}

/// What the backoff ladder or the expired lease would do minutes later: the row is due again.
async fn make_due_again(db: &PgAdapter) {
    db.execute_batch(
        "UPDATE _event_outbox SET next_attempt_at = '2000-01-01T00:00:00+00:00', \
         claim_expires_at = '2000-01-01T00:00:00+00:00' WHERE status = 'pending';",
    )
    .await
    .unwrap();
}

async fn outbox_status(db: &PgAdapter) -> Vec<String> {
    db.query("SELECT status FROM _event_outbox ORDER BY created_at", &Params::new())
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| r["status"].as_str().unwrap_or_default().to_owned())
        .collect()
}

async fn recorded_message_ids(db: &PgAdapter) -> Vec<String> {
    let mut p = Params::new();
    p.insert("listener".into(), json!(HOST_NOTIFY_LISTENER));
    db.query(
        "SELECT provider_message_id FROM _event_delivery WHERE listener_command = :listener",
        &p,
    )
    .await
    .unwrap()
    .rows
    .iter()
    .map(|r| r["provider_message_id"].as_str().unwrap_or_default().to_owned())
    .collect()
}

/// Every attempt carried a key, and it was the same one.
fn assert_one_stable_key(keys: &[Option<String>], attempts: usize) {
    assert_eq!(keys.len(), attempts, "attempts that reached erplora.com: {keys:?}");
    let first = keys[0].clone().expect("the first attempt must carry an Idempotency-Key");
    assert!(!first.trim().is_empty(), "an empty key names nothing");
    for key in keys {
        assert_eq!(key.as_deref(), Some(first.as_str()), "every retry repeats the key: {keys:?}");
    }
}

/// The database refuses the «sent» mark right after erplora.com accepted the message (a one-second
/// outage, a failover). The retry must not reach the customer a second time.
#[tokio::test]
async fn a_send_whose_mark_the_database_refuses_reaches_the_customer_once_hub2648() {
    let cloud = fake_cloud(ANSWER).await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;
    // The real failure, in Postgres: the INSERT of the delivery mark is refused.
    db.execute_batch(&format!(
        "CREATE FUNCTION refuse_mark() RETURNS trigger LANGUAGE plpgsql AS \
           $$ BEGIN RAISE EXCEPTION 'database blip while recording the send'; END $$; \
         CREATE TRIGGER refuse_mark BEFORE INSERT ON _event_delivery FOR EACH ROW \
           WHEN (NEW.listener_command = '{HOST_NOTIFY_LISTENER}') EXECUTE FUNCTION refuse_mark();"
    ))
    .await
    .unwrap();

    queue_confirmation(&db, &reg, "Your appointment is confirmed for Tuesday 10:00").await;
    let _ = outbox::drain(&db, &reg).await;
    assert_eq!(cloud.provider_sends(), 1, "the first attempt reaches the provider");
    assert_eq!(outbox_status(&db).await, ["pending"], "the refused mark leaves it to retry");

    // The database is back; the ladder's next rung comes due.
    db.execute_batch("DROP TRIGGER refuse_mark ON _event_delivery;")
        .await
        .unwrap();
    make_due_again(&db).await;
    let _ = outbox::drain(&db, &reg).await;

    assert_eq!(cloud.provider_sends(), 1, "the customer got the confirmation twice");
    assert_one_stable_key(&cloud.keys(), 2);
    assert_eq!(outbox_status(&db).await, ["delivered"]);
    assert_eq!(
        recorded_message_ids(&db).await,
        ["wamid.1"],
        "the mark names the message the customer really got"
    );
}

/// The hub dies while it waits for erplora.com's answer: the provider already has the message.
/// When the lease expires and the relay takes the row again, the customer must not get it twice.
#[tokio::test]
async fn a_send_the_hub_died_waiting_for_reaches_the_customer_once_hub2648() {
    let cloud = fake_cloud(HANG).await;
    let db = Arc::new(hub_db().await);
    let reg = Arc::new(registry(&cloud));
    authorize(&db, &reg).await;
    queue_confirmation(&db, &reg, "Reminder: tomorrow at 10:00").await;

    let relay = {
        let (db, reg) = (db.clone(), reg.clone());
        tokio::spawn(async move { outbox::process_once(&*db, &reg).await })
    };
    tokio::time::timeout(Duration::from_secs(10), cloud.proxy.sent.notified())
        .await
        .expect("the relay never reached erplora.com");
    // The process dies: the relay is gone mid-call, nothing after the send ran.
    relay.abort();
    let _ = relay.await;
    assert_eq!(outbox_status(&db).await, ["pending"]);

    // Restarted, and five minutes later the lease is up.
    cloud.set_mode(ANSWER);
    make_due_again(&db).await;
    let _ = outbox::drain(&*db, &reg).await;

    assert_eq!(cloud.provider_sends(), 1, "the customer got the reminder twice");
    assert_one_stable_key(&cloud.keys(), 2);
    assert_eq!(outbox_status(&db).await, ["delivered"]);
    assert_eq!(recorded_message_ids(&db).await, ["wamid.1"]);
}

/// erplora.com answers 500 after the provider accepted (its quota bookkeeping failed): the hub
/// retries — that is the ladder — but it retries THE SAME send, so the proxy can recognise it.
#[tokio::test]
async fn a_send_answered_with_an_error_after_it_left_reaches_the_customer_once_hub2648() {
    let cloud = fake_cloud(FAIL_ONCE).await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;

    queue_confirmation(&db, &reg, "Your table is booked for 21:00").await;
    let _ = outbox::drain(&db, &reg).await;
    assert_eq!(outbox_status(&db).await, ["pending"], "a 500 is retried");
    make_due_again(&db).await;
    let _ = outbox::drain(&db, &reg).await;

    assert_eq!(cloud.provider_sends(), 1, "the customer got the booking twice");
    assert_one_stable_key(&cloud.keys(), 2);
    assert_eq!(outbox_status(&db).await, ["delivered"]);
}

/// The key names ONE delivery, not the customer or the text: two confirmations to the same phone
/// are two messages, and both leave.
#[tokio::test]
async fn two_different_messages_to_the_same_customer_both_leave_hub2648() {
    let cloud = fake_cloud(ANSWER).await;
    let db = hub_db().await;
    let reg = registry(&cloud);
    authorize(&db, &reg).await;

    queue_confirmation(&db, &reg, "Your appointment is confirmed for Tuesday 10:00").await;
    queue_confirmation(&db, &reg, "Your appointment is confirmed for Tuesday 10:00").await;
    let _ = outbox::drain(&db, &reg).await;

    assert_eq!(cloud.provider_sends(), 2, "two messages queued, two messages sent");
    let keys = cloud.keys();
    assert_eq!(keys.len(), 2);
    assert!(keys.iter().all(|k| k.as_deref().is_some_and(|k| !k.is_empty())));
    assert_ne!(keys[0], keys[1], "two deliveries cannot share a key: {keys:?}");
    assert_eq!(outbox_status(&db).await, ["delivered", "delivered"]);
}
