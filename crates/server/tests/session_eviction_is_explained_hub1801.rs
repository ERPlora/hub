//! **The second device threw you out and the hub said nothing** (hub#1801).
//!
//! On the Free plan the plan covers ONE device. Signing in from a second one closes the first one's
//! session — that part is correct and it is what the plan promises. What was not correct is how the
//! first one found out: it did not. The screen simply stopped working and dropped back to the login
//! without a word, which from where that person sits looks like the hub going down, or somebody
//! changing their password. They call support.
//!
//! So the refusal has to be **distinguishable**. This file pins the contract at the door the shell
//! actually asks — `GET /api/settings` is the probe `lib/runtime.ts` uses to confirm a session is
//! dead — and it pins both halves, because only the pair is worth anything:
//!
//!   - an EVICTED session answers `401` carrying the stable code `session_evicted_device_limit`;
//!   - a session that merely expired by time answers `401` WITHOUT it. If both said the same, the
//!     screen would be back to guessing, just in the other direction.
//!
//! The code travels as **data**, never prose (ADR-0055): the sentence belongs to the shell's
//! catalogue in `en` and `es`, not to the runtime.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // oneshot

/// A hub with one admin, signed in on the office laptop and on the counter till.
async fn fixture(hub_id: &str) -> (axum::Router, AppState, String, String) {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let admin = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let on_laptop = rt
        .create_session(&admin, 3600, Some("laptop-1"))
        .await
        .unwrap();
    // Born expired: nobody evicted it, time did.
    let stale = rt
        .create_session(&admin, -60, Some("laptop-1"))
        .await
        .unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-hub1801-{hub_id}-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
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
    let state = AppState::with_config(rt, cfg);
    (app(state.clone()), state, on_laptop, stale)
}

/// The probe the shell uses to tell "this session is dead" from "that door is not for you".
async fn probe(router: &axum::Router, session: &str) -> (StatusCode, Value) {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/settings")
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap_or(Value::Null))
}

#[tokio::test]
async fn an_evicted_session_is_refused_with_a_code_the_login_screen_can_explain() {
    let (router, state, on_laptop, _stale) = fixture("hub-1801").await;

    // Precondition: while it is alive, the probe is not a refusal at all.
    assert_eq!(probe(&router, &on_laptop).await.0, StatusCode::OK);

    // The till signs in on a plan of ONE device: the laptop is evicted.
    {
        let arc = state.runtime_for(&state.hub_id()).await.unwrap();
        let rt = arc.read().await;
        rt.enforce_device_limit(1, Some("till-1")).await.unwrap();
    }

    let (status, body) = probe(&router, &on_laptop).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(
        body["code"], "session_evicted_device_limit",
        "the refusal has to name WHY, as data: without it the login screen can only stay quiet ({body})"
    );
}

#[tokio::test]
async fn a_session_that_merely_expired_carries_no_eviction_code() {
    let (router, _state, _on_laptop, stale) = fixture("hub-1801-stale").await;

    let (status, body) = probe(&router, &stale).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_ne!(
        body["code"], "session_evicted_device_limit",
        "expiring by time is not being thrown out, and telling the person otherwise would send \
         them to upgrade a plan that was never the problem ({body})"
    );
}
