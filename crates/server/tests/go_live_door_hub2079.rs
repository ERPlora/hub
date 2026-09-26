//! **`/api/fiscal/go-live` — the one button that takes a hub to the real AEAT** (hub#2079).
//!
//! `fiscal_profile::go_live` was the only writer of `production` and nothing called it: the
//! VeriFactu screen wrote the environment into its own config instead, skipping the grant, the demo
//! pin and the expired certificate. This file pins the door the screen goes through:
//!  - anyone with a session READS where the hub files (`testing` on a fresh hub);
//!  - only an admin goes live; a hub that is not ready is refused with the go-live's own code and
//!    stays in `testing`; a demo is refused with `fiscal.go_live_forbidden`;
//!  - a ready hub goes live, and the answer (and the next read) says `production`;
//!  - `DELETE` stands it back down while nothing was filed;
//!  - a module that names itself needs the `certificate` capability granted, like the other fiscal
//!    doors (hub#1844) — otherwise any installed module could send the business to production.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::Router;
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-go-live-door";
const URI: &str = "/api/fiscal/go-live";

fn config(tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-go-live-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: HUB.into(),
        cloud_base_url: "http://127.0.0.1:9".into(),
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
    }
}

struct Fixture {
    router: Router,
    admin: String,
    employee: String,
}

/// `profile_sql` runs against `_hub_fiscal_profile` before the router is built (`:hub_id` bound).
async fn fixture(tag: &str, profile_sql: Option<&str>) -> Fixture {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    erplora_runtime::fiscal_profile::ensure(rt.db(), HUB)
        .await
        .unwrap();
    if let Some(sql) = profile_sql {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB));
        rt.db().execute(sql, &p).await.unwrap();
    }
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee_id = rt
        .create_user("Caja", "2222", "employee", None)
        .await
        .unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    Fixture {
        router: app(AppState::with_config(rt, config(tag))),
        admin,
        employee,
    }
}

/// READY on ERPlora's road with the grant approved: everything the go-live asks for.
const READY_WITH_GRANT: &str = "UPDATE _hub_fiscal_profile \
     SET status = 'READY', representation_status = 'vigente' WHERE hub_id = :hub_id";

async fn send(
    router: &Router,
    method: &str,
    session: &str,
    module: Option<&str>,
) -> (StatusCode, Value) {
    let mut request = Request::builder()
        .method(method)
        .uri(URI)
        .header("x-hub-session", session);
    if let Some(module) = module {
        request = request.header("x-erplora-module", module);
    }
    let response = router
        .clone()
        .oneshot(request.body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

fn code(body: &Value) -> &str {
    body["error"]["code"].as_str().unwrap_or_default()
}

#[tokio::test]
async fn any_session_reads_where_the_hub_files() {
    let f = fixture("read", None).await;
    let (status, body) = send(&f.router, "GET", &f.employee, None).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["data"]["environment"], "testing");
    assert_eq!(body["data"]["can_go_live"], true);
    assert_eq!(body["data"]["filed_for_real"], false);
}

#[tokio::test]
async fn only_an_admin_goes_live() {
    let f = fixture("employee", Some(READY_WITH_GRANT)).await;
    let (status, _) = send(&f.router, "POST", &f.employee, None).await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    let (_, body) = send(&f.router, "GET", &f.admin, None).await;
    assert_eq!(body["data"]["environment"], "testing");
}

/// 🔴 The check the old select skipped: a hub that is not ready does not reach production.
#[tokio::test]
async fn a_hub_that_is_not_ready_is_refused_and_stays_in_testing() {
    let f = fixture("not-ready", None).await;
    let (status, body) = send(&f.router, "POST", &f.admin, None).await;
    assert!(status.is_client_error(), "{status} {body}");
    assert!(
        code(&body).starts_with("fiscal."),
        "the go-live's own code reaches the screen: {body}"
    );
    let (_, body) = send(&f.router, "GET", &f.admin, None).await;
    assert_eq!(body["data"]["environment"], "testing");
}

/// The Anexo I (hub#817): READY on ERPlora's road without the approved grant is refused with the
/// code the screen turns into «sign the authorisation».
#[tokio::test]
async fn without_the_signed_grant_the_door_says_so() {
    let f = fixture(
        "no-grant",
        Some("UPDATE _hub_fiscal_profile SET status = 'READY' WHERE hub_id = :hub_id"),
    )
    .await;
    let (status, body) = send(&f.router, "POST", &f.admin, None).await;
    assert!(status.is_client_error(), "{status} {body}");
    assert_eq!(code(&body), "fiscal.no_representation_grant");
}

#[tokio::test]
async fn a_demo_is_refused_with_its_own_code() {
    let f = fixture(
        "demo",
        Some(
            "UPDATE _hub_fiscal_profile SET status = 'READY', representation_status = 'vigente', \
             can_go_live = 0 WHERE hub_id = :hub_id",
        ),
    )
    .await;
    let (status, body) = send(&f.router, "POST", &f.admin, None).await;
    assert!(status.is_client_error(), "{status} {body}");
    assert_eq!(code(&body), "fiscal.go_live_forbidden");
}

/// The positive control, and the way back while nothing was filed.
#[tokio::test]
async fn a_ready_hub_goes_live_and_can_stand_down_before_filing() {
    let f = fixture("ready", Some(READY_WITH_GRANT)).await;
    let (status, body) = send(&f.router, "POST", &f.admin, None).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["data"]["environment"], "production");
    let (_, body) = send(&f.router, "GET", &f.employee, None).await;
    assert_eq!(body["data"]["environment"], "production");

    let (status, _) = send(&f.router, "DELETE", &f.employee, None).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "only an admin stands down");
    let (status, body) = send(&f.router, "DELETE", &f.admin, None).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["data"]["environment"], "testing");
}

/// Once a record left for the real AEAT, there is no way back (ADR-0273 D3).
#[tokio::test]
async fn after_the_first_real_record_the_door_does_not_stand_down() {
    let f = fixture(
        "filed",
        Some(
            "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production', \
             first_record_at = '2026-09-24T10:00:00Z' WHERE hub_id = :hub_id",
        ),
    )
    .await;
    let (_, body) = send(&f.router, "GET", &f.admin, None).await;
    assert_eq!(body["data"]["filed_for_real"], true);
    let (status, body) = send(&f.router, "DELETE", &f.admin, None).await;
    assert!(status.is_client_error(), "{status} {body}");
    assert!(code(&body).starts_with("fiscal."), "{body}");
    let (_, body) = send(&f.router, "GET", &f.admin, None).await;
    assert_eq!(body["data"]["environment"], "production");
}

/// A module naming itself without the `certificate` grant does not get to send the business to
/// production; the same admin, without naming a module (the shell), does.
#[tokio::test]
async fn a_module_without_the_certificate_grant_cannot_go_live() {
    let f = fixture("module", Some(READY_WITH_GRANT)).await;
    let (status, body) = send(&f.router, "POST", &f.admin, Some("verifactu")).await;
    assert!(status.is_client_error(), "{status} {body}");
    let (_, body) = send(&f.router, "GET", &f.admin, None).await;
    assert_eq!(body["data"]["environment"], "testing");
}
