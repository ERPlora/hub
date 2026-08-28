//! The two doors of the representation grant, as the ROUTER wires them (hub#1293).
//!
//! `representation_grant.rs` has its own tests for what the handlers do; this file asserts what
//! only `app()` can get wrong, because it lives in the router and not in the module:
//!
//!   * `POST /api/fiscal/representation-grant/model` is an **admin** door. The kernel snapshot
//!     derives `auth:admin` from the source; this is the same fact observed from outside, with a
//!     real session of each role.
//!   * `POST /api/fiscal/representation-grant` has a body limit **wider than axum's 2 MB default**.
//!     `MAX_UPLOAD_BYTES` alone proves nothing — a constant nobody applies is a constant — so the
//!     test pushes a 3 MB document through the real route and expects `validate` to answer, not
//!     the framework with a `413`.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt;

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn fixture() -> (axum::Router, String, String, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-grant-door");
    rt.ensure_system_tables().await.unwrap();
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
        "erplora-grant-door-{}-{admin_id}",
        std::process::id()
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-grant-door".into(),
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

fn model_request(session: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder()
        .method("POST")
        .uri("/api/fiscal/representation-grant/model")
        .header("content-type", "application/json");
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    // An EMPTY obligado: past the gate, `validate_model_fields` refuses it with its own code
    // before anything reaches the network — which is how the test tells "admitted" from "denied"
    // without a control plane.
    builder
        .body(Body::from(
            r#"{"obligado_nif": "", "signer_nif": "1", "signer_name": "x"}"#,
        ))
        .unwrap()
}

/// 🔒 **The model route is an admin door** — the fields travel into a document that names the
/// business as a taxpayer, the same bar as the upload. Anonymous and a plain employee are refused;
/// an admin gets past the gate and is answered by `validate_model_fields`.
#[tokio::test]
async fn the_model_route_admits_only_an_admin_session() {
    let (router, admin, employee, temp) = fixture().await;

    let anonymous = router.clone().oneshot(model_request(None)).await.unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let denied = router
        .clone()
        .oneshot(model_request(Some(&employee)))
        .await
        .unwrap();
    assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);

    let admitted = router
        .clone()
        .oneshot(model_request(Some(&admin)))
        .await
        .unwrap();
    assert_eq!(admitted.status(), StatusCode::BAD_REQUEST);
    assert_eq!(body_json(admitted).await["error"], "obligado_nif_required");

    std::fs::remove_dir_all(temp).ok();
}

/// 🔴 **The upload door is wider than axum's default.** A signed model scanned at any sensible
/// resolution is more than 2 MB; sent through the real route, it must reach `validate` (which
/// here answers `dni_copy_required`, because no ID copy travels) and never the framework's `413`.
#[tokio::test]
async fn a_three_megabyte_document_reaches_validate_instead_of_a_413() {
    let (router, admin, _employee, temp) = fixture().await;
    let boundary = "grant-door-boundary";

    let mut document = b"%PDF-1.7 ".to_vec();
    document.resize(3 * 1024 * 1024, b' ');

    let mut multipart = Vec::new();
    for (name, value) in [
        ("obligado_nif", "12345678Z"),
        ("signer_nif", "12345678Z"),
        ("signer_name", "Manolo García"),
        ("document_type", "dni"),
    ] {
        multipart.extend_from_slice(
            format!("--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
                .as_bytes(),
        );
    }
    multipart.extend_from_slice(
        format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"signed_document\"; filename=\"anexo-i.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
        )
        .as_bytes(),
    );
    multipart.extend_from_slice(&document);
    multipart.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());

    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/fiscal/representation-grant")
                .header("x-hub-session", &admin)
                .header(
                    "content-type",
                    format!("multipart/form-data; boundary={boundary}"),
                )
                .body(Body::from(multipart))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(body_json(response).await["error"], "dni_copy_required");

    std::fs::remove_dir_all(temp).ok();
}

/// And past the door, the refusal has to say WHAT was wrong. When the body limit cuts the stream,
/// the multipart reader fails mid-way; an empty capture would then answer `obligado_nif_required`
/// — «your business needs a taxpayer ID» — to somebody whose only mistake was a 45 MB scan. The
/// code that names the actual problem is `document_too_large`.
#[tokio::test]
async fn an_upload_heavier_than_the_door_is_refused_as_too_large_not_as_missing_fields() {
    let (router, admin, _employee, temp) = fixture().await;
    let boundary = "grant-door-boundary";

    let mut document = b"%PDF-1.7 ".to_vec();
    document.resize(
        erplora_server::representation_grant::MAX_UPLOAD_BYTES + 1,
        b' ',
    );

    let mut multipart = Vec::new();
    for (name, value) in [
        ("obligado_nif", "12345678Z"),
        ("signer_nif", "12345678Z"),
        ("signer_name", "Manolo García"),
        ("document_type", "dni"),
    ] {
        multipart.extend_from_slice(
            format!("--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
                .as_bytes(),
        );
    }
    multipart.extend_from_slice(
        format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"signed_document\"; filename=\"anexo-i.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
        )
        .as_bytes(),
    );
    multipart.extend_from_slice(&document);
    multipart.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());

    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/fiscal/representation-grant")
                .header("x-hub-session", &admin)
                .header(
                    "content-type",
                    format!("multipart/form-data; boundary={boundary}"),
                )
                .body(Body::from(multipart))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(body_json(response).await["error"], "document_too_large");

    std::fs::remove_dir_all(temp).ok();
}
