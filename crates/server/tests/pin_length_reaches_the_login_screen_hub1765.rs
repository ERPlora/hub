//! The boot context tells the login screen **how many digits this hub's PIN has**
//! (ERPlora/hub#1765).
//!
//! hub#974 made the PIN length a per-hub setting (4 or 6, the same for everybody) and the web
//! reads it from `hub_settings.pin_length` through `lib/pin-length.ts`. The catch: that value only
//! ever travelled in `GET /api/settings`, which **requires a session** — and the login screen is
//! precisely the one screen that has none. Measured on the PRE bench
//! (`banco-pre.a.erplora.com/login`, 2026-09-10): `GET /api/settings` → `401 falta sesión`, the
//! boot context carried no `pin_length`, so the pinpad fell back to the default 4 and painted
//! **four circles for a six-digit PIN**. That is not cosmetic: `ok-pinpad` submits on the last
//! circle, so the hub could not be signed into by PIN at all — the fourth digit fired a login with
//! a truncated PIN.
//!
//! What this file pins: the boot context — the one door the login screen CAN read, with no
//! session — publishes `pin_length`, it is this hub's value and not a constant, and a hub that
//! never chose one gets the runtime's own default rather than nothing.
//!
//! The length is not a secret: anyone looking at the pinpad counts the circles. What it must never
//! be is *wrong*, which is what a client-side default guarantees the moment a hub picks the other
//! one.
use axum::body::Body;
use axum::http::Request;
use erplora_db::testutil::fresh_db;
use erplora_runtime::pin_policy::{DEFAULT_PIN_LENGTH, PIN_LENGTHS};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Map, Value};
use tower::ServiceExt; // oneshot

fn config(tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-ctx-pin-{}-{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-pin".into(),
        cloud_base_url: "https://pre.erplora.com".into(),
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
    }
}

/// The boot context exactly as the login screen fetches it: no session, no headers, no cookie.
async fn context_with_pin_length(chosen: Option<i64>, tag: &str) -> Value {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-pin");
    rt.ensure_system_tables().await.unwrap();
    if let Some(n) = chosen {
        let mut updates = Map::new();
        updates.insert("pin_length".into(), json!(n));
        rt.set_settings(&updates, "hub_user:test").await.unwrap();
    }
    let router = app(AppState::with_config(rt, config(tag)));
    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

#[tokio::test]
async fn the_boot_context_publishes_this_hubs_pin_length() {
    for length in PIN_LENGTHS {
        let body = context_with_pin_length(Some(length), &format!("chose{length}")).await;
        assert_eq!(
            body["pin_length"],
            json!(length),
            "the login screen has no session, so the boot context is the only place it can learn \
             how many circles to paint; a hub that chose {length} must not get a default: {body}"
        );
    }
}

#[tokio::test]
async fn a_hub_that_never_chose_publishes_the_runtimes_own_default() {
    let body = context_with_pin_length(None, "default").await;
    assert_eq!(
        body["pin_length"],
        json!(DEFAULT_PIN_LENGTH),
        "no row yet must publish the runtime's default, never `null` — the shell would then have \
         to invent one, which is the bug this closes: {body}"
    );
}

/// The boot context for a hub whose `pin_length` row holds something the write door would never
/// have accepted — `set_settings` validates against [`PIN_LENGTHS`], so a row like this can only
/// come from raw SQL: an imported bundle, a hand-edited database, a migration gone wrong.
async fn context_with_raw_pin_length_row(raw: &str, tag: &str) -> Value {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-pin");
    rt.ensure_system_tables().await.unwrap();
    let mut p = erplora_db::Params::new();
    p.insert("hub_id".into(), json!("hub-pin"));
    p.insert("value".into(), json!(raw));
    rt.db()
        .execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
             VALUES (:hub_id, 'pin_length', :value, '2026-09-10T00:00:00Z', 'raw-sql')",
            &p,
        )
        .await
        .unwrap();
    let router = app(AppState::with_config(rt, config(tag)));
    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// A length no keypad can type must never reach the login screen.
///
/// This is the end of the chain, and it is the reason the guarantee is worth a test of its own:
/// `ok-pinpad` **submits on the last circle**, so the published length does not decide how many
/// dots are painted — it decides *when the PIN is sent*. Publish a 5 and the keypad waits forever
/// for a fifth circle that the four-digit PIN will never fill: a till that cannot be opened, with
/// nothing on screen saying why. So whatever a row says, the boot context publishes one of the two
/// lengths a person can actually type.
#[tokio::test]
async fn a_length_no_keypad_can_type_never_reaches_the_login_screen() {
    for (i, raw) in ["5", "0", "-6", "12", "abc", ""].iter().enumerate() {
        let body = context_with_raw_pin_length_row(raw, &format!("raw{i}")).await;
        assert_eq!(
            body["pin_length"],
            json!(DEFAULT_PIN_LENGTH),
            "a stored `pin_length` of {raw:?} is not a length anybody can type; the login screen \
             must be given the default instead of a keypad that never submits: {body}"
        );
        assert!(
            PIN_LENGTHS.contains(&body["pin_length"].as_i64().unwrap_or(0)),
            "whatever the row says, what reaches the login screen is one of {PIN_LENGTHS:?}: {body}"
        );
    }
}
