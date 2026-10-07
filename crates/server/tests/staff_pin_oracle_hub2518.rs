//! hub#2518 — **Empleados** was a PIN oracle with no brake. PINs are unique among active people
//! (hub#355), so creating a person (`POST /api/hub/users`) or editing their record
//! (`PUT /api/hub/users/{id}`) with a number somebody already holds answers `pin_in_use`. Whoever
//! manages the staff could type number after number into any record —a throwaway employee will do—
//! until the refusal named a taken PIN, the account owner's included (whose own record they cannot
//! touch), and then sign in at the till by picking the owner's name on the pinpad.
//!
//! These doors now spend the same per-person budget as changing one's own PIN (hub#2499):
//! [`PIN_CHANGE_MAX_ATTEMPTS`] tries per hour ([`erplora_server::login_throttle`], hub#2564),
//! counted against the EDITOR, every try a PIN travels in, the accepted ones too (an accepted
//! number is stored and the prober carries on with the next). One budget per person across all
//! three doors: a separate one per door would just multiply the tries. What this file locks down:
//!
//!  - once spent, the door answers `429 too_many_attempts` BEFORE looking at the digits, so a taken
//!    PIN no longer says `pin_in_use`, and nothing is written;
//!  - refusals spend it like acceptances;
//!  - creating people spends it as editing them does;
//!  - the lock is the editor's: another administrator still sets that same record's PIN;
//!  - edits that carry no PIN (name, role, deactivation) spend nothing and are not locked;
//!  - the budget is shared with the own-PIN change of «Mi perfil»;
//!  - and it is big enough for a whole staff set up in one sitting (hub#2564).
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::hub_users::NewHubUser;
use erplora_runtime::Runtime;
use erplora_server::login_throttle::{LoginThrottle, MAX_FAILURES, PIN_CHANGE_MAX_ATTEMPTS};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::sync::Arc;
use tower::ServiceExt;

const OWNER_PIN: &str = "4917";
const DUMMY: &str = "Pau Gil";
const DUMMY_PIN: &str = "1379";
/// The budget of tries, as a count.
const BUDGET: usize = PIN_CHANGE_MAX_ATTEMPTS as usize;

/// Free, non-guessable PINs the prober rotates through; one more than the budget. Steps of 41 from
/// 2000 never land on a repeated digit or a run (1234), nor on the fixture's PINs.
fn free_pins() -> Vec<String> {
    (0..=BUDGET)
        .map(|i| format!("{:04}", 2000 + 41 * i))
        .collect()
}

struct Fixture {
    router: axum::Router,
    /// The account owner, holding [`OWNER_PIN`] — the PIN worth stealing.
    owner_session: String,
    /// A second administrator: manages the staff, cannot touch the owner's record.
    prober_session: String,
    /// A local employee whose record the prober types numbers into.
    dummy_id: String,
    /// The budget of PIN tries every door of hub#2499/#2518 spends (`pin_change_throttle`).
    throttle: Arc<LoginThrottle>,
    /// The prober's id: the key those doors spend the prober's tries under.
    prober_id: String,
}

impl Fixture {
    /// The tries the prober already spent before the ones a test watches, spent straight into the
    /// budget under the same key the doors use. Each try through a door costs several argon2
    /// hashes in a debug build, and with a budget of thirty, spending all of it over HTTP cost the
    /// CI suite minutes (hub#2564). The tries that decide —the last ones and the one past the
    /// budget— always go through the doors.
    fn spent(&self, n: usize) {
        for _ in 0..n {
            self.throttle.record_attempt(&self.prober_id);
        }
    }
}

async fn fixture(hub_id: &str) -> Fixture {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();

    assert!(rt.seed_owner("ioan@example.com").await.unwrap());
    let owner = rt
        .get_or_link_cloud_user(
            "cloud-1",
            "Ioan Beilic",
            "admin",
            Some("ioan@example.com"),
            None,
        )
        .await
        .unwrap();
    rt.set_pin(&owner.id, None, OWNER_PIN).await.unwrap();
    let prober = rt
        .create_hub_user(
            &NewHubUser {
                name: "Ana Soto".into(),
                email: "ana@example.com".into(),
                role: "admin".into(),
                ..NewHubUser::default()
            },
            0,
        )
        .await
        .unwrap();
    let dummy = rt
        .create_user(DUMMY, DUMMY_PIN, "employee", None)
        .await
        .unwrap();

    let owner_session = rt.create_session(&owner.id, 3600, None).await.unwrap();
    let prober_session = rt.create_session(&prober, 3600, None).await.unwrap();

    let media = std::env::temp_dir().join(format!("erplora-{hub_id}-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        // Unreachable on purpose: none of these edits needs the SaaS (local people, PIN only).
        cloud_base_url: "https://example.invalid".into(),
        module_cache: media.join("modules"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: media,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let state = AppState::with_config(rt, cfg);
    let throttle = state.pin_change_throttle.clone();
    Fixture {
        router: app(state),
        owner_session,
        prober_session,
        dummy_id: dummy,
        throttle,
        prober_id: prober,
    }
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

async fn send(
    router: &axum::Router,
    method: &str,
    uri: &str,
    session: Option<&str>,
    payload: Value,
) -> (StatusCode, Value) {
    let mut builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("content-type", "application/json");
    if let Some(session) = session {
        builder = builder.header("x-hub-session", session);
    }
    let response = router
        .clone()
        .oneshot(builder.body(Body::from(payload.to_string())).unwrap())
        .await
        .unwrap();
    let status = response.status();
    (status, body_json(response).await)
}

async fn edit(fx: &Fixture, session: &str, payload: Value) -> (StatusCode, Value) {
    let uri = format!("/api/hub/users/{}", fx.dummy_id);
    send(&fx.router, "PUT", &uri, Some(session), payload).await
}

async fn create_local(fx: &Fixture, name: &str, pin: &str) -> (StatusCode, Value) {
    let payload = json!({ "name": name, "role": "employee", "pin": pin, "local": true });
    send(&fx.router, "POST", "/api/hub/users", Some(&fx.prober_session), payload).await
}

/// Does `name` + `pin` open a session at the pinpad? The ground truth of what was written.
async fn pin_opens(fx: &Fixture, name: &str, pin: &str) -> bool {
    let payload = json!({ "name": name, "pin": pin });
    let (status, _) = send(&fx.router, "POST", "/api/auth/pin", None, payload).await;
    status == StatusCode::OK
}

fn assert_locked(status: StatusCode, body: &Value) {
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS, "{body}");
    assert_eq!(body["code"], "too_many_attempts", "{body}");
    assert!(
        body["retry_after_secs"].as_u64().is_some_and(|s| s > 0),
        "the refusal says how long to wait: {body}"
    );
    assert!(
        !body.to_string().contains("pin_in_use"),
        "a locked editor learns nothing about the digits: {body}"
    );
}

#[tokio::test]
async fn probing_a_record_is_braked_before_the_owners_pin_is_named() {
    let fx = fixture("hub-2518-probe").await;
    let budget = BUDGET;
    let free_pins = free_pins();

    fx.spent(budget - 2);
    for pin in &free_pins[budget - 2..budget] {
        let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": pin })).await;
        assert_eq!(status, StatusCode::OK, "a free PIN is accepted: {body}");
    }

    // The owner's PIN, one try past the budget: no `pin_in_use`, and nothing written.
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": OWNER_PIN })).await;
    assert_locked(status, &body);
    assert!(
        pin_opens(&fx, DUMMY, &free_pins[budget - 1]).await,
        "the refused edit left the record's PIN as it was"
    );
}

#[tokio::test]
async fn refusals_spend_the_budget_too() {
    let fx = fixture("hub-2518-refusals").await;

    fx.spent(BUDGET - 2);
    for _ in 0..2 {
        let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": OWNER_PIN })).await;
        assert_eq!(status, StatusCode::CONFLICT, "{body}");
        assert_eq!(body["error"]["code"], "hub.users.pin_in_use", "{body}");
    }
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": OWNER_PIN })).await;
    assert_locked(status, &body);
}

#[tokio::test]
async fn creating_people_spends_the_same_budget() {
    let fx = fixture("hub-2518-create").await;
    let budget = BUDGET;
    let free_pins = free_pins();

    fx.spent(budget - 2);
    for (i, pin) in free_pins[budget - 2..budget].iter().enumerate() {
        let (status, body) = create_local(&fx, &format!("Probe {i}"), pin).await;
        assert_eq!(status, StatusCode::OK, "{body}");
    }
    let (status, body) = create_local(&fx, "Probe last", OWNER_PIN).await;
    assert_locked(status, &body);

    let (_, list) = send(&fx.router, "GET", "/api/hub/users", Some(&fx.owner_session), json!({})).await;
    assert!(
        !list.to_string().contains("Probe last"),
        "the locked alta wrote nobody: {list}"
    );

    // And the two doors share it: editing a record is locked as well.
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": free_pins[budget] })).await;
    assert_locked(status, &body);
}

#[tokio::test]
async fn the_lock_is_the_editors_not_the_records() {
    let fx = fixture("hub-2518-whose").await;
    let budget = BUDGET;
    let free_pins = free_pins();

    fx.spent(budget - 1);
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": free_pins[0] })).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": free_pins[budget] })).await;
    assert_locked(status, &body);

    // The owner sets that same record's PIN: their budget is untouched.
    let (status, body) = edit(&fx, &fx.owner_session, json!({ "pin": free_pins[budget] })).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert!(pin_opens(&fx, DUMMY, &free_pins[budget]).await);
}

#[tokio::test]
async fn edits_that_carry_no_pin_spend_nothing_and_are_never_locked() {
    let fx = fixture("hub-2518-no-pin").await;
    let budget = BUDGET;
    let free_pins = free_pins();

    // Twice the budget in renames: none of them is a try.
    for i in 0..(2 * budget) {
        let (status, body) = edit(&fx, &fx.prober_session, json!({ "name": format!("Pau {i}") })).await;
        assert_eq!(status, StatusCode::OK, "{body}");
    }
    // The whole PIN budget is still there: all but its last try spent, the last one is answered.
    fx.spent(budget - 1);
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": free_pins[0] })).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    // Locked for PINs now, yet a rename still goes through.
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": free_pins[budget] })).await;
    assert_locked(status, &body);
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "name": DUMMY })).await;
    assert_eq!(status, StatusCode::OK, "{body}");
}

#[tokio::test]
async fn the_budget_is_shared_with_changing_ones_own_pin() {
    let fx = fixture("hub-2518-shared").await;
    let budget = BUDGET;
    let free_pins = free_pins();

    // One try at «Mi perfil» (the prober has no PIN yet, so no current one is asked)…
    let (status, body) = send(
        &fx.router,
        "POST",
        "/api/auth/set-pin",
        Some(&fx.prober_session),
        json!({ "pin": free_pins[0] }),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    // …leaves the rest for Empleados.
    fx.spent(budget - 2);
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": free_pins[1] })).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let (status, body) = edit(&fx, &fx.prober_session, json!({ "pin": OWNER_PIN })).await;
    assert_locked(status, &body);

    // And «Mi perfil» is locked by what was spent in Empleados.
    let (status, body) = send(
        &fx.router,
        "POST",
        "/api/auth/set-pin",
        Some(&fx.prober_session),
        json!({ "pin": OWNER_PIN, "current_pin": free_pins[0] }),
    )
    .await;
    assert_locked(status, &body);
}

/// hub#2564 — the brake must not tax the very first thing the app asks of a new owner: setting up
/// the whole staff in one sitting, each person with their own PIN. The alta past the pinpad's
/// budget (the sixth, where it used to stop) goes through without a «wait»; that the budget holds
/// a whole staff is the unit test of [`LoginThrottle::pin_change`].
#[tokio::test]
async fn a_whole_staff_is_set_up_in_one_sitting_without_waiting() {
    let fx = fixture("hub-2564-onboarding").await;

    for (i, pin) in free_pins()
        .iter()
        .take(MAX_FAILURES as usize + 1)
        .enumerate()
    {
        let (status, body) = create_local(&fx, &format!("Staff {i}"), pin).await;
        assert_eq!(
            status,
            StatusCode::OK,
            "alta #{} with PIN {pin}: {body}",
            i + 1
        );
    }
}
