//! E2E — the manager-approval door is held by the same per-address guard as the sign-in doors
//! (hub#2517).
//!
//! `POST /api/elevation/approve` checks a manager's PIN (or badge) like the pinpad does, but it
//! only knew the per-NAME lock: whoever stands at a till could rotate the approver's name and try
//! five PINs per name every five minutes, or swipe invented card numbers that each started a
//! counter of their own. What these tests pin, from the outside and through the real router:
//!
//! - wrong PINs and unknown badges at the approval dialog count against the client address, and
//!   once it reaches `MAX_GUESSES` the dialog answers `429 too_many_attempts` — even to the RIGHT
//!   PIN of a name that was never tried — and so does the pinpad (it is one guard);
//! - an address the pinpad already locked cannot keep guessing through the approval dialog;
//! - another address is never touched;
//! - a card counts against the SAME per-card counter at both doors (its index), so the five
//!   swipes the pinpad refused keep it locked at the approval dialog;
//! - every refused approval leaves the stable `event=auth_failed` line the edge bans on.
use std::path::PathBuf;
use std::sync::{Arc, Mutex, OnceLock};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::address_guard::MAX_GUESSES;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// Sofía's card: a manager who can approve the till's payment.
const SOFIA_BADGE: &str = "04A1B2C3D4";

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

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// The till fixture, a manager (Sofía, PIN and card) who can approve the payment and an employee,
/// in `Dev` auth mode: the cashier asking for the approval comes from the headers.
async fn fixture() -> axum::Router {
    sink();
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_elevation"),
    )
    .await
    .unwrap();
    let sofia = rt
        .create_user("Sofía", "8317", "manager", None)
        .await
        .unwrap();
    rt.set_user_badge(&sofia, SOFIA_BADGE).await.unwrap();
    rt.create_user("Nacho", "4692", "employee", None)
        .await
        .unwrap();
    // The device gate is disarmed: what is under test is the address guard, which the pinpad
    // checks BEFORE it, and an untrusted-device refusal would hide it.
    let cfg = HubConfig {
        device_trust_enforce: false,
        ..HubConfig::from_env_with_auth(AuthMode::Dev)
    };
    app(AppState::with_config(rt, cfg))
}

/// What Traefik sends: whatever the caller wrote, then the peer it actually saw.
fn forwarded(client: &str) -> String {
    format!("10.9.9.9, {client}")
}

fn approve(client: &str, credential: Value) -> Request<Body> {
    let mut body = json!({
        "command": "till.sale.take_payment",
        "payload": { "label": "table 4" }
    });
    for (k, v) in credential.as_object().unwrap() {
        body[k] = v.clone();
    }
    Request::builder()
        .method("POST")
        .uri("/api/elevation/approve")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u-cashier")
        .header("x-permissions", "till.view_sale,till.add_sale")
        .header("x-forwarded-for", forwarded(client))
        .body(Body::from(body.to_string()))
        .unwrap()
}

fn approve_with_pin(client: &str, approver: &str, pin: &str) -> Request<Body> {
    approve(client, json!({ "approver": approver, "pin": pin }))
}

fn approve_with_badge(client: &str, badge: &str) -> Request<Body> {
    approve(client, json!({ "badge": badge }))
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

fn badge_login(client: &str, badge: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/badge")
        .header("content-type", "application/json")
        .header("x-forwarded-for", forwarded(client))
        .body(Body::from(json!({ "badge": badge }).to_string()))
        .unwrap()
}

/// The lock the dialog shows: `429 too_many_attempts` with the seconds left — the same code the
/// shell's approval dialog already turns into «wait {minutes} minutes» (`elevationRefusal`).
async fn assert_locked(resp: axum::response::Response, what: &str) {
    assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS, "{what}");
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(false), "{what}: {body}");
    assert_eq!(body["error"]["code"], json!("too_many_attempts"), "{what}");
    assert!(
        body["error"]["retry_after_secs"]
            .as_u64()
            .is_some_and(|s| s > 0),
        "{what}: the lock has to name the wait: {body}"
    );
}

/// Rotating the approver's NAME no longer escapes: each name stays under its own five, the address
/// does not, and then not even Sofía's right PIN approves from there — nor does the pinpad open.
#[tokio::test]
async fn hub2517_rotating_names_at_the_approval_dialog_locks_the_address() {
    let app = fixture().await;
    let client = "198.51.100.17";

    for i in 0..MAX_GUESSES {
        let resp = app
            .clone()
            .oneshot(approve_with_pin(client, &format!("Person {i}"), "0000"))
            .await
            .unwrap();
        assert_eq!(
            body_json(resp).await["error"]["code"],
            json!("hub.elevation.rejected"),
            "guess {i} is a plain wrong PIN, no lock yet"
        );
    }

    let resp = app
        .clone()
        .oneshot(approve_with_pin(client, "Sofía", "8317"))
        .await
        .unwrap();
    assert_locked(resp, "the right PIN, from the address that guessed").await;

    // One guard for every PIN door: the pinpad is closed to that address as well (in the sign-in
    // doors' own envelope, with the code at the top level).
    let resp = app
        .clone()
        .oneshot(pin_login(client, "Nacho", "4692"))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS, "the pinpad");
    assert_eq!(
        body_json(resp).await["code"],
        json!("too_many_attempts"),
        "the pinpad, from the address that guessed"
    );

    // Another till, another address: untouched.
    let resp = app
        .oneshot(approve_with_pin("198.51.100.99", "Sofía", "8317"))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "another address still approves"
    );

    let lines = failure_lines(client);
    assert_eq!(
        lines.len(),
        MAX_GUESSES as usize,
        "one auth_failed line per refused approval: {lines:#?}"
    );
    assert!(lines.iter().all(|l| l.contains("reason=pin")), "{lines:#?}");
}

/// Swiping invented card numbers at the dialog spends the same address budget.
#[tokio::test]
async fn hub2517_unknown_badges_at_the_approval_dialog_lock_the_address() {
    let app = fixture().await;
    let client = "198.51.100.18";

    for i in 0..MAX_GUESSES {
        let resp = app
            .clone()
            .oneshot(approve_with_badge(client, &format!("FFFF{i:06}")))
            .await
            .unwrap();
        assert_eq!(
            body_json(resp).await["error"]["code"],
            json!("hub.elevation.rejected"),
            "swipe {i} is a card nobody carries, no lock yet"
        );
    }

    let resp = app
        .clone()
        .oneshot(approve_with_badge(client, SOFIA_BADGE))
        .await
        .unwrap();
    assert_locked(resp, "the right card, from the address that guessed").await;

    let lines = failure_lines(client);
    assert_eq!(lines.len(), MAX_GUESSES as usize, "{lines:#?}");
    assert!(
        lines.iter().all(|l| l.contains("reason=badge")),
        "{lines:#?}"
    );
}

/// An address the pinpad locked cannot move over to the approval dialog and keep guessing there.
#[tokio::test]
async fn hub2517_an_address_locked_at_the_pinpad_is_locked_at_the_approval_dialog() {
    let app = fixture().await;
    let client = "198.51.100.19";

    for i in 0..MAX_GUESSES {
        let resp = app
            .clone()
            .oneshot(pin_login(client, &format!("Person {i}"), "0000"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "guess {i}");
    }

    let resp = app
        .clone()
        .oneshot(approve_with_pin(client, "Sofía", "8317"))
        .await
        .unwrap();
    assert_locked(resp, "approval with a PIN from a locked address").await;

    let resp = app
        .oneshot(approve_with_badge(client, SOFIA_BADGE))
        .await
        .unwrap();
    assert_locked(resp, "approval with a badge from a locked address").await;
}

/// One card, one counter: the five swipes the pinpad refused hold at the approval dialog too,
/// whatever address they come from. Before hub#2517 the dialog counted the number as read and
/// the pinpad its index, so the same card had two budgets.
#[tokio::test]
async fn hub2517_a_card_locked_at_the_pinpad_is_locked_at_the_approval_dialog() {
    let app = fixture().await;
    // A card nobody carries, written as the label reads and as a reader sends it: one card.
    let card = "0badc0de77";

    for i in 0..5 {
        let resp = app
            .clone()
            .oneshot(badge_login(&format!("198.51.100.{}", 30 + i), card))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "swipe {i}");
    }

    let resp = app
        .oneshot(approve_with_badge(
            "198.51.100.40",
            &card.to_ascii_uppercase(),
        ))
        .await
        .unwrap();
    assert_locked(resp, "the same card at the approval dialog").await;
}

/// Tapping the wrong person is a mistake anybody makes, and it is not a guess at a PIN: twenty
/// honest refusals of someone who cannot approve leave the address budget untouched, so the till
/// is not locked out of its own approvals — nor its pinpad — for using the dialog (HUB-F135: «elegir
/// a una persona que no puede aprobarlo no cuenta como fallo»).
#[tokio::test]
async fn hub2517_tapping_someone_who_cannot_approve_never_spends_the_address_budget() {
    let app = fixture().await;
    let client = "198.51.100.21";

    // Nacho's PIN is RIGHT; he just cannot approve a payment.
    for i in 0..MAX_GUESSES {
        let resp = app
            .clone()
            .oneshot(approve_with_pin(client, "Nacho", "4692"))
            .await
            .unwrap();
        assert_eq!(
            body_json(resp).await["error"]["code"],
            json!("hub.elevation.approver_cannot"),
            "refusal {i} is about the person, not the digits"
        );
    }

    let resp = app
        .clone()
        .oneshot(approve_with_pin(client, "Sofía", "8317"))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "the right manager still approves from that address"
    );

    let resp = app
        .oneshot(pin_login(client, "Nacho", "4692"))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "and the pinpad is still open"
    );

    let lines = failure_lines(client);
    assert!(
        lines.is_empty(),
        "no auth_failed line for a refusal that is not a guess: {lines:#?}"
    );
}
