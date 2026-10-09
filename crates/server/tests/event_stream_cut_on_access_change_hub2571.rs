//! **Changing what a person may do ends the live channel they opened** (`GET /ws`,
//! `GET /api/events`, hub#2571).
//!
//! hub#2522 closed the channel when its credential ended (signing out, revoking or rotating a key).
//! It left three doors that change who a person is **without** ending the session they listen
//! with, and the channel kept hearing what it could hear when it opened:
//!
//! 1. **Changing their role** (`PUT /api/hub/users/:id`, or `POST /api/members` over an existing
//!    address): a manager demoted to employee kept hearing the modules only a manager reads.
//! 2. **Taking them off the team** (`DELETE /api/hub/users/:id`, `DELETE /api/members/:email`): the
//!    sessions are deleted, but the socket of the person who just left kept hearing every sale.
//! 3. **Throwing a device out because the plan covers one** (HUB-F137): the evicted till's session
//!    no longer resolves, and its socket kept hearing the business anyway.
//!
//! Each door is paired with a channel connected at the same instant that keeps hearing — another
//! person, or the device that just signed in — so a cut that closed every socket of the hub fails
//! here. And an edit that changes nothing a channel is entitled to (the name) closes nothing.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use cloud_client::{EntitledModule, EntitlementClaims};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::event_stream::ERR_CREDENTIAL_ENDED;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::net::SocketAddr;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;
use tokio_tungstenite::tungstenite::Message;
use tower::ServiceExt;

const HUB_ID: &str = "hub-events-cut-hub2571";

const FRAME_TIMEOUT: Duration = Duration::from_secs(10);
/// How long a channel that must stay open is watched for an unwanted cut.
const QUIET_WINDOW: Duration = Duration::from_millis(500);

const STAFF_EMAIL: &str = "lucia@example.com";

struct Server {
    addr: SocketAddr,
    state: AppState,
    /// The administrator who makes every change.
    admin: String,
    /// An employee with a PIN only (nothing of theirs lives in erplora.com).
    employee_id: String,
    employee: String,
    /// Another person of the hub, listening at the same time.
    manager: String,
    /// A person who signs in with an account (`hub_user.email`), the one the members door finds.
    staff: String,
}

async fn serve() -> Server {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin_user = rt
        .create_user("Owner", "1357", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_user, 3600, None).await.unwrap();
    let employee_id = rt
        .create_user("Pau", "2468", "employee", None)
        .await
        .unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let manager_user = rt
        .create_user("Marta", "3579", "manager", None)
        .await
        .unwrap();
    let manager = rt.create_session(&manager_user, 3600, None).await.unwrap();
    let staff_id = rt
        .create_login_user(STAFF_EMAIL, "employee", 0)
        .await
        .unwrap()
        .id;
    let staff = rt.create_session(&staff_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-events-cut-2571-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
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
        demo: false,
    };
    let state = AppState::with_config(rt, cfg);
    let router = app(state.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        let _ = axum::serve(listener, router.into_make_service()).await;
    });
    Server {
        addr,
        state,
        admin,
        employee_id,
        employee,
        manager,
        staff,
    }
}

/// Calls one of the hub's own doors with the administrator's session, as the app does.
async fn admin_call(srv: &Server, method: &str, uri: &str, body: Option<Value>) -> StatusCode {
    let mut req = Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-session", &srv.admin);
    let body = match body {
        Some(json) => {
            req = req.header("content-type", "application/json");
            Body::from(json.to_string())
        }
        None => Body::empty(),
    };
    app(srv.state.clone())
        .oneshot(req.body(body).unwrap())
        .await
        .unwrap()
        .status()
}

async fn edit_person(srv: &Server, id: &str, change: Value) {
    assert_eq!(
        admin_call(srv, "PUT", &format!("/api/hub/users/{id}"), Some(change)).await,
        StatusCode::OK,
        "the edit is accepted"
    );
}

async fn ticket(srv: &Server, session: &str) -> String {
    let req = Request::builder()
        .method("POST")
        .uri("/api/events/ticket")
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "a session gets a ticket");
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap();
    json["data"]["ticket"].as_str().unwrap().to_string()
}

/// A frame every listener of this file is entitled to (an app was installed).
fn something_happens(srv: &Server) {
    srv.state
        .broadcast(json!({ "type": "module.installed", "module_id": "sales" }));
}

// ── The WebSocket door ────────────────────────────────────────────────────────────────────────

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

async fn ws_with(srv: &Server, token: &str) -> Socket {
    let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{}/ws", srv.addr))
        .await
        .expect("the upgrade succeeds");
    socket
        .send(Message::Text(
            json!({ "type": "auth", "token": token }).to_string(),
        ))
        .await
        .unwrap();
    socket
}

async fn ws_as(srv: &Server, session: &str) -> Socket {
    let t = ticket(srv, session).await;
    let mut socket = ws_with(srv, &t).await;
    assert_eq!(recv(&mut socket).await["type"], "stream.ready");
    socket
}

async fn recv(socket: &mut Socket) -> Value {
    loop {
        let next = tokio::time::timeout(FRAME_TIMEOUT, socket.next())
            .await
            .expect("the hub answered within the window");
        match next {
            Some(Ok(Message::Text(t))) => return serde_json::from_str(&t).expect("a JSON frame"),
            Some(Ok(_)) => continue,
            other => panic!("the channel closed instead of answering: {other:?}"),
        }
    }
}

/// The socket was told why and then closed: the next thing after the `stream.error` frame is the
/// end of the stream, not another frame.
async fn assert_cut(socket: &mut Socket, srv: &Server, what: &str) {
    let last = match tokio::time::timeout(FRAME_TIMEOUT, socket.next()).await {
        Err(_) => panic!("{what}: the socket was neither cut nor told"),
        Ok(Some(Ok(Message::Text(t)))) => serde_json::from_str::<Value>(&t).unwrap(),
        Ok(other) => panic!("{what}: the socket ended without saying why: {other:?}"),
    };
    assert_eq!(last["type"], "stream.error", "{what}: {last}");
    assert_eq!(last["code"], ERR_CREDENTIAL_ENDED, "{what}: {last}");
    something_happens(srv);
    loop {
        match tokio::time::timeout(FRAME_TIMEOUT, socket.next()).await {
            Err(_) => panic!("{what}: the socket was told it ended but was left open"),
            Ok(None) | Ok(Some(Err(_))) | Ok(Some(Ok(Message::Close(_)))) => return,
            Ok(Some(Ok(Message::Text(t)))) => {
                panic!("{what}: the socket kept hearing after the cut: {t}")
            }
            Ok(Some(Ok(_))) => continue,
        }
    }
}

/// The socket hears the next frame, and that frame is not a cut.
async fn assert_still_hears(socket: &mut Socket, srv: &Server, what: &str) {
    // Give a wrongly issued cut the time to land before the frame is sent: a cut that arrives
    // later than the frame would let this pass.
    tokio::time::sleep(QUIET_WINDOW).await;
    something_happens(srv);
    let heard = recv(socket).await;
    assert_eq!(heard["type"], "module.installed", "{what}: {heard}");
}

/// **The hole, over a socket.** The administrator promotes the employee: their open socket closes
/// with `events.credential_ended`, so the app reconnects with a ticket that carries the new role.
/// Another person's screen keeps listening.
#[tokio::test]
async fn changing_a_persons_role_closes_their_socket_and_no_one_elses() {
    let srv = serve().await;
    let mut employee = ws_as(&srv, &srv.employee).await;
    let mut manager = ws_as(&srv, &srv.manager).await;

    edit_person(&srv, &srv.employee_id, json!({ "role": "manager" })).await;

    assert_cut(&mut employee, &srv, "the employee's role changed").await;
    assert_still_hears(&mut manager, &srv, "another person").await;
}

/// …and an edit that changes nothing the channel hears with (the name) closes nothing: cutting on
/// every edit would make every screen of a person blink each time somebody fixes a typo.
#[tokio::test]
async fn renaming_a_person_leaves_their_socket_open() {
    let srv = serve().await;
    let mut employee = ws_as(&srv, &srv.employee).await;

    edit_person(&srv, &srv.employee_id, json!({ "name": "Pau Vidal" })).await;

    assert_still_hears(&mut employee, &srv, "only the name changed").await;
}

/// …nor does saving the role the person already has (the form sends every field back).
#[tokio::test]
async fn saving_the_same_role_leaves_their_socket_open() {
    let srv = serve().await;
    let mut employee = ws_as(&srv, &srv.employee).await;

    edit_person(&srv, &srv.employee_id, json!({ "role": "employee" })).await;

    assert_still_hears(&mut employee, &srv, "the role did not change").await;
}

/// **A ticket minted with the old role opens nothing after the change**: it carries the
/// permissions the role had when it was minted.
#[tokio::test]
async fn a_ticket_minted_before_a_role_change_opens_nothing_after_it() {
    let srv = serve().await;
    let t = ticket(&srv, &srv.employee).await;

    edit_person(&srv, &srv.employee_id, json!({ "role": "manager" })).await;

    let mut socket = ws_with(&srv, &t).await;
    let answer = recv(&mut socket).await;
    assert_eq!(answer["type"], "stream.error", "{answer}");
    assert_eq!(answer["code"], "unauthenticated", "{answer}");

    // …while a ticket asked for after it opens, with the new role.
    let _reconnected = ws_as(&srv, &srv.employee).await;
}

/// **Taking a person off the team** (Employees → «Dar de baja») closes their socket.
#[tokio::test]
async fn taking_a_person_off_the_team_closes_their_socket_and_no_one_elses() {
    let srv = serve().await;
    let mut employee = ws_as(&srv, &srv.employee).await;
    let mut manager = ws_as(&srv, &srv.manager).await;

    assert_eq!(
        admin_call(
            &srv,
            "DELETE",
            &format!("/api/hub/users/{}", srv.employee_id),
            None
        )
        .await,
        StatusCode::OK
    );

    assert_cut(&mut employee, &srv, "the employee was taken off the team").await;
    assert_still_hears(&mut manager, &srv, "another person").await;
}

/// …through the members door too, and **before** erplora.com is told: here it does not answer
/// (the refusal is the 502 the screen already explains), and the local door is closed anyway.
#[tokio::test]
async fn removing_a_member_closes_their_socket_even_when_erplora_does_not_answer() {
    let srv = serve().await;
    let mut staff = ws_as(&srv, &srv.staff).await;
    let mut manager = ws_as(&srv, &srv.manager).await;

    let status = admin_call(&srv, "DELETE", &format!("/api/members/{STAFF_EMAIL}"), None).await;
    assert_ne!(status, StatusCode::OK, "erplora.com is not reachable here");
    assert_ne!(
        status,
        StatusCode::FORBIDDEN,
        "the admin may remove members"
    );

    assert_cut(&mut staff, &srv, "the member was removed").await;
    assert_still_hears(&mut manager, &srv, "another person").await;
}

/// …and the members door that re-grants an existing address with another role is a role change.
#[tokio::test]
async fn regranting_a_member_with_another_role_closes_their_socket() {
    let srv = serve().await;
    let mut staff = ws_as(&srv, &srv.staff).await;
    let mut manager = ws_as(&srv, &srv.manager).await;

    let status = admin_call(
        &srv,
        "POST",
        "/api/members",
        Some(json!({ "email": STAFF_EMAIL, "role": "manager" })),
    )
    .await;
    assert_ne!(
        status,
        StatusCode::FORBIDDEN,
        "the admin may re-grant members"
    );

    assert_cut(&mut staff, &srv, "the member's role changed").await;
    assert_still_hears(&mut manager, &srv, "another person").await;
}

/// …while re-granting the role they already have (the invitation sent again) closes nothing.
#[tokio::test]
async fn regranting_a_member_with_the_same_role_leaves_their_socket_open() {
    let srv = serve().await;
    let mut staff = ws_as(&srv, &srv.staff).await;

    let status = admin_call(
        &srv,
        "POST",
        "/api/members",
        Some(json!({ "email": STAFF_EMAIL, "role": "employee" })),
    )
    .await;
    assert_ne!(
        status,
        StatusCode::FORBIDDEN,
        "the admin may re-grant members"
    );

    assert_still_hears(&mut staff, &srv, "the role did not change").await;
}

// ── The device limit (HUB-F137) ─────────────────────────────────────────────────────────────────

fn one_device_plan() -> EntitlementClaims {
    EntitlementClaims {
        hub_id: HUB_ID.into(),
        modules: vec![EntitledModule {
            module_id: "pos".into(),
            tier: "basic".into(),
            version: "1.0.0".into(),
        }],
        iat: 1_000,
        exp: 2_000,
        grace_until: 9_999_999_999,
        paid_grace_until: None,
        plan: Some("free".into()),
        max_devices: 1,
        max_database_size_gb: 0,
        max_users: 0,
    }
}

async fn pin_login(srv: &Server, name: &str, pin: &str, device: &str) -> String {
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/pin")
        .header("content-type", "application/json")
        .body(Body::from(
            json!({ "name": name, "pin": pin, "device_id": device }).to_string(),
        ))
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the PIN login is accepted");
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    v["token"].as_str().expect("a session token").to_string()
}

/// **The plan covers one device**: signing in on the second till throws the first one out, and
/// the first one's socket closes with it. The till that just signed in keeps listening.
#[tokio::test]
async fn being_thrown_out_by_the_device_limit_closes_that_devices_socket() {
    let srv = serve().await;
    srv.state
        .entitlement
        .write()
        .unwrap()
        .apply_success(one_device_plan(), 1_500);

    let first = pin_login(&srv, "Pau", "2468", "till-1").await;
    let mut first_till = ws_as(&srv, &first).await;

    let second = pin_login(&srv, "Marta", "3579", "till-2").await;
    let mut second_till = ws_as(&srv, &second).await;

    assert_cut(&mut first_till, &srv, "the first till was thrown out").await;
    assert_still_hears(&mut second_till, &srv, "the till that signed in").await;
}

// ── The SSE door (`GET /api/events`) ───────────────────────────────────────────────────────────

async fn sse_as(srv: &Server, session: &str) -> axum::body::BodyDataStream {
    let t = ticket(srv, session).await;
    let req = Request::builder()
        .uri(format!("/api/events?ticket={t}"))
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the stream opens");
    resp.into_body().into_data_stream()
}

/// Next `data:` frame, or `Err(())` once the stream has ended. `Ok(None)` is silence.
async fn sse_next(
    body: &mut axum::body::BodyDataStream,
    window: Duration,
) -> Result<Option<Value>, ()> {
    let deadline = tokio::time::Instant::now() + window;
    let mut buffered = String::new();
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        if left.is_zero() {
            return Ok(None);
        }
        match tokio::time::timeout(left, body.next()).await {
            Err(_) => return Ok(None),
            Ok(None) | Ok(Some(Err(_))) => return Err(()),
            Ok(Some(Ok(chunk))) => {
                buffered.push_str(&String::from_utf8_lossy(&chunk));
                for line in buffered.lines() {
                    if let Some(rest) = line.strip_prefix("data:") {
                        if let Ok(v) = serde_json::from_str::<Value>(rest.trim()) {
                            return Ok(Some(v));
                        }
                    }
                }
            }
        }
    }
}

/// **The hole as the issue reports it**, over SSE: the role changes and the stream ends.
#[tokio::test]
async fn changing_a_persons_role_closes_their_sse_stream_and_no_one_elses() {
    let srv = serve().await;
    let mut employee = sse_as(&srv, &srv.employee).await;
    let mut manager = sse_as(&srv, &srv.manager).await;

    edit_person(&srv, &srv.employee_id, json!({ "role": "manager" })).await;

    let last = sse_next(&mut employee, FRAME_TIMEOUT)
        .await
        .expect("the stream said why before ending")
        .expect("the stream was neither cut nor told");
    assert_eq!(last["type"], "stream.error", "{last}");
    assert_eq!(last["code"], ERR_CREDENTIAL_ENDED, "{last}");
    tokio::time::sleep(QUIET_WINDOW).await;
    something_happens(&srv);
    assert!(
        sse_next(&mut employee, FRAME_TIMEOUT).await.is_err(),
        "the stream ends after the cut"
    );
    let heard = sse_next(&mut manager, FRAME_TIMEOUT)
        .await
        .expect("another person's stream stays open")
        .expect("another person keeps hearing");
    assert_eq!(heard["type"], "module.installed", "{heard}");
}
