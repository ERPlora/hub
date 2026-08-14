//! **The dead-letter queue, seen from a MODULE** (hub#953) — the second gate of `/api/hub/events*`.
//!
//! `@erplora/module-sdk` grows the six dead-letter gestures so `ERPlora/flows#20` can draw the
//! «needs your attention» tray. The routes themselves are hub#660's and do not move. What moves is
//! WHO can be behind them: until now the only gate was «a human owner/admin session», which was the
//! right answer while the shell's System → Events tab was the only caller. The moment a typed
//! surface exists, «an admin is logged in» would mean **every installed module** can list, replay
//! and close the events of every other one.
//!
//! So the door gains the same second gate `…/events/shape` (hub#715) and `…/events` (hub#823)
//! already have, for a stronger version of the same reason (ADR-0312):
//!
//! 1. **A dead-letter carries the whole payload.** `…/shape` redacts what could be about a person
//!    and `…/events` answers names only; this queue answers `{"customer":{"email":…}}` verbatim,
//!    because there an operator is deciding whether to replay one specific row and the payload IS
//!    the decision. It is the widest read of the three and it was the least gated.
//! 2. **Replaying is an ACTION with somebody else's authority.** Since hub#686 a listener runs with
//!    its own module's permissions, so `POST …/retry` re-runs another module's command as that
//!    module. An inventory app that can replay the till's events is not reading a business, it is
//!    driving one.
//! 3. **Discarding closes a record for good.**
//!
//! `require_flows_capability` passes when the caller names NO module, so the shell's own bell and
//! System → Events tab (`apps/web/src/lib/dead-letter.ts`, which sends no `X-Erplora-Module`) and
//! `curl` with an admin session are untouched. That is pinned below too: this narrows the door for
//! modules and for nobody else.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tower::ServiceExt;

const HUB: &str = "hub-dead-letter-door";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module the owner installed to edit and watch flows: it DECLARES `manage_flows`.
const EDITOR: &str = "flows_editor";
/// An ordinary installed module. It must not get to read — much less replay — what died.
const INVENTORY: &str = "inventory";

/// One row per gesture, so the mutating ones do not eat each other's subject.
const DEAD_LISTED: &str = "evt-dead-listed";
const DEAD_RETRY: &str = "evt-dead-retry";
const DEAD_DISCARD: &str = "evt-dead-discard";

struct Fixture {
    router: axum::Router,
    admin: String,
    temp: PathBuf,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// A module on disk, so the installer registers a REAL manifest — the capability gate reads what
/// the module declared, not what a test asserted.
fn module_dir(root: &Path, id: &str, extra: Value) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
    let mut manifest = json!({ "id": id, "name": id, "version": "1.0.0" });
    if let Value::Object(map) = extra {
        for (k, v) in map {
            manifest[k] = v;
        }
    }
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    dir
}

/// A row the relay gave up on, with a payload that names a person — the thing this gate is about.
async fn seed_dead(db: &dyn DatabaseAdapter, id: &str) {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(HUB));
    p.insert(
        "payload".into(),
        json!(r#"{"invoice_id":"F2-1","customer":{"email":"marta@example.com"}}"#),
    );
    p.insert("at".into(), json!("2026-08-09T10:00:00+00:00"));
    db.execute(
        "INSERT INTO _event_outbox \
         (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, status, \
          attempts, next_attempt_at, last_error, created_at) \
         VALUES (:id, :hub_id, 'cashier-1', '[]', 'sale.closed', 'sales', :payload, 1, 'dead', \
                 8, :at, 'verifactu.records.ingest_invoice: permission_denied', :at)",
        &p,
    )
    .await
    .unwrap();
}

/// `granted` = the owner ticked `manage_flows` for the editor in Settings → Permissions.
async fn fixture(granted: bool) -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();

    let admin_id = rt.create_user("Ioan", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();

    for id in [DEAD_LISTED, DEAD_RETRY, DEAD_DISCARD] {
        seed_dead(rt.db_for_test(), id).await;
    }

    let temp = std::env::temp_dir().join(format!(
        "erplora-dead-letter-door-{}-{admin_id}",
        std::process::id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(
        &modules,
        EDITOR,
        json!({ "capabilities": { "manage_flows": {} } }),
    ))
    .await
    .unwrap();
    rt.install_from_dir(&module_dir(&modules, INVENTORY, json!({})))
        .await
        .unwrap();
    if granted {
        rt.set_module_capability(EDITOR, "manage_flows", true, "hub_user:admin")
            .await
            .unwrap();
    }

    let cfg = HubConfig {
        demo: false,
        hub_id: HUB.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        admin,
        temp,
    }
}

fn request(method: &str, uri: &str, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if let Some(id) = module {
        builder = builder.header(MODULE_HEADER, id);
    }
    builder.body(Body::empty()).unwrap()
}

async fn send(router: &axum::Router, request: Request<Body>) -> axum::response::Response {
    router.clone().oneshot(request).await.unwrap()
}

/// Every gesture of the queue, as `(method, uri)`. The list is here so a route added later without
/// a gate turns this red instead of shipping open.
///
/// Ordered so that a caller who gets THROUGH all six leaves each row to its own gesture:
/// `retry-all` goes last because it sweeps every remaining dead row, and a `retry` after it would
/// meet a `pending` one and answer `404` for a reason that has nothing to do with any gate.
fn every_gesture() -> Vec<(&'static str, String)> {
    vec![
        ("GET", "/api/hub/events/dead".to_string()),
        ("GET", "/api/hub/events/dead/count".to_string()),
        ("GET", format!("/api/hub/events/{DEAD_LISTED}/trace")),
        ("POST", format!("/api/hub/events/{DEAD_RETRY}/retry")),
        ("POST", format!("/api/hub/events/{DEAD_DISCARD}/discard")),
        ("POST", "/api/hub/events/retry-all".to_string()),
    ]
}

/// **The gate that hub#953 adds.** An ordinary installed module, calling inside a real admin's
/// session, must not be able to see what died — let alone replay it with the emitter's authority.
#[tokio::test]
async fn an_ordinary_module_never_reaches_the_dead_letter_queue() {
    let f = fixture(true).await;

    for (method, uri) in every_gesture() {
        let refused = send(
            &f.router,
            request(method, &uri, Some(&f.admin), Some(INVENTORY)),
        )
        .await;
        assert_eq!(
            refused.status(),
            StatusCode::FORBIDDEN,
            "{method} {uri} let a module without `manage_flows` in"
        );
        let body = body_json(refused).await;
        assert_eq!(
            body["error"]["code"],
            json!("capability_denied"),
            "the refusal has to be the code that lets a screen ask for the grant: {body}"
        );
        // The refusal is not a 403 that still leaked the row on the way out.
        assert!(
            !body.to_string().contains("marta@example.com"),
            "a refused call still returned a payload: {body}"
        );
    }

    // Nothing the refused module did moved a row: all three are still dead.
    let listed = body_json(
        send(
            &f.router,
            request("GET", "/api/hub/events/dead", Some(&f.admin), None),
        )
        .await,
    )
    .await;
    assert_eq!(
        listed["data"].as_array().unwrap().len(),
        3,
        "a refused call must not have retried or discarded anything: {listed}"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// Declaring the capability is not being granted it: the same editor, before the owner ticks the
/// box in Settings → Permissions, is exactly as refused as the inventory app.
#[tokio::test]
async fn declaring_manage_flows_is_not_the_same_as_being_granted_it() {
    let f = fixture(false).await;

    for (method, uri) in every_gesture() {
        let refused = send(
            &f.router,
            request(method, &uri, Some(&f.admin), Some(EDITOR)),
        )
        .await;
        assert_eq!(
            refused.status(),
            StatusCode::FORBIDDEN,
            "{method} {uri} let an UNGRANTED module in"
        );
        assert_eq!(
            body_json(refused).await["error"]["code"],
            json!("capability_denied")
        );
    }

    std::fs::remove_dir_all(f.temp).ok();
}

/// With the manifest declaring it and the owner granting it, the editor reaches all six — which is
/// the half of flows#20 that could not be built. Ordered so each mutating gesture has its own row.
#[tokio::test]
async fn the_granted_editor_reaches_every_gesture() {
    let f = fixture(true).await;

    for (method, uri) in every_gesture() {
        let response = send(
            &f.router,
            request(method, &uri, Some(&f.admin), Some(EDITOR)),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "{method} {uri} refused the module the owner chose for this"
        );
        assert_eq!(body_json(response).await["ok"], json!(true));
    }

    std::fs::remove_dir_all(f.temp).ok();
}

/// **The narrowing stops at modules.** The shell's own bell and System → Events tab send no
/// `X-Erplora-Module` (`apps/web/src/lib/dead-letter.ts` uses `runtimeHeaders()`), and neither does
/// an operator with `curl`. Both keep working on the admin session alone — this test is what would
/// catch the day the gate is applied to the session instead of to the module.
#[tokio::test]
async fn the_shell_and_curl_name_no_module_and_are_untouched() {
    let f = fixture(true).await;

    for (method, uri) in every_gesture() {
        let response = send(&f.router, request(method, &uri, Some(&f.admin), None)).await;
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "{method} {uri} broke the shell, which names no module"
        );
    }

    // A blank header is the same as none: the shell must not have to strip an empty string.
    let blank = send(
        &f.router,
        request("GET", "/api/hub/events/dead", Some(&f.admin), Some("   ")),
    )
    .await;
    assert_eq!(blank.status(), StatusCode::OK);

    std::fs::remove_dir_all(f.temp).ok();
}
