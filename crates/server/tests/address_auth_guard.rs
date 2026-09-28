//! E2E — the hub counts failed sign-ins per client address (hub#2282).
//!
//! Since infra#335 the edge no longer bans on 401s (it banned shops whose till retried a dead
//! session, infra#334), so the hub has to hold the line itself. What these tests pin, from the
//! outside and through the real router:
//!
//! - rotating NAMES does not escape the lock: the address is locked after `MAX_GUESSES` wrong
//!   PINs/badges, even for the right PIN of a user it never tried;
//! - inventing sessions counts too — through each of the three credentials that skip the edge
//!   bouncer (`X-Hub-Session`, the `erplora_media` cookie and an `/api/events` ticket) — and a
//!   locked address cannot then start guessing PINs;
//! - a till repeating its ONE dead session (the infra#334 shape) never locks anybody;
//! - whoever already holds a session keeps working, and other addresses are never touched;
//! - the address is the proxy's hop, not one the caller wrote;
//! - every failure leaves the stable `event=auth_failed` line a watcher can alert or ban on.
use std::sync::{Arc, Mutex, OnceLock};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::address_guard::{MAX_FORGED_SESSIONS, MAX_GUESSES};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-addr";

#[derive(Clone, Default)]
struct Sink(Arc<Mutex<Vec<u8>>>);

impl std::io::Write for Sink {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0
            .lock()
            .map_err(|_| std::io::Error::other("poisoned log sink"))?
            .extend_from_slice(buf);
        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for Sink {
    type Writer = Self;

    fn make_writer(&'a self) -> Self::Writer {
        self.clone()
    }
}

/// One global capture for this binary: `tracing` caches callsite interest process-wide
/// (hub#1796). Each test uses its own client address and only reads the lines that name it.
fn sink() -> &'static Sink {
    static SINK: OnceLock<Sink> = OnceLock::new();
    SINK.get_or_init(|| {
        let sink = Sink::default();
        let subscriber = tracing_subscriber::fmt()
            .with_writer(sink.clone())
            .with_ansi(false)
            .with_max_level(tracing::Level::TRACE)
            .finish();
        tracing::subscriber::set_global_default(subscriber)
            .expect("this test binary installs the only global subscriber");
        sink
    })
}

fn failure_lines(client: &str) -> Vec<String> {
    let text = String::from_utf8_lossy(&sink().0.lock().unwrap()).to_string();
    text.lines()
        .filter(|l| l.contains("event=auth_failed") && l.contains(&format!("client={client}")))
        .map(str::to_owned)
        .collect()
}

async fn fixture() -> axum::Router {
    sink();
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-addr-guard-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
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
    app(AppState::with_config(rt, cfg))
}

/// What Traefik sends: whatever the caller wrote, then the peer it actually saw.
fn forwarded(client: &str) -> String {
    format!("10.9.9.9, {client}")
}

fn pin_login(client: &str, name: &str, pin: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/pin")
        .header("content-type", "application/json")
        .header("x-forwarded-for", forwarded(client))
        .body(Body::from(json!({ "name": name, "pin": pin }).to_string()))
        .unwrap()
}

fn profile_with_session(client: &str, token: &str) -> Request<Body> {
    Request::builder()
        .uri("/api/profile")
        .header("x-hub-session", token)
        .header("x-forwarded-for", forwarded(client))
        .body(Body::empty())
        .unwrap()
}

fn media_with_cookie(client: &str, token: &str) -> Request<Body> {
    Request::builder()
        .uri("/api/media/raw?path=logo.png")
        .header("cookie", format!("erplora_media={token}"))
        .header("x-forwarded-for", forwarded(client))
        .body(Body::empty())
        .unwrap()
}

fn events_with_ticket(client: &str, ticket: &str) -> Request<Body> {
    Request::builder()
        .uri(format!("/api/events?ticket={ticket}"))
        .header("x-forwarded-for", forwarded(client))
        .body(Body::empty())
        .unwrap()
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

async fn send(router: &axum::Router, req: Request<Body>) -> (StatusCode, Value) {
    let resp = router.clone().oneshot(req).await.unwrap();
    let status = resp.status();
    (status, body_json(resp).await)
}

/// The right PIN from `client` must now wait: the lock holds before anything is verified.
async fn assert_locked(router: &axum::Router, client: &str) {
    let (status, body) = send(router, pin_login(client, "Admin", "1111")).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS, "{client}: {body}");
    assert_eq!(body["code"], json!("too_many_attempts"), "{body}");
    assert!(body["retry_after_secs"].as_u64().unwrap_or(0) > 0, "{body}");
}

async fn assert_signs_in(router: &axum::Router, client: &str) -> String {
    let (status, body) = send(router, pin_login(client, "Admin", "1111")).await;
    assert_eq!(status, StatusCode::OK, "{client}: {body}");
    body["token"].as_str().expect("a session token").to_string()
}

#[tokio::test]
async fn rotating_names_does_not_escape_the_address_lock() {
    let router = fixture().await;
    let attacker = "198.51.100.10";
    // Never five on the same name, so the per-name lock never fires: only the address can see it.
    for i in 0..MAX_GUESSES {
        let (status, _) = send(&router, pin_login(attacker, &format!("guess-{}", i % 7), "0000")).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED, "guess {i}");
    }
    assert_locked(&router, attacker).await;
    // Writing a new first hop does not buy a fresh counter: the proxy's hop is the same.
    let spoofed = Request::builder()
        .method("POST")
        .uri("/api/auth/pin")
        .header("content-type", "application/json")
        .header("x-forwarded-for", format!("1.1.1.1, {attacker}"))
        .body(Body::from(json!({ "name": "Admin", "pin": "1111" }).to_string()))
        .unwrap();
    assert_eq!(send(&router, spoofed).await.0, StatusCode::TOO_MANY_REQUESTS);
    // Another address is untouched.
    assert_signs_in(&router, "198.51.100.11").await;
}

#[tokio::test]
async fn one_short_of_the_limit_still_signs_in() {
    let router = fixture().await;
    let shop = "198.51.100.20";
    for i in 0..MAX_GUESSES - 1 {
        send(&router, pin_login(shop, &format!("typo-{}", i % 7), "0000")).await;
    }
    assert_signs_in(&router, shop).await;
}

#[tokio::test]
async fn an_open_session_keeps_working_while_its_address_is_locked() {
    let router = fixture().await;
    let shop = "198.51.100.30";
    let token = assert_signs_in(&router, shop).await;
    for i in 0..MAX_GUESSES {
        send(&router, pin_login(shop, &format!("guess-{}", i % 7), "0000")).await;
    }
    assert_locked(&router, shop).await;
    let (status, body) = send(&router, profile_with_session(shop, &token)).await;
    assert_eq!(status, StatusCode::OK, "the signed-in till is never touched: {body}");
}

#[tokio::test]
async fn invented_sessions_lock_the_address_out_of_the_pin_door() {
    let router = fixture().await;
    let attacker = "198.51.100.40";
    for i in 0..MAX_FORGED_SESSIONS {
        let (status, _) = send(&router, profile_with_session(attacker, &format!("forged-{i:060}"))).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED, "a forged session is still a plain 401");
    }
    assert_locked(&router, attacker).await;
    assert_signs_in(&router, "198.51.100.41").await;
}

#[tokio::test]
async fn invented_media_cookies_count_like_sessions() {
    let router = fixture().await;
    let attacker = "198.51.100.50";
    for i in 0..MAX_FORGED_SESSIONS {
        let (status, _) = send(&router, media_with_cookie(attacker, &format!("cookie-{i}"))).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
    }
    assert_locked(&router, attacker).await;
}

#[tokio::test]
async fn invented_event_tickets_count_like_sessions() {
    let router = fixture().await;
    let attacker = "198.51.100.60";
    for i in 0..MAX_FORGED_SESSIONS {
        let (status, _) = send(&router, events_with_ticket(attacker, &format!("evt_forged{i}"))).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
    }
    assert_locked(&router, attacker).await;
}

/// infra#334: a till retrying its one dead session all day long is not an attack.
#[tokio::test]
async fn a_till_repeating_its_dead_session_never_locks_the_shop() {
    let router = fixture().await;
    let shop = "198.51.100.70";
    for _ in 0..(MAX_FORGED_SESSIONS * 5) {
        send(&router, profile_with_session(shop, "dead-session-of-the-till")).await;
        send(&router, media_with_cookie(shop, "dead-session-of-the-till")).await;
        send(&router, events_with_ticket(shop, "evt_used_ticket")).await;
    }
    assert_signs_in(&router, shop).await;
}

#[tokio::test]
async fn every_failure_leaves_a_stable_log_line() {
    let router = fixture().await;
    let client = "198.51.100.80";
    send(&router, pin_login(client, "Admin", "0000")).await;
    send(&router, profile_with_session(client, "forged-token")).await;
    send(&router, events_with_ticket(client, "evt_forged")).await;
    let lines = failure_lines(client);
    for reason in ["pin", "session_invalid", "ticket_invalid"] {
        assert!(
            lines
                .iter()
                .any(|l| l.contains(&format!("reason={reason}")) && l.contains(&format!("hub={HUB_ID}"))),
            "no auth_failed line with reason={reason}: {lines:#?}"
        );
    }
    // A successful sign-in is not a failure.
    let before = failure_lines(client).len();
    assert_signs_in(&router, client).await;
    assert_eq!(failure_lines(client).len(), before);
}

#[tokio::test]
async fn wrong_badges_count_towards_the_same_lock() {
    let router = fixture().await;
    let attacker = "198.51.100.90";
    for i in 0..MAX_GUESSES {
        let req = Request::builder()
            .method("POST")
            .uri("/api/auth/badge")
            .header("content-type", "application/json")
            .header("x-forwarded-for", forwarded(attacker))
            .body(Body::from(json!({ "badge": format!("card-{i}") }).to_string()))
            .unwrap();
        let (status, body) = send(&router, req).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED, "{body}");
    }
    assert_locked(&router, attacker).await;
    // And the badge door holds the lock too.
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/badge")
        .header("content-type", "application/json")
        .header("x-forwarded-for", forwarded(attacker))
        .body(Body::from(json!({ "badge": "card-x" }).to_string()))
        .unwrap();
    assert_eq!(send(&router, req).await.0, StatusCode::TOO_MANY_REQUESTS);
}
