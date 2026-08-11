//! **What comes OUT of the event channel** (`GET /ws`, `GET /api/events`, hub#529).
//!
//! hub#504 put a door on this channel: nobody listens without an API key of this hub that may
//! read. It did not put a **filter** behind it — once inside, the fan-out was all-or-nothing. A
//! `custom` key with read on `invoice` (the accountant's key of ADR-0057 §7) also heard
//! `sale.completed`, whatever `cash_register` emits and every kitchen order, payloads included.
//! The permission decided **who enters** and not **what they take**, which makes the module ×
//! {read, write} matrix decorative on this channel.
//!
//! What this file pins:
//!
//! 1. **A scoped key hears its modules and nothing else**, on **both** transports. The negative is
//!    always paired with a live listener that DOES hear the same frame — a channel that had simply
//!    stopped working would pass every negative on its own.
//! 2. **The neighbour emits for real**: the events come out of a real declarative command of a
//!    real installed module, through the runtime's own `EventSink`. Nothing here fabricates a
//!    frame, because the whole question is what the emitter puts on it.
//! 3. **The module is declared, not guessed from the name.** `sales` emits an event *called*
//!    `invoice.paid`; the accountant's key, scoped to `invoice`, must not get it. An
//!    implementation that split the event name on `.` would pass every other test in this file.
//! 4. **The shell keeps hearing everything.** The app reads with the hub's own blanket
//!    `read_only` key: the filter is for scoped third-party keys, not for the owner watching their
//!    own till.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::api_keys::{ApiKeyAccess, ApiKeyScope, ScopeEntry};
use erplora_runtime::{RequestContext, Runtime};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::StreamExt;
use serde_json::{json, Value};
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tower::ServiceExt;

const HUB_ID: &str = "hub-event-scope";
/// The module the accountant's key is scoped to.
const INVOICE: &str = "invoice";
/// The neighbour. The accountant may not read it — and it is alive and trading throughout.
const SALES: &str = "sales";

/// How long a test waits for a frame it expects before calling the channel broken.
const FRAME_TIMEOUT: Duration = Duration::from_secs(10);
/// How long a negative waits before concluding nothing is coming. The broadcast is in-process, so
/// a frame that is coming at all is already here.
const SILENCE_WINDOW: Duration = Duration::from_millis(500);

struct Server {
    addr: SocketAddr,
    state: AppState,
}

/// A module on disk, so the installer registers a REAL manifest and the runtime dispatches a REAL
/// command. `emit` is what ends up on the channel.
fn module_dir(root: &Path, id: &str, commands: Value, emits: Value) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(dir.join("sql")).unwrap();
    let manifest = json!({
        "id": id,
        "name": id,
        "version": "1.0.0",
        "commands": commands,
        "events": { "emits": emits },
    });
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    // No business effect: the command exists to emit.
    std::fs::write(dir.join("sql/run.sql"), "SELECT 1;").unwrap();
    dir
}

fn command(emit: &[&str]) -> Value {
    json!({
        "permission": "",
        "transaction": true,
        "sql": ["sql/run.sql"],
        "emit": emit,
    })
}

async fn serve() -> Server {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-event-scope-{}-{:?}",
        std::process::id(),
        std::thread::current().id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(
        &modules,
        INVOICE,
        json!({ "invoice.issue": command(&["invoice.issued"]) }),
        json!(["invoice.issued"]),
    ))
    .await
    .unwrap();
    // `sales` emits an event of its own AND one named after the neighbour's namespace. The second
    // is the trap: the event name is a convention nobody verifies, so a filter that reads the
    // module out of `invoice.paid` would hand the accountant a sale.
    rt.install_from_dir(&module_dir(
        &modules,
        SALES,
        json!({ "sales.sell": command(&["sale.completed", "invoice.paid"]) }),
        json!(["sale.completed", "invoice.paid"]),
    ))
    .await
    .unwrap();

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

    Server { addr, state }
}

/// The accountant's key: `custom`, read on `invoice`, nothing else (ADR-0057 §7).
async fn accountant_key(srv: &Server) -> String {
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.lock().await;
    rt.create_api_key(
        "Gestoría",
        &ApiKeyScope::custom(vec![ScopeEntry {
            module: INVOICE.into(),
            read: true,
            write: false,
        }]),
        600,
        "hub_user:1",
    )
    .await
    .unwrap()
    .secret
}

/// A blanket `read_only` key — what the hub issues to its own app. It is the paired positive of
/// every negative here: the same frame, at the same instant, on a listener entitled to it.
async fn shell_key(srv: &Server) -> String {
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.lock().await;
    rt.create_api_key(
        "Shell",
        &ApiKeyScope::blanket(ApiKeyAccess::ReadOnly),
        600,
        "hub_user:1",
    )
    .await
    .unwrap()
    .secret
}

/// Runs a real command of a real module: the events go out through the runtime's `EventSink`,
/// which is the only place that knows who emitted them.
async fn run(srv: &Server, command: &str) {
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.lock().await;
    rt.execute_command(
        command,
        &Params::new(),
        &RequestContext::new(HUB_ID, "hub_user:1", ["*".to_string()]),
    )
    .await
    .unwrap_or_else(|e| panic!("`{command}` must run: {e}"));
}

// ── The WebSocket door ────────────────────────────────────────────────────────────────────────

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

/// Opens a socket authenticated at the handshake, the way a third-party integration does.
async fn listen(addr: SocketAddr, token: &str) -> Socket {
    let mut req = format!("ws://{addr}/ws").into_client_request().unwrap();
    req.headers_mut()
        .insert("authorization", format!("Bearer {token}").parse().unwrap());
    let (socket, _) = tokio_tungstenite::connect_async(req)
        .await
        .expect("a read-entitled key opens the socket");
    socket
}

async fn recv(socket: &mut Socket) -> Value {
    loop {
        let next = tokio::time::timeout(FRAME_TIMEOUT, socket.next())
            .await
            .expect("the hub answered within the window");
        match next {
            Some(Ok(tokio_tungstenite::tungstenite::Message::Text(t))) => {
                return serde_json::from_str(&t).expect("a JSON frame")
            }
            Some(Ok(_)) => continue,
            other => panic!("the channel closed instead of answering: {other:?}"),
        }
    }
}

async fn assert_silent(socket: &mut Socket, what: &str) {
    match tokio::time::timeout(SILENCE_WINDOW, socket.next()).await {
        Err(_) => {}
        Ok(None) | Ok(Some(Err(_))) => {}
        Ok(Some(Ok(tokio_tungstenite::tungstenite::Message::Text(t)))) => {
            panic!("{what}, but the socket was sent: {t}")
        }
        Ok(Some(Ok(_))) => {}
    }
}

/// **The hole, over the wire.** The accountant's key may read `invoice` and only `invoice`. It used
/// to hear every sale of the business, with the payload.
///
/// The sale is real (a command of `sales` runs), and a blanket listener is connected at the same
/// time and does hear it — so the silence below is the filter, not a dead channel.
#[tokio::test]
async fn a_key_scoped_to_one_module_hears_nothing_of_the_neighbour_on_the_socket() {
    let srv = serve().await;
    let mut accountant = listen(srv.addr, &accountant_key(&srv).await).await;
    let mut shell = listen(srv.addr, &shell_key(&srv).await).await;
    tokio::time::sleep(Duration::from_millis(100)).await;

    run(&srv, "sales.sell").await;

    // The paired positive: the sale really happened and really went on the channel.
    let heard = recv(&mut shell).await;
    assert_eq!(heard["name"], "sale.completed", "{heard}");

    assert_silent(&mut accountant, "the neighbour completed a sale").await;
}

/// …and the accountant is not simply cut off: its own module's events arrive. Without this, a
/// filter that refused everything would look correct.
#[tokio::test]
async fn the_scoped_key_still_hears_its_own_module_on_the_socket() {
    let srv = serve().await;
    let mut accountant = listen(srv.addr, &accountant_key(&srv).await).await;
    tokio::time::sleep(Duration::from_millis(100)).await;

    run(&srv, "invoice.issue").await;

    let heard = recv(&mut accountant).await;
    assert_eq!(heard["name"], "invoice.issued", "{heard}");
}

/// **The name of an event is not proof of who emitted it.** `sales` emits `invoice.paid`; the
/// accountant may read `invoice`. A filter that took the module from the name's prefix would hand
/// over a sale of a module this key was never given.
#[tokio::test]
async fn an_event_named_after_another_module_does_not_reach_that_modules_key() {
    let srv = serve().await;
    let mut accountant = listen(srv.addr, &accountant_key(&srv).await).await;
    let mut shell = listen(srv.addr, &shell_key(&srv).await).await;
    tokio::time::sleep(Duration::from_millis(100)).await;

    run(&srv, "sales.sell").await;

    // Both events of `sales` land on the blanket listener, `invoice.paid` among them.
    let mut names = vec![recv(&mut shell).await, recv(&mut shell).await];
    names.sort_by_key(|f| f["name"].as_str().unwrap_or_default().to_string());
    assert_eq!(names[0]["name"], "invoice.paid", "{:?}", names);
    assert_eq!(names[1]["name"], "sale.completed", "{:?}", names);

    assert_silent(
        &mut accountant,
        "`sales` emitted an event named `invoice.paid`",
    )
    .await;
}

/// **The shell is not the one being filtered.** The app reads with the hub's own blanket
/// `read_only` key; the owner watching their own till must keep seeing everything, including the
/// hub's own system frames.
#[tokio::test]
async fn the_blanket_read_key_of_the_shell_still_hears_the_whole_hub() {
    let srv = serve().await;
    let mut shell = listen(srv.addr, &shell_key(&srv).await).await;
    tokio::time::sleep(Duration::from_millis(100)).await;

    run(&srv, "invoice.issue").await;
    assert_eq!(recv(&mut shell).await["name"], "invoice.issued");

    run(&srv, "sales.sell").await;
    let a = recv(&mut shell).await;
    let b = recv(&mut shell).await;
    let mut heard = [a["name"].as_str().unwrap(), b["name"].as_str().unwrap()];
    heard.sort();
    assert_eq!(heard, ["invoice.paid", "sale.completed"]);

    // A system frame — nobody's module, the hub's own fact.
    srv.state
        .broadcast(json!({ "type": "module.installed", "module_id": SALES }));
    assert_eq!(recv(&mut shell).await["type"], "module.installed");
}

/// **A frame that belongs to no module is the hub's own**, and a key scoped to modules was never
/// given the hub. `module.installed`, `module.install.progress` and `print.queued` say what the
/// business is doing at the till; a third-party integration scoped to `invoice` has no claim on
/// them. The blanket listener alive at the same instant proves the frame was published.
#[tokio::test]
async fn a_system_frame_does_not_reach_a_key_scoped_to_modules() {
    let srv = serve().await;
    let mut accountant = listen(srv.addr, &accountant_key(&srv).await).await;
    let mut shell = listen(srv.addr, &shell_key(&srv).await).await;
    tokio::time::sleep(Duration::from_millis(100)).await;

    srv.state
        .broadcast(json!({ "type": "print.queued", "role": "kitchen" }));

    assert_eq!(recv(&mut shell).await["type"], "print.queued");
    assert_silent(&mut accountant, "a ticket was queued for the kitchen").await;
}

// ── The SSE door (`GET /api/events`) ──────────────────────────────────────────────────────────

/// Opens the SSE stream with a bearer token and hands back its body, already subscribed.
async fn sse_stream(srv: &Server, token: &str) -> axum::body::BodyDataStream {
    let req = Request::builder()
        .uri("/api/events")
        .header("authorization", format!("Bearer {token}"))
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "a read-entitled key streams");
    resp.into_body().into_data_stream()
}

/// Next `data:` frame on an SSE body, or `None` if `window` passes in silence.
async fn sse_next(body: &mut axum::body::BodyDataStream, window: Duration) -> Option<Value> {
    let deadline = tokio::time::Instant::now() + window;
    let mut buffered = String::new();
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        if left.is_zero() {
            return None;
        }
        match tokio::time::timeout(left, body.next()).await {
            Err(_) | Ok(None) | Ok(Some(Err(_))) => return None,
            Ok(Some(Ok(chunk))) => {
                buffered.push_str(&String::from_utf8_lossy(&chunk));
                for line in buffered.lines() {
                    if let Some(rest) = line.strip_prefix("data:") {
                        if let Ok(v) = serde_json::from_str::<Value>(rest.trim()) {
                            return Some(v);
                        }
                    }
                }
            }
        }
    }
}

/// **The same filter on the other transport.** Two doors and one filter: if the rule were written
/// twice, one copy could be deleted with the whole suite green — so each door gets its own test.
#[tokio::test]
async fn the_sse_door_filters_by_scope_the_same_way() {
    let srv = serve().await;
    let mut accountant = sse_stream(&srv, &accountant_key(&srv).await).await;
    let mut shell = sse_stream(&srv, &shell_key(&srv).await).await;

    run(&srv, "sales.sell").await;

    // Paired positive: the sale is on the channel.
    let heard = sse_next(&mut shell, FRAME_TIMEOUT)
        .await
        .expect("the blanket listener hears the sale");
    assert_eq!(heard["name"], "sale.completed", "{heard}");

    assert!(
        sse_next(&mut accountant, SILENCE_WINDOW).await.is_none(),
        "the accountant's SSE stream must not carry the neighbour's sale"
    );

    // …and it is not a dead stream: its own module still arrives.
    run(&srv, "invoice.issue").await;
    let mine = sse_next(&mut accountant, FRAME_TIMEOUT)
        .await
        .expect("its own module's event arrives");
    assert_eq!(mine["name"], "invoice.issued", "{mine}");
}
