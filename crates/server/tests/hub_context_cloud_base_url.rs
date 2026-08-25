//! The boot context tells the web app **which Cloud this hub belongs to** (ERPlora/hub#1164).
//!
//! One image serves several SaaS (pre / prod). The runtime already knows its Cloud
//! (`HUB_CLOUD_API_URL` → `HubConfig::cloud_base_url`) and bakes it into the CSP `connect-src`,
//! but the web app used to carry its own copy fixed at build time (`VITE_CLOUD_API_URL`). A hub
//! provisioned by pre then sent the login to prod and its own CSP blocked it.
//!
//! What this file pins: `GET /api/hub/context` publishes `cloud_base_url` with exactly the value
//! the CSP was built from, and an empty value (dev binary with no Cloud) is published as such so
//! the shell can fall back to its build-time default.
use axum::body::Body;
use axum::http::Request;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, default_csp, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn config(cloud_base_url: &str, tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-ctx-cloud-{}-{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-pre".into(),
        cloud_base_url: cloud_base_url.into(),
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

async fn context_for(cloud_base_url: &str, tag: &str) -> Value {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-pre");
    rt.ensure_system_tables().await.unwrap();
    let router = app(AppState::with_config(rt, config(cloud_base_url, tag)));
    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

#[tokio::test]
async fn the_boot_context_publishes_the_cloud_this_hub_belongs_to() {
    let body = context_for("https://pre.erplora.com", "pre").await;
    assert_eq!(
        body["cloud_base_url"],
        json!("https://pre.erplora.com"),
        "the shell must learn its Cloud from the runtime, not from the build: {body}"
    );
}

#[tokio::test]
async fn the_published_cloud_is_the_one_the_csp_already_allows() {
    let cloud = "https://pre.erplora.com";
    let body = context_for(cloud, "csp").await;
    let csp = default_csp(body["cloud_base_url"].as_str().unwrap_or_default());
    assert!(
        csp.contains("connect-src 'self' ipc: http://ipc.localhost https://pre.erplora.com"),
        "a login sent to `cloud_base_url` must pass the CSP the same value feeds: {csp}"
    );
}

#[tokio::test]
async fn a_hub_without_a_cloud_publishes_an_empty_value_so_the_shell_falls_back() {
    let body = context_for("", "empty").await;
    assert_eq!(
        body["cloud_base_url"],
        json!(""),
        "no Cloud configured (dev binary) → empty string, never a fabricated prod URL: {body}"
    );
}
