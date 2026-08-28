//! What the browser is allowed to READ when the SaaS refuses a member sync (ERPlora/hub#1214).
//!
//! Every alta/baja of a login user notifies the SaaS, which is the source of truth of ACCESS
//! (ADR-0157 §7). When that call fails, `members::members_error_response` used to answer with the
//! `Display` of the error — and that `Display` embedded the **raw body of the other system**:
//!
//! ```text
//! el SaaS respondió 429: {"detail":"Request was throttled. Expected available in 2828 seconds."}
//! ```
//!
//! DRF's English inside a Spanish sentence, painted verbatim on a Spanish screen (seen in prod on
//! `qa-validate-20260822-0752.a.erplora.com`, v1.1.9). It is the same class of leak that hub#1074
//! and hub#1186 closed for the dispatcher: the hub's plumbing — and here, somebody else's — is
//! redacted to a **stable code** and the detail goes to the log.
//!
//! Two properties are pinned here, and they are different:
//!
//!  1. **The body of the SaaS does not travel.** Not in `message`, not in any other key: the
//!     assertion is on the WHOLE serialized response.
//!  2. **A 429 is not a business rejection.** «Wait and retry» and «fix what you typed» are
//!     opposite actions for whoever is administering, so they carry different codes
//!     (`cloud_rate_limited` vs `cloud_rejected`) — the same code `entitlement.rs` already uses.
//!
//! Every assertion is on the **code** (ADR-0055): never on the sentence, which is written for the
//! log and may be reworded without breaking a screen.

use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

/// The real SaaS route the runtime notifies (`cloud_client::CloudClient::members_add`).
const CLOUD_PATH: &str = "/api/v1/hub/device/members/";
/// The EXACT prose DRF returns on a throttle, seen painted on the Spanish UI (hub#1167/#1214).
const SAAS_PROSE: &str = "Request was throttled. Expected available in 2828 seconds.";
/// The EXACT prose a business rejection of the SaaS carries — also somebody else's wording.
const SAAS_BUSINESS_PROSE: &str = "A member with this email already exists in another hub.";
/// The Spanish wrapper the runtime used to build around the foreign body.
const RUNTIME_WRAPPER: &str = "el SaaS respondió";

struct Fixture {
    router: Router,
    /// Admin session: the gate of `/api/members` and `/api/hub/users` is owner/admin.
    admin: String,
    media: std::path::PathBuf,
}

async fn fixture(cloud_base_url: String, tag: &str) -> Fixture {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-1214");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt
        .get_or_link_cloud_user("cloud-1214", "Ioan Beilic", "admin", None, None)
        .await
        .unwrap();
    let session = rt.create_session(&admin.id, 3600, None).await.unwrap();
    let media = std::env::temp_dir().join(format!(
        "erplora-members-1214-{tag}-{}",
        std::process::id()
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-1214".into(),
        cloud_base_url,
        module_cache: media.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: media.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        admin: session,
        media,
    }
}

/// A SaaS that always refuses the member sync with `status` + `body`.
fn refusing_cloud(status: StatusCode, body: Value) -> Router {
    let body = Arc::new(body);
    Router::new().route(
        CLOUD_PATH,
        post(move || {
            let body = body.clone();
            async move { (status, Json((*body).clone())) }
        }),
    )
}

async fn post_json(router: &Router, uri: &str, session: &str, body: Value) -> (StatusCode, Value) {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(uri)
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap_or(Value::Null))
}

/// The whole body serialized — a leak that moves to another key is still a leak.
fn flat(body: &Value) -> String {
    serde_json::to_string(body).unwrap_or_default()
}

fn assert_hides_the_cloud_body(body: &Value, foreign: &str) {
    let raw = flat(body);
    assert!(
        !raw.contains(foreign),
        "the body written by the SaaS reached the browser: {raw}"
    );
    assert!(
        !raw.contains(RUNTIME_WRAPPER),
        "the sentence that wrapped the foreign body is still travelling: {raw}"
    );
}

/// ⓵ A 429 of the SaaS travels as `cloud_rate_limited` — the code `entitlement.rs` already uses —
/// and its prose stays in the log.
#[tokio::test]
async fn a_429_from_the_saas_travels_as_a_rate_limit_code_hub1214() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let cloud = refusing_cloud(
        StatusCode::TOO_MANY_REQUESTS,
        json!({ "detail": SAAS_PROSE }),
    );
    let server = tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });

    let f = fixture(format!("http://{address}"), "throttled").await;
    let (status, body) = post_json(
        &f.router,
        "/api/members",
        &f.admin,
        json!({ "email": "ana@example.com", "role": "manager" }),
    )
    .await;

    assert_eq!(
        status,
        StatusCode::TOO_MANY_REQUESTS,
        "a throttle keeps its own status, not a generic 4xx: {}",
        flat(&body)
    );
    assert_eq!(
        body["error"]["code"], "cloud_rate_limited",
        "the screen translates by CODE (ADR-0055), and «wait and retry» is not «fix what you typed»: {}",
        flat(&body)
    );
    assert_hides_the_cloud_body(&body, SAAS_PROSE);
    server.abort();
    std::fs::remove_dir_all(f.media).ok();
}

/// ⓶ A business rejection (4xx that is not a throttle) keeps `cloud_rejected` — and its body stays
/// out of the browser too. Both refusals are foreign prose; only one of them means «wait».
#[tokio::test]
async fn a_business_rejection_keeps_its_own_code_and_hides_the_body_hub1214() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let cloud = refusing_cloud(
        StatusCode::BAD_REQUEST,
        json!({ "detail": SAAS_BUSINESS_PROSE }),
    );
    let server = tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });

    let f = fixture(format!("http://{address}"), "rejected").await;
    let (status, body) = post_json(
        &f.router,
        "/api/members",
        &f.admin,
        json!({ "email": "ana@example.com", "role": "manager" }),
    )
    .await;

    assert_eq!(status, StatusCode::BAD_REQUEST, "{}", flat(&body));
    assert_eq!(
        body["error"]["code"], "cloud_rejected",
        "a business refusal is NOT a rate limit: {}",
        flat(&body)
    );
    assert_hides_the_cloud_body(&body, SAAS_BUSINESS_PROSE);
    server.abort();
    std::fs::remove_dir_all(f.media).ok();
}

/// ⓷ The screen that actually broke. Personal → «New user» posts to `/api/hub/users`, which syncs
/// access through the very same door: the code has to be INSIDE `error`, where the shell reads it.
#[tokio::test]
async fn the_employees_screen_reads_the_code_inside_error_hub1214() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let cloud = refusing_cloud(
        StatusCode::TOO_MANY_REQUESTS,
        json!({ "detail": SAAS_PROSE }),
    );
    let server = tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });

    let f = fixture(format!("http://{address}"), "employees").await;
    let (status, body) = post_json(
        &f.router,
        "/api/hub/users",
        &f.admin,
        json!({ "name": "Ana Soto", "email": "ana@example.com", "role": "manager" }),
    )
    .await;

    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS, "{}", flat(&body));
    assert_eq!(
        body["error"]["code"], "cloud_rate_limited",
        "the shell reads `error.code`; a sibling `code` leaves it with nothing but the prose: {}",
        flat(&body)
    );
    assert_hides_the_cloud_body(&body, SAAS_PROSE);
    server.abort();
    std::fs::remove_dir_all(f.media).ok();
}

/// ⓸ **Vecino del mismo fichero** (spin-off de hub#1214): la validación del propio alta salía en
/// prosa española y fuera del envelope (`{"ok":false,"error":"email y role son obligatorios"}`).
/// Es la misma regla — código estable dentro de `error` — aplicada a la puerta de al lado, y es la
/// que ya usan las demás puertas del runtime para un cuerpo mal formado (`invalid_payload`).
#[tokio::test]
async fn a_malformed_alta_is_refused_with_a_stable_code_too_hub1214() {
    let f = fixture("http://127.0.0.1:1".into(), "malformed").await;
    let (status, body) = post_json(
        &f.router,
        "/api/members",
        &f.admin,
        json!({ "email": "  ", "role": "manager" }),
    )
    .await;

    assert_eq!(status, StatusCode::BAD_REQUEST, "{}", flat(&body));
    assert_eq!(
        body["error"]["code"], "invalid_payload",
        "the envelope is the same one everywhere, and the code is what the screen reads: {}",
        flat(&body)
    );
    std::fs::remove_dir_all(f.media).ok();
}
