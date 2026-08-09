//! The three gates of hub#240 still cut BEFORE the network, now that the transport is real
//! (hub#663, ADR-0283 §5 K4).
//!
//! `crates/runtime/src/outbox.rs` already proves the gates against `MockTransport`, but a mock
//! that records in memory cannot tell you whether a real hub would have *dialled out*. Here the
//! transport is the production [`CloudNotifyTransport`] pointed at a fake SaaS that counts every
//! request it receives, so "nothing was sent" means the socket was never opened — the property
//! that actually matters when the alternative is exfiltrating a customer list and spending money.

use std::sync::{Arc, Mutex, RwLock};

use axum::extract::State;
use axum::http::StatusCode;
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params, PgAdapter};
use erplora_runtime::elevation::Grants;
use erplora_runtime::host_notify::ALLOWED_RECIPIENTS_SETTING;
use erplora_runtime::manifest::CommandDef;
use erplora_runtime::registry::{ModuleStatus, RegisteredCommand, Registry, RequestContext};
use erplora_runtime::{
    capabilities, commands, identity, installer, outbox, settings, system_migrations,
};
use erplora_server::notify_transport::CloudNotifyTransport;
use serde_json::{json, Value};

const HUB: &str = "h1";

/// Requests the fake SaaS saw. Its only job is to be able to say "zero".
type Seen = Arc<Mutex<Vec<Value>>>;

struct FakeCloud {
    base_url: String,
    seen: Seen,
    server: tokio::task::JoinHandle<()>,
}

impl FakeCloud {
    fn count(&self) -> usize {
        self.seen.lock().unwrap().len()
    }
}

impl Drop for FakeCloud {
    fn drop(&mut self) {
        self.server.abort();
    }
}

async fn fake_cloud() -> FakeCloud {
    async fn record(State(seen): State<Seen>, body: String) -> (StatusCode, Json<Value>) {
        seen.lock()
            .unwrap()
            .push(serde_json::from_str(&body).unwrap_or(Value::Null));
        (StatusCode::OK, Json(json!({ "message_id": "sent-1" })))
    }

    let seen: Seen = Arc::new(Mutex::new(Vec::new()));
    let app = Router::new()
        .route("/api/v1/hub/device/notify/email/", post(record))
        .route("/api/v1/hub/device/notify/whatsapp/", post(record))
        .with_state(seen.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    FakeCloud {
        base_url: format!("http://{addr}"),
        seen,
        server,
    }
}

/// A hub database with the system tables `host.notify` reads: capability grants, settings, users
/// and the outbox itself.
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

/// Registry with the `appt` module, its emitting command and the real cloud transport wired in.
/// `channels` is what the module DECLARES in its manifest.
fn registry(channels: &[&str], cloud: &FakeCloud) -> Registry {
    let manifest = json!({
        "id": "appt", "name": "Appointments", "version": "1.0.0",
        "capabilities": { "notify": { "channels": channels } },
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

/// Grants the `notify` capability and puts `to` on the hub owner's allowlist.
async fn authorize(db: &PgAdapter, reg: &Registry, to: &str) {
    capabilities::set_grant(db, reg, HUB, "appt", "notify", true, "hub_user:admin")
        .await
        .unwrap();
    let mut s = Params::new();
    s.insert(ALLOWED_RECIPIENTS_SETTING.into(), json!(to));
    settings::set_many(db, HUB, &s, "hub_user:admin", false)
        .await
        .unwrap();
}

fn reminder(channel: &str, to: &str) -> Params {
    let mut p = Params::new();
    p.insert("channel".into(), json!(channel));
    p.insert("to".into(), json!(to));
    p.insert("template".into(), json!("appointment_reminder"));
    p.insert(
        "vars".into(),
        json!({ "subject": "Tu cita", "text": "mañana a las 10:00" }),
    );
    p
}

async fn emit_and_drain(db: &PgAdapter, reg: &Registry, payload: Params) {
    let ctx = RequestContext::new(HUB, "", ["*".to_string()]);
    commands::execute(db, reg, "appt.remind", &payload, &ctx, &Grants::new())
        .await
        .unwrap();
    // A failing delivery is a retry, not a panic: `drain` reporting an error is exactly what the
    // relay does in production, and the assertion we care about is how many requests went out.
    let _ = outbox::drain(db, reg).await;
}

/// Happy path: with the capability granted, the channel declared and the recipient on the hub's
/// allowlist, the reminder really does leave through the SaaS proxy.
#[tokio::test]
async fn an_authorized_reminder_reaches_the_cloud_proxy() {
    let cloud = fake_cloud().await;
    let db = hub_db().await;
    let reg = registry(&["email"], &cloud);
    authorize(&db, &reg, "cliente@x.com").await;

    emit_and_drain(&db, &reg, reminder("email", "cliente@x.com")).await;

    assert_eq!(cloud.count(), 1, "the reminder must actually go out");
    let body = cloud.seen.lock().unwrap()[0].clone();
    assert_eq!(body["to"], "cliente@x.com");
    assert_eq!(body["subject"], "Tu cita");
    assert_eq!(body["text"], "mañana a las 10:00");
}

/// Gate 1 — capability. Without the `notify` grant nothing may leave the hub, and with a real
/// transport "nothing" has to mean no request at all.
#[tokio::test]
async fn a_module_without_the_notify_grant_never_reaches_the_network() {
    let cloud = fake_cloud().await;
    let db = hub_db().await;
    let reg = registry(&["email"], &cloud);
    // Recipient allowlisted, capability NOT granted.
    let mut s = Params::new();
    s.insert(ALLOWED_RECIPIENTS_SETTING.into(), json!("cliente@x.com"));
    settings::set_many(&db, HUB, &s, "hub_user:admin", false)
        .await
        .unwrap();

    emit_and_drain(&db, &reg, reminder("email", "cliente@x.com")).await;

    assert_eq!(cloud.count(), 0, "no grant, no socket");
}

/// Gate 2 — declared channel. Declaring `email` does not buy WhatsApp, which is the paid one.
#[tokio::test]
async fn an_undeclared_channel_never_reaches_the_network() {
    let cloud = fake_cloud().await;
    let db = hub_db().await;
    let reg = registry(&["email"], &cloud);
    authorize(&db, &reg, "+34600999888").await;

    emit_and_drain(&db, &reg, reminder("whatsapp", "+34600999888")).await;

    assert_eq!(cloud.count(), 0, "an undeclared channel must not dial out");
}

/// Gate 3 — the recipient comes from the hub's own data. A free address in a module's payload is
/// how a customer list walks out one message at a time.
#[tokio::test]
async fn a_recipient_that_is_not_the_hubs_never_reaches_the_network() {
    let cloud = fake_cloud().await;
    let db = hub_db().await;
    let reg = registry(&["email"], &cloud);
    authorize(&db, &reg, "cliente@x.com").await;

    emit_and_drain(&db, &reg, reminder("email", "atacante@evil.com")).await;

    assert_eq!(
        cloud.count(),
        0,
        "an address only the payload knows is not a recipient"
    );
}
