//! HTTP contract of **the devices door** (hub#455): `GET /api/devices` + `DELETE /api/devices/:id`.
//!
//! This is the gesture "somebody walked off with the tablet". Until now it did not exist: the
//! runtime could revoke a device and nothing in the product could ask it to, so a tablet marked
//! `personal` kept a session alive for **thirty days** with no pinpad in front of it.
//!
//! A door that disconnects devices is a door that takes tills down, so most of this file is about
//! who cannot open it. The gate is the **admin session** — the same one as `/api/settings`, the API
//! keys, the role catalogue and `PUT /api/device/mode` — which is exactly the set of roles the core
//! grants `hub.administer` to (ADR-0248, hub#435). It is not a new permission and a module manifest
//! cannot mint it (`identity::permissions_for_role` refuses the `hub.` namespace; there is a test).
//!
//! The read is **not** public, and that is a deliberate departure from its neighbour
//! `GET /api/device/mode`: that one has to answer the login screen, before any session exists, and
//! it only ever says one word about the id presented. This one enumerates every device of the
//! business with when it was last used — a shopping list for whoever is holding a stolen one.
//! hub#454 is the cautionary tale: `GET /api/hub/context` needed no session and published the value
//! that was, at the time, every browser's device id (ADR-0257).
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::device_mode::DeviceMode;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

type Response = axum::response::Response;

async fn body_json(response: Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// Sessions a fixture hands back: who is signed in, and on which device.
struct Sessions {
    admin: String,
    employee: String,
    /// The admin's session, opened on `laptop-1` — the one that revoking `laptop-1` cuts off.
    admin_on_laptop: String,
}

/// A business with a counter till and an office laptop, both trusted as an online login would have
/// left them; the laptop is `personal`, the lax mode this issue is about.
async fn fixture(hub_id: &str) -> (axum::Router, Sessions) {
    let (router, sessions, _state) = fixture_with_state(hub_id).await;
    (router, sessions)
}

/// The same business, keeping the `AppState` so a test can reach the runtime behind the router.
async fn fixture_with_state(hub_id: &str) -> (axum::Router, Sessions, AppState) {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    rt.set_device_mode("laptop-1", DeviceMode::Personal, &admin_id)
        .await
        .unwrap();
    let sessions = Sessions {
        admin: rt.create_session(&admin_id, 3600, None).await.unwrap(),
        employee: rt
            .create_session(&employee_id, 3600, Some("till-1"))
            .await
            .unwrap(),
        admin_on_laptop: rt
            .create_session(&admin_id, 3600, Some("laptop-1"))
            .await
            .unwrap(),
    };

    let temp =
        std::env::temp_dir().join(format!("erplora-devices-{}-{}", hub_id, std::process::id()));
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
    (app(state.clone()), sessions, state)
}

/// A request with whatever the caller decided to present. `claims` are extra headers — the shape a
/// client uses to declare who it is when nobody is checking.
async fn call(
    router: &axum::Router,
    method: &str,
    uri: &str,
    session: Option<&str>,
    claims: &[(&str, &str)],
) -> Response {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    for (name, value) in claims {
        builder = builder.header(*name, *value);
    }
    router
        .clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

/// The device ids the hub lists for this caller (asserting the read itself succeeded).
async fn listed_ids(router: &axum::Router, session: &str) -> Vec<String> {
    let response = call(router, "GET", "/api/devices", Some(session), &[]).await;
    assert_eq!(response.status(), StatusCode::OK);
    body_json(response).await["data"]["devices"]
        .as_array()
        .expect("a list of devices")
        .iter()
        .map(|d| d["device_id"].as_str().unwrap_or_default().to_string())
        .collect()
}

// ── The guards, first ────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn without_a_session_the_devices_of_a_business_are_not_readable() {
    let (router, _s) = fixture("hub-455").await;

    let response = call(&router, "GET", "/api/devices", None, &[]).await;

    assert_eq!(
        response.status(),
        StatusCode::UNAUTHORIZED,
        "unlike GET /api/device/mode, this enumerates the business: a list of every device with \
         when it was last used is a shopping list for whoever holds a stolen one (ADR-0257)"
    );
}

#[tokio::test]
async fn without_a_session_nothing_can_be_disconnected() {
    let (router, sessions) = fixture("hub-455").await;

    let response = call(&router, "DELETE", "/api/devices/till-1", None, &[]).await;

    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    // And it did not happen anyway: an endpoint that disconnects devices is an endpoint that takes
    // tills down, so "refused" has to mean the till is still working.
    assert!(listed_ids(&router, &sessions.admin)
        .await
        .contains(&"till-1".to_string()));
}

#[tokio::test]
async fn an_employee_can_neither_see_the_devices_nor_disconnect_one() {
    let (router, sessions) = fixture("hub-455").await;

    let read = call(
        &router,
        "GET",
        "/api/devices",
        Some(&sessions.employee),
        &[],
    )
    .await;
    let write = call(
        &router,
        "DELETE",
        "/api/devices/laptop-1",
        Some(&sessions.employee),
        &[],
    )
    .await;

    // Same gate as settings, API keys and the role catalogue (ADR-0248): who administers the
    // business, not whoever happens to be holding a device. Since hub#1702 the answer is `403`, not
    // `401`: the session is fine and the role is not, and signing in again as the same employee
    // would never help — the same split `api_keys.rs` got in hub#1700.
    assert_eq!(read.status(), StatusCode::FORBIDDEN);
    assert_eq!(write.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        listed_ids(&router, &sessions.admin).await.len(),
        2,
        "nothing was disconnected"
    );
}

/// The stable code of a refusal, wherever the envelope puts it.
fn refusal_code(body: &Value) -> Option<&str> {
    body["error"]["code"].as_str()
}

/// 🔴 hub#1702: a refusal of this door carries the code the screen translates. Without it, Settings →
/// Devices could only say «check the connection» to somebody whose session had simply expired.
#[tokio::test]
async fn a_refusal_names_why_an_expired_session_and_a_missing_role_apart() {
    let (router, sessions) = fixture("hub-1702").await;

    for (method, uri) in [("GET", "/api/devices"), ("DELETE", "/api/devices/till-1")] {
        let no_session = call(&router, method, uri, Some("expired-or-forged"), &[]).await;
        assert_eq!(no_session.status(), StatusCode::UNAUTHORIZED, "{method} {uri}");
        assert_eq!(
            refusal_code(&body_json(no_session).await),
            Some("unauthorized"),
            "{method} {uri}: a dead session is `unauthorized` — the screen says «sign in again»"
        );

        let wrong_role = call(&router, method, uri, Some(&sessions.employee), &[]).await;
        assert_eq!(wrong_role.status(), StatusCode::FORBIDDEN, "{method} {uri}");
        assert_eq!(
            refusal_code(&body_json(wrong_role).await),
            Some("forbidden"),
            "{method} {uri}: a valid session without the role is `forbidden` — signing in again as \
             the same person would never help"
        );
    }
}

#[tokio::test]
async fn a_caller_that_declares_itself_an_administrator_is_still_not_one() {
    let (router, sessions) = fixture("hub-455").await;
    // Everything a client can say about itself: the dev-mode identity headers and a permission list
    // with the wildcard. In `Session` mode the authority is the session row, and these are noise.
    let self_proclaimed = [
        ("x-user-id", "whoever"),
        ("x-user-role", "admin"),
        ("x-permissions", "*"),
        ("x-hub-id", "hub-455"),
    ];

    let no_session = call(
        &router,
        "DELETE",
        "/api/devices/laptop-1",
        None,
        &self_proclaimed,
    )
    .await;
    let as_employee = call(
        &router,
        "DELETE",
        "/api/devices/laptop-1",
        Some(&sessions.employee),
        &self_proclaimed,
    )
    .await;
    let reading = call(&router, "GET", "/api/devices", None, &self_proclaimed).await;

    assert_eq!(no_session.status(), StatusCode::UNAUTHORIZED);
    // A declared role is still the employee's real one: `403` (hub#1702), and nothing moved.
    assert_eq!(as_employee.status(), StatusCode::FORBIDDEN);
    assert_eq!(reading.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(listed_ids(&router, &sessions.admin).await.len(), 2);
}

#[tokio::test]
async fn a_device_of_another_business_is_not_reachable_from_here() {
    let (mine, my_sessions) = fixture("hub-455").await;
    // The neighbour is a whole running hub, ALIVE and populated while the revocation happens — a
    // test that stood it down first would pass with SQL that has no `WHERE` at all. Per ADR-0201
    // each hub owns its database; `hub_trusted_device` carries no `hub_id` column, so in the
    // pre-ADR-0201 shared-database shape this isolation is the database's and not this door's
    // (hub#489, declared, not dodged).
    let (neighbours, their_sessions) = fixture("hub-neighbour").await;

    let response = call(
        &mine,
        "DELETE",
        "/api/devices/laptop-1",
        Some(&my_sessions.admin),
        &[("x-hub-id", "hub-neighbour")],
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK, "it revoked MY laptop-1");
    assert_eq!(
        listed_ids(&mine, &my_sessions.admin).await,
        vec!["till-1".to_string()]
    );
    // The neighbour came out untouched: both devices listed and their sessions still open.
    let mut theirs = listed_ids(&neighbours, &their_sessions.admin).await;
    theirs.sort();
    assert_eq!(theirs, vec!["laptop-1".to_string(), "till-1".to_string()]);
    let still_working = call(
        &neighbours,
        "GET",
        "/api/devices",
        Some(&their_sessions.admin_on_laptop),
        &[],
    )
    .await;
    assert_eq!(
        still_working.status(),
        StatusCode::OK,
        "the session open on the neighbour's laptop is exactly as it was"
    );
}

#[tokio::test]
async fn a_request_that_names_no_device_deletes_nothing() {
    let (router, sessions) = fixture("hub-455").await;

    // `%20` is a path segment of blanks: a mis-built URL, never an instruction.
    let blank = call(
        &router,
        "DELETE",
        "/api/devices/%20",
        Some(&sessions.admin),
        &[],
    )
    .await;
    // And with no segment at all there is simply no such door.
    let nothing = call(
        &router,
        "DELETE",
        "/api/devices/",
        Some(&sessions.admin),
        &[],
    )
    .await;

    assert_eq!(blank.status(), StatusCode::UNPROCESSABLE_ENTITY);
    assert_ne!(nothing.status(), StatusCode::OK);
    assert_eq!(listed_ids(&router, &sessions.admin).await.len(), 2);
}

// ── What the door is FOR ─────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_list_says_what_lets_an_owner_point_at_the_device_they_lost() {
    let (router, sessions) = fixture("hub-455").await;

    let response = call(&router, "GET", "/api/devices", Some(&sessions.admin), &[]).await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let devices = body["data"]["devices"].as_array().unwrap();
    let laptop = devices
        .iter()
        .find(|d| d["device_id"] == "laptop-1")
        .expect("the laptop is listed");
    assert_eq!(laptop["label"], "Office laptop");
    assert_eq!(laptop["mode"], "personal");
    assert_eq!(laptop["open_sessions"], 1);
    assert!(!laptop["trusted_at"].as_str().unwrap_or_default().is_empty());
    assert!(!laptop["signed_in_until"]
        .as_str()
        .unwrap_or_default()
        .is_empty());
}

#[tokio::test]
async fn the_device_asking_is_the_one_marked_current() {
    let (router, sessions) = fixture("hub-455").await;

    let response = call(
        &router,
        "GET",
        "/api/devices",
        Some(&sessions.admin),
        &[("x-device-id", " laptop-1 ")],
    )
    .await;

    let body = body_json(response).await;
    let devices = body["data"]["devices"].as_array().unwrap();
    // The screen has to be able to say "this one is the device you are holding" before the owner
    // taps a button that signs them out. The header only NAMES it (ADR-0257); it decides nothing.
    for device in devices {
        assert_eq!(
            device["current"],
            Value::Bool(device["device_id"] == "laptop-1"),
            "{device}"
        );
    }
}

#[tokio::test]
async fn nothing_is_current_when_the_caller_names_no_device() {
    let (router, sessions) = fixture("hub-455").await;

    let response = call(&router, "GET", "/api/devices", Some(&sessions.admin), &[]).await;

    let body = body_json(response).await;
    for device in body["data"]["devices"].as_array().unwrap() {
        assert_eq!(device["current"], Value::Bool(false), "{device}");
    }
}

#[tokio::test]
async fn a_row_with_no_id_is_never_the_device_you_are_holding() {
    let (router, sessions, state) = fixture_with_state("hub-455").await;
    // A trust row keyed on the empty string is writable, and a caller that names no device also
    // presents `""`. Comparing the two would flag a row the owner is NOT holding as "the one you
    // are using" — right next to the button that signs them out.
    state
        .runtime
        .read()
        .await
        .trust_device("", "ghost")
        .await
        .unwrap();

    let response = call(&router, "GET", "/api/devices", Some(&sessions.admin), &[]).await;

    let body = body_json(response).await;
    let devices = body["data"]["devices"].as_array().unwrap();
    assert_eq!(
        devices.len(),
        3,
        "the nameless row is listed, it is just never current"
    );
    for device in devices {
        assert_eq!(device["current"], Value::Bool(false), "{device}");
    }
}

#[tokio::test]
async fn a_path_segment_with_blanks_around_a_real_id_still_names_that_device() {
    let (router, sessions) = fixture("hub-455").await;

    let response = call(
        &router,
        "DELETE",
        "/api/devices/%20laptop-1%20",
        Some(&sessions.admin),
        &[("x-device-id", "laptop-1")],
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    // Trimmed in ONE place and used everywhere: the device revoked, the id reported back and the
    // "was it the one I am holding" answer all have to be about the same device.
    assert_eq!(body["data"]["device_id"], "laptop-1");
    assert_eq!(body["data"]["was_current"], Value::Bool(true));
    assert_eq!(
        listed_ids(&router, &sessions.admin).await,
        vec!["till-1".to_string()]
    );
}

#[tokio::test]
async fn disconnecting_a_device_closes_the_session_it_had_open_right_away() {
    let (router, sessions) = fixture("hub-455").await;
    // The token was minted BEFORE the revocation and is nowhere near expiring: this is the thirty
    // days a `personal` device is worth, and the reason the screen can promise "right away".
    assert_eq!(
        call(
            &router,
            "GET",
            "/api/devices",
            Some(&sessions.admin_on_laptop),
            &[]
        )
        .await
        .status(),
        StatusCode::OK
    );

    let response = call(
        &router,
        "DELETE",
        "/api/devices/laptop-1",
        Some(&sessions.admin),
        &[],
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["data"]["was_known"], Value::Bool(true));
    assert_eq!(body["data"]["sessions_closed"], 1);
    assert_eq!(body["data"]["was_current"], Value::Bool(false));
    assert_eq!(
        call(
            &router,
            "GET",
            "/api/devices",
            Some(&sessions.admin_on_laptop),
            &[]
        )
        .await
        .status(),
        StatusCode::UNAUTHORIZED,
        "the very next request from the revoked device is already out"
    );
    // The counter till kept working: the neighbour inside the same business, alive throughout.
    assert_eq!(
        call(&router, "GET", "/api/devices", Some(&sessions.employee), &[])
            .await
            .status(),
        StatusCode::FORBIDDEN,
        "(the employee still cannot read the list — but for the role, not because they were cut off)"
    );
    assert_eq!(
        listed_ids(&router, &sessions.admin).await,
        vec!["till-1".to_string()]
    );
}

#[tokio::test]
async fn an_administrator_can_disconnect_the_device_they_are_holding_and_is_told_so() {
    let (router, sessions) = fixture("hub-455").await;

    let response = call(
        &router,
        "DELETE",
        "/api/devices/laptop-1",
        Some(&sessions.admin_on_laptop),
        &[("x-device-id", "laptop-1")],
    )
    .await;

    // Allowed: "I am holding the device I want to disconnect" is a real situation (handing a tablet
    // back, selling it), and refusing would leave the only device an owner can definitely reach as
    // the one they cannot clean. The answer says it happened so the screen can send them to the
    // login instead of leaving them tapping a dead session.
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["data"]["was_current"], Value::Bool(true));
    assert_eq!(
        call(
            &router,
            "GET",
            "/api/devices",
            Some(&sessions.admin_on_laptop),
            &[]
        )
        .await
        .status(),
        StatusCode::UNAUTHORIZED,
        "it signed itself out, which is exactly what it asked for"
    );
}

#[tokio::test]
async fn disconnecting_the_same_device_twice_is_not_an_error() {
    let (router, sessions) = fixture("hub-455").await;

    let first = call(
        &router,
        "DELETE",
        "/api/devices/laptop-1",
        Some(&sessions.admin),
        &[],
    )
    .await;
    let second = call(
        &router,
        "DELETE",
        "/api/devices/laptop-1",
        Some(&sessions.admin),
        &[],
    )
    .await;

    assert_eq!(first.status(), StatusCode::OK);
    // Two administrators reacting to the same lost tablet is the normal case; the second one must
    // not be shown a failure for a device that is already off.
    assert_eq!(second.status(), StatusCode::OK);
    let body = body_json(second).await;
    assert_eq!(body["data"]["was_known"], Value::Bool(false));
    assert_eq!(body["data"]["sessions_closed"], 0);
}

// ── Naming a device: `PUT /api/devices/:device_id` (hub#494) ─────────────────────────────────
//
// The revocation above is only as good as the owner's ability to point at the right row. Until
// this door, the one readable field was `label` — the name of the *person* who last signed in
// online, overwritten on every login and chosen by the client. Three tablets, three rows saying
// "Marta", and the gesture that cuts one off is a coin toss.

/// A request that carries a JSON body. `call` sends none, and the two shapes are worth keeping
/// apart: everything above is about doors that take no payload.
async fn call_with_body(
    router: &axum::Router,
    method: &str,
    uri: &str,
    session: Option<&str>,
    body: Value,
) -> Response {
    let mut builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("content-type", "application/json");
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    router
        .clone()
        .oneshot(builder.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap()
}

/// What the list says one device is called (`name`), asserting the read succeeded.
async fn listed_name(router: &axum::Router, session: &str, device_id: &str) -> String {
    let response = call(router, "GET", "/api/devices", Some(session), &[]).await;
    assert_eq!(response.status(), StatusCode::OK);
    body_json(response).await["data"]["devices"]
        .as_array()
        .expect("a list of devices")
        .iter()
        .find(|d| d["device_id"] == device_id)
        .unwrap_or_else(|| panic!("{device_id} is listed"))["name"]
        .as_str()
        .unwrap_or_default()
        .to_string()
}

#[tokio::test]
async fn an_administrator_can_name_a_device_and_the_list_says_so() {
    let (router, sessions) = fixture("hub-494").await;
    // Nobody has named it yet, and that is a different fact from "its name is blank": the empty
    // string is what the screen turns into "unnamed", never into a row with no title.
    assert_eq!(listed_name(&router, &sessions.admin, "till-1").await, "");

    let response = call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.admin),
        json!({ "name": "  Barra  " }),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    // Trimmed in one place and used everywhere, like the id on the revocation door.
    assert_eq!(body["data"]["name"], "Barra");
    assert_eq!(body["data"]["device_id"], "till-1");
    assert_eq!(
        listed_name(&router, &sessions.admin, "till-1").await,
        "Barra"
    );
}

#[tokio::test]
async fn the_next_online_login_does_not_touch_the_name_the_business_chose() {
    let (router, sessions, state) = fixture_with_state("hub-494").await;
    call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.admin),
        json!({ "name": "Barra" }),
    )
    .await;

    // Somebody else signs in online on that till: `trust_device` upserts, and its `DO UPDATE` is
    // the statement this whole issue turns on. It may keep rewriting `label` — that field IS "who
    // signed in last" — and it must never reach `name`, or the owner's choice lasts one shift.
    state
        .runtime
        .read()
        .await
        .trust_device("till-1", "Luis Prats")
        .await
        .unwrap();

    let response = call(&router, "GET", "/api/devices", Some(&sessions.admin), &[]).await;
    let body = body_json(response).await;
    let till = body["data"]["devices"]
        .as_array()
        .unwrap()
        .iter()
        .find(|d| d["device_id"] == "till-1")
        .expect("the till is listed");
    assert_eq!(till["name"], "Barra", "the name the business chose stayed");
    assert_eq!(
        till["label"], "Luis Prats",
        "and the hint about who signed in moved on"
    );
}

#[tokio::test]
async fn a_name_can_be_taken_back_and_the_device_returns_to_unnamed() {
    let (router, sessions) = fixture("hub-494").await;
    call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.admin),
        json!({ "name": "Barra" }),
    )
    .await;

    let response = call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.admin),
        json!({ "name": "   " }),
    )
    .await;

    // Blank is not a malformed request here (unlike a blank *id*, which names no device at all):
    // it is "I no longer want to call it that", and it puts the row back to unnamed.
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(listed_name(&router, &sessions.admin, "till-1").await, "");
}

#[tokio::test]
async fn a_name_longer_than_any_screen_could_show_is_refused() {
    let (router, sessions) = fixture("hub-494").await;

    let response = call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.admin),
        json!({ "name": "B".repeat(200) }),
    )
    .await;

    // The name exists to be recognised at a glance in a list; a paragraph pushed into the column
    // would push the row that matters off the screen — the opposite of what this door is for.
    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(listed_name(&router, &sessions.admin, "till-1").await, "");
}

#[tokio::test]
async fn naming_a_device_this_business_does_not_know_creates_nothing() {
    let (router, sessions) = fixture("hub-494").await;

    let response = call_with_body(
        &router,
        "PUT",
        "/api/devices/never-seen",
        Some(&sessions.admin),
        json!({ "name": "Cocina" }),
    )
    .await;

    // A device is listed because it was TRUSTED, never because somebody typed its id. Inventing a
    // row here would put an entry in the owner's list that no login ever produced.
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert_eq!(listed_ids(&router, &sessions.admin).await.len(), 2);
}

#[tokio::test]
async fn only_an_administrator_can_name_a_device() {
    let (router, sessions) = fixture("hub-494").await;

    let no_session = call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        None,
        json!({ "name": "Barra" }),
    )
    .await;
    let as_employee = call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.employee),
        json!({ "name": "Barra" }),
    )
    .await;

    // Same gate as the read and the revocation (ADR-0248): the name is what an owner will trust
    // when deciding which till to cut off, so whoever holds a device cannot write it. `403` for the
    // employee since hub#1702: the session is valid, the role is not.
    assert_eq!(no_session.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(refusal_code(&body_json(no_session).await), Some("unauthorized"));
    assert_eq!(as_employee.status(), StatusCode::FORBIDDEN);
    assert_eq!(refusal_code(&body_json(as_employee).await), Some("forbidden"));
    assert_eq!(listed_name(&router, &sessions.admin, "till-1").await, "");
}

#[tokio::test]
async fn naming_a_device_is_not_disconnecting_it() {
    let (router, sessions) = fixture("hub-494").await;

    let response = call_with_body(
        &router,
        "PUT",
        "/api/devices/laptop-1",
        Some(&sessions.admin),
        json!({ "name": "Portátil despacho" }),
    )
    .await;

    // Two gestures, two doors, on purpose: renaming is housekeeping and revoking takes a till down.
    // A rename that closed sessions would sign the office out for a typo.
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        call(
            &router,
            "GET",
            "/api/devices",
            Some(&sessions.admin_on_laptop),
            &[]
        )
        .await
        .status(),
        StatusCode::OK,
        "the session open on the renamed laptop is exactly as it was"
    );
    assert_eq!(listed_ids(&router, &sessions.admin).await.len(), 2);
}

#[tokio::test]
async fn a_device_of_another_business_cannot_be_renamed_from_here() {
    let (mine, my_sessions) = fixture("hub-494").await;
    // The neighbour is alive and holds a device with the SAME id — the real case of one tablet
    // working in two shops. Without a `hub_id` in the statement, this write crosses.
    let (neighbours, their_sessions) = fixture("hub-494-neighbour").await;
    call_with_body(
        &neighbours,
        "PUT",
        "/api/devices/till-1",
        Some(&their_sessions.admin),
        json!({ "name": "Su barra" }),
    )
    .await;

    call_with_body(
        &mine,
        "PUT",
        "/api/devices/till-1",
        Some(&my_sessions.admin),
        json!({ "name": "Mi barra" }),
    )
    .await;

    assert_eq!(
        listed_name(&mine, &my_sessions.admin, "till-1").await,
        "Mi barra"
    );
    assert_eq!(
        listed_name(&neighbours, &their_sessions.admin, "till-1").await,
        "Su barra",
        "the shop next door kept the name it chose"
    );
}

#[tokio::test]
async fn the_first_login_names_a_device_after_the_platform_it_announced() {
    let (router, sessions, state) = fixture_with_state("hub-494").await;

    // What the login does when a device this hub has never seen signs in online: the name it is
    // born with is the platform, NOT the person (the person is `label`, and it changes shift to
    // shift). ADR-0257 forbids reading it off the id, which is 128 opaque bits.
    state
        .runtime
        .read()
        .await
        .trust_device_with_default_name("tablet-9", "Marta Ruiz", "Chrome · Android")
        .await
        .unwrap();
    // …and a SECOND online login on the same device leaves that name alone: the default is what a
    // device is called until somebody decides otherwise, not something rewritten on every entry.
    state
        .runtime
        .read()
        .await
        .trust_device_with_default_name("tablet-9", "Luis Prats", "Safari · iPad")
        .await
        .unwrap();

    assert_eq!(
        listed_name(&router, &sessions.admin, "tablet-9").await,
        "Chrome · Android"
    );
}

// ── One device, ONE name: the printer card follows the device list (hub#1560) ─────────────────
//
// hub#1527 made Settings → Printers say *which* device prints each station. The registry it reads
// has a name column of its own (`_print_host.label`), so without this the same tablet would carry
// two names: "Barra" in the device list and whatever it happened to register with on the printer
// card — and renaming it in the one place an owner can rename anything would not move the other.

#[tokio::test]
async fn hub1560_naming_a_device_names_it_on_the_printer_card_too() {
    let (router, sessions, state) = fixture_with_state("hub-1560").await;
    state
        .runtime
        .read()
        .await
        .register_print_host("till-1", "receipt", "Chrome · Android", "u1")
        .await
        .unwrap();

    let response = call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.admin),
        json!({ "name": "Barra" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);

    let hosts = state.runtime.read().await.print_hosts().await.unwrap();
    let till = hosts
        .iter()
        .find(|h| h.device_id == "till-1")
        .expect("the till is a print host");
    assert_eq!(
        till.label, "Barra",
        "the printer card must not keep a name the owner has just replaced"
    );
}

#[tokio::test]
async fn hub1560_taking_the_name_back_does_not_blank_the_printer_card() {
    let (router, sessions, state) = fixture_with_state("hub-1560-blank").await;
    state
        .runtime
        .read()
        .await
        .register_print_host("till-1", "receipt", "Caja 1", "u1")
        .await
        .unwrap();

    // Blank is a real gesture on the device list ("I have no name for it") and it returns that row
    // to unnamed. It must not, however, wipe the name off the printer card and put the opaque
    // device id back on it — the same contract `print_hosts::register` already keeps for a client
    // that registers without repeating the name.
    call_with_body(
        &router,
        "PUT",
        "/api/devices/till-1",
        Some(&sessions.admin),
        json!({ "name": "   " }),
    )
    .await;

    let hosts = state.runtime.read().await.print_hosts().await.unwrap();
    assert_eq!(
        hosts
            .iter()
            .find(|h| h.device_id == "till-1")
            .expect("the till is a print host")
            .label,
        "Caja 1"
    );
}
