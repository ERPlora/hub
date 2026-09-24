//! **A refused API-key gesture says WHY** (hub#1700).
//!
//! The panel in Settings → API keys had exactly one sentence for every refusal — «could not revoke
//! this key, check your connection» — and it was not the screen's fault: the four handlers of
//! `/api/keys*` answered `{"ok":false,"error":"<flat string>"}`, so there was nothing to branch on.
//! Worse, the client reads `error.message` (hub#1697's shape), and on a flat string that is
//! `undefined`, so even the prose was lost: what reached the person was the fallback line.
//!
//! Every other admin door of this hub already answers the SAME envelope — `{"ok":false,"error":
//! {"code","message"}}` — from one implementation (`err_response` / `auth_rejected`, hub#1074,
//! hub#1241). This file pins that these four join it, refusal by refusal, on the door's REAL body:
//! the defect of origin was a screen translating a code nobody sent, so a mocked body would prove
//! nothing.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-keys-1700";

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

struct Fixture {
    router: axum::Router,
    admin: String,
    employee: String,
    /// The read-only key the hub issued to itself: it may not be rotated nor revoked.
    system_key_id: String,
}

/// A business with an admin and a cashier, both signed in, and the hub's own key already minted.
async fn fixture() -> Fixture {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let employee_id = rt
        .create_user("Cashier", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let system_key_id = rt.ensure_app_api_key().await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-keys-1700-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        // Session mode on purpose: `Dev` grants the admin gate to whoever asks, so the two
        // refusals this door owes a code to (no session · wrong role) are unreachable there.
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
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        admin,
        employee,
        system_key_id,
    }
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-id", HUB_ID);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    match body {
        Some(json) => builder
            .header("content-type", "application/json")
            .body(Body::from(json.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

/// The stable code of a refusal, read the way `lib/api-keys.ts` reads it.
fn code_of(body: &Value) -> Option<&str> {
    body["error"]["code"].as_str()
}

#[tokio::test]
async fn revoking_a_key_that_is_gone_says_so() {
    let f = fixture().await;
    let response = f
        .router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/keys/nosuchkey",
            Some(&f.admin),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body = body_json(response).await;
    assert_eq!(
        code_of(&body),
        Some("not_found"),
        "the panel translates this into «that key no longer exists»: {body}"
    );
    // And the prose still travels, in the shape hub#1697's clients read (`error.message`).
    assert!(
        body["error"]["message"]
            .as_str()
            .is_some_and(|m| !m.is_empty()),
        "a refusal keeps a message for the log: {body}"
    );
}

#[tokio::test]
async fn rotating_a_key_that_is_gone_says_so() {
    let f = fixture().await;
    let response = f
        .router
        .clone()
        .oneshot(request(
            "POST",
            "/api/keys/nosuchkey/rotate",
            Some(&f.admin),
            Some(json!({})),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body = body_json(response).await;
    assert_eq!(code_of(&body), Some("not_found"), "{body}");
}

#[tokio::test]
async fn a_dead_session_is_not_a_broken_connection() {
    let f = fixture().await;
    // The exact case the ticket describes: the person's session lapsed while the panel was open.
    for (method, uri, payload) in [
        ("GET", "/api/keys".to_string(), None),
        (
            "POST",
            "/api/keys".to_string(),
            Some(json!({ "name": "Gestoría", "scope": [] })),
        ),
        (
            "POST",
            "/api/keys/whatever/rotate".to_string(),
            Some(json!({})),
        ),
        ("DELETE", "/api/keys/whatever".to_string(), None),
    ] {
        let response = f
            .router
            .clone()
            .oneshot(request(method, &uri, None, payload))
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::UNAUTHORIZED,
            "{method} {uri} with no session"
        );
        let body = body_json(response).await;
        assert_eq!(
            code_of(&body),
            Some("unauthorized"),
            "{method} {uri} → {body}"
        );
    }
}

#[tokio::test]
async fn a_cashier_is_told_it_is_not_their_door_not_to_sign_in_again() {
    let f = fixture().await;
    // A valid session with the wrong role: signing in again as the same cashier never helps, so
    // this is `403 forbidden` and NOT the `401` that invites a re-login (hub#660).
    let response = f
        .router
        .clone()
        .oneshot(request("GET", "/api/keys", Some(&f.employee), None))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    let body = body_json(response).await;
    assert_eq!(code_of(&body), Some("forbidden"), "{body}");
}

#[tokio::test]
async fn the_hubs_own_key_refuses_with_its_own_reason() {
    let f = fixture().await;
    for (method, uri) in [
        ("DELETE", format!("/api/keys/{}", f.system_key_id)),
        ("POST", format!("/api/keys/{}/rotate", f.system_key_id)),
    ] {
        let response = f
            .router
            .clone()
            .oneshot(request(&method, &uri, Some(&f.admin), Some(json!({}))))
            .await
            .unwrap();
        let status = response.status();
        let body = body_json(response).await;
        assert_eq!(status, StatusCode::CONFLICT, "{method} {uri} → {body}");
        // The LITERAL, not `ERR_KEY_IS_SYSTEM`: the panel keys its sentence on
        // `apiKeys.errors.api_key.system_key`, so the value of that constant is a contract with the
        // catalogue and not an internal name. Asserted against the constant this reads
        // `X == X` — renaming it travels to the screen, which then has no sentence for the code and
        // falls back to the generic line, with this suite green (verified: rv-1703 renamed it to
        // `api_key.owned_by_the_hub` and all 6 still passed).
        assert_eq!(
            code_of(&body),
            Some("api_key.system_key"),
            "{method} {uri} → {body}"
        );
        assert_eq!(
            erplora_runtime::api_keys::ERR_KEY_IS_SYSTEM,
            "api_key.system_key",
            "the constant the door reads and the code the catalogue translates are the same string"
        );
    }
}

#[tokio::test]
async fn a_rate_limit_out_of_range_is_a_refusal_with_a_code() {
    let f = fixture().await;
    let response = f
        .router
        .clone()
        .oneshot(request(
            "POST",
            "/api/keys",
            Some(&f.admin),
            Some(json!({ "name": "Gestoría", "scope": [], "rate_limit_per_minute": 0 })),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let body = body_json(response).await;
    assert!(
        code_of(&body).is_some_and(|c| !c.is_empty()),
        "every refusal of this door carries a code: {body}"
    );
}
