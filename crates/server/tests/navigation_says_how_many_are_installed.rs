//! `GET /api/navigation` must say how many modules are expected to contribute a menu (hub#894).
//!
//! The endpoint answers the menu, and the menu is «installed **and** active, and only the entries
//! the manifest declares». That is the right list — but on its own it cannot tell apart the two
//! situations that produce the same empty array:
//!
//! 1. a brand-new hub, where nothing is installed yet, and
//! 2. a hub with twelve modules registered whose menu came out empty anyway.
//!
//! The first is a fact worth painting («add your first app»). The second is not, and it was painted
//! as if it were: a real production hub (`peluqueria-mac-qa`, 12/12 registered per `/readyz`) told
//! its owner «you have no apps yet» and offered to install the ones it already had. The shell had
//! nothing to check the empty list against, so it believed it.
//!
//! `active_modules` is that something. Two decisions in it, both load-bearing:
//!
//! - It counts the **active** ones, not the installed ones. A module the admin switched off is not
//!   expected to contribute a menu, so counting it would turn a deliberately-quiet hub into a false
//!   «I could not load your apps». The denominator is what the hub expects to contribute.
//! - It is **additive**: `ok` and `data` keep the exact shape they had, so an older shell reading
//!   this answer sees no change.
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

/// A hub with an active module reports it, next to the menu it produced.
#[tokio::test]
async fn navigation_reports_how_many_modules_are_active() {
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
        j["active_modules"],
        json!(1),
        "the answer must carry how many modules are expected to contribute a menu: {j}"
    );
}

/// A genuinely new hub says zero, so «add your first app» stays true where it IS true.
#[tokio::test]
async fn a_hub_with_nothing_installed_reports_zero() {
    let rt = Runtime::new(Box::new(fresh_db().await));
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let j = navigation(app).await;

    assert_eq!(j["data"], json!([]));
    assert_eq!(j["active_modules"], json!(0), "{j}");
}

/// And a hub whose modules the admin switched off ALSO says zero — the correction to the first cut
/// of this fix, which counted `installed` and would have shouted «I could not load your apps» at a
/// hub that is empty on purpose. Both numbers being zero is what keeps the shell quiet here: an
/// empty menu with nothing expected to fill it is a fact, not a failure.
#[tokio::test]
async fn a_hub_whose_modules_are_all_switched_off_reports_zero_not_a_failure() {
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
        j["active_modules"],
        json!(0),
        "…and nothing was expected to publish one, so this is not a contradiction: {j}"
    );
}
