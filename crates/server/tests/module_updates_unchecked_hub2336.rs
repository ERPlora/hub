//! `GET /api/modules/updates` tells «nothing new» apart from «could not ask» (hub#2336).
//!
//! When the marketplace did not answer, every row came back `update_available: false` inside an
//! `ok: true` envelope — word for word what «everything is up to date» says. Apps → «My apps» and
//! the bell painted a hub nobody could vouch for as up to date. Each row now carries `checked`:
//! `true` only when the marketplace's answer about that app was actually read.

use std::sync::Arc;

use axum::body::Body;
use axum::extract::{Path as AxumPath, State};
use axum::http::{Request, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig, DEV_HUB_ID};
use serde_json::{json, Value};
use tower::ServiceExt;

/// How the fake marketplace answers `versions/`.
#[derive(Clone, Copy)]
enum Answer {
    /// `[{version: 2.0.0, is_active: true}]` — a newer version.
    Newer,
    /// `[{version: 1.0.0, is_active: true}]` — the installed one is the newest.
    Same,
    /// 404: the marketplace does not publish this app (a private or local one).
    NotPublished,
    /// 503 with an HTML page, as a proxy in front of a marketplace that is down answers.
    Down,
    /// 200 with something that is not the list.
    Garbage,
    /// 500 whose body happens to parse as a list: an error status is never the answer.
    ErrorWithList,
}

async fn spawn_mock_cloud(answer: Answer) -> String {
    async fn versions(State(a): State<Arc<Answer>>, AxumPath(_id): AxumPath<String>) -> Response {
        match *a {
            Answer::Newer => {
                Json(json!([{ "version": "2.0.0", "is_active": true }])).into_response()
            }
            Answer::Same => {
                Json(json!([{ "version": "1.0.0", "is_active": true }])).into_response()
            }
            Answer::NotPublished => (
                StatusCode::NOT_FOUND,
                Json(json!({ "detail": "Not found." })),
            )
                .into_response(),
            Answer::Down => (StatusCode::SERVICE_UNAVAILABLE, "<html>503</html>").into_response(),
            Answer::Garbage => (StatusCode::OK, "<html>maintenance</html>").into_response(),
            Answer::ErrorWithList => {
                (StatusCode::INTERNAL_SERVER_ERROR, Json(json!([]))).into_response()
            }
        }
    }
    let router = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .with_state(Arc::new(answer));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    format!("http://{addr}")
}

/// An address nobody listens on: the marketplace (or the hub's network) is down.
async fn unreachable_cloud() -> String {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{addr}")
}

const PARTS_INIT: &str =
    "CREATE TABLE IF NOT EXISTS parts_item (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);";

/// The `parts` row of `GET /api/modules/updates` on a hub with `parts@1.0.0` installed. Without a
/// machine `token` the hub is the local development one: a production hub without its credential
/// is stopped earlier by the enrolment barrier (428) and never reaches the route.
async fn parts_row(
    cloud_base_url: String,
    tag: &str,
    token: Option<&str>,
    pin: Option<&str>,
) -> Value {
    let hub_id = if token.is_some() {
        "hub-upd-unchecked"
    } else {
        DEV_HUB_ID
    };
    let temp = std::env::temp_dir().join(format!(
        "erplora-upd-unchecked-{}-{tag}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&temp);

    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let session = rt.create_session(&admin_id, 3600, None).await.unwrap();

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
    if let Some(pin) = pin {
        let mut p = erplora_db::Params::new();
        p.insert("pin".into(), json!(pin));
        p.insert("hub_id".into(), json!(hub_id));
        rt.db()
            .execute(
                "UPDATE hub_module SET pinned_version = :pin WHERE hub_id = :hub_id AND module_id = 'parts'",
                &p,
            )
            .await
            .expect("pin parts");
    }

    let cfg = HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: if token.is_some() {
            AuthMode::Session
        } else {
            AuthMode::Dev
        },
        jwt_public_key: None,
        cloud_api_token: token.map(str::to_string),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let router = app(AppState::with_config(rt, cfg));
    let response = router
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/modules/updates")
                .header("x-hub-session", &session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let body: Value = serde_json::from_slice(&bytes).unwrap();
    let _ = std::fs::remove_dir_all(temp);
    assert_eq!(body["ok"], json!(true), "{body}");
    body["data"]
        .as_array()
        .and_then(|rows| {
            rows.iter()
                .find(|r| r["module_id"] == json!("parts"))
                .cloned()
        })
        .unwrap_or_else(|| panic!("no row for parts: {body}"))
}

async fn answered(answer: Answer, tag: &str) -> Value {
    parts_row(
        spawn_mock_cloud(answer).await,
        tag,
        Some("machine-secret"),
        None,
    )
    .await
}

// ── «Could not ask» ─────────────────────────────────────────────────────────────────────────

/// THE symptom: the marketplace does not answer at all.
#[tokio::test]
async fn a_marketplace_that_does_not_answer_is_not_up_to_date() {
    let row = parts_row(
        unreachable_cloud().await,
        "refused",
        Some("machine-secret"),
        None,
    )
    .await;
    assert_eq!(row["checked"], json!(false), "{row}");
    assert_eq!(
        row["update_available"],
        json!(false),
        "«I don't know» is never an update: {row}"
    );
    assert_eq!(row["latest"], json!("1.0.0"), "{row}");
}

#[tokio::test]
async fn a_marketplace_answering_an_error_page_is_not_up_to_date() {
    let row = answered(Answer::Down, "down").await;
    assert_eq!(row["checked"], json!(false), "{row}");
    assert_eq!(row["update_available"], json!(false), "{row}");
}

#[tokio::test]
async fn an_answer_that_is_not_the_list_is_not_up_to_date() {
    let row = answered(Answer::Garbage, "garbage").await;
    assert_eq!(row["checked"], json!(false), "{row}");
}

#[tokio::test]
async fn an_error_status_is_not_an_answer_whatever_its_body() {
    let row = answered(Answer::ErrorWithList, "error-list").await;
    assert_eq!(row["checked"], json!(false), "{row}");
}

/// Without a marketplace credential (a local development hub with no signed-in account) nothing
/// can be asked: one row per app saying so, not an empty list the screen reads as «nothing new».
#[tokio::test]
async fn without_a_marketplace_credential_every_app_is_unchecked() {
    let row = parts_row(spawn_mock_cloud(Answer::Newer).await, "no-cred", None, None).await;
    assert_eq!(row["checked"], json!(false), "{row}");
    assert_eq!(row["update_available"], json!(false), "{row}");
    assert_eq!(row["installed"], json!("1.0.0"), "{row}");
    assert_eq!(row["latest"], json!("1.0.0"), "{row}");
}

// ── «Asked, and this is the answer» ─────────────────────────────────────────────────────────

#[tokio::test]
async fn an_answered_newer_version_is_checked() {
    let row = answered(Answer::Newer, "newer").await;
    assert_eq!(row["checked"], json!(true), "{row}");
    assert_eq!(row["update_available"], json!(true), "{row}");
}

#[tokio::test]
async fn an_answered_same_version_is_checked_and_up_to_date() {
    let row = answered(Answer::Same, "same").await;
    assert_eq!(row["checked"], json!(true), "{row}");
    assert_eq!(row["update_available"], json!(false), "{row}");
}

/// A 404 IS an answer: the marketplace does not publish this app, so there is nothing to offer —
/// otherwise a private app would keep the screen saying «could not check» forever.
#[tokio::test]
async fn an_app_the_marketplace_does_not_publish_is_checked() {
    let row = answered(Answer::NotPublished, "unpublished").await;
    assert_eq!(row["checked"], json!(true), "{row}");
    assert_eq!(row["update_available"], json!(false), "{row}");
}

/// A pinned app never moves, whatever the marketplace says — that is a known answer, even with
/// the marketplace down (it is not even asked).
#[tokio::test]
async fn a_pinned_app_is_checked_even_with_the_marketplace_down() {
    let row = parts_row(
        unreachable_cloud().await,
        "pinned",
        Some("machine-secret"),
        Some("1.0.0"),
    )
    .await;
    assert_eq!(row["checked"], json!(true), "{row}");
    assert_eq!(row["update_available"], json!(false), "{row}");
}

/// A pinned app is a known answer even where nothing can be asked.
#[tokio::test]
async fn a_pinned_app_is_checked_without_a_marketplace_credential() {
    let row = parts_row(
        spawn_mock_cloud(Answer::Newer).await,
        "no-cred-pinned",
        None,
        Some("1.0.0"),
    )
    .await;
    assert_eq!(row["checked"], json!(true), "{row}");
    assert_eq!(row["update_available"], json!(false), "{row}");
}
