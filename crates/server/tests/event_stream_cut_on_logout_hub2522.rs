//! **Ending a credential ends the live channel it opened** (`GET /ws`, `GET /api/events`,
//! hub#2522).
//!
//! The channel decides who listens once, when it opens (hub#504, hub#2501), and until hub#2522
//! nothing ever looked again: a person who signed out, or an integration whose key the owner
//! revoked, kept hearing every sale and every docket on the socket that was already open — until
//! that screen happened to reconnect. What this file pins, on both transports and over a real TCP
//! listener:
//!
//! 1. **Signing out** (`POST /api/auth/logout`) closes the channels opened with THAT session, with a
//!    last `stream.error` frame carrying [`ERR_CREDENTIAL_ENDED`], and nothing after it.
//! 2. **Revoking a key** (`DELETE /api/keys/:id`) and **rotating it** (`POST /api/keys/:id/rotate`)
//!    close the channels opened with that key.
//! 3. **Only those.** Every cut is paired with a channel connected at the same instant that keeps
//!    hearing: the same person on another device, another person, another key. A cut that closed
//!    every socket of the hub would pass the negatives alone.
//! 4. **A ticket minted before signing out does not open a channel after it**: the ticket was
//!    checked against a session that no longer exists.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::api_keys::{ApiKeyAccess, ApiKeyScope};
use erplora_runtime::Runtime;
use erplora_server::event_stream::ERR_CREDENTIAL_ENDED;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::net::SocketAddr;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::Message;
use tower::ServiceExt;

const HUB_ID: &str = "hub-events-cut-hub2522";

const FRAME_TIMEOUT: Duration = Duration::from_secs(10);

struct Server {
    addr: SocketAddr,
    state: AppState,
    /// The owner's session on the till.
    owner: String,
    /// The same owner, signed in on a second device.
    owner_elsewhere: String,
    /// Another person of the hub.
    manager: String,
}

async fn serve() -> Server {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let owner_user = rt
        .create_user("Owner", "1111", "admin", None)
        .await
        .unwrap();
    let owner = rt.create_session(&owner_user, 3600, None).await.unwrap();
    let owner_elsewhere = rt.create_session(&owner_user, 3600, None).await.unwrap();
    let manager_user = rt
        .create_user("Manager", "2222", "admin", None)
        .await
        .unwrap();
    let manager = rt.create_session(&manager_user, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-events-cut-{}-{}",
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
        owner,
        owner_elsewhere,
        manager,
    }
}

/// A blanket read key: `(id, token)`.
async fn read_key(srv: &Server, name: &str) -> (String, String) {
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.read().await;
    let key = rt
        .create_api_key(
            name,
            &ApiKeyScope::blanket(ApiKeyAccess::ReadOnly),
            600,
            "hub_user:1",
        )
        .await
        .unwrap();
    (key.id, key.secret)
}

/// Calls one of the hub's own doors with an administrator's session, as the app does.
async fn call(srv: &Server, method: &str, uri: &str, session: &str) -> StatusCode {
    let req = Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap();
    app(srv.state.clone()).oneshot(req).await.unwrap().status()
}

async fn sign_out(srv: &Server, session: &str) {
    assert_eq!(
        call(srv, "POST", "/api/auth/logout", session).await,
        StatusCode::OK
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

/// Opens `/ws` with `token` in the first frame (a session's ticket, or a key), as the browser does.
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
    let last = recv(socket).await;
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

async fn assert_still_hears(socket: &mut Socket, what: &str) {
    let heard = recv(socket).await;
    assert_eq!(heard["type"], "module.installed", "{what}: {heard}");
}

/// **The hole, over a socket.** The owner signs out on the till; the till's socket stops hearing.
/// The same owner's other device and another person's screen keep listening.
#[tokio::test]
async fn signing_out_closes_the_socket_of_that_session_and_no_other() {
    let srv = serve().await;
    let mut till = ws_as(&srv, &srv.owner.clone()).await;
    let mut phone = ws_as(&srv, &srv.owner_elsewhere.clone()).await;
    let mut manager = ws_as(&srv, &srv.manager.clone()).await;

    sign_out(&srv, &srv.owner.clone()).await;

    assert_cut(&mut till, &srv, "the till signed out").await;
    assert_still_hears(&mut phone, "the owner's other device").await;
    assert_still_hears(&mut manager, "another person").await;
}

/// **Revoking a key closes the integration's socket** — the one that presented the key in the
/// handshake header, the way `websocat` or an integration does — and not another key's.
#[tokio::test]
async fn revoking_a_key_closes_its_socket_and_no_other_keys() {
    let srv = serve().await;
    let (revoked_id, revoked) = read_key(&srv, "Gestoría").await;
    let (_, kept) = read_key(&srv, "Contabilidad").await;

    let mut request = format!("ws://{}/ws", srv.addr)
        .into_client_request()
        .unwrap();
    request.headers_mut().insert(
        "authorization",
        format!("Bearer {revoked}").parse().unwrap(),
    );
    let (mut integration, _) = tokio_tungstenite::connect_async(request).await.unwrap();
    let mut other = ws_with(&srv, &kept).await;
    assert_eq!(recv(&mut other).await["type"], "stream.ready");
    // The handshake-authenticated socket says nothing back: prove it is listening before the cut.
    something_happens(&srv);
    assert_still_hears(&mut integration, "the key before it was revoked").await;
    assert_still_hears(&mut other, "the other key").await;

    let owner = srv.owner.clone();
    assert_eq!(
        call(&srv, "DELETE", &format!("/api/keys/{revoked_id}"), &owner).await,
        StatusCode::OK
    );

    assert_cut(&mut integration, &srv, "the key was revoked").await;
    assert_still_hears(&mut other, "another key").await;
}

/// **Rotating a key** invalidates the old secret, so the socket opened with it closes too.
#[tokio::test]
async fn rotating_a_key_closes_the_socket_the_old_secret_opened() {
    let srv = serve().await;
    let (id, token) = read_key(&srv, "Gestoría").await;
    let mut integration = ws_with(&srv, &token).await;
    assert_eq!(recv(&mut integration).await["type"], "stream.ready");

    let owner = srv.owner.clone();
    let req = Request::builder()
        .method("POST")
        .uri(format!("/api/keys/{id}/rotate"))
        .header("x-hub-session", &owner)
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let rotated: Value = serde_json::from_slice(&bytes).unwrap();
    let new_secret = rotated["data"]["secret"].as_str().unwrap().to_string();

    assert_cut(&mut integration, &srv, "the key was rotated").await;

    // …and the integration reconnects with its new secret at once: the cut was for the old one.
    let mut reconnected = ws_with(&srv, &new_secret).await;
    assert_eq!(recv(&mut reconnected).await["type"], "stream.ready");
    something_happens(&srv);
    assert_still_hears(&mut reconnected, "the new secret").await;
}

/// **A ticket outlives nothing.** It is minted, the person signs out within its 60 seconds, and
/// then it is presented: the session it was checked against is gone, so the socket is refused.
#[tokio::test]
async fn a_ticket_minted_before_signing_out_opens_nothing_after_it() {
    let srv = serve().await;
    let owner = srv.owner.clone();
    let t = ticket(&srv, &owner).await;
    sign_out(&srv, &owner).await;

    let mut socket = ws_with(&srv, &t).await;
    let answer = recv(&mut socket).await;
    assert_eq!(answer["type"], "stream.error", "{answer}");
    assert_eq!(answer["code"], "unauthenticated", "{answer}");
}

// ── The SSE door (`GET /api/events`) ───────────────────────────────────────────────────────────

async fn sse(srv: &Server, uri: String, bearer: Option<&str>) -> axum::body::BodyDataStream {
    let mut req = Request::builder().uri(uri);
    if let Some(token) = bearer {
        req = req.header("authorization", format!("Bearer {token}"));
    }
    let resp = app(srv.state.clone())
        .oneshot(req.body(Body::empty()).unwrap())
        .await
        .unwrap();
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

async fn sse_assert_cut(body: &mut axum::body::BodyDataStream, srv: &Server, what: &str) {
    let last = sse_next(body, FRAME_TIMEOUT)
        .await
        .unwrap_or_else(|_| panic!("{what}: the stream ended without saying why"))
        .unwrap_or_else(|| panic!("{what}: the stream was neither cut nor told"));
    assert_eq!(last["type"], "stream.error", "{what}: {last}");
    assert_eq!(last["code"], ERR_CREDENTIAL_ENDED, "{what}: {last}");
    something_happens(srv);
    match sse_next(body, FRAME_TIMEOUT).await {
        Err(()) => {}
        Ok(Some(frame)) => panic!("{what}: the stream kept hearing after the cut: {frame}"),
        Ok(None) => panic!("{what}: the stream was told it ended but was left open"),
    }
}

async fn sse_assert_still_hears(body: &mut axum::body::BodyDataStream, what: &str) {
    let heard = sse_next(body, FRAME_TIMEOUT)
        .await
        .unwrap_or_else(|_| panic!("{what}: the stream ended"))
        .unwrap_or_else(|| panic!("{what}: heard nothing"));
    assert_eq!(heard["type"], "module.installed", "{what}: {heard}");
}

/// **The hole as the issue reports it**: an SSE stream opened with a session's ticket keeps
/// arriving after that session signs out.
#[tokio::test]
async fn signing_out_closes_the_sse_stream_of_that_session_and_no_other() {
    let srv = serve().await;
    let t = ticket(&srv, &srv.owner.clone()).await;
    let mut till = sse(&srv, format!("/api/events?ticket={t}"), None).await;
    let t = ticket(&srv, &srv.owner_elsewhere.clone()).await;
    let mut phone = sse(&srv, format!("/api/events?ticket={t}"), None).await;

    sign_out(&srv, &srv.owner.clone()).await;

    sse_assert_cut(&mut till, &srv, "the till signed out").await;
    sse_assert_still_hears(&mut phone, "the owner's other device").await;
}

/// …and an SSE stream opened with a key ends when the key is revoked.
#[tokio::test]
async fn revoking_a_key_closes_its_sse_stream_and_no_other_keys() {
    let srv = serve().await;
    let (revoked_id, revoked) = read_key(&srv, "Gestoría").await;
    let (_, kept) = read_key(&srv, "Contabilidad").await;
    let mut integration = sse(&srv, "/api/events".into(), Some(&revoked)).await;
    let mut other = sse(&srv, "/api/events".into(), Some(&kept)).await;

    let owner = srv.owner.clone();
    assert_eq!(
        call(&srv, "DELETE", &format!("/api/keys/{revoked_id}"), &owner).await,
        StatusCode::OK
    );

    sse_assert_cut(&mut integration, &srv, "the key was revoked").await;
    sse_assert_still_hears(&mut other, "another key").await;
}
