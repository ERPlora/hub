use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::SqliteAdapter;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::json;
use tower::ServiceExt;

async fn fixture() -> (axum::Router, String, String, std::path::PathBuf) {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let rt = Runtime::with_hub_id(Box::new(db), "hub-auth");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600).await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-core-api-auth-{}-{admin_id}",
        std::process::id()
    ));
    let cfg = HubConfig {
        hub_id: "hub-auth".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
    };
    (app(AppState::with_config(rt, cfg)), admin, employee, temp)
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if body.is_some() {
        builder = builder.header("content-type", "application/json");
    }
    builder
        .body(Body::from(body.unwrap_or_default().to_owned()))
        .unwrap()
}

#[tokio::test]
async fn core_diagnostics_and_module_metadata_require_a_user_session() {
    let (router, _admin, employee, temp) = fixture().await;
    let private_uris = [
        "/api/system",
        "/api/navigation",
        "/api/modules",
        "/api/entitlement",
        "/api/bridge/token",
        "/api/marketplace/catalog",
        "/api/blueprints/catalog",
        "/api/blueprints/example/download",
    ];
    for uri in private_uris {
        let anonymous = router
            .clone()
            .oneshot(request("GET", uri, None, None))
            .await
            .unwrap();
        assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED, "{uri}");
    }
    for uri in ["/api/system", "/api/navigation", "/api/modules"] {
        let authenticated = router
            .clone()
            .oneshot(request("GET", uri, Some(&employee), None))
            .await
            .unwrap();
        assert_eq!(authenticated.status(), StatusCode::OK, "{uri}");
    }
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn only_admin_can_mutate_module_lifecycle() {
    let (router, admin, employee, temp) = fixture().await;
    let install_body = json!({ "dir": temp.join("missing") }).to_string();

    for (method, uri, body) in [
        ("POST", "/api/modules/install", Some(install_body.as_str())),
        ("POST", "/api/modules/missing/activate", None),
        ("POST", "/api/modules/missing/deactivate", None),
        ("POST", "/api/modules/missing/uninstall", None),
    ] {
        let anonymous = router
            .clone()
            .oneshot(request(method, uri, None, body))
            .await
            .unwrap();
        assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED, "{uri}");

        let denied = router
            .clone()
            .oneshot(request(method, uri, Some(&employee), body))
            .await
            .unwrap();
        assert_eq!(denied.status(), StatusCode::UNAUTHORIZED, "{uri}");

        let allowed_to_reach_runtime = router
            .clone()
            .oneshot(request(method, uri, Some(&admin), body))
            .await
            .unwrap();
        assert_ne!(
            allowed_to_reach_runtime.status(),
            StatusCode::UNAUTHORIZED,
            "{uri}"
        );
    }
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn cloud_install_cannot_use_the_hub_machine_token_without_an_admin_session() {
    let (router, _admin, employee, temp) = fixture().await;
    let body = json!({ "module_id": "inventory", "version": "1.0.0" }).to_string();

    let anonymous = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/modules/request-install",
            None,
            Some(&body),
        ))
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let denied = router
        .oneshot(request(
            "POST",
            "/api/modules/request-install",
            Some(&employee),
            Some(&body),
        ))
        .await
        .unwrap();
    assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);
    std::fs::remove_dir_all(temp).ok();
}
