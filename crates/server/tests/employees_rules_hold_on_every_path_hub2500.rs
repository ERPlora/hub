//! hub#2500 — Employees, seen from the HTTP door the screen uses (`/api/hub/users`).
//!
//! - The address a person types in «My profile» is theirs to show, never the key of anybody's
//!   access: taking a PIN-only person off the team does not ask erplora.com to remove the access of
//!   whoever owns the address they typed (HUB-F149). The hub here points at an unreachable
//!   erplora.com on purpose: any call to it would turn the answer into `cloud_unreachable`.
//! - Editing a PIN-only person into an administrator is refused like the sign-up refuses it
//!   (HUB-F148), with the same stable code.
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

struct Fixture {
    router: axum::Router,
    owner: String,
    cashier: String,
    cashier_id: String,
    media: std::path::PathBuf,
}

async fn fixture(hub_id: &str) -> Fixture {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let owner = rt
        .get_or_link_cloud_user("cloud-1", "Ioan Beilic", "admin", None, None)
        .await
        .unwrap();
    let cashier = rt
        .create_user("Marta Ruiz", "4821", "employee", None)
        .await
        .unwrap();
    let owner_token = rt.create_session(&owner.id, 3600, None).await.unwrap();
    let cashier_token = rt.create_session(&cashier, 3600, None).await.unwrap();
    let media = std::env::temp_dir().join(format!(
        "erplora-hub2500-{}-{}",
        std::process::id(),
        owner.id
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: media.join("modules"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: media.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        owner: owner_token,
        cashier: cashier_token,
        cashier_id: cashier,
        media,
    }
}

async fn send(
    router: &axum::Router,
    method: &str,
    uri: &str,
    session: &str,
    body: Value,
) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method(method)
                .uri(uri)
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

#[tokio::test]
async fn hub2500_taking_a_pin_only_person_off_the_team_never_revokes_the_address_they_typed() {
    let f = fixture("hub-2500-http-a").await;
    // Marta signs in with her PIN only and writes the owner's address in her own profile.
    let res = send(
        &f.router,
        "PUT",
        "/api/profile",
        &f.cashier,
        json!({ "first_name": "Marta", "last_name": "Ruiz", "email": "ioan@example.com" }),
    )
    .await;
    assert_eq!(res.status(), StatusCode::OK);

    let res = send(
        &f.router,
        "DELETE",
        &format!("/api/hub/users/{}", f.cashier_id),
        &f.owner,
        json!({}),
    )
    .await;
    let status = res.status();
    let body = body_json(res).await;
    assert_eq!(
        status,
        StatusCode::OK,
        "a PIN-only person has no membership in erplora.com, so nothing is revoked there: {body}"
    );
    assert_eq!(body["data"]["is_active"], false);
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn hub2500_editing_a_pin_only_person_into_an_administrator_answers_the_stable_code() {
    let f = fixture("hub-2500-http-b").await;
    let res = send(
        &f.router,
        "PUT",
        &format!("/api/hub/users/{}", f.cashier_id),
        &f.owner,
        json!({ "role": "admin" }),
    )
    .await;
    assert_eq!(res.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(res).await["error"]["code"],
        "hub.users.local_cannot_administer"
    );
    std::fs::remove_dir_all(f.media).ok();
}
