//! `GET /api/modules/updates` says which ERPlora the offered version needs (hub#2082).
//!
//! The Apps page offered «Update to X» for an installed app whose X needs a newer ERPlora than
//! the hub runs, and the owner only learnt it when the runtime refused the update (hub#521). The
//! floor of each version comes from the marketplace's `versions/` (`min_erplora_version`, saas);
//! this door passes along the floor of the version it OFFERS — not of the newest published one,
//! which the resolver may skip (quarantine) — so the screen can say it before the press.

use std::collections::HashMap;
use std::sync::Arc;

use axum::body::Body;
use axum::extract::{Path as AxumPath, State};
use axum::http::{Request, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

/// module id → what `versions/` offers: `(version, is_active, min_erplora_version)`.
struct MockCloud {
    offered: HashMap<String, Vec<(String, bool, Option<String>)>>,
}

type Shared = Arc<MockCloud>;

async fn spawn_mock_cloud(mock: Shared) -> String {
    async fn versions(State(m): State<Shared>, AxumPath(id): AxumPath<String>) -> Json<Value> {
        let list: Vec<Value> = m
            .offered
            .get(&id)
            .map(|versions| {
                versions
                    .iter()
                    .map(|(v, active, floor)| {
                        json!({ "version": v, "is_active": active, "min_erplora_version": floor })
                    })
                    .collect()
            })
            .unwrap_or_default();
        Json(json!(list))
    }
    let router = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .with_state(mock);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    format!("http://{addr}")
}

// ── Hub under test ───────────────────────────────────────────────────────────────────────

const PARTS_INIT: &str =
    "CREATE TABLE IF NOT EXISTS parts_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);";

/// A hub with `parts@1.0.0` installed, its router, an admin session and an employee one.
async fn fixture(tag: &str, mock: Shared) -> (axum::Router, String, String, std::path::PathBuf) {
    let cloud_base_url = spawn_mock_cloud(mock).await;
    let temp = std::env::temp_dir().join(format!("erplora-upd-floor-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&temp);

    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-upd-floor");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let session = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let cashier_id = rt
        .create_user("Cashier", "2222", "employee", None)
        .await
        .unwrap();
    let employee = rt.create_session(&cashier_id, 3600, None).await.unwrap();

    let v1_dir = temp.join("seed").join("1.0.0");
    std::fs::create_dir_all(v1_dir.join("migrations/postgres")).unwrap();
    std::fs::write(
        v1_dir.join("module.json"),
        serde_json::to_string(&json!({
            "id": "parts", "name": "Parts", "version": "1.0.0",
            "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
        }))
        .unwrap(),
    )
    .unwrap();
    std::fs::write(v1_dir.join("migrations/postgres/001_init.sql"), PARTS_INIT).unwrap();
    let mut rt = rt;
    rt.install_from_dir(&v1_dir)
        .await
        .expect("seed parts@1.0.0");

    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-upd-floor".into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    (app(AppState::with_config(rt, cfg)), session, employee, temp)
}

fn updates_request(session: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri("/api/modules/updates")
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

async fn parts_row(mock: Shared, tag: &str) -> Value {
    let (router, session, _employee, temp) = fixture(tag, mock).await;
    let response = router.oneshot(updates_request(&session)).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let body: Value = serde_json::from_slice(&bytes).unwrap();
    let _ = std::fs::remove_dir_all(temp);
    body["data"]
        .as_array()
        .and_then(|rows| {
            rows.iter()
                .find(|r| r["module_id"] == json!("parts"))
                .cloned()
        })
        .unwrap_or_else(|| panic!("no row for parts: {body}"))
}

fn offered(versions: &[(&str, bool, Option<&str>)]) -> Shared {
    Arc::new(MockCloud {
        offered: HashMap::from([(
            "parts".to_string(),
            versions
                .iter()
                .map(|(v, a, f)| (v.to_string(), *a, f.map(str::to_string)))
                .collect(),
        )]),
    })
}

#[tokio::test]
async fn the_offered_update_carries_the_floor_of_that_version() {
    let row = parts_row(
        offered(&[("2.0.0", true, Some("9.9.9")), ("1.0.0", true, None)]),
        "floor",
    )
    .await;
    assert_eq!(row["latest"], json!("2.0.0"), "{row}");
    assert_eq!(row["update_available"], json!(true), "{row}");
    assert_eq!(row["latest_min_erplora_version"], json!("9.9.9"), "{row}");
}

/// The floor belongs to the version offered, never to a newer one the resolver skipped.
#[tokio::test]
async fn a_skipped_quarantined_version_does_not_lend_its_floor() {
    let row = parts_row(
        // Newest first, as the marketplace serves `versions/` (`order_by("-created_at")`).
        offered(&[
            ("3.0.0", false, Some("9.9.9")),
            ("2.0.0", true, Some("1.2.0")),
        ]),
        "quarantine",
    )
    .await;
    assert_eq!(row["latest"], json!("2.0.0"), "{row}");
    assert_eq!(row["latest_min_erplora_version"], json!("1.2.0"), "{row}");
}

/// A version that declares no floor — or a marketplace older than the field — answers `null`,
/// which the screen reads as «nothing to warn about» (the runtime still refuses at update time).
#[tokio::test]
async fn a_version_without_a_floor_answers_null() {
    let row = parts_row(offered(&[("2.0.0", true, None)]), "none").await;
    assert_eq!(row["update_available"], json!(true), "{row}");
    assert_eq!(row["latest_min_erplora_version"], Value::Null, "{row}");
}

/// No update, no floor: there is nothing on offer for it to describe.
#[tokio::test]
async fn without_an_update_there_is_no_floor() {
    let row = parts_row(offered(&[("1.0.0", true, Some("9.9.9"))]), "same").await;
    assert_eq!(row["update_available"], json!(false), "{row}");
    assert_eq!(row["latest_min_erplora_version"], Value::Null, "{row}");
}
