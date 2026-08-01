use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::webhooks::{WebhookDelivery, WebhookTransport};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-edge-1";

#[derive(Debug)]
struct RetryTransport {
    failures_left: AtomicUsize,
    attempts: AtomicUsize,
    sent: Mutex<Vec<WebhookDelivery>>,
}

impl RetryTransport {
    fn fail_once() -> Self {
        Self {
            failures_left: AtomicUsize::new(1),
            attempts: AtomicUsize::new(0),
            sent: Mutex::new(Vec::new()),
        }
    }
}

#[async_trait]
impl WebhookTransport for RetryTransport {
    async fn send(&self, delivery: &WebhookDelivery) -> Result<(), String> {
        self.attempts.fetch_add(1, Ordering::SeqCst);
        if self
            .failures_left
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| n.checked_sub(1))
            .is_ok()
        {
            return Err("fallo transitorio de prueba".into());
        }
        self.sent.lock().unwrap().push(delivery.clone());
        Ok(())
    }
}

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_public_api")
}

fn config() -> HubConfig {
    HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache: std::env::temp_dir().join("erplora-edge-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("machine".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-edge-media"),
        sector: None,
        dev_mode: true,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

fn admin(method: &str, uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method(method)
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", HUB_ID)
        .header("x-user-id", "admin")
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

fn external(uri: &str, token: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("authorization", format!("Bearer {token}"))
        .body(Body::from(body.to_string()))
        .unwrap()
}

async fn json_body(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn create_key(app: &axum::Router, limit: i64, name: &str) -> String {
    let response = app
        .clone()
        .oneshot(admin(
            "POST",
            "/api/keys",
            json!({
                "name": name,
                "rate_limit_per_minute": limit,
                "scope": [{"module":"catalog","read":true,"write":true}]
            }),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    json_body(response).await["data"]["secret"]
        .as_str()
        .unwrap()
        .to_string()
}

#[tokio::test]
async fn inbound_is_idempotent_rate_limited_and_outbound_retries_with_signature() {
    // 32 bytes base64. El secreto de la suscripción debe quedar cifrado at-rest.
    let previous = std::env::var("HUB_SECRETS_KEY").ok();
    unsafe {
        std::env::set_var(
            "HUB_SECRETS_KEY",
            "BwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwc=",
        )
    };

    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), HUB_ID);
    runtime.ensure_system_tables().await.unwrap();
    runtime.install_from_dir(&fixture()).await.unwrap();
    let transport = Arc::new(RetryTransport::fail_once());
    runtime.set_webhook_transport(transport.clone());
    let state = AppState::with_config(runtime, config());
    let app = app(state.clone());

    let subscription = app
        .clone()
        .oneshot(admin(
            "POST",
            "/api/webhooks/subscriptions",
            json!({
                "name": "ERP receptor",
                "url": "http://127.0.0.1:45678/capture",
                "events": ["catalog.item.created"]
            }),
        ))
        .await
        .unwrap();
    let subscription_status = subscription.status();
    let subscription_body = json_body(subscription).await;
    assert_eq!(subscription_status, StatusCode::OK, "{subscription_body:?}");
    let revealed_secret = subscription_body["data"]["secret"]
        .as_str()
        .unwrap()
        .to_string();

    // El secreto solo se revela al alta; PostgreSQL conserva un envelope cifrado, no el whsec.
    {
        let runtime = state.runtime.lock().await;
        let rows = runtime
            .db()
            .query(
                "SELECT secret_encrypted FROM hub_webhook_subscription",
                &Params::new(),
            )
            .await
            .unwrap();
        let stored = rows.rows[0]["secret_encrypted"].as_str().unwrap();
        assert!(stored.starts_with("v1:"));
        assert!(!stored.contains(&revealed_secret));
    }

    let token = create_key(&app, 10, "Entrada").await;
    let body =
        json!({"id":"order-42","occurred_at":"2026-08-01T10:00:00Z","payload":{"name":"Widget"}});
    let first = app
        .clone()
        .oneshot(external(
            "/webhook/catalog/item.create",
            &token,
            body.clone(),
        ))
        .await
        .unwrap();
    assert_eq!(first.status(), StatusCode::OK);
    assert_eq!(json_body(first).await["replay"], json!(false));
    let replay = app
        .clone()
        .oneshot(external("/webhook/catalog/item.create", &token, body))
        .await
        .unwrap();
    assert_eq!(replay.status(), StatusCode::OK);
    assert_eq!(json_body(replay).await["replay"], json!(true));
    let conflict = app
        .clone()
        .oneshot(external(
            "/webhook/catalog/item.create",
            &token,
            json!({"id":"order-42","payload":{"name":"Payload distinto"}}),
        ))
        .await
        .unwrap();
    assert_eq!(conflict.status(), StatusCode::CONFLICT);

    // Una sola mutación pese al retry del emisor.
    {
        let runtime = state.runtime.lock().await;
        let rows = runtime
            .db()
            .query(
                "SELECT COUNT(*) AS count FROM catalog_items",
                &Params::new(),
            )
            .await
            .unwrap();
        assert_eq!(rows.rows[0]["count"], json!(1));

        // Primer envío externo falla: el Outbox conserva la fila para retry.
        runtime.process_outbox().await.unwrap();
        let rows = runtime
            .db()
            .query("SELECT status, attempts FROM _event_outbox", &Params::new())
            .await
            .unwrap();
        assert_eq!(rows.rows[0]["status"], json!("pending"));
        assert_eq!(rows.rows[0]["attempts"], json!(1));
        runtime
            .db()
            .execute(
                "UPDATE _event_outbox SET next_attempt_at = '2020-01-01T00:00:00Z'",
                &Params::new(),
            )
            .await
            .unwrap();
        runtime.process_outbox().await.unwrap();
    }
    assert_eq!(transport.attempts.load(Ordering::SeqCst), 2);
    let sent = transport.sent.lock().unwrap();
    assert_eq!(sent.len(), 1);
    assert_eq!(sent[0].event_name, "catalog.item.created");
    assert!(sent[0].signature.starts_with("v1="));
    assert!(sent[0].body.contains("\"id\":\""));
    drop(sent);

    // La cuota se comparte entre endpoints externos y devuelve 429 con Retry-After.
    let limited = create_key(&app, 1, "Limitada").await;
    let first = app
        .clone()
        .oneshot(external(
            "/api/v1/catalog/q/items.list",
            &limited,
            json!({"params":{}}),
        ))
        .await
        .unwrap();
    assert_eq!(first.status(), StatusCode::OK);
    let second = app
        .clone()
        .oneshot(external(
            "/api/v1/catalog/q/items.list",
            &limited,
            json!({"params":{}}),
        ))
        .await
        .unwrap();
    assert_eq!(second.status(), StatusCode::TOO_MANY_REQUESTS);
    assert!(second.headers().contains_key("retry-after"));

    unsafe {
        match previous {
            Some(value) => std::env::set_var("HUB_SECRETS_KEY", value),
            None => std::env::remove_var("HUB_SECRETS_KEY"),
        }
    }
}
