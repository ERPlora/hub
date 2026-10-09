//! **Removing a device of the business ends the live channel it had open** (`GET /ws`,
//! `GET /api/events`, hub#2599).
//!
//! "Remove this device" (`DELETE /api/devices/:id`, HUB-F141) deletes the device's sessions, and
//! "remove the ones unused for 30 days" (`POST /api/devices/prune`) deletes the sessions of each
//! device it forgets. hub#2522 and hub#2571 made signing out, a role change, a removal from the team
//! and the device limit end the channels those sessions held; these two doors did not, so the
//! tablet somebody walked off with kept hearing every sale, order and appointment until it
//! reconnected.
//!
//! The cut is by **session**, not by person: removing a device signs that device out, never the
//! person (HUB-F141, "se corta el dispositivo, no la persona"). Every case therefore pairs the
//! removed device with **the same person** listening on another device at the same instant, so a
//! cut that closed every channel of the person — or of the hub — fails here.
use axum::body::Body;
use axum::http::{Request, StatusCode};
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

const HUB_ID: &str = "hub-events-cut-hub2599";

const FRAME_TIMEOUT: Duration = Duration::from_secs(10);
/// How long a channel that must stay open is watched for an unwanted cut.
const QUIET_WINDOW: Duration = Duration::from_millis(500);

/// The device that gets removed, and the other one the same person works on.
const LOST_TILL: &str = "till-1";
const OTHER_TILL: &str = "till-2";
/// The device the administrator holds while removing.
const ADMIN_DEVICE: &str = "office-laptop";

struct Server {
    addr: SocketAddr,
    state: AppState,
    /// The administrator who removes the device.
    admin: String,
    /// The employee's session on the device that gets removed.
    on_lost_till: String,
    /// The SAME employee's session on another device of the business.
    on_other_till: String,
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
    let admin = rt
        .create_session(&admin_user, 3600, Some(ADMIN_DEVICE))
        .await
        .unwrap();
    let employee = rt
        .create_user("Pau", "2468", "employee", None)
        .await
        .unwrap();
    for device in [LOST_TILL, OTHER_TILL, ADMIN_DEVICE] {
        rt.trust_device(device, "Owner").await.unwrap();
    }
    let on_lost_till = rt
        .create_session(&employee, 3600, Some(LOST_TILL))
        .await
        .unwrap();
    let on_other_till = rt
        .create_session(&employee, 3600, Some(OTHER_TILL))
        .await
        .unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-events-cut-2599-{}-{}",
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
        on_lost_till,
        on_other_till,
    }
}

/// Calls a device door with the administrator's session, from the device they hold.
async fn admin_call(srv: &Server, method: &str, uri: &str) -> Value {
    let req = Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-session", &srv.admin)
        .header("x-device-id", ADMIN_DEVICE)
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "{method} {uri} is accepted");
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn remove_lost_till(srv: &Server) {
    let removed = admin_call(srv, "DELETE", &format!("/api/devices/{LOST_TILL}")).await;
    assert_eq!(removed["data"]["sessions_closed"], 1, "{removed}");
}

/// Ages `device_id` the way `devices_api.rs` does for hub#2215: trusted 60 days ago, last signed
/// in 40 days ago, its sessions run out 39 days ago — what the bulk clean-up takes.
async fn make_dead(srv: &Server, device_id: &str) {
    let days_ago = |d: i64| (chrono::Utc::now() - chrono::Duration::days(d)).to_rfc3339();
    let mut p = erplora_db::Params::new();
    p.insert("hub_id".into(), json!(HUB_ID));
    p.insert("device_id".into(), json!(device_id));
    p.insert("trusted".into(), json!(days_ago(60)));
    p.insert("seen".into(), json!(days_ago(40)));
    p.insert("expires".into(), json!(days_ago(39)));
    let rt = srv.state.runtime.read().await;
    rt.db()
        .execute(
            "UPDATE hub_trusted_device SET trusted_at = :trusted, last_seen_at = :seen \
              WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await
        .unwrap();
    rt.db()
        .execute(
            "UPDATE hub_session SET created_at = :seen, expires_at = :expires \
              WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await
        .unwrap();
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

/// **The hole, over a socket.** The administrator removes the lost till: its open socket closes
/// with `events.credential_ended`. The same person's screen on the other till keeps listening —
/// the device is cut, not the person.
#[tokio::test]
async fn removing_a_device_closes_its_socket_and_not_the_same_persons_other_device() {
    let srv = serve().await;
    let mut lost = ws_as(&srv, &srv.on_lost_till).await;
    let mut other = ws_as(&srv, &srv.on_other_till).await;

    remove_lost_till(&srv).await;

    assert_cut(&mut lost, &srv, "the lost till was removed").await;
    assert_still_hears(&mut other, &srv, "the same person on the other till").await;
}

/// A ticket the lost till asked for just before it was removed is the session's word from before:
/// it opens nothing afterwards (`unauthenticated`), the same as after signing out.
#[tokio::test]
async fn a_ticket_minted_before_the_device_was_removed_opens_nothing_after_it() {
    let srv = serve().await;
    let early = ticket(&srv, &srv.on_lost_till).await;

    remove_lost_till(&srv).await;

    let mut socket = ws_with(&srv, &early).await;
    let refused = recv(&mut socket).await;
    assert_eq!(refused["type"], "stream.error", "{refused}");
    assert_eq!(refused["code"], "unauthenticated", "{refused}");
}

/// **The bulk clean-up** forgets a device nobody signed in on for 30 days, with its sessions; the
/// channel such a session still held closes too. The device in use keeps listening.
#[tokio::test]
async fn clearing_unused_devices_closes_the_socket_a_forgotten_device_still_held() {
    let srv = serve().await;
    let mut forgotten = ws_as(&srv, &srv.on_lost_till).await;
    let mut in_use = ws_as(&srv, &srv.on_other_till).await;
    make_dead(&srv, LOST_TILL).await;

    let pruned = admin_call(&srv, "POST", "/api/devices/prune").await;
    assert_eq!(pruned["data"]["removed"], 1, "{pruned}");

    assert_cut(&mut forgotten, &srv, "the unused till was forgotten").await;
    assert_still_hears(&mut in_use, &srv, "the till in use").await;
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

/// **The hole as the issue reports it**, over SSE: the device is removed and its stream ends; the
/// same person's stream on the other till stays.
#[tokio::test]
async fn removing_a_device_closes_its_sse_stream_and_not_the_same_persons_other_device() {
    let srv = serve().await;
    let mut lost = sse_as(&srv, &srv.on_lost_till).await;
    let mut other = sse_as(&srv, &srv.on_other_till).await;

    remove_lost_till(&srv).await;

    let last = sse_next(&mut lost, FRAME_TIMEOUT)
        .await
        .expect("the stream said why before ending")
        .expect("the stream was neither cut nor told");
    assert_eq!(last["type"], "stream.error", "{last}");
    assert_eq!(last["code"], ERR_CREDENTIAL_ENDED, "{last}");
    tokio::time::sleep(QUIET_WINDOW).await;
    something_happens(&srv);
    assert!(
        sse_next(&mut lost, FRAME_TIMEOUT).await.is_err(),
        "the stream ends after the cut"
    );
    let heard = sse_next(&mut other, FRAME_TIMEOUT)
        .await
        .expect("the other till's stream stays open")
        .expect("the other till keeps hearing");
    assert_eq!(heard["type"], "module.installed", "{heard}");
}
