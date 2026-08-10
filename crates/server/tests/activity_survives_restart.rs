//! E2E — the user-activity mark SURVIVES a restart (hub#670).
//!
//! `ActivityState` used to live only in memory. A visit that happened between the mark and the
//! next heartbeat died with the process — and with blue/green (ADR-0269) a restart is no longer
//! rare: **every update kills a task**. Losing that mark is not cosmetic. The Cloud's inactivity
//! clock (ADR-0175) powers a free hub off at 60 days, flags it at 90 and **deletes it at 120**,
//! and the only thing that resets it is this mark. A visit that really happened must not vanish.
//!
//! The route under test is the production one end to end: PIN login → authenticated request →
//! the router's activity middleware → the flush → **a brand new process over the same database**.
use std::path::{Path, PathBuf};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::TestDb;
use erplora_db::PgAdapter;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn temp_dir() -> PathBuf {
    std::env::temp_dir().join(format!("erplora-activity-670-{}", std::process::id()))
}

fn config(hub_id: &str, temp: &Path) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.to_path_buf(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// Boots a hub process over `db`: system tables, a PIN user the first time, and the restore of
/// whatever the previous process left persisted (what `serve()` does at startup).
async fn boot(db: PgAdapter, hub_id: &str, create_user: bool) -> (axum::Router, AppState) {
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    if create_user {
        rt.create_user("Admin", "1111", "admin", None)
            .await
            .unwrap();
    }
    let state = AppState::with_config(rt, config(hub_id, &temp_dir()));
    erplora_server::activity::restore_from_db(&state).await;
    (app(state.clone()), state)
}

fn pin_login() -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/pin")
        .header("content-type", "application/json")
        .body(Body::from(
            json!({ "name": "Admin", "pin": "1111", "device_id": "dev-670" }).to_string(),
        ))
        .unwrap()
}

async fn session_token(resp: axum::response::Response) -> String {
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "the PIN login must return 200"
    );
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    v["token"]
        .as_str()
        .expect("token in the response")
        .to_string()
}

/// Somebody logs in and uses the hub. Returns nothing: what matters is the side effect on the
/// activity mark, which is exactly what must outlive the process.
async fn a_real_visit(router: &axum::Router) {
    let token = session_token(router.clone().oneshot(pin_login()).await.unwrap()).await;
    let resp = router
        .clone()
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/system")
                .header("x-hub-session", &token)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "an authenticated request is a visit"
    );
}

/// 🔴 The bug: the hub is updated (or crashes) before the next heartbeat, and the visit is gone.
#[tokio::test]
async fn a_visit_before_the_restart_still_reaches_the_cloud() {
    let db = TestDb::new().await;
    let (router, state) = boot(db.adapter().await, "hub-670", true).await;

    a_real_visit(&router).await;
    let seen = state
        .activity
        .last_activity()
        .expect("the middleware marks an authenticated request");
    // The write-behind flush: what the background task does every tick.
    erplora_server::activity::flush(&state).await;

    // ── the process dies here (SIGTERM from the blue/green rollout) ────────────────────────────
    drop(router);
    drop(state);

    // ── and a brand new one starts over the SAME database ─────────────────────────────────────
    let (_router, restarted) = boot(db.adapter().await, "hub-670", false).await;
    assert_eq!(
        restarted.activity.pending(),
        Some(seen),
        "the visit happened: the next heartbeat must still report it, or the Cloud counts days \
         towards deleting a hub somebody is actually using (ADR-0175)"
    );
}

/// A mark already confirmed by the Cloud is not re-sent after a restart either: `last_reported`
/// travels with the visit, so a hub that restarts twice a day does not spam the control plane
/// with a timestamp it already stored.
#[tokio::test]
async fn a_mark_already_confirmed_is_not_reported_again_after_the_restart() {
    let db = TestDb::new().await;
    let (router, state) = boot(db.adapter().await, "hub-670b", true).await;

    a_real_visit(&router).await;
    let seen = state.activity.pending().expect("pending after the visit");
    state.activity.mark_reported(seen); // the heartbeat got its 2xx
    erplora_server::activity::flush(&state).await;

    let (_router, restarted) = boot(db.adapter().await, "hub-670b", false).await;
    assert_eq!(
        restarted.activity.pending(),
        None,
        "already reported: a restart must not turn it into news again"
    );
    assert_eq!(
        restarted.activity.last_activity(),
        Some(seen),
        "but the hub still knows when it was last used"
    );
}

/// 🔒 Isolation with a **live neighbour**: hub B is really used (its own router, its own PIN
/// login, its own flush). Hub A is never touched. If the restore ignored `hub_id`, A would come
/// back believing somebody entered — and a free hub nobody uses would never be reclaimed.
#[tokio::test]
async fn a_restarted_hub_does_not_inherit_the_neighbours_visit() {
    let db = TestDb::new().await;

    // The neighbour exists for real and is used for real.
    let (neighbour_router, neighbour) = boot(db.adapter().await, "hub-neighbour", true).await;
    a_real_visit(&neighbour_router).await;
    erplora_server::activity::flush(&neighbour).await;
    assert!(
        neighbour.activity.last_activity().is_some(),
        "the neighbour must really have a visit, or this test proves nothing"
    );

    // The hub under test shares the database and has never seen anybody.
    let (_quiet_router, quiet) = boot(db.adapter().await, "hub-quiet", false).await;
    assert_eq!(
        quiet.activity.pending(),
        None,
        "nobody entered THIS hub: reporting the neighbour's visit would keep an unused free hub \
         alive forever"
    );
    assert_eq!(quiet.activity.last_activity(), None);
}
