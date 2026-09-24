//! **Which till caused this event** (hub#1980).
//!
//! Two tills, each with its own receipt printer and «print on payment» on. Every open shell hears
//! `sale.completed` over `/ws` (one broadcast for the whole hub), and until now the frame did not
//! say which shell's request produced it — so EVERY till printed the ticket, and both papers were
//! «originals».
//!
//! The fix lives on the frame, next to `module` (hub#529): the command door reads the caller's
//! `X-Client-Instance` (a random id each shell tab makes for itself at load) and the event frames
//! that command produces carry it as `client_instance`. The shell prints only the frames it caused.
//!
//! What this file pins, through the REAL door (`POST /api/command`) and the REAL sink:
//!
//! 1. the header travels to the frame, verbatim;
//! 2. no header → no field (an API integration, a flow, a scheduled task: nobody's till);
//! 3. a header that is not a plain short id is DROPPED, not echoed: the value is repeated to every
//!    listener of the hub, so it cannot be a channel for arbitrary text;
//! 4. the module cannot forge it: a payload key of the same name does not become the frame's.
use std::time::Duration;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tower::ServiceExt;

const HUB_ID: &str = "hub-event-client-instance";

fn module_dir(root: &Path) -> PathBuf {
    let dir = root.join("sales");
    std::fs::create_dir_all(dir.join("sql")).unwrap();
    let manifest = json!({
        "id": "sales",
        "name": "sales",
        "version": "1.0.0",
        "commands": {
            "sales.sell": {
                "permission": "sales.sell",
                "transaction": true,
                "sql": ["sql/run.sql"],
                "emit": ["sale.completed"],
            }
        },
        "events": { "emits": ["sale.completed"] },
        "role_permissions": { "admin": ["sales.sell"] },
    });
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    std::fs::write(dir.join("sql/run.sql"), "SELECT 1;").unwrap();
    dir
}

async fn fixture(tag: &str) -> (AppState, String) {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-client-instance-{tag}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&temp);
    rt.install_from_dir(&module_dir(&temp.join("modules")))
        .await
        .unwrap();
    let cashier = rt
        .create_user("Cashier", "1111", "admin", None)
        .await
        .unwrap();
    let session = rt.create_session(&cashier, 3600, None).await.unwrap();
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("cache"),
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
    (AppState::with_config(rt, cfg), session)
}

/// Charges through the shell's own door and returns the `sale.completed` frame it produced.
async fn charge(state: &AppState, session: &str, instance: Option<&str>, payload: Value) -> Value {
    let mut rx = state.events.subscribe();
    let mut req = Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-session", session);
    if let Some(id) = instance {
        req = req.header("x-client-instance", id);
    }
    let body = json!({ "name": "sales.sell", "payload": payload }).to_string();
    let res = app(state.clone())
        .oneshot(req.body(Body::from(body)).unwrap())
        .await
        .unwrap();
    let status = res.status();
    if status != StatusCode::OK {
        let bytes = axum::body::to_bytes(res.into_body(), usize::MAX)
            .await
            .unwrap();
        panic!(
            "the command must run: {status} {}",
            String::from_utf8_lossy(&bytes)
        );
    }
    loop {
        let frame = tokio::time::timeout(Duration::from_secs(5), rx.recv())
            .await
            .expect("timed out waiting for sale.completed")
            .unwrap();
        if frame["name"] == "sale.completed" {
            return frame;
        }
    }
}

#[tokio::test]
async fn the_frame_names_the_client_instance_that_charged_hub1980() {
    let (state, session) = fixture("named").await;
    let frame = charge(&state, &session, Some("till-a-3f9c"), json!({})).await;
    assert_eq!(frame["client_instance"], json!("till-a-3f9c"));
    // Still attributed to its module (hub#529): the new field sits next to it, it does not replace it.
    assert_eq!(frame["module"], json!("sales"));
}

#[tokio::test]
async fn no_header_means_no_till_hub1980() {
    let (state, session) = fixture("absent").await;
    let frame = charge(&state, &session, None, json!({})).await;
    assert!(
        frame.get("client_instance").is_none(),
        "a request without X-Client-Instance is nobody's till: {frame}"
    );
}

#[tokio::test]
async fn a_header_that_is_not_a_short_plain_id_is_dropped_hub1980() {
    let (state, session) = fixture("junk").await;
    for junk in ["", "   ", "<script>x</script>", "a b", &"x".repeat(65)] {
        let frame = charge(&state, &session, Some(junk), json!({})).await;
        assert!(
            frame.get("client_instance").is_none(),
            "{junk:?} must not be echoed to every listener: {frame}"
        );
    }
    // The positive of the same loop: the longest id still accepted reaches the frame.
    let longest = "x".repeat(64);
    let frame = charge(&state, &session, Some(&longest), json!({})).await;
    assert_eq!(frame["client_instance"], json!(longest));
}

#[tokio::test]
async fn the_module_cannot_forge_the_till_through_its_payload_hub1980() {
    let (state, session) = fixture("forged").await;
    // The payload is the module's; the frame field is the hub's. Nothing the module writes reaches it.
    let frame = charge(
        &state,
        &session,
        None,
        json!({ "client_instance": "till-b" }),
    )
    .await;
    assert!(frame.get("client_instance").is_none(), "{frame}");
}
