//! **A session that runs out ends the live channel it had open** (`GET /ws`, `GET /api/events`,
//! hub#2600).
//!
//! A session lasts what it was opened with (HUB-F136: 12 h on a shared till, 1 h when the business
//! asks for the PIN every time) and every request checks it again — but the live channel was only
//! checked when it opened. hub#2522, hub#2571 and hub#2599 made signing out, a change of access and
//! removing a device end it; running out of time did not, so the till whose shift ended kept
//! hearing every sale, order and customer until it reconnected, however long that took.
//!
//! The end is by **session**: the same person keeps listening on another device whose session is
//! still alive. Every case pairs the session that runs out with that one, so an end that closed
//! every channel of the person — or that fired for everybody at the first deadline — fails here.
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

const HUB_ID: &str = "hub-events-expiry-hub2600";

/// How long the short session lives. Long enough to open a channel and hear a frame on it first —
/// so a channel cut the moment it opens fails — and short enough for a test.
const SHORT_SESSION_SECS: i64 = 3;
/// Far past the short session's end, far short of the stream ticket's minute: an end that waited
/// for the ticket, or for nothing, fails here.
const FRAME_TIMEOUT: Duration = Duration::from_secs(10);
/// How long a channel that must stay open is watched for an unwanted cut.
const QUIET_WINDOW: Duration = Duration::from_millis(500);

struct Server {
    addr: SocketAddr,
    state: AppState,
    /// The employee's session on the till whose shift is ending: [`SHORT_SESSION_SECS`].
    running_out: String,
    /// The SAME employee's session on another device, alive for an hour.
    alive: String,
}

async fn serve() -> Server {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let employee = rt
        .create_user("Pau", "2468", "employee", None)
        .await
        .unwrap();
    let alive = rt
        .create_session(&employee, 3600, Some("till-2"))
        .await
        .unwrap();
    let running_out = rt
        .create_session(&employee, SHORT_SESSION_SECS, Some("till-1"))
        .await
        .unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-events-expiry-2600-{}-{}",
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
        running_out,
        alive,
    }
}

async fn ticket(srv: &Server, session: &str) -> String {
    let req = Request::builder()
        .method("POST")
        .uri("/api/events/ticket")
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "a live session gets a ticket"
    );
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap();
    json["data"]["ticket"].as_str().unwrap().to_string()
}

/// Waits until the short session has run out, with a margin.
async fn until_the_shift_ends() {
    tokio::time::sleep(Duration::from_millis(
        SHORT_SESSION_SECS as u64 * 1000 + 500,
    ))
    .await;
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

/// **The hole, over a socket.** The till's socket hears while its session lives, and closes with
/// `events.credential_ended` when the session runs out — with no request, no sign-out, nobody
/// touching anything. The same person's socket on the other device keeps listening.
#[tokio::test]
async fn hub2600_a_session_that_runs_out_closes_its_socket_and_not_the_other_device() {
    let srv = serve().await;
    let mut till = ws_as(&srv, &srv.running_out).await;
    let mut other = ws_as(&srv, &srv.alive).await;
    assert_still_hears(&mut till, &srv, "the till while its session lives").await;

    assert_cut(&mut till, &srv, "the till's session ran out").await;
    assert_still_hears(&mut other, &srv, "the same person on the other device").await;
}

/// A ticket the till asked for while its session lived is that session's word: once the session
/// has run out it opens nothing (`unauthenticated`), the same as after signing out.
#[tokio::test]
async fn hub2600_a_ticket_minted_before_the_session_ran_out_opens_nothing_after_it() {
    let srv = serve().await;
    let early = ticket(&srv, &srv.running_out).await;
    let still_good = ticket(&srv, &srv.alive).await;

    until_the_shift_ends().await;

    let mut socket = ws_with(&srv, &early).await;
    let refused = recv(&mut socket).await;
    assert_eq!(refused["type"], "stream.error", "{refused}");
    assert_eq!(refused["code"], "unauthenticated", "{refused}");
    let mut other = ws_with(&srv, &still_good).await;
    assert_eq!(recv(&mut other).await["type"], "stream.ready");
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

/// **The hole as the issue reports it**, over SSE: the till's stream hears while its session
/// lives, says why and ends when it runs out; the same person's stream on the other device stays.
#[tokio::test]
async fn hub2600_a_session_that_runs_out_ends_its_sse_stream_and_not_the_other_device() {
    let srv = serve().await;
    let mut till = sse_as(&srv, &srv.running_out).await;
    let mut other = sse_as(&srv, &srv.alive).await;
    tokio::time::sleep(QUIET_WINDOW).await;
    something_happens(&srv);
    let heard = sse_next(&mut till, FRAME_TIMEOUT)
        .await
        .expect("the till's stream is open while its session lives")
        .expect("the till hears while its session lives");
    assert_eq!(heard["type"], "module.installed", "{heard}");
    let heard = sse_next(&mut other, FRAME_TIMEOUT).await.unwrap().unwrap();
    assert_eq!(heard["type"], "module.installed", "{heard}");

    let last = sse_next(&mut till, FRAME_TIMEOUT)
        .await
        .expect("the stream said why before ending")
        .expect("the stream was neither cut nor told");
    assert_eq!(last["type"], "stream.error", "{last}");
    assert_eq!(last["code"], ERR_CREDENTIAL_ENDED, "{last}");
    tokio::time::sleep(QUIET_WINDOW).await;
    something_happens(&srv);
    assert!(
        sse_next(&mut till, FRAME_TIMEOUT).await.is_err(),
        "the stream ends after the session ran out"
    );
    let heard = sse_next(&mut other, FRAME_TIMEOUT)
        .await
        .expect("the other device's stream stays open")
        .expect("the other device keeps hearing");
    assert_eq!(heard["type"], "module.installed", "{heard}");
}
