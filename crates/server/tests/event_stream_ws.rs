//! **The event stream over a real socket and a real SSE request** (`GET /ws`, `GET /api/events`,
//! hub#504).
//!
//! `crates/server/src/event_stream.rs` tests the guard by calling the frame handler directly, which
//! is where the guard lives. This file exists for the part no direct call can reach: whether the
//! **fan-out** actually stops. The hole was never in a refusal message — it was that connecting was
//! enough to be subscribed. So the assertion that matters is negative and has to be made on the
//! wire: a socket that did not authenticate is sent **nothing** while the business trades.
//!
//! Every test here pairs that negative with the positive — the same event, on an authenticated
//! socket, does arrive. A channel that has simply stopped working would pass the negative alone.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::api_keys::{ApiKeyAccess, ApiKeyScope};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::net::SocketAddr;
use tokio_tungstenite::tungstenite::Message;
use tower::ServiceExt;

const HUB_ID: &str = "hub-events-ws";

/// How long a test waits for a frame before calling the channel broken.
const FRAME_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(10);

/// How long the negative assertions wait before concluding that nothing is coming. Short: the
/// broadcast is in-process, so a frame that is coming at all arrives immediately.
const SILENCE_WINDOW: std::time::Duration = std::time::Duration::from_millis(500);

struct Server {
    addr: SocketAddr,
    session: String,
    state: AppState,
}

async fn serve() -> Server {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let user = rt
        .create_user("Cashier", "1111", "employee", None)
        .await
        .unwrap();
    let session = rt.create_session(&user, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-events-ws-{}", std::process::id()));
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
        bootstrap_blueprint: None,
        // hub#376: this hub is not an ephemeral demo.
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
        session,
        state,
    }
}

/// A key of this hub, through the runtime — the same row the keys screen writes.
async fn key_with(srv: &Server, access: ApiKeyAccess) -> String {
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.lock().await;
    rt.create_api_key(
        "Integration",
        &ApiKeyScope::blanket(access),
        60,
        "hub_user:1",
    )
    .await
    .unwrap()
    .secret
}

/// The app asking the hub for its stream credential, over the **real** HTTP door.
async fn ticket_over_http(srv: &Server, session: Option<&str>) -> axum::response::Response {
    let mut req = Request::builder()
        .method("POST")
        .uri("/api/events/ticket")
        .header("content-type", "application/json");
    if let Some(s) = session {
        req = req.header("x-hub-session", s);
    }
    app(srv.state.clone())
        .oneshot(req.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

async fn ticket(srv: &Server) -> String {
    let resp = ticket_over_http(srv, Some(&srv.session)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap();
    json["data"]["ticket"].as_str().unwrap().to_string()
}

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

async fn connect(addr: SocketAddr) -> Socket {
    let (socket, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws"))
        .await
        .expect("the hub accepts a WebSocket upgrade on the event channel");
    socket
}

async fn send(socket: &mut Socket, frame: Value) {
    socket.send(Message::Text(frame.to_string())).await.unwrap();
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

/// Asserts that **nothing** arrives on this socket in [`SILENCE_WINDOW`].
async fn assert_silent(socket: &mut Socket, what: &str) {
    match tokio::time::timeout(SILENCE_WINDOW, socket.next()).await {
        Err(_) => {}
        Ok(None) | Ok(Some(Ok(Message::Close(_)))) | Ok(Some(Err(_))) => {}
        Ok(Some(Ok(Message::Text(t)))) => panic!("{what}, but the socket was sent: {t}"),
        Ok(Some(Ok(_))) => {}
    }
}

/// A sale, published on the very channel the runtime's `EventSink` publishes on.
fn a_sale_happens(srv: &Server) {
    let _ = srv.state.events.send(json!({
        "name": "sale.completed",
        "payload": { "total_cents": 4_250, "customer": "Ana", "lines": 3 },
    }));
}

/// **The hole, over the wire.** Before hub#504 this socket was subscribed the moment it connected,
/// and every sale of the business went down it — to anybody on the internet who knew the subdomain.
///
/// The upgrade still succeeds: a browser cannot put a header on a WebSocket handshake, so there is
/// nowhere to refuse it earlier. What changed is that connecting no longer subscribes.
#[tokio::test]
async fn an_anonymous_socket_is_told_nothing_while_the_business_trades() {
    let srv = serve().await;
    let mut anonymous = connect(srv.addr).await;

    // Give the socket loop a moment to be up, so this is a real race and not a head start.
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    a_sale_happens(&srv);
    assert_silent(&mut anonymous, "a sale went through").await;

    // …and the channel is not simply broken: an authenticated listener hears the next one.
    let ticket = ticket(&srv).await;
    let mut listener = connect(srv.addr).await;
    send(&mut listener, json!({ "type": "auth", "token": ticket })).await;
    assert_eq!(recv(&mut listener).await["type"], "stream.ready");

    a_sale_happens(&srv);
    let event = recv(&mut listener).await;
    assert_eq!(event["name"], "sale.completed");
    assert_eq!(event["payload"]["total_cents"], 4_250);

    // The anonymous socket heard that one either.
    assert_silent(&mut anonymous, "a second sale went through").await;
}

/// **The handshake window is a window, not an instant.** A webview that has just opened the socket
/// still has to fetch its ticket over HTTP before it can say anything, so a deadline computed the
/// wrong way round — in the past — would shut every browser out of the channel while every other
/// test still passed. Pinned over the wire because the deadline lives in the socket loop, where no
/// frame-handler test can reach it. (Same guard `/ws/print` needed, hub#343.)
#[tokio::test]
async fn a_listener_that_takes_a_moment_to_authenticate_is_still_welcome() {
    let srv = serve().await;
    let mut socket = connect(srv.addr).await;

    // Long enough that a deadline in the past would already have closed the socket, short enough
    // that the real window is nowhere near.
    tokio::time::sleep(std::time::Duration::from_millis(400)).await;

    let t = ticket(&srv).await;
    send(&mut socket, json!({ "type": "auth", "token": t })).await;
    assert_eq!(recv(&mut socket).await["type"], "stream.ready");
}

/// The frame cap has to clear the biggest legitimate frame — an `auth` carrying an
/// `erpl_live_<32 hex>_<64 hex>` token, about 130 bytes — with room for whatever the frame grows
/// next, while still being a cap on a peer that has proved nothing. A kilobyte would be neither.
#[test]
fn the_frame_cap_leaves_room_for_a_real_credential_frame() {
    assert!(
        erplora_server::event_stream::MAX_FRAME_BYTES >= 4 * 1024,
        "the cap must clear a credential frame by a wide margin"
    );
    assert!(
        erplora_server::event_stream::MAX_FRAME_BYTES <= 64 * 1024,
        "…and still be a cap: this socket takes bytes before anybody has proved who they are"
    );
}

/// A credential this hub does not know is refused and hung up on — and the socket that is refused
/// never becomes a listener, which is the part that matters.
#[tokio::test]
async fn a_socket_with_an_unknown_key_is_refused_and_hung_up_on() {
    let srv = serve().await;
    let mut socket = connect(srv.addr).await;

    send(
        &mut socket,
        json!({ "type": "auth", "token": "erpl_live_deadbeef_nope" }),
    )
    .await;
    let refusal = recv(&mut socket).await;
    assert_eq!(refusal["type"], "stream.error");
    assert_eq!(refusal["code"], "unauthenticated");

    let closed = tokio::time::timeout(FRAME_TIMEOUT, socket.next())
        .await
        .expect("the hub hung up rather than leaving the socket open");
    assert!(
        matches!(closed, None | Some(Ok(Message::Close(_))) | Some(Err(_))),
        "expected the channel to be closed, got {closed:?}"
    );
}

/// **An integration listens with its own key**, in the header, at the handshake — the door a
/// third party uses, with no ticket involved.
#[tokio::test]
async fn a_client_that_can_set_headers_authenticates_at_the_handshake() {
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;

    let srv = serve().await;
    let token = key_with(&srv, ApiKeyAccess::ReadOnly).await;
    let mut req = format!("ws://{}/ws", srv.addr).into_client_request().unwrap();
    req.headers_mut().insert(
        "authorization",
        format!("Bearer {token}").parse().unwrap(),
    );
    let (mut socket, _) = tokio_tungstenite::connect_async(req).await.unwrap();

    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    a_sale_happens(&srv);
    let event = recv(&mut socket).await;
    assert_eq!(event["name"], "sale.completed");
}

/// **A write-only key connects and still hears nothing.** Authentication and authorisation are two
/// questions; a feed that may only push data in has no business watching what comes out.
#[tokio::test]
async fn a_write_only_key_opens_no_socket() {
    let srv = serve().await;
    let token = key_with(&srv, ApiKeyAccess::WriteOnly).await;
    let mut socket = connect(srv.addr).await;

    send(&mut socket, json!({ "type": "auth", "token": token })).await;
    let refusal = recv(&mut socket).await;
    assert_eq!(refusal["code"], "events.read_required");
    assert_ne!(
        refusal["code"], "unauthenticated",
        "the two refusals must stay distinguishable"
    );
}

// ── The SSE door (`GET /api/events`) ─────────────────────────────────────────────────────────

async fn sse(srv: &Server, uri: &str, bearer: Option<&str>) -> axum::response::Response {
    let mut req = Request::builder().uri(uri);
    if let Some(token) = bearer {
        req = req.header("authorization", format!("Bearer {token}"));
    }
    app(srv.state.clone())
        .oneshot(req.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

async fn code_of(resp: axum::response::Response) -> String {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap();
    json["error"]["code"].as_str().unwrap_or_default().to_string()
}

/// The other half of the same hole: `curl -N https://<slug>.erplora.com/api/events`, no headers.
#[tokio::test]
async fn the_sse_door_refuses_a_request_without_a_credential() {
    let srv = serve().await;
    let resp = sse(&srv, "/api/events", None).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(code_of(resp).await, "unauthenticated");
}

#[tokio::test]
async fn the_sse_door_streams_to_a_read_key_and_refuses_a_write_only_one() {
    let srv = serve().await;

    let read_key = key_with(&srv, ApiKeyAccess::ReadOnly).await;
    let resp = sse(&srv, "/api/events", Some(&read_key)).await;
    assert_eq!(resp.status(), StatusCode::OK);
    let ct = resp
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default()
        .to_string();
    assert!(ct.starts_with("text/event-stream"), "content-type = {ct}");
    // El body es un stream infinito (keep-alive) → no se consume en el test.

    let write_key = key_with(&srv, ApiKeyAccess::WriteOnly).await;
    let resp = sse(&srv, "/api/events", Some(&write_key)).await;
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    assert_eq!(code_of(resp).await, "events.read_required");
}

/// The browser's only option on `EventSource`: a single-use ticket in the query string. It works
/// once, and the reconnect has to ask for another — which is what makes putting it in a URL
/// acceptable at all.
#[tokio::test]
async fn the_sse_door_takes_a_ticket_in_the_query_and_spends_it() {
    let srv = serve().await;
    let t = ticket(&srv).await;

    let resp = sse(&srv, &format!("/api/events?ticket={t}"), None).await;
    assert_eq!(resp.status(), StatusCode::OK);

    let resp = sse(&srv, &format!("/api/events?ticket={t}"), None).await;
    assert_eq!(
        resp.status(),
        StatusCode::UNAUTHORIZED,
        "a spent ticket is not a credential"
    );
}

/// **The ticket door needs a session.** If it did not, the hub would be handing its own read-only
/// credential to anybody who asked, and the whole chain above would be decoration.
#[tokio::test]
async fn the_ticket_door_needs_a_session() {
    let srv = serve().await;

    let resp = ticket_over_http(&srv, None).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(code_of(resp).await, "unauthenticated");

    let resp = ticket_over_http(&srv, Some("not-a-session")).await;
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

    // With a real session it mints — and the key it minted is the hub's own, marked so the keys
    // screen shows it and refuses to delete it.
    let t = ticket(&srv).await;
    assert!(t.starts_with("erpl_tkt_"));
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.lock().await;
    let keys = rt.list_api_keys().await.unwrap();
    assert_eq!(keys.len(), 1, "one key, however many tickets were asked for");
    assert!(keys[0].system);
    assert_eq!(keys[0].access, ApiKeyAccess::ReadOnly);
}
