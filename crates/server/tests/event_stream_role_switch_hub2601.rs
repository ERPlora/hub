//! **Switching an app's role off changes nothing its holders may read or hear** (`PUT
//! /api/hub/roles/{key}`, hub#2601).
//!
//! hub#2571 closes a person's live channel whenever what they may hear changes (a new role, taken
//! off the team). Switching a role off in **Employees → Roles** is not one of those doors: it only
//! decides whether the role can be **handed** to somebody else (`roles::ensure_assignable`, «can no
//! longer be assigned» on screen). The permissions of whoever already holds it are still the union
//! of what the active modules grant to the key (`identity::permissions_for_role`), so their next
//! query is served and their open channel keeps hearing exactly what that query door would serve.
//!
//! What this file pins, over the real router and a real module on disk:
//!
//! 1. After the switch, the holder still reads the module through the query door **and** their
//!    open socket still hears it, without a cut. The two always agree: if switching a role off ever
//!    starts taking permissions away, the first assertion fails here — and that change must then
//!    close the holders' channels with `hub_users::end_live_channels_of`, like hub#2571 does.
//! 2. A ticket minted before the switch still opens a channel: no cut was registered for the
//!    holder, so their screens do not blink every time the administrator tidies the catalogue.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;
use tokio_tungstenite::tungstenite::Message;
use tower::ServiceExt;

use erplora_server::{app, AppState, AuthMode, HubConfig};

const HUB_ID: &str = "hub-role-switch-hub2601";
/// The app that declares its own role.
const KITCHEN: &str = "kitchen";
/// The role the kitchen app declares, and the only key its read permission is granted to.
const COOK: &str = "kitchen";
const READ: &str = "kitchen.view_ticket";

const FRAME_TIMEOUT: Duration = Duration::from_secs(10);
/// Time for a wrongly issued cut to land before the next frame is sent.
const QUIET_WINDOW: Duration = Duration::from_millis(500);

struct Server {
    addr: SocketAddr,
    state: AppState,
    /// The administrator who switches the role.
    admin: String,
    /// A person whose role is the kitchen's own.
    cook: String,
}

fn scratch_dir() -> PathBuf {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    std::env::temp_dir().join(format!(
        "erplora-role-switch-2601-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ))
}

/// The kitchen app on disk: it declares the `kitchen` role, grants it the permission of its one
/// query, and has a command that emits `ticket.created`.
fn kitchen_dir(root: &Path) -> PathBuf {
    let dir = root.join(KITCHEN);
    std::fs::create_dir_all(dir.join("sql")).unwrap();
    let manifest = json!({
        "id": KITCHEN,
        "name": "Kitchen",
        "version": "1.0.0",
        "roles": [{ "key": COOK, "label": "Kitchen", "extends": "employee" }],
        "permissions": [READ],
        "role_permissions": { "admin": [READ], COOK: [READ] },
        "queries": {
            "kitchen.list": { "permission": READ, "sql": "sql/list.sql" }
        },
        "commands": {
            "kitchen.touch": {
                "permission": "",
                "transaction": true,
                "sql": ["sql/run.sql"],
                "emit": ["ticket.created"],
            }
        },
        "events": { "emits": ["ticket.created"] },
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
    rt.install_from_dir(&kitchen_dir(&temp.join("modules")))
        .await
        .unwrap();

    let admin_user = rt
        .create_user("Owner", "1357", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_user, 3600, None).await.unwrap();
    // The role is handed out while it is switched on, as the administrator does in Employees.
    rt.set_role_active(COOK, true, &admin_user).await.unwrap();
    let cook_user = rt.create_user("Iker", "2468", COOK, None).await.unwrap();
    let cook = rt.create_session(&cook_user, 3600, None).await.unwrap();

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
        cook,
    }
}

/// `PUT /api/hub/roles/{key}` with the administrator's session — the toggle of Employees → Roles.
async fn switch_role(srv: &Server, key: &str, active: bool) {
    let req = Request::builder()
        .method("PUT")
        .uri(format!("/api/hub/roles/{key}"))
        .header("x-hub-session", &srv.admin)
        .header("content-type", "application/json")
        .body(Body::from(json!({ "active": active }).to_string()))
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the switch is accepted");
}

/// What the query door answers `session` for the kitchen's query.
async fn reads_the_kitchen(srv: &Server, session: &str) -> StatusCode {
    let req = Request::builder()
        .method("POST")
        .uri("/api/query")
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from(json!({ "name": "kitchen.list" }).to_string()))
        .unwrap();
    app(srv.state.clone()).oneshot(req).await.unwrap().status()
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

/// Runs the kitchen's real command, so the frame is built by the runtime's own `EventSink`.
async fn the_kitchen_emits(srv: &Server) {
    let arc = srv.state.runtime_for(&srv.state.hub_id()).await.unwrap();
    let rt = arc.read().await;
    rt.execute_command(
        "kitchen.touch",
        &Params::new(),
        &RequestContext::new(HUB_ID, "hub_user:1", ["*".to_string()]),
    )
    .await
    .unwrap_or_else(|e| panic!("`kitchen.touch` must run: {e}"));
}

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

/// Opens `/ws` the way the browser does: a ticket in the first frame. Returns the first answer.
async fn open_with(srv: &Server, ticket: &str) -> (Socket, Value) {
    let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{}/ws", srv.addr))
        .await
        .expect("the upgrade succeeds");
    socket
        .send(Message::Text(
            json!({ "type": "auth", "token": ticket }).to_string(),
        ))
        .await
        .unwrap();
    let first = recv(&mut socket).await;
    (socket, first)
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

/// **The contract, over the wire.** The cook listens; the administrator switches the kitchen's
/// role off. The cook may still read the kitchen through the query door, and the socket they
/// opened before the switch hears the kitchen's next event — not a cut.
#[tokio::test]
async fn switching_a_role_off_leaves_its_holders_reading_and_listening() {
    let srv = serve().await;
    let t = ticket(&srv, &srv.cook).await;
    let (mut cook, ready) = open_with(&srv, &t).await;
    assert_eq!(ready["type"], "stream.ready", "{ready}");

    switch_role(&srv, COOK, false).await;

    assert_eq!(
        reads_the_kitchen(&srv, &srv.cook).await,
        StatusCode::OK,
        "switching a role off only stops it from being handed out: its holder keeps reading"
    );
    tokio::time::sleep(QUIET_WINDOW).await;
    the_kitchen_emits(&srv).await;
    let heard = recv(&mut cook).await;
    assert_eq!(heard["name"], "ticket.created", "{heard}");
    assert_eq!(heard["module"], KITCHEN, "{heard}");
}

/// …and no cut is registered for the holder: a ticket their app asked for before the switch still
/// opens a channel, so their screens do not reconnect each time the catalogue is tidied.
#[tokio::test]
async fn a_ticket_minted_before_switching_a_role_off_still_opens() {
    let srv = serve().await;
    let t = ticket(&srv, &srv.cook).await;

    switch_role(&srv, COOK, false).await;

    let (_cook, first) = open_with(&srv, &t).await;
    assert_eq!(first["type"], "stream.ready", "{first}");
}
