//! Who may ask the hub about its assistant plan, and who may open a checkout for it — ERPlora/hub#1254.
//!
//! Regression test for ERPlora/hub#1254. `contracts/kernel/routes.snapshot` (ADR «El Hub se CIERRA
//! como KERNEL») showed `GET /api/assistant/config` and `POST /api/assistant/checkout` as
//! `auth:none`: the only credential on that path was `auth::hub_scoped_auth`, which is the hub's
//! OUTBOUND machine token (ADR-0003) and never looks at who is calling. Anybody who reached the
//! hub's URL — no session, no PIN, no API key — could read the plan and open Stripe checkout
//! sessions billed to the hub.
//!
//! The gate is asserted from OUTSIDE, through the router, and the Cloud is a local stub that
//! COUNTS its hits: a refusal that still asked the Cloud would not be a refusal at all, and a test
//! that only looked at the status code could not tell the two apart.
//!
//! The classes are the ones the rest of the group already uses:
//!
//!  - `config` is a **read** any signed-in hub user needs (the drawer shows the tier and what is
//!    left of the month), so: session.
//!  - `checkout` **contracts a plan the hub pays for**, so: admin session — the same door as
//!    settings, API keys and the certificate. A valid session with the wrong role gets `403`, not
//!    `401`: re-authenticating as the same cashier would never help.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const CONFIG_URI: &str = "/api/assistant/config";
const CHECKOUT_URI: &str = "/api/assistant/checkout";

/// How many times the stub Cloud was actually asked. A door that refuses AFTER proxying has
/// already leaked the call (and, for checkout, already created the session).
#[derive(Clone, Default)]
struct CloudHits(Arc<AtomicUsize>);

impl CloudHits {
    fn count(&self) -> usize {
        self.0.load(Ordering::SeqCst)
    }
}

/// The SaaS endpoints the two handlers proxy to (`crates/cloud-client`), answering happily. If the
/// hub's own door is missing, this stub is what an anonymous caller gets to talk to.
async fn stub_cloud() -> (String, CloudHits, tokio::task::JoinHandle<()>) {
    let hits = CloudHits::default();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let for_config = hits.clone();
    let for_checkout = hits.clone();
    let router = Router::new()
        .route(
            "/api/v1/hub/device/assistant/config/",
            get(move || {
                let hits = for_config.clone();
                async move {
                    hits.0.fetch_add(1, Ordering::SeqCst);
                    Json(json!({ "tier": "basic", "usage": { "messages_used": 3 } }))
                }
            }),
        )
        .route(
            "/api/v1/hub/device/assistant/subscription/checkout/",
            post(move |Json(_body): Json<Value>| {
                let hits = for_checkout.clone();
                async move {
                    hits.0.fetch_add(1, Ordering::SeqCst);
                    Json(json!({ "checkout_url": "https://checkout.stripe.test/s/1" }))
                }
            }),
        );
    let served = tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    (format!("http://{address}"), hits, served)
}

/// Router in `Session` mode (production's mode) with an admin and an employee signed in, and with
/// the machine token present — so `hub_scoped_auth` succeeds and the ONLY thing that can stop an
/// anonymous request is a door of the hub's own.
async fn fixture(cloud_base_url: String, tag: &str) -> (Router, String, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-assistant");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-assistant-{tag}-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-assistant".into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    (app(AppState::with_config(rt, cfg)), admin, employee)
}

fn read_config(session: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("GET").uri(CONFIG_URI);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    builder.body(Body::empty()).unwrap()
}

fn open_checkout(session: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder()
        .method("POST")
        .uri(CHECKOUT_URI)
        .header("content-type", "application/json");
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    builder
        .body(Body::from(
            json!({ "tier_slug": "basic", "billing_interval": "month" }).to_string(),
        ))
        .unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

#[tokio::test]
async fn assistant_config_without_a_session_is_401_hub1254() {
    let (cloud_url, hits, served) = stub_cloud().await;
    let (router, _admin, _employee) = fixture(cloud_url, "config-anon").await;

    let response = router.oneshot(read_config(None)).await.unwrap();

    assert_eq!(
        response.status(),
        StatusCode::UNAUTHORIZED,
        "un anónimo no lee el plan del asistente de este hub: {:?}",
        body_json(response).await
    );
    assert_eq!(
        hits.count(),
        0,
        "la petición anónima llegó hasta el Cloud: la puerta no está antes del proxy"
    );
    served.abort();
}

#[tokio::test]
async fn assistant_checkout_without_a_session_is_401_hub1254() {
    let (cloud_url, hits, served) = stub_cloud().await;
    let (router, _admin, _employee) = fixture(cloud_url, "checkout-anon").await;

    let response = router.oneshot(open_checkout(None)).await.unwrap();

    assert_eq!(
        response.status(),
        StatusCode::UNAUTHORIZED,
        "un anónimo no abre un checkout a cuenta de este hub: {:?}",
        body_json(response).await
    );
    assert_eq!(
        hits.count(),
        0,
        "se creó una sesión de checkout en el Cloud para un llamador anónimo"
    );
    served.abort();
}

#[tokio::test]
async fn assistant_checkout_with_an_employee_session_is_403_hub1254() {
    let (cloud_url, hits, served) = stub_cloud().await;
    let (router, _admin, employee) = fixture(cloud_url, "checkout-employee").await;

    let response = router
        .oneshot(open_checkout(Some(&employee)))
        .await
        .unwrap();

    assert_eq!(
        response.status(),
        StatusCode::FORBIDDEN,
        "quien contrata el plan es owner/admin; volver a autenticarse como cajero no ayudaría"
    );
    assert_eq!(hits.count(), 0, "el cajero llegó a crear el checkout");
    served.abort();
}

#[tokio::test]
async fn assistant_config_with_any_session_still_reaches_the_cloud_hub1254() {
    let (cloud_url, hits, served) = stub_cloud().await;
    let (router, _admin, employee) = fixture(cloud_url, "config-employee").await;

    let response = router.oneshot(read_config(Some(&employee))).await.unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        body_json(response).await["tier"],
        "basic",
        "el JSON del Cloud se entrega tal cual (contrato previo de `proxy_cloud_get`)"
    );
    assert_eq!(hits.count(), 1);
    served.abort();
}

#[tokio::test]
async fn assistant_checkout_with_an_admin_session_still_reaches_the_cloud_hub1254() {
    let (cloud_url, hits, served) = stub_cloud().await;
    let (router, admin, _employee) = fixture(cloud_url, "checkout-admin").await;

    let response = router.oneshot(open_checkout(Some(&admin))).await.unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        body_json(response).await["checkout_url"],
        "https://checkout.stripe.test/s/1",
        "cerrar la puerta no puede romper la compra de quien SÍ contrata"
    );
    assert_eq!(hits.count(), 1);
    served.abort();
}
