use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::SqliteAdapter;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::json;
use tower::ServiceExt;

async fn fixture() -> (axum::Router, String, String, std::path::PathBuf) {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let rt = Runtime::with_hub_id(Box::new(db), "hub-media");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let media = std::env::temp_dir().join(format!(
        "erplora-media-api-{}-{admin_id}",
        std::process::id()
    ));
    let cfg = HubConfig {
        hub_id: "hub-media".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: media.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        // El fixture prueba autorización humana de media, no el alta inicial de la máquina.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: media.clone(),
        sector: None,
    };
    (
        app(AppState::with_config(rt, cfg)),
        admin,
        employee,
        media,
    )
}

#[tokio::test]
async fn media_requires_a_human_session_even_for_reads() {
    let (router, _admin, employee, media) = fixture().await;
    let anonymous = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/media")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let authenticated = router
        .oneshot(
            Request::builder()
                .uri("/api/media")
                .header("x-hub-session", employee)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(authenticated.status(), StatusCode::OK);
    std::fs::remove_dir_all(media).ok();
}

#[tokio::test]
async fn only_admin_can_modify_media() {
    let (router, admin, employee, media) = fixture().await;
    let body = json!({ "parent": "", "name": "facturas" }).to_string();
    let denied = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/media/folder")
                .header("content-type", "application/json")
                .header("x-hub-session", employee)
                .body(Body::from(body.clone()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);

    let allowed = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/media/folder")
                .header("content-type", "application/json")
                .header("x-hub-session", admin)
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(allowed.status(), StatusCode::OK);
    assert!(media.join("facturas").is_dir());
    std::fs::remove_dir_all(media).ok();
}
