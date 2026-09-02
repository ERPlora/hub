use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn fixture() -> (axum::Router, String, String, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-profile");
    rt.ensure_system_tables().await.unwrap();
    let alice = rt
        .create_user("Alice Doe", "1111", "admin", None)
        .await
        .unwrap();
    let bob = rt
        .create_user("Bob Roe", "2222", "employee", None)
        .await
        .unwrap();
    let alice_token = rt.create_session(&alice, 3600, None).await.unwrap();
    let bob_token = rt.create_session(&bob, 3600, None).await.unwrap();
    let media = std::env::temp_dir().join(format!(
        "erplora-profile-api-{}-{}",
        std::process::id(),
        alice
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-profile".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: media.join("modules"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        // El fixture prueba el aislamiento del perfil, no el alta inicial de la máquina.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: media.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    (
        app(AppState::with_config(rt, cfg)),
        alice_token,
        bob_token,
        media,
    )
}

#[tokio::test]
async fn profile_updates_only_the_authenticated_user() {
    let (router, alice, bob, media) = fixture().await;
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri("/api/profile")
                .header("content-type", "application/json")
                .header("x-hub-session", &alice)
                .body(Body::from(
                    json!({
                        "id": "attempted-other-user",
                        "first_name": "Alicia",
                        "last_name": "Doe",
                        "email": "alice@example.com",
                        "preferences": {
                            "language": "en",
                            "theme_mode": "dark",
                            "theme_palette": "ocean"
                        }
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let profile = body_json(response).await;
    assert_eq!(profile["name"], "Alicia Doe");
    assert_eq!(profile["preferences"]["theme_palette"], "ocean");
    assert!(profile["permissions"].is_array());

    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/profile")
                .header("x-hub-session", bob)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let bob_profile = body_json(response).await;
    assert_eq!(bob_profile["name"], "Bob Roe");
    assert!(bob_profile["preferences"]["language"].is_null());
    std::fs::remove_dir_all(media).ok();
}

#[tokio::test]
async fn avatar_upload_is_private_and_persistent() {
    let (router, alice, bob, media) = fixture().await;
    let boundary = "profile-boundary";
    let image = b"\x89PNG\r\n\x1a\nfake-image-bytes";
    let mut multipart = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"avatar\"; filename=\"me.png\"\r\nContent-Type: image/png\r\n\r\n"
    )
    .into_bytes();
    multipart.extend_from_slice(image);
    multipart.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());

    let upload = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/profile/avatar")
                .header("x-hub-session", &alice)
                .header(
                    "content-type",
                    format!("multipart/form-data; boundary={boundary}"),
                )
                .body(Body::from(multipart))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(upload.status(), StatusCode::OK);
    assert_eq!(body_json(upload).await["avatar_url"], "/api/profile/avatar");

    let own = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/profile/avatar")
                .header("x-hub-session", alice)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(own.status(), StatusCode::OK);
    assert_eq!(
        own.into_body().collect().await.unwrap().to_bytes().as_ref(),
        image
    );

    let other = router
        .oneshot(
            Request::builder()
                .uri("/api/profile/avatar")
                .header("x-hub-session", bob)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(other.status(), StatusCode::NOT_FOUND);
    std::fs::remove_dir_all(media).ok();
}

#[tokio::test]
async fn dev_mode_materializes_the_header_user_without_a_fake_session() {
    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.unwrap();
    let router = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/profile")
                .header("x-user-id", "demo-user")
                .header("x-user-name", "Demo Owner")
                .header("x-user-role", "admin")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let profile = body_json(response).await;
    assert_eq!(profile["id"], "demo-user");
    assert_eq!(profile["name"], "Demo Owner");
    assert_eq!(profile["role"], "admin");
    assert!(profile["permissions"].is_array());
}
