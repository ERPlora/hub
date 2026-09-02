//! `GET /api/modules/:id/versions` — the list behind the version dropdown (hub#675).
//!
//! The update route already lets a module fix land without a new hub image. What it did not let
//! anyone do is **choose**: the body takes a `version`, but nothing ever told the screen which
//! versions exist, so the only reachable option was «whatever the resolver picks».
//!
//! The ordering rules live in `erplora_runtime::module_update::offer` and are unit-tested there.
//! What only shows up once the whole door is wired —and is what this file exists for— is that the
//! door **uses those rules**: a quarantined version must not reach the dropdown, and the dropdown
//! must not be a way of going backwards. A second door with a second policy is a second policy.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

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

// ── Mock marketplace ─────────────────────────────────────────────────────────────────────

/// module id → what `versions/` offers, as `(version, is_active)`. `is_active = false` is the
/// quarantine (`ModuleVersion.is_active` in the Cloud: «marked as broken»).
struct MockCloud {
    offered: HashMap<String, Vec<(String, bool)>>,
    calls: Mutex<Vec<String>>,
}

type Shared = Arc<MockCloud>;

async fn spawn_mock_cloud(mock: Shared) -> String {
    async fn versions(State(m): State<Shared>, AxumPath(id): AxumPath<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("versions:{id}"));
        let list: Vec<Value> = m
            .offered
            .get(&id)
            .map(|versions| {
                versions
                    .iter()
                    .map(|(v, active)| json!({ "version": v, "is_active": active }))
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
    let temp = std::env::temp_dir().join(format!("erplora-vers-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&temp);

    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-vers");
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
        hub_id: "hub-vers".into(),
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

fn versions_request(module_id: &str, session: Option<&str>) -> Request<Body> {
    let builder = Request::builder()
        .method("GET")
        .uri(format!("/api/modules/{module_id}/versions"));
    let builder = match session {
        Some(s) => builder.header("x-hub-session", s),
        None => builder,
    };
    builder.body(Body::empty()).unwrap()
}

async fn json_body(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

fn offered(module: &str, versions: &[(&str, bool)]) -> Shared {
    Arc::new(MockCloud {
        offered: HashMap::from([(
            module.to_string(),
            versions
                .iter()
                .map(|(v, a)| (v.to_string(), *a))
                .collect::<Vec<_>>(),
        )]),
        calls: Mutex::new(Vec::new()),
    })
}

// ── 1. What the dropdown gets ────────────────────────────────────────────────────────────

/// Newest first, and the one already installed is reported apart: the screen needs both to say
/// «1.0.0 → 2.1.0» and to preselect the latest without inventing it.
#[tokio::test]
async fn the_dropdown_gets_the_versions_the_marketplace_offers_newest_first() {
    let mock = offered(
        "parts",
        &[("1.0.0", true), ("2.0.0", true), ("2.1.0", true)],
    );
    let (router, session, _employee, temp) = fixture("newest", mock).await;

    let response = router
        .oneshot(versions_request("parts", Some(&session)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = json_body(response).await;

    assert_eq!(body["ok"], json!(true), "{body}");
    assert_eq!(body["data"]["installed"], json!("1.0.0"), "{body}");
    assert_eq!(body["data"]["latest"], json!("2.1.0"), "{body}");
    assert_eq!(
        body["data"]["versions"],
        json!(["2.1.0", "2.0.0"]),
        "newest first, and NEVER the installed one or an older one — going back is not an \
         operation that exists (ADR-0269 §3.4): {body}"
    );

    let _ = std::fs::remove_dir_all(temp);
}

// ── 2. The quarantine holds on this door too ─────────────────────────────────────────────

/// A version marked broken must not become reachable just because there is now a menu. The
/// quarantine exists precisely to keep it off hubs; a dropdown that lists it is a second door.
#[tokio::test]
async fn a_quarantined_version_never_reaches_the_dropdown() {
    let mock = offered("parts", &[("2.0.0", true), ("3.0.0", false)]);
    let (router, session, _employee, temp) = fixture("quarantine", mock).await;

    let body = json_body(
        router
            .oneshot(versions_request("parts", Some(&session)))
            .await
            .unwrap(),
    )
    .await;

    assert_eq!(body["data"]["versions"], json!(["2.0.0"]), "{body}");
    assert_eq!(
        body["data"]["latest"],
        json!("2.0.0"),
        "the latest OFFERED is not the latest published when the newest is in quarantine: {body}"
    );

    let _ = std::fs::remove_dir_all(temp);
}

// ── 3. Choosing a version at INSTALL time ────────────────────────────────────────────────

/// The same door serves the catalogue: a module this hub does not have yet has no installed
/// version to move forward from, so every published version is a legitimate choice. It must not
/// 404 — that is the update route's rule, not this one's.
#[tokio::test]
async fn a_module_this_hub_does_not_have_yet_offers_every_published_version() {
    let mock = offered("extras", &[("1.0.0", true), ("1.2.0", true)]);
    let (router, session, _employee, temp) = fixture("fresh", mock).await;

    let response = router
        .oneshot(versions_request("extras", Some(&session)))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = json_body(response).await;

    assert_eq!(body["data"]["installed"], json!(null), "{body}");
    assert_eq!(
        body["data"]["versions"],
        json!(["1.2.0", "1.0.0"]),
        "{body}"
    );

    let _ = std::fs::remove_dir_all(temp);
}

// ── 4. The door is the admin's ───────────────────────────────────────────────────────────

/// Same gate as install and update, and **a cashier is not an admin**: a session is not the same
/// thing as permission. Reading the list is the first step of moving the version this hub runs, so
/// the door has to be the same one — and neither caller may reach the Cloud, because the request
/// travels on the hub's machine token and would be spending it on someone else's behalf.
#[tokio::test]
async fn without_an_admin_session_there_is_no_list() {
    let mock = offered("parts", &[("2.0.0", true)]);
    let (router, _session, employee, temp) = fixture("noauth", mock.clone()).await;

    for (who, session) in [("anonymous", None), ("cashier", Some(employee.as_str()))] {
        let response = router
            .clone()
            .oneshot(versions_request("parts", session))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "{who}");
    }
    assert!(
        mock.calls.lock().unwrap().is_empty(),
        "and the Cloud is never asked on behalf of someone who is not an admin: {:?}",
        mock.calls.lock().unwrap()
    );

    let _ = std::fs::remove_dir_all(temp);
}
