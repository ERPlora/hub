//! **The print host's channel over a real socket** (`GET /ws/print`, hub#343, ADR-0196 §6).
//!
//! `crates/server/src/print_ws.rs` tests the protocol by calling the frame handler directly, which
//! is where the guards live and where they belong. This file exists for the half that testing the
//! handler can never reach: the **transport**. `/ws` had never accepted a single frame from a
//! client — it only ever pushed — so "the socket now listens" is a claim about axum's upgrade, the
//! `select!` between the two directions and the `wake` nudge, none of which a direct call exercises.
//!
//! So this binds a real server on a real port and talks to it with a real WebSocket client:
//! handshake, hello, claim, done, and a nudge arriving unprompted while the host sits idle.
use axum::body::Body;
use axum::http::Request;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use std::net::SocketAddr;
use tokio_tungstenite::tungstenite::Message;

const HUB_ID: &str = "hub-drain-ws";

/// How long a test waits for a frame before calling the channel broken. Generous enough for a
/// loaded CI box, short enough that a hang is a failure and not a timeout of the whole suite.
const FRAME_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(10);

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
    // The device that is going to drain: registered through the runtime, exactly as the HTTP door
    // of hub#342 would have done it.
    rt.register_print_host("till-1", "receipt", "Counter till", &user)
        .await
        .unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-drain-ws-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
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

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

async fn connect(addr: SocketAddr) -> Socket {
    let (socket, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws/print"))
        .await
        .expect("the hub accepts a WebSocket upgrade on the print channel");
    socket
}

async fn send(socket: &mut Socket, frame: Value) {
    socket
        .send(Message::Text(frame.to_string()))
        .await
        .expect("the channel takes a frame from the client");
}

/// Next JSON frame, or a failure — never a hang.
async fn recv(socket: &mut Socket) -> Value {
    loop {
        let next = tokio::time::timeout(FRAME_TIMEOUT, socket.next())
            .await
            .expect("the hub answered within the window");
        match next {
            Some(Ok(Message::Text(t))) => return serde_json::from_str(&t).expect("a JSON frame"),
            // Transport chatter is not protocol.
            Some(Ok(_)) => continue,
            other => panic!("the channel closed instead of answering: {other:?}"),
        }
    }
}

/// Enqueues a ticket through the **public HTTP door**, which is how a job really arrives: the till
/// that charges is not the socket that drains.
async fn enqueue_over_http(srv: &Server, job_id: &str, role: &str) {
    use http_body_util::BodyExt;
    use tower::ServiceExt;

    let body = json!({ "jobId": job_id, "role": role, "html": format!("<p>{job_id}</p>") });
    let resp = app(srv.state.clone())
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/print/jobs")
                .header("x-hub-session", &srv.session)
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(json["ok"], true, "the ticket was queued: {json}");
}

/// **The channel exists and it listens.** Handshake, `hello`, and the hub answering with what this
/// device is for — the first client→server exchange this hub has ever had.
#[tokio::test]
async fn the_hub_accepts_a_print_host_on_a_real_socket() {
    let srv = serve().await;
    let mut socket = connect(srv.addr).await;

    send(
        &mut socket,
        json!({ "type": "hello", "session": srv.session, "deviceId": "till-1" }),
    )
    .await;

    let ready = recv(&mut socket).await;
    assert_eq!(ready["type"], "ready");
    assert_eq!(ready["deviceId"], "till-1");
    assert_eq!(ready["roles"], json!(["receipt"]));
    assert!(
        ready["heartbeatSeconds"].as_i64().unwrap_or(0) > 0,
        "the hub tells the host how often to beat"
    );
}

/// **The handshake window is a window, not an instant.** An unauthenticated socket is hung up on
/// after [`erplora_server::print_ws::HELLO_TIMEOUT_SECONDS`], and the point of that number is that a
/// real client has time to use it: a webview that has just opened the socket still has to read its
/// session out of storage and mint or load its device id.
///
/// Pinned over the wire because the deadline lives in the socket loop, where no frame handler test
/// can reach it — and because a deadline computed the wrong way round (in the past) shuts every
/// print host out of the hub while every other test still passes.
#[tokio::test]
async fn a_host_that_takes_a_moment_to_say_hello_is_still_welcome() {
    let srv = serve().await;
    let mut socket = connect(srv.addr).await;

    // Long enough that a deadline in the past would already have closed the socket, short enough
    // that the real window (15 s) is nowhere near.
    tokio::time::sleep(std::time::Duration::from_millis(400)).await;

    send(
        &mut socket,
        json!({ "type": "hello", "session": srv.session, "deviceId": "till-1" }),
    )
    .await;
    assert_eq!(recv(&mut socket).await["type"], "ready");
}

/// The full round trip over the wire: a ticket queued through HTTP comes out of the socket with its
/// document, and the confirmation closes it.
#[tokio::test]
async fn a_ticket_queued_over_http_is_drained_and_confirmed_over_the_socket() {
    let srv = serve().await;
    enqueue_over_http(&srv, "j1", "receipt").await;
    let mut socket = connect(srv.addr).await;

    send(
        &mut socket,
        json!({ "type": "hello", "session": srv.session, "deviceId": "till-1" }),
    )
    .await;
    assert_eq!(recv(&mut socket).await["type"], "ready");

    send(&mut socket, json!({ "type": "claim", "role": "receipt" })).await;
    let job = recv(&mut socket).await;
    assert_eq!(job["type"], "job");
    assert_eq!(job["jobId"], "j1");
    assert_eq!(job["html"], "<p>j1</p>");

    send(&mut socket, json!({ "type": "done", "jobId": "j1" })).await;
    let ack = recv(&mut socket).await;
    assert_eq!(ack["confirmed"], true);

    // Terminal: the queue has nothing left for this host.
    send(&mut socket, json!({ "type": "claim", "role": "receipt" })).await;
    assert_eq!(recv(&mut socket).await["type"], "idle");
}

/// **The nudge, which is the reason this is a socket at all.** The host is idle and asks for
/// nothing; a sale happens somewhere else and the hub tells it, unprompted. Without this the ticket
/// would sit in the queue until the host next happened to poll.
///
/// It carries the role and not the document: the paper only ever travels in the answer to a claim.
#[tokio::test]
async fn an_idle_host_is_woken_when_a_ticket_is_queued_for_its_role() {
    let srv = serve().await;
    let mut socket = connect(srv.addr).await;
    send(
        &mut socket,
        json!({ "type": "hello", "session": srv.session, "deviceId": "till-1" }),
    )
    .await;
    assert_eq!(recv(&mut socket).await["type"], "ready");

    // Nobody asks the socket for anything. The sale happens on another device entirely.
    enqueue_over_http(&srv, "j-woken", "receipt").await;

    let wake = recv(&mut socket).await;
    assert_eq!(wake["type"], "wake");
    assert_eq!(wake["role"], "receipt");
    assert!(
        wake.get("html").is_none(),
        "a nudge is not a delivery: the document goes through the guarded claim"
    );

    send(&mut socket, json!({ "type": "claim", "role": "receipt" })).await;
    assert_eq!(recv(&mut socket).await["jobId"], "j-woken");
}

/// **A socket that never authenticates drains nothing, over the wire too.** The upgrade succeeds —
/// it has to, there is nowhere to put a credential in a browser's WebSocket handshake — and the
/// refusal lands on the first frame, before anything is read from the queue.
#[tokio::test]
async fn a_socket_that_claims_before_hello_is_refused_and_hung_up_on() {
    let srv = serve().await;
    enqueue_over_http(&srv, "j1", "receipt").await;
    let mut socket = connect(srv.addr).await;

    send(&mut socket, json!({ "type": "claim", "role": "receipt" })).await;

    let refusal = recv(&mut socket).await;
    assert_eq!(refusal["type"], "error");
    assert_eq!(refusal["code"], "print.not_ready");
    assert!(
        refusal.get("html").is_none(),
        "not a byte of the ticket left the hub"
    );

    // And the socket is gone: an anonymous peer does not get to keep trying.
    let closed = tokio::time::timeout(FRAME_TIMEOUT, socket.next())
        .await
        .expect("the hub hung up rather than leaving the socket open");
    assert!(
        matches!(closed, None | Some(Ok(Message::Close(_))) | Some(Err(_))),
        "expected the channel to be closed, got {closed:?}"
    );
}

/// A wrong credential is refused on the wire the same way, and the ticket stays in the queue for
/// the host that is entitled to it.
#[tokio::test]
async fn a_socket_with_an_invalid_session_is_refused_over_the_wire() {
    let srv = serve().await;
    enqueue_over_http(&srv, "j1", "receipt").await;
    let mut socket = connect(srv.addr).await;

    send(
        &mut socket,
        json!({ "type": "hello", "session": "not-a-session", "deviceId": "till-1" }),
    )
    .await;

    let refusal = recv(&mut socket).await;
    assert_eq!(refusal["code"], "unauthenticated");

    // The real host still finds its ticket waiting.
    let mut host = connect(srv.addr).await;
    send(
        &mut host,
        json!({ "type": "hello", "session": srv.session, "deviceId": "till-1" }),
    )
    .await;
    assert_eq!(recv(&mut host).await["type"], "ready");
    send(&mut host, json!({ "type": "claim", "role": "receipt" })).await;
    assert_eq!(recv(&mut host).await["jobId"], "j1");
}
