//! `GET /api/navigation` must say how many modules this hub HAS (hub#894).
//!
//! The endpoint answers the menu, and the menu is «installed **and** active, and only the entries
//! the manifest declares». That is the right list — but on its own it cannot tell the shell apart
//! the two situations that produce the same empty array:
//!
//! 1. a brand-new hub, where nothing is installed yet, and
//! 2. a hub with twelve modules registered whose menu came out empty anyway.
//!
//! The first is a fact worth painting («add your first app»). The second is a CONTRADICTION, and it
//! was painted as the first one: a real production hub (`peluqueria-mac-qa`, 12/12 registered per
//! `/readyz`) told its owner «you have no apps yet» and offered to install the ones it already had.
//! The shell had nothing to check the empty list against, so it believed it.
//!
//! `installed` is the count the shell checks against. It is **additive**: `ok` and `data` keep the
//! exact shape they had, so an older shell reading this answer sees no change.
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_inventory")
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn navigation(app: axum::Router) -> Value {
    let resp = app
        .oneshot(
            Request::builder()
                .uri("/api/navigation")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    body_json(resp).await
}

/// A hub with a module installed reports it, next to the menu it produced.
#[tokio::test]
async fn navigation_reports_the_number_of_installed_modules() {
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&fixture()).await.unwrap();
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let j = navigation(app).await;

    assert_eq!(j["ok"], json!(true));
    assert!(
        j["data"].as_array().is_some_and(|d| !d.is_empty()),
        "the menu itself is unchanged: {j}"
    );
    assert_eq!(
        j["installed"],
        json!(1),
        "the answer must carry how many modules this hub has: {j}"
    );
}

/// The one that matters: an EMPTY menu on a hub that HAS a module. Without the count this answer is
/// byte-for-byte the answer of a hub where nothing was ever installed, and the shell painted it as
/// such. Deactivating is the cheapest way to reach the shape — what is being pinned is that the two
/// numbers are reported independently, so a shell can notice they disagree.
#[tokio::test]
async fn an_empty_menu_still_reports_the_modules_the_hub_has() {
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&fixture()).await.unwrap();
    rt.deactivate("inventory").await.unwrap();
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let j = navigation(app).await;

    assert_eq!(
        j["data"],
        json!([]),
        "an inactive module publishes no menu — that part is correct: {j}"
    );
    assert_eq!(
        j["installed"],
        json!(1),
        "…but «no menu» must never read as «this hub has nothing»: {j}"
    );
}

/// And a genuinely new hub says zero, so «add your first app» stays true where it IS true.
#[tokio::test]
async fn a_hub_with_nothing_installed_reports_zero() {
    let rt = Runtime::new(Box::new(fresh_db().await));
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let j = navigation(app).await;

    assert_eq!(j["data"], json!([]));
    assert_eq!(j["installed"], json!(0), "{j}");
}
