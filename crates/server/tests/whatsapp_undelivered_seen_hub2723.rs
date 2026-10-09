//! A WhatsApp that WhatsApp accepts and then does not deliver is seen as failed, with its reason,
//! in «Eventos caídos» (hub#2723).
//!
//! Meta answers a send with an id (`wamid`) the moment it ACCEPTS it; whether the customer's phone
//! ever gets it arrives later, as a status (`sent`, `delivered`, `read` or `failed`). The commonest
//! `failed` is free text to a customer who has not written in 24 hours (131047). erplora.com keeps
//! those statuses for the hub (ERPlora/saas#2669) and the hub collects them the way it collects the
//! messages that come in: fetch, write, and only then acknowledge.
//!
//! The fake erplora.com below keeps the real contract — a status stays pending until the hub acks
//! that exact (`wa_message_id`, `status`) pair — and the hub is the production one: the outbox
//! relay, [`CloudNotifyTransport`], the status poller and a real Postgres.

use std::path::PathBuf;
use std::sync::{Arc, Mutex, RwLock};

use axum::extract::State;
use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::elevation::Grants;
use erplora_runtime::host_notify::ALLOWED_RECIPIENTS_SETTING;
use erplora_runtime::registry::RequestContext;
use erplora_runtime::{capabilities, commands, outbox, settings, Runtime};
use erplora_server::entitlement;
use erplora_server::notify_transport::CloudNotifyTransport;
use erplora_server::state::SharedRuntime;
use erplora_server::whatsapp_statuses::StatusPoller;
use serde_json::{json, Value};
use tokio::sync::RwLock as RuntimeLock;

const HUB: &str = "hub-wa-2723";
const MODULE: &str = "whatsapp_inbox";
const CUSTOMER: &str = "+34600111222";

/// How the fake erplora.com answers a send.
#[derive(Clone, Copy, PartialEq)]
enum SendAnswer {
    /// Meta accepted it: `200 {message_id: wamid.N}`.
    Accept,
    /// Meta refused it in the act and said why (ERPlora/saas#2669): `502 meta_send_failed` with
    /// `meta_error.reason = outside_window`.
    RefuseOutsideWindow,
    /// Meta refused it with nothing the hub can act on: the generic `meta_error` reason.
    RefuseGeneric,
    /// A 502 that names no reason at all (an older erplora.com, or Meta not answering).
    RefuseBare,
}

#[derive(Default)]
struct Ledger {
    sends: usize,
    /// Statuses waiting for the hub, in the shape `GET …/statuses/` serves them.
    pending: Vec<Value>,
    /// How many times the hub asked for statuses.
    status_fetches: usize,
    /// Every ack body the hub sent, in order.
    acks: Vec<Value>,
}

#[derive(Clone)]
struct Cloud {
    ledger: Arc<Mutex<Ledger>>,
    answer: Arc<Mutex<SendAnswer>>,
}

struct FakeCloud {
    base_url: String,
    cloud: Cloud,
    server: tokio::task::JoinHandle<()>,
}

impl Drop for FakeCloud {
    fn drop(&mut self) {
        self.server.abort();
    }
}

impl FakeCloud {
    fn sends(&self) -> usize {
        self.cloud.ledger.lock().unwrap().sends
    }

    fn status_fetches(&self) -> usize {
        self.cloud.ledger.lock().unwrap().status_fetches
    }

    fn acks(&self) -> Vec<Value> {
        self.cloud.ledger.lock().unwrap().acks.clone()
    }

    fn pending(&self) -> Vec<Value> {
        self.cloud.ledger.lock().unwrap().pending.clone()
    }

    /// Meta reports a status for one of the hub's messages.
    fn report(&self, wamid: &str, status: &str, error: Value) {
        self.cloud.ledger.lock().unwrap().pending.push(json!({
            "wa_message_id": wamid,
            "status": status,
            "error": error,
            "status_at": "2026-10-09T10:00:00+00:00",
        }));
    }
}

fn outside_window_error() -> Value {
    json!({
        "code": 131047,
        "reason": "outside_window",
        "title": "Re-engagement message",
        "detail": "More than 24 hours have passed since the recipient last replied to the sender number.",
    })
}

async fn fake_cloud(answer: SendAnswer) -> FakeCloud {
    async fn notify(State(cloud): State<Cloud>) -> (StatusCode, Json<Value>) {
        let answer = *cloud.answer.lock().unwrap();
        let mut ledger = cloud.ledger.lock().unwrap();
        ledger.sends += 1;
        match answer {
            SendAnswer::Accept => (
                StatusCode::OK,
                Json(json!({ "message_id": format!("wamid.{}", ledger.sends) })),
            ),
            SendAnswer::RefuseOutsideWindow => (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "error": "meta_send_failed", "meta_error": outside_window_error() })),
            ),
            SendAnswer::RefuseGeneric => (
                StatusCode::BAD_GATEWAY,
                Json(json!({
                    "error": "meta_send_failed",
                    "meta_error": {"code": 1, "reason": "meta_error", "title": "Unknown", "detail": ""},
                })),
            ),
            SendAnswer::RefuseBare => (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "error": "meta_send_failed" })),
            ),
        }
    }

    async fn statuses(State(cloud): State<Cloud>) -> Json<Value> {
        let mut ledger = cloud.ledger.lock().unwrap();
        ledger.status_fetches += 1;
        Json(json!({ "statuses": ledger.pending.clone() }))
    }

    /// Confirms only the pairs that still match what is pending — the SaaS rule: a status that
    /// moved on is served again.
    async fn ack(State(cloud): State<Cloud>, Json(body): Json<Value>) -> Json<Value> {
        let mut ledger = cloud.ledger.lock().unwrap();
        ledger.acks.push(body.clone());
        let named: Vec<(String, String)> = body["statuses"]
            .as_array()
            .cloned()
            .unwrap_or_default()
            .iter()
            .map(|s| {
                (
                    s["wa_message_id"].as_str().unwrap_or_default().to_owned(),
                    s["status"].as_str().unwrap_or_default().to_owned(),
                )
            })
            .collect();
        let before = ledger.pending.len();
        ledger.pending.retain(|p| {
            !named.iter().any(|(id, st)| {
                p["wa_message_id"].as_str() == Some(id) && p["status"].as_str() == Some(st)
            })
        });
        let acked = before - ledger.pending.len();
        Json(json!({ "acked": acked }))
    }

    let cloud = Cloud {
        ledger: Arc::default(),
        answer: Arc::new(Mutex::new(answer)),
    };
    let app = Router::new()
        .route("/api/v1/hub/device/notify/whatsapp/", post(notify))
        .route("/api/v1/hub/device/whatsapp/statuses/", get(statuses))
        .route("/api/v1/hub/device/whatsapp/statuses/ack/", post(ack))
        .with_state(cloud.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    FakeCloud {
        base_url: format!("http://{addr}"),
        cloud,
        server,
    }
}

fn scratch_dir(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "erplora-{tag}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// A hub that runs the WhatsApp inbox, allowed to send WhatsApp to [`CUSTOMER`], with the real
/// cloud transport. Installed through `install_from_dir`, the one door that registers anything.
async fn hub(cloud: &FakeCloud, with_inbox: bool) -> SharedRuntime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    if with_inbox {
        let dir = scratch_dir("wa-2723");
        std::fs::create_dir_all(dir.join("sql")).unwrap();
        std::fs::write(dir.join("sql/remind.sql"), "SELECT 1").unwrap();
        std::fs::write(
            dir.join("module.json"),
            json!({
                "id": MODULE, "name": "WhatsApp Inbox", "version": "1.0.0",
                "capabilities": { "notify": { "channels": ["whatsapp"] } },
                "commands": {
                    "remind": {
                        "permission": "",
                        "transaction": true,
                        "sql": ["sql/remind.sql"],
                        "emit": [format!("{MODULE}.reminder.due")],
                    }
                },
            })
            .to_string(),
        )
        .unwrap();
        rt.install_from_dir(&dir).await.unwrap();
        let _ = std::fs::remove_dir_all(&dir);
        capabilities::set_grant(rt.db(), rt.registry(), HUB, MODULE, "notify", true, "hub_user:admin")
            .await
            .unwrap();
        let mut s = Params::new();
        s.insert(ALLOWED_RECIPIENTS_SETTING.into(), json!(CUSTOMER));
        settings::set_many(rt.db(), HUB, &s, "hub_user:admin")
            .await
            .unwrap();
    }
    rt.set_notify_transport(Arc::new(CloudNotifyTransport::new(
        reqwest::Client::new(),
        &cloud.base_url,
        Arc::new(RwLock::new(HUB.to_string())),
        Arc::new(RwLock::new(Some("machine-tok".to_string()))),
    )));
    Arc::new(RuntimeLock::new(rt))
}

fn poller(cloud: &FakeCloud) -> StatusPoller {
    StatusPoller::new(
        reqwest::Client::new(),
        &cloud.base_url,
        Arc::new(RwLock::new(HUB.to_string())),
        Arc::new(RwLock::new(Some("machine-tok".to_string()))),
    )
}

/// The appointment reminder, queued the way the module does it: a command that emits it.
async fn queue_reminder(runtime: &SharedRuntime) {
    let rt = runtime.read().await;
    let mut p = Params::new();
    p.insert("channel".into(), json!("whatsapp"));
    p.insert("to".into(), json!(CUSTOMER));
    p.insert("template".into(), json!(""));
    p.insert("vars".into(), json!({ "text": "See you tomorrow at 10:00" }));
    let ctx = RequestContext::new(HUB, "", ["*".to_string()]);
    commands::execute(rt.db(), rt.registry(), &format!("{MODULE}.remind"), &p, &ctx, &Grants::new())
        .await
        .unwrap();
}

async fn relay_once(runtime: &SharedRuntime) {
    let _ = runtime.read().await.process_outbox().await;
}

async fn outbox_status(runtime: &SharedRuntime) -> Vec<String> {
    runtime
        .read()
        .await
        .db()
        .query(
            "SELECT status FROM _event_outbox WHERE event_name LIKE '%.reminder.due' ORDER BY created_at",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| r["status"].as_str().unwrap_or_default().to_owned())
        .collect()
}

async fn dead(runtime: &SharedRuntime) -> Vec<outbox::DeadEvent> {
    runtime.read().await.list_dead_events(100).await.unwrap()
}

/// The issue itself: the reminder went out, Meta accepted it, and then failed it because the
/// customer had not written in 24 hours. Today the hub keeps it as sent and nobody finds out.
#[tokio::test]
async fn a_whatsapp_failed_after_being_accepted_shows_in_dead_events_with_its_reason_hub2723() {
    let cloud = fake_cloud(SendAnswer::Accept).await;
    let runtime = hub(&cloud, true).await;
    queue_reminder(&runtime).await;
    relay_once(&runtime).await;
    assert_eq!(outbox_status(&runtime).await, ["delivered"], "Meta accepted it");

    cloud.report("wamid.1", "failed", outside_window_error());
    poller(&cloud)
        .poll_once(&runtime, &entitlement::new_shared())
        .await
        .unwrap();

    let dead = dead(&runtime).await;
    assert_eq!(dead.len(), 1, "the failed send must be in «Eventos caídos»: {dead:?}");
    assert_eq!(dead[0].failure_kind, "whatsapp.undelivered.outside_window");
    assert!(
        !dead[0].retryable,
        "resending reaches erplora.com with the same key, which answers the old id without sending: \
         the button would lie"
    );
    assert_eq!(dead[0].payload["to"], CUSTOMER, "who did not get it stays visible");
    assert!(dead[0].last_error.contains("131047"), "Meta's code: {}", dead[0].last_error);
    assert!(cloud.pending().is_empty(), "recorded, so acknowledged");
    assert_eq!(
        cloud.acks(),
        [json!({"statuses": [{"wa_message_id": "wamid.1", "status": "failed"}]})]
    );
}

/// `sent`, `delivered` and `read` change nothing the business sees, and a status for a message this
/// hub did not send (one the owner typed in the WhatsApp Business app) is not its to record. All of
/// them are acknowledged, or they would be served again on every tick.
#[tokio::test]
async fn good_news_and_foreign_ids_are_acknowledged_and_change_nothing_hub2723() {
    let cloud = fake_cloud(SendAnswer::Accept).await;
    let runtime = hub(&cloud, true).await;
    queue_reminder(&runtime).await;
    relay_once(&runtime).await;

    cloud.report("wamid.1", "delivered", Value::Null);
    cloud.report("wamid.1", "read", Value::Null);
    cloud.report("wamid.from-the-phone", "failed", outside_window_error());
    poller(&cloud)
        .poll_once(&runtime, &entitlement::new_shared())
        .await
        .unwrap();

    assert!(dead(&runtime).await.is_empty());
    assert_eq!(outbox_status(&runtime).await, ["delivered"]);
    assert!(cloud.pending().is_empty(), "every status acknowledged: {:?}", cloud.pending());
}

/// A reason this hub does not know yet (Meta grows its list) is still a failure: it lands with the
/// generic reason rather than being dropped.
#[tokio::test]
async fn an_unknown_reason_still_lands_with_the_generic_one_hub2723() {
    let cloud = fake_cloud(SendAnswer::Accept).await;
    let runtime = hub(&cloud, true).await;
    queue_reminder(&runtime).await;
    relay_once(&runtime).await;

    cloud.report(
        "wamid.1",
        "failed",
        json!({"code": 999999, "reason": "something_new", "title": "New", "detail": ""}),
    );
    poller(&cloud)
        .poll_once(&runtime, &entitlement::new_shared())
        .await
        .unwrap();

    let dead = dead(&runtime).await;
    assert_eq!(dead.len(), 1);
    assert_eq!(dead[0].failure_kind, "whatsapp.undelivered.meta_error");
}

/// No inbox module, no request: a hub that does not run WhatsApp must not ask 120 times an hour.
#[tokio::test]
async fn without_the_inbox_no_request_leaves_the_hub_hub2723() {
    let cloud = fake_cloud(SendAnswer::Accept).await;
    let runtime = hub(&cloud, false).await;
    cloud.report("wamid.1", "failed", outside_window_error());
    poller(&cloud)
        .poll_once(&runtime, &entitlement::new_shared())
        .await
        .unwrap();
    assert_eq!(cloud.status_fetches(), 0);
}

/// Meta refused in the act and SAID why (ERPlora/saas#2669): the eighth attempt would get the same
/// answer, so the reminder lands in «Eventos caídos» on the first pass, with the reason, and can
/// be resent once the customer writes back (erplora.com forgot the key of a refused send).
#[tokio::test]
async fn a_refusal_meta_explains_lands_at_once_and_can_be_resent_hub2723() {
    let cloud = fake_cloud(SendAnswer::RefuseOutsideWindow).await;
    let runtime = hub(&cloud, true).await;
    queue_reminder(&runtime).await;
    relay_once(&runtime).await;

    assert_eq!(cloud.sends(), 1);
    let dead = dead(&runtime).await;
    assert_eq!(dead.len(), 1, "no 4-minute ladder against the same answer");
    assert_eq!(dead[0].failure_kind, "whatsapp.refused.outside_window");
    assert!(dead[0].retryable, "a refused send was never sent: resending does send it");
    assert!(dead[0].last_error.contains("131047"), "{}", dead[0].last_error);

    let moved = {
        let rt = runtime.read().await;
        outbox::retry_all(rt.db(), HUB).await.unwrap()
    };
    assert_eq!(moved, 1, "«Reenviar todos» picks it up too");
    *cloud.cloud.answer.lock().unwrap() = SendAnswer::Accept;
    relay_once(&runtime).await;
    assert_eq!(outbox_status(&runtime).await, ["delivered"]);
}

/// The control: a refusal with no reason the hub can act on is still a stumble and keeps the
/// ladder (Meta down, an older erplora.com).
#[tokio::test]
async fn a_refusal_without_a_reason_keeps_the_ladder_hub2723() {
    for answer in [SendAnswer::RefuseGeneric, SendAnswer::RefuseBare] {
        let cloud = fake_cloud(answer).await;
        let runtime = hub(&cloud, true).await;
        queue_reminder(&runtime).await;
        relay_once(&runtime).await;
        assert_eq!(outbox_status(&runtime).await, ["pending"]);
        assert!(dead(&runtime).await.is_empty());
    }
}
