//! HTTP contract of the role catalogue's activation (paso 2b, hub#352): `PUT /api/hub/roles/{key}`.
//!
//! Reading the catalogue is any user session — role names are already public in the PIN grid of
//! the login. **Switching a role on is administration of the hub**: it decides which figures exist
//! in this business, so it takes an admin session, the same gate as settings, files, API keys and
//! the module lifecycle.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

/// A module that declares its own business roles (hub#351).
const KITCHEN: &str = r#"{
  "id":"kitchen",
  "name":"Kitchen",
  "version":"2.3.1",
  "roles":[{"key":"kitchen","label":"Kitchen","extends":"employee"}],
  "role_permissions":{"kitchen":["kitchen.view_ticket"]}
}"#;

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// Router + admin session + employee session.
async fn fixture() -> (axum::Router, String, String, std::path::PathBuf) {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-roles");
    rt.ensure_system_tables().await.unwrap();

    let dir = std::env::temp_dir().join(format!(
        "erplora-role-activation-api-{}-{:?}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    // Atomic write (hub#490): under load, a plain `write` followed by `install_from_dir` could
    // observe a zero-byte file — the OS hadn't flushed the page cache yet when the reader opened
    // it, producing `EOF while parsing a value, line 1 column 0`. Writing to a `.tmp` sidecar and
    // `rename`-ing makes the manifest appear atomically: a reader either sees the old name (gone)
    // or the complete new file, never a half-written one. `rename` on the same filesystem is atomic
    // by POSIX, so the tmpdir + sidecar (same parent dir) satisfies it.
    let target = dir.join("module.json");
    let sidecar = dir.join("module.json.tmp");
    std::fs::write(&sidecar, KITCHEN).unwrap();
    std::fs::rename(&sidecar, &target).unwrap();
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).unwrap();

    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-role-activation-{}-{admin_id}",
        std::process::id()
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-roles".into(),
        cloud_base_url: "https://example.invalid".into(),
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
    (app(AppState::with_config(rt, cfg)), admin, employee, temp)
}

async fn put(router: &axum::Router, uri: &str, session: Option<&str>, body: Value) -> Response {
    let mut builder = Request::builder()
        .method("PUT")
        .uri(uri)
        .header("content-type", "application/json");
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    router
        .clone()
        .oneshot(builder.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap()
}

async fn roles(router: &axum::Router, session: &str) -> Vec<Value> {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/hub/roles")
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    body_json(response).await["data"]
        .as_array()
        .unwrap()
        .clone()
}

type Response = axum::response::Response;

#[tokio::test]
async fn the_catalogue_travels_with_its_label_source_and_activation() {
    let (router, admin, employee, temp) = fixture().await;

    // Any user session reads it.
    let listed = roles(&router, &employee).await;
    let kitchen = listed
        .iter()
        .find(|r| r["name"] == "kitchen")
        .expect("the role the installed module declares is in the catalogue");
    assert_eq!(kitchen["label"], "Kitchen");
    assert_eq!(kitchen["extends"], "employee");
    assert_eq!(
        kitchen["source"],
        json!({"kind": "module", "module_id": "kitchen"})
    );
    assert_eq!(kitchen["active"], false, "opt-in until somebody says so");

    let admin_role = listed.iter().find(|r| r["name"] == "admin").unwrap();
    assert_eq!(admin_role["source"], json!({ "kind": "core" }));
    assert_eq!(admin_role["active"], true);

    let _ = std::fs::remove_dir_all(temp);
    drop(admin);
}

#[tokio::test]
async fn only_an_administrator_switches_a_role_on() {
    let (router, admin, employee, temp) = fixture().await;

    let denied = put(
        &router,
        "/api/hub/roles/kitchen",
        Some(&employee),
        json!({ "active": true }),
    )
    .await;
    // hub#1705: `403 forbidden`, not `401`. The session is valid and the role is not; the screen
    // must say who can do this instead of «sign in again», which would never help.
    assert_eq!(
        denied.status(),
        StatusCode::FORBIDDEN,
        "deciding which roles exist in the business is administration"
    );
    assert_eq!(body_json(denied).await["error"]["code"], "forbidden");
    assert_eq!(
        roles(&router, &employee)
            .await
            .iter()
            .find(|r| r["name"] == "kitchen")
            .unwrap()["active"],
        false,
        "a refused call changes nothing"
    );

    // No session at all is refused too.
    let anonymous = put(
        &router,
        "/api/hub/roles/kitchen",
        None,
        json!({ "active": true }),
    )
    .await;
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(body_json(anonymous).await["error"]["code"], "unauthorized");

    let granted = put(
        &router,
        "/api/hub/roles/kitchen",
        Some(&admin),
        json!({ "active": true }),
    )
    .await;
    assert_eq!(granted.status(), StatusCode::OK);
    let body = body_json(granted).await;
    assert_eq!(body["ok"], true);
    let kitchen = body["data"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["name"] == "kitchen")
        .expect("the answer carries the updated catalogue")
        .clone();
    assert_eq!(kitchen["active"], true);

    // …and switching it back off is the same door.
    let off = put(
        &router,
        "/api/hub/roles/kitchen",
        Some(&admin),
        json!({ "active": false }),
    )
    .await;
    assert_eq!(off.status(), StatusCode::OK);
    assert_eq!(
        roles(&router, &employee)
            .await
            .iter()
            .find(|r| r["name"] == "kitchen")
            .unwrap()["active"],
        false
    );

    let _ = std::fs::remove_dir_all(temp);
}

#[tokio::test]
async fn the_endpoint_never_mints_a_role_no_module_declares() {
    let (router, admin, employee, temp) = fixture().await;

    let refused = put(
        &router,
        "/api/hub/roles/superadmin",
        Some(&admin),
        json!({ "active": true }),
    )
    .await;
    assert_eq!(
        refused.status(),
        StatusCode::UNPROCESSABLE_ENTITY,
        "the write door is not a place to invent role keys"
    );
    assert!(
        !roles(&router, &employee)
            .await
            .iter()
            .any(|r| r["name"] == "superadmin"),
        "nothing was created"
    );

    let _ = std::fs::remove_dir_all(temp);
}
