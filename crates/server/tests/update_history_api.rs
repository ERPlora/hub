//! `GET /api/system/update-history` — what we changed on this hub (hub#564, ADR-0269 §3.5).
//!
//! We update on our own, without asking. The counterpart is that the owner can find out **what** we
//! changed, and this is the door they read it through.
//!
//! What the tests here pin is the part that carries the value, which is not "a list came back":
//!
//!  - **A hub nobody has updated shows NOTHING.** Not 24 rows saying "no change" — the definition
//!    of done says so, and a screen that is noise on day one is a screen nobody opens on day sixty.
//!  - **Each entry says where it came from.** "Inventory 1.1.2" is not information; "1.1.1 → 1.1.2"
//!    is.
//!  - **Reading it takes a session.** Which versions a hub runs is a map of its attack surface;
//!    handing that to an unauthenticated caller is telling anyone which known bug applies.
//!  - **Only THIS hub's history.** The neighbour is alive in that test on purpose.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_runtime::update_history::{self, Change, Component, Outcome};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt;

const HUB_ID: &str = "hub-update-history";

/// Router + an employee session + a handle on the same schema to seed transitions with.
///
/// The seeding goes through the runtime rather than an HTTP door because there is no HTTP door that
/// writes history — and there must not be one. A history you can POST into is not a record of what
/// we did, it is a record of what somebody said we did.
async fn fixture() -> (axum::Router, String, erplora_db::PgAdapter) {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let db = test_db.adapter().await;
    let probe = test_db.adapter().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let user = rt
        .create_user("Cashier", "2222", "employee", None)
        .await
        .unwrap();
    let session = rt.create_session(&user, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-update-history-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
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
    (app(AppState::with_config(rt, cfg)), session, probe)
}

async fn get(router: &axum::Router, uri: &str, session: Option<&str>) -> (StatusCode, Value) {
    let mut builder = Request::builder().method("GET").uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    let response = router
        .clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, body)
}

fn module_update<'a>(id: &'a str, name: &'a str, from: &'a str, to: &'a str) -> Change<'a> {
    Change {
        component: Component::Module,
        id,
        name,
        from,
        to,
        outcome: Outcome::Updated,
        reason: "",
    }
}

/// Which versions this hub runs is not public information.
#[tokio::test]
async fn reading_the_history_takes_a_session() {
    let (router, _session, _db) = fixture().await;

    let (status, _) = get(&router, "/api/system/update-history", None).await;

    assert_eq!(status, StatusCode::UNAUTHORIZED);
}

/// A hub nobody has updated shows an EMPTY history — the definition of done of hub#564.
#[tokio::test]
async fn an_untouched_hub_shows_an_empty_history() {
    let (router, session, db) = fixture().await;
    // The boot noted the core version it found. That is bookkeeping so the NEXT jump has a `from`,
    // and it must not reach the screen: nothing has happened to this owner yet.
    update_history::note_core_version(&db, HUB_ID, "1.0.2")
        .await
        .unwrap();

    let (status, body) = get(&router, "/api/system/update-history", Some(&session)).await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["ok"], true);
    assert_eq!(
        body["data"].as_array().unwrap().len(),
        0,
        "an untouched hub must show nothing, not a baseline row"
    );
}

/// Every entry says WHAT changed and FROM which version, newest first.
#[tokio::test]
async fn the_history_says_what_changed_and_from_which_version() {
    let (router, session, db) = fixture().await;
    update_history::note_core_version(&db, HUB_ID, "1.0.1")
        .await
        .unwrap();
    update_history::note_core_version(&db, HUB_ID, "1.0.2")
        .await
        .unwrap();
    update_history::record(
        &db,
        HUB_ID,
        module_update("inventory", "Inventory", "1.1.1", "1.1.2"),
    )
    .await
    .unwrap();

    let (status, body) = get(&router, "/api/system/update-history", Some(&session)).await;

    assert_eq!(status, StatusCode::OK);
    let rows = body["data"].as_array().unwrap();
    assert_eq!(rows.len(), 2, "only what moved: two things moved");

    assert_eq!(rows[0]["component"], "module", "newest first");
    assert_eq!(rows[0]["id"], "inventory");
    assert_eq!(rows[0]["name"], "Inventory");
    assert_eq!(rows[0]["from"], "1.1.1");
    assert_eq!(rows[0]["to"], "1.1.2");
    assert_eq!(rows[0]["outcome"], "updated");
    assert!(
        rows[0]["at"].as_str().is_some_and(|s| !s.is_empty()),
        "an entry without a moment is not a history"
    );

    assert_eq!(rows[1]["component"], "hub");
    assert_eq!(
        rows[1]["name"], "ERPlora",
        "the owner reads a product name, not «the image» (ADR-0254)"
    );
    assert_eq!(rows[1]["from"], "1.0.1");
    assert_eq!(rows[1]["to"], "1.0.2");
}

/// A rollback is an entry, and it is told as a rollback.
#[tokio::test]
async fn a_rollback_is_an_entry_of_its_own() {
    let (router, session, db) = fixture().await;
    update_history::record(
        &db,
        HUB_ID,
        Change {
            outcome: Outcome::RolledBack,
            reason: "migration 004 failed",
            ..module_update("inventory", "Inventory", "1.1.2", "1.1.1")
        },
    )
    .await
    .unwrap();

    let (_, body) = get(&router, "/api/system/update-history", Some(&session)).await;

    let rows = body["data"].as_array().unwrap();
    assert_eq!(rows[0]["outcome"], "rolled_back");
    assert_eq!(rows[0]["from"], "1.1.2");
    assert_eq!(rows[0]["to"], "1.1.1");
}

/// One hub never reads another hub's history — with the neighbour ALIVE, so an empty result cannot
/// be what makes this pass.
#[tokio::test]
async fn a_hub_only_reads_its_own_history() {
    let (router, session, db) = fixture().await;
    update_history::record(
        &db,
        HUB_ID,
        module_update("inventory", "Inventory", "1.0.0", "1.1.0"),
    )
    .await
    .unwrap();
    update_history::record(
        &db,
        "somebody-elses-hub",
        module_update("sales", "Sales", "2.0.0", "2.1.0"),
    )
    .await
    .unwrap();

    let (_, body) = get(&router, "/api/system/update-history", Some(&session)).await;

    let rows = body["data"].as_array().unwrap();
    assert_eq!(
        rows.len(),
        1,
        "the neighbour is alive, and I still see mine"
    );
    assert_eq!(rows[0]["id"], "inventory");
}
