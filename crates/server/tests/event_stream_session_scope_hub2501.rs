//! **What a PERSON hears on the live channel** (`GET /ws`, `GET /api/events`, hub#2501).
//!
//! hub#529 filtered this channel by the scope of the API key that opened it. The app, though,
//! never opened it with a key of its own person: `POST /api/events/ticket` handed every session —
//! the owner's and the cashier's alike — a ticket bound to the hub's blanket `read_only` key. So a
//! cashier's till heard every event of the business with its payload: customers created, flow
//! questions with the customer's name in the summary, modules the cashier has no permission to
//! open.
//!
//! What this file pins:
//!
//! 1. **A session hears what its role may read through the normal API, and nothing else**, on both
//!    transports. «May read a module» is the dispatcher's own question: the role holds the
//!    permission of at least one query of that module. Every negative is paired with an
//!    administrator connected at the same instant who DOES hear the frame — a channel that had
//!    simply stopped working would pass every negative on its own.
//! 2. **The cashier is not cut off**: the module the role may read still arrives, and so do the
//!    hub's housekeeping frames (an app was installed, a ticket was queued) that every screen needs
//!    and that carry no data about anybody.
//! 3. **The hub's own named events** (a flow asking a question, with the customer in the summary)
//!    go to whoever can answer them — the approvals tray is the administrator's.
//! 4. **A second `auth` on `/ws` does not widen a socket** that is already listening.
//! 5. **The connection cap is per person**, not one for the whole hub.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::api_keys::{ApiKeyAccess, ApiKeyScope};
use erplora_runtime::{RequestContext, Runtime};
use erplora_server::event_stream::MAX_STREAMS_PER_KEY;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;
use tower::ServiceExt;

const HUB_ID: &str = "hub-event-session-scope";
/// The module the cashier's role may read.
const SALES: &str = "sales";
/// The module the cashier's role may NOT read: customer records.
const CUSTOMERS: &str = "customers";

const FRAME_TIMEOUT: Duration = Duration::from_secs(10);
/// The broadcast is in-process: a frame that is coming at all is already here.
const SILENCE_WINDOW: Duration = Duration::from_millis(500);

struct Server {
    addr: SocketAddr,
    state: AppState,
    /// Session of an `employee` — the cashier. Its role may read `sales`, not `customers`.
    cashier: String,
    /// Session of an `admin` — the paired positive of every negative here.
    owner: String,
}

fn scratch_dir() -> PathBuf {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    std::env::temp_dir().join(format!(
        "erplora-event-session-scope-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ))
}

/// A real module on disk: one query gated by `read_permission`, one command that emits `emits`,
/// and the role grants of its manifest.
fn module_dir(
    root: &Path,
    id: &str,
    read_permission: &str,
    emits: &str,
    role_permissions: Value,
) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(dir.join("sql")).unwrap();
    let manifest = json!({
        "id": id,
        "name": id,
        "version": "1.0.0",
        "permissions": [read_permission],
        "role_permissions": role_permissions,
        "queries": {
            format!("{id}.list"): { "permission": read_permission, "sql": "sql/list.sql" }
        },
        "commands": {
            format!("{id}.touch"): {
                "permission": "",
                "transaction": true,
                "sql": ["sql/run.sql"],
                "emit": [emits],
            }
        },
        "events": { "emits": [emits] },
    });
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    std::fs::write(dir.join("sql/list.sql"), "SELECT 1 AS one;").unwrap();
    std::fs::write(dir.join("sql/run.sql"), "SELECT 1;").unwrap();
    dir
}

async fn serve() -> Server {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();

    let temp = scratch_dir();
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(
        &modules,
        SALES,
        "sales.view",
        "sale.completed",
        json!({ "admin": ["sales.view"], "employee": ["sales.view"] }),
    ))
    .await
    .unwrap();
    rt.install_from_dir(&module_dir(
        &modules,
        CUSTOMERS,
        "customers.view",
        "customer.created",
        json!({ "admin": ["customers.view"], "manager": ["customers.view"] }),
    ))
    .await
    .unwrap();

    let cashier_user = rt
        .create_user("Cashier", "1111", "employee", None)
        .await
        .unwrap();
    let cashier = rt.create_session(&cashier_user, 3600, None).await.unwrap();
    let owner_user = rt
        .create_user("Owner", "2222", "admin", None)
        .await
        .unwrap();
    let owner = rt.create_session(&owner_user, 3600, None).await.unwrap();

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
        cashier,
        owner,
    }
}

/// `POST /api/events/ticket` with `session` — exactly what the app does on connect.
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

/// Runs a real command of a real module, so the frame is built by the runtime's own `EventSink`.
async fn run(srv: &Server, command: &str) {
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.read().await;
    rt.execute_command(
        command,
        &Params::new(),
        &RequestContext::new(HUB_ID, "hub_user:1", ["*".to_string()]),
    )
    .await
    .unwrap_or_else(|e| panic!("`{command}` must run: {e}"));
}

/// A flow asking a question: the core's own event, with the customer in the summary — the same
/// shape `flows::executor` publishes through `EventSource::Core` (no `module` on the frame).
fn a_flow_asks_about_a_customer(srv: &Server) {
    let _ = srv.state.events.send(json!({
        "name": "flow.approval.created",
        "payload": {
            "approval_id": "ap-1",
            "title": "Refund Ana García?",
            "summary": "Ana García (+34 600 000 000) asks for a refund of 42 €",
            "assignee_role": "admin",
        },
    }));
}

// ── The WebSocket door ────────────────────────────────────────────────────────────────────────

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

/// Opens `/ws` the way the browser does: no header, a ticket in the first frame.
async fn listen_as(srv: &Server, session: &str) -> Socket {
    let t = ticket(srv, session).await;
    let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{}/ws", srv.addr))
        .await
        .expect("the upgrade succeeds");
    send(&mut socket, json!({ "type": "auth", "token": t })).await;
    assert_eq!(recv(&mut socket).await["type"], "stream.ready");
    socket
}

async fn send(socket: &mut Socket, frame: Value) {
    socket
        .send(tokio_tungstenite::tungstenite::Message::Text(
            frame.to_string(),
        ))
        .await
        .unwrap();
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
        Err(_) | Ok(None) | Ok(Some(Err(_))) => {}
        Ok(Some(Ok(tokio_tungstenite::tungstenite::Message::Text(t)))) => {
            panic!("{what}, but the socket was sent: {t}")
        }
        Ok(Some(Ok(_))) => {}
    }
}

/// **The hole, over the wire.** A customer record is created; the owner's screen hears it, the
/// cashier's — whose role cannot read `customers` through the API — must not.
#[tokio::test]
async fn a_cashier_does_not_hear_a_module_its_role_cannot_read() {
    let srv = serve().await;
    let mut owner = listen_as(&srv, &srv.owner.clone()).await;
    let mut cashier = listen_as(&srv, &srv.cashier.clone()).await;

    run(&srv, "customers.touch").await;

    let heard = recv(&mut owner).await;
    assert_eq!(heard["name"], "customer.created", "{heard}");
    assert_silent(&mut cashier, "a customer record was created").await;
}

/// …and the cashier is not simply cut off: the module its role reads still arrives.
#[tokio::test]
async fn a_cashier_still_hears_the_module_its_role_reads() {
    let srv = serve().await;
    let mut cashier = listen_as(&srv, &srv.cashier.clone()).await;

    run(&srv, "sales.touch").await;

    let heard = recv(&mut cashier).await;
    assert_eq!(heard["name"], "sale.completed", "{heard}");
    assert_eq!(heard["module"], SALES, "{heard}");
}

/// The hub's own housekeeping frames carry no data about anybody and every screen needs them: the
/// menu refreshes when an app is installed, the till learns a ticket is waiting.
#[tokio::test]
async fn a_cashier_still_hears_the_hubs_housekeeping_frames() {
    let srv = serve().await;
    let mut cashier = listen_as(&srv, &srv.cashier.clone()).await;

    srv.state
        .broadcast(json!({ "type": "module.installed", "module_id": SALES }));
    assert_eq!(recv(&mut cashier).await["type"], "module.installed");

    srv.state
        .broadcast(json!({ "type": "print.queued", "role": "kitchen" }));
    assert_eq!(recv(&mut cashier).await["type"], "print.queued");
}

/// A flow's question names the customer. The approvals tray is the administrator's; the cashier's
/// till must not be told.
#[tokio::test]
async fn a_flow_question_reaches_the_owner_and_not_the_cashier() {
    let srv = serve().await;
    let mut owner = listen_as(&srv, &srv.owner.clone()).await;
    let mut cashier = listen_as(&srv, &srv.cashier.clone()).await;

    a_flow_asks_about_a_customer(&srv);

    let heard = recv(&mut owner).await;
    assert_eq!(heard["name"], "flow.approval.created", "{heard}");
    assert_silent(&mut cashier, "a flow asked about a customer").await;
}

/// **A second `auth` does not widen a socket.** The cashier's socket presents a blanket key that
/// may read everything; the socket keeps the audience it opened with.
#[tokio::test]
async fn a_second_auth_does_not_widen_an_open_socket() {
    let srv = serve().await;
    let blanket = {
        let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
        let rt = arc.read().await;
        rt.create_api_key(
            "Borrowed",
            &ApiKeyScope::blanket(ApiKeyAccess::ReadOnly),
            600,
            "hub_user:1",
        )
        .await
        .unwrap()
        .secret
    };
    let mut owner = listen_as(&srv, &srv.owner.clone()).await;
    let mut cashier = listen_as(&srv, &srv.cashier.clone()).await;

    send(&mut cashier, json!({ "type": "auth", "token": blanket })).await;
    let answer = recv(&mut cashier).await;
    assert_eq!(answer["type"], "stream.error", "{answer}");
    assert_eq!(answer["code"], "invalid_payload", "{answer}");

    run(&srv, "customers.touch").await;
    assert_eq!(recv(&mut owner).await["name"], "customer.created");
    assert_silent(&mut cashier, "a customer record was created").await;
}

/// **The cap is per person.** Every screen used to share the hub's one key, so the 17th screen of
/// the whole business heard nothing. One person holding the cap must not lock another out.
#[tokio::test]
async fn one_person_at_the_cap_does_not_lock_another_out() {
    let srv = serve().await;
    let mut held = Vec::new();
    for _ in 0..MAX_STREAMS_PER_KEY {
        held.push(listen_as(&srv, &srv.owner.clone()).await);
    }
    // `listen_as` asserts `stream.ready`: the cashier's first socket is not refused.
    let mut cashier = listen_as(&srv, &srv.cashier.clone()).await;
    run(&srv, "sales.touch").await;
    assert_eq!(recv(&mut cashier).await["name"], "sale.completed");
}

// ── The SSE door (`GET /api/events?ticket=`) ───────────────────────────────────────────────────

async fn sse_as(srv: &Server, session: &str) -> axum::body::BodyDataStream {
    let t = ticket(srv, session).await;
    let req = Request::builder()
        .uri(format!("/api/events?ticket={t}"))
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "a session's ticket streams");
    resp.into_body().into_data_stream()
}

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

/// **The same audience on the other transport.**
#[tokio::test]
async fn the_sse_door_filters_a_session_the_same_way() {
    let srv = serve().await;
    let mut owner = sse_as(&srv, &srv.owner.clone()).await;
    let mut cashier = sse_as(&srv, &srv.cashier.clone()).await;

    run(&srv, "customers.touch").await;
    let heard = sse_next(&mut owner, FRAME_TIMEOUT)
        .await
        .expect("the owner hears the customer record");
    assert_eq!(heard["name"], "customer.created", "{heard}");
    assert!(
        sse_next(&mut cashier, SILENCE_WINDOW).await.is_none(),
        "the cashier's SSE stream must not carry a customer record"
    );

    run(&srv, "sales.touch").await;
    let mine = sse_next(&mut cashier, FRAME_TIMEOUT)
        .await
        .expect("the cashier hears the module its role reads");
    assert_eq!(mine["name"], "sale.completed", "{mine}");
}
