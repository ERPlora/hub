//! E2E — the boot context names the team only to a trusted device (hub#2510).
//!
//! `GET /api/hub/context` takes no session: the login screen reads it before anybody signed in. It
//! used to hand EVERY caller on the internet the name and role of each person with a PIN. The
//! faces exist for one screen — the pinpad — and the pinpad only works on a trusted device
//! (HUB-F133), so that is who gets them, gated in the order the PIN door already applies:
//!
//! - a live session gets them (the approval dialog and «switch user» run behind one, also on a
//!   browser that entered through the panel courier and was never trusted);
//! - otherwise a locked ADDRESS gets nothing, even from a trusted device (HUB-F135 first);
//! - otherwise the DEVICE decides, with the same rule as the PIN door: trusted, or the first device
//!   of a virgin demo; with trust disarmed (`HUB_DEVICE_TRUST=off`) the PIN is open to anybody, so
//!   the faces are too.
//!
//! An invented session presented here counts against the address like at any other door
//! (hub#2282): without it this door would be a free oracle for session tokens.
//!
//! Everything else in the context (currency, PIN length, Cloud URL, registration flags) still
//! reaches everybody: the login screen needs it and it names nobody. So does the hub id, on
//! purpose: erplora.com reads it without a credential to prove that a custom domain reaches THIS
//! hub (`saas` `custom_domains._fetch_hub_id`), and so do the module toolkit's `--against-hub` and
//! the CI batteries. It names the business, not a person, and it is no secret: the import that
//! trusts it is fixed where it trusts it (hub#2497).
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::address_guard::{MAX_FORGED_SESSIONS, MAX_GUESSES};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-ctx-2510";
const TILL: &str = "dev_counter-till";
const STRANGER: &str = "dev_made-up-by-a-stranger";

struct Hub {
    router: axum::Router,
    rt_session: String,
}

async fn hub(device_trust_enforce: bool, demo: bool) -> Hub {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin = rt
        .create_user("Admin", "1357", "admin", None)
        .await
        .unwrap();
    rt.create_user("Marta", "2468", "cashier", None)
        .await
        .unwrap();
    if !demo {
        rt.trust_device(TILL, "Counter").await.unwrap();
    }
    // A session opened on a device the hub never trusted: the panel courier in a browser.
    let rt_session = rt.create_session(&admin, 3600, None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-ctx-2510-{}", std::process::id()));
    let cfg = HubConfig {
        demo,
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    Hub {
        router: app(AppState::with_config(rt, cfg)),
        rt_session,
    }
}

fn forwarded(client: &str) -> String {
    format!("10.9.9.9, {client}")
}

async fn context(
    router: &axum::Router,
    client: &str,
    device: Option<&str>,
    session: Option<&str>,
) -> Value {
    let mut request = Request::builder()
        .uri("/api/hub/context")
        .header("x-forwarded-for", forwarded(client));
    if let Some(device) = device {
        request = request.header("x-device-id", device);
    }
    if let Some(session) = session {
        request = request.header("x-hub-session", session);
    }
    let response = router
        .clone()
        .oneshot(request.body(Body::empty()).unwrap())
        .await
        .unwrap();
    // The login screen must still boot: a withheld context is a 200 with less in it, never an
    // error the shell would turn into «cannot connect».
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn faces(body: &Value) -> Vec<String> {
    body["pin_users"]
        .as_array()
        .map(|users| {
            users
                .iter()
                .filter_map(|u| u["name"].as_str().map(str::to_owned))
                .collect()
        })
        .unwrap_or_default()
}

/// Nothing in the answer names a person.
fn assert_withheld(body: &Value, why: &str) {
    assert_eq!(faces(body), Vec::<String>::new(), "{why}: {body}");
    let text = body.to_string();
    for leaked in ["Marta", "Admin", "cashier"] {
        assert!(!text.contains(leaked), "{why}: «{leaked}» leaked: {body}");
    }
    // What the login screen needs to paint itself is still there.
    assert_eq!(body["pin_length"], json!(4), "{why}: {body}");
    assert_eq!(body["currency"], json!("EUR"), "{why}: {body}");
    assert_eq!(
        body["cloud_base_url"],
        json!("https://example.invalid"),
        "{why}: {body}"
    );
    // The custom-domain probe of erplora.com reads it with no credential (see the header).
    assert_eq!(body["hub_id"], json!(HUB_ID), "{why}: {body}");
}

fn assert_disclosed(body: &Value, why: &str) {
    let mut names = faces(body);
    names.sort();
    assert_eq!(names, vec!["Admin", "Marta"], "{why}: {body}");
    assert_eq!(body["hub_id"], json!(HUB_ID), "{why}: {body}");
}

#[tokio::test]
async fn a_caller_with_no_device_and_no_session_learns_nobody() {
    let hub = hub(true, false).await;
    let body = context(&hub.router, "198.51.100.1", None, None).await;
    assert_withheld(&body, "anonymous caller");
}

#[tokio::test]
async fn a_device_the_hub_never_trusted_learns_nobody() {
    let hub = hub(true, false).await;
    let body = context(&hub.router, "198.51.100.2", Some(STRANGER), None).await;
    assert_withheld(&body, "untrusted device");
    // Blanks are a client that did not identify itself, never a lookup for "  ".
    let body = context(&hub.router, "198.51.100.2", Some("   "), None).await;
    assert_withheld(&body, "blank device id");
}

#[tokio::test]
async fn the_trusted_till_gets_its_pinpad() {
    let hub = hub(true, false).await;
    let body = context(&hub.router, "198.51.100.3", Some(TILL), None).await;
    assert_disclosed(&body, "trusted till");
}

#[tokio::test]
async fn the_trusted_till_keeps_its_pinpad_when_its_session_has_died() {
    // Every morning: the till boots with yesterday's session still stored and the shell presents
    // it (HUB_SHELL-F04). It no longer resolves — but the device is still the trusted one, so the
    // grid is painted: a dead session is a reason to ask the device, never to send the till to the
    // account door. And a till repeating its own dead session is one token, counted once (HUB-F135):
    // it cannot lock itself out by rebooting.
    let hub = hub(true, false).await;
    let client = "198.51.100.9";
    for _ in 0..(MAX_FORGED_SESSIONS + 5) {
        let body = context(
            &hub.router,
            client,
            Some(TILL),
            Some("sess-that-expired-overnight"),
        )
        .await;
        assert_disclosed(&body, "trusted till with a dead session");
    }
}

#[tokio::test]
async fn a_live_session_gets_them_even_on_an_untrusted_device() {
    let hub = hub(true, false).await;
    let session = hub.rt_session.clone();
    let body = context(&hub.router, "198.51.100.4", Some(STRANGER), Some(&session)).await;
    assert_disclosed(&body, "session from the panel courier");
}

#[tokio::test]
async fn a_locked_address_learns_nobody_even_from_the_trusted_till() {
    let hub = hub(true, false).await;
    let client = "198.51.100.5";
    // Wrong PINs from the trusted till until the address locks (HUB-F135), one name each so the
    // per-name lock never answers first.
    for n in 0..MAX_GUESSES {
        let response = hub
            .router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/auth/pin")
                    .header("content-type", "application/json")
                    .header("x-forwarded-for", forwarded(client))
                    .body(Body::from(
                        json!({ "name": format!("nobody-{n}"), "pin": "9753", "device_id": TILL })
                            .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }
    let body = context(&hub.router, client, Some(TILL), None).await;
    assert_withheld(&body, "locked address");
    // Another address on the same till is not touched.
    let body = context(&hub.router, "198.51.100.55", Some(TILL), None).await;
    assert_disclosed(&body, "other address");
    // And whoever already holds a session keeps working behind the locked address.
    let session = hub.rt_session.clone();
    let body = context(&hub.router, client, Some(TILL), Some(&session)).await;
    assert_disclosed(&body, "session behind a locked address");
}

#[tokio::test]
async fn invented_sessions_here_count_against_the_address() {
    let hub = hub(true, false).await;
    let client = "198.51.100.6";
    for n in 0..MAX_FORGED_SESSIONS {
        let body = context(
            &hub.router,
            client,
            Some(STRANGER),
            Some(&format!("forged-{n}")),
        )
        .await;
        assert_withheld(&body, "invented session");
    }
    // The address is now locked: even the trusted till learns nobody from it.
    let body = context(&hub.router, client, Some(TILL), None).await;
    assert_withheld(&body, "address locked by invented sessions");
}

#[tokio::test]
async fn with_trust_disarmed_the_pin_is_open_and_so_are_the_faces() {
    let hub = hub(false, false).await;
    let body = context(&hub.router, "198.51.100.7", None, None).await;
    assert_disclosed(&body, "HUB_DEVICE_TRUST=off");
}

#[tokio::test]
async fn a_virgin_demo_shows_its_pinpad_to_the_first_device() {
    let hub = hub(true, true).await;
    let body = context(&hub.router, "198.51.100.8", Some("dev_demo-visitor"), None).await;
    assert_disclosed(&body, "first device of a virgin demo");
    // Adoption adopts a device, it does not invent one.
    let body = context(&hub.router, "198.51.100.8", None, None).await;
    assert_withheld(&body, "demo caller without a device");
}
