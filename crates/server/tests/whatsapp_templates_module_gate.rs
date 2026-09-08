//! The gate that keeps the templates door from becoming a PUBLIC door the day a module can reach
//! it (hub#1682).
//!
//! hub#1610 opened three runtime routes that register, list and delete the templates the business
//! promises Meta, behind an owner/admin session. Nothing could call them from module code, so the
//! session was the whole gate and that was enough. hub#1682 gives `@erplora/module-sdk` a typed
//! surface for exactly those routes — and the moment it exists, EVERY installed module can reach
//! them whenever an admin happens to be logged in: the inventory app the owner installed could
//! delete every approved template of the business, and with them every appointment reminder, every
//! «your order is ready» and every confirmation, all of which take days to get approved again.
//!
//! So the surface arrives WITH its gate, in the same change, and the gate is the one the kernel
//! already has: `crates/server/src/flows_api.rs::require_module_capability`, hung here on
//! **`notify`** — the capability the owner already grants as «Notificaciones · permite enviar
//! notificaciones por email, SMS o WhatsApp» (`crates/server/src/settings.rs`). No new capability:
//! a Meta template is the only thing that makes a WhatsApp notification legal outside the 24 h
//! since the customer last wrote, so registering one is the same risk the owner weighed when they
//! granted `notify`, not a different one.
//!
//! ⚠️ **The hub#1677 exception does NOT apply here.** `admin_session_no_capability!` drops the
//! capability half for the flow-template switches because the call site replaces it with a
//! narrower rule — a module may only touch recipes ITS OWN publisher wrote. A Meta template has no
//! owning module: it belongs to the business, it is stored per hub in the SaaS, and there is no
//! narrower rule to put in the gate's place. With nothing to replace it, the default-deny gate
//! stays.
//!
//! What is asserted: a module that has not been granted `notify` is refused on all three doors and
//! the SaaS is NEVER called; the same module with the grant gets through; and the shell — which
//! names no module — keeps passing exactly as it did before this change.
use axum::body::Body;
use axum::extract::Path;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::{delete, get};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use std::path::{Path as FsPath, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use tower::ServiceExt;

const HUB: &str = "hub-wa-gate";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module that owns the «Plantillas» tab and therefore the one that calls this door.
const WHATSAPP: &str = "whatsapp_inbox";

/// A module on disk that DECLARES `notify`. Declaring is not being granted: the owner still has to
/// tick it in Settings → Permissions, which is what `granted` does below.
fn module_dir(root: &FsPath, id: &str) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
    let manifest = json!({
        "id": id,
        "name": id,
        "version": "2.1.51",
        "capabilities": { "notify": {} }
    });
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    dir
}

struct Fixture {
    router: Router,
    admin: String,
    /// How many times the fake SaaS was called. A refusal that still calls Meta is not a refusal.
    saas_calls: Arc<AtomicUsize>,
}

async fn fixture(granted: bool, tag: &str) -> Fixture {
    let saas_calls = Arc::new(AtomicUsize::new(0));
    let cloud_base_url = fake_saas(saas_calls.clone()).await;

    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-wa-gate-{tag}-{}-{}",
        std::process::id(),
        granted
    ));
    rt.install_from_dir(&module_dir(&temp.join("modules"), WHATSAPP))
        .await
        .unwrap();
    if granted {
        rt.set_module_capability(WHATSAPP, "notify", true, "hub_user:admin")
            .await
            .unwrap();
    }

    let config = HubConfig {
        demo: false,
        hub_id: HUB.into(),
        cloud_base_url,
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
    };
    Fixture {
        router: app(AppState::with_config(rt, config)),
        admin,
        saas_calls,
    }
}

/// A SaaS that answers every door and COUNTS: what matters here is whether it was reached at all.
async fn fake_saas(calls: Arc<AtomicUsize>) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (c1, c2, c3) = (calls.clone(), calls.clone(), calls.clone());
    let saas = Router::new()
        .route(
            "/api/v1/hub/device/whatsapp/templates/",
            get(move |_: HeaderMap| {
                let c = c1.clone();
                async move {
                    c.fetch_add(1, Ordering::SeqCst);
                    Json(json!({ "templates": [], "stale": false }))
                }
            })
            .post(move |_: HeaderMap, Json(_): Json<Value>| {
                let c = c2.clone();
                async move {
                    c.fetch_add(1, Ordering::SeqCst);
                    (
                        StatusCode::CREATED,
                        Json(json!({ "name": "table_ready", "status": "PENDING" })),
                    )
                }
            }),
        )
        .route(
            "/api/v1/hub/device/whatsapp/templates/:name/",
            delete(move |Path(_): Path<String>, _: HeaderMap| {
                let c = c3.clone();
                async move {
                    c.fetch_add(1, Ordering::SeqCst);
                    StatusCode::NO_CONTENT
                }
            }),
        );
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

/// The three doors, as the SDK surface calls them.
fn doors() -> [(&'static str, &'static str, Option<Value>); 3] {
    [
        ("GET", "/api/hub/whatsapp/templates", None),
        (
            "POST",
            "/api/hub/whatsapp/templates",
            Some(json!({ "name": "table_ready", "language": "es" })),
        ),
        ("DELETE", "/api/hub/whatsapp/templates/table_ready", None),
    ]
}

fn request(
    method: &str,
    uri: &str,
    session: &str,
    module: Option<&str>,
    body: Option<Value>,
) -> Request<Body> {
    let mut req = Request::builder().method(method).uri(uri);
    if body.is_some() {
        req = req.header("content-type", "application/json");
    }
    req = req.header("x-hub-session", session);
    if let Some(m) = module {
        req = req.header(MODULE_HEADER, m);
    }
    req.body(body.map_or(Body::empty(), |b| Body::from(b.to_string())))
        .unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

#[tokio::test]
async fn a_module_the_owner_never_granted_notify_reaches_none_of_the_three_doors() {
    let f = fixture(false, "denied").await;

    for (method, uri, body) in doors() {
        let response = f
            .router
            .clone()
            .oneshot(request(method, uri, &f.admin, Some(WHATSAPP), body))
            .await
            .unwrap();

        assert_eq!(
            response.status(),
            StatusCode::FORBIDDEN,
            "{method} {uri} let a module through without the grant"
        );
        let envelope = body_json(response).await;
        assert_eq!(
            envelope["error"]["code"], "capability_denied",
            "the tab has to be able to ask for the grant, so the refusal travels as a CODE: {envelope}"
        );
    }

    assert_eq!(
        f.saas_calls.load(Ordering::SeqCst),
        0,
        "a refusal that has already talked to Meta is not a refusal"
    );
}

#[tokio::test]
async fn the_owner_grants_notify_and_the_module_reaches_meta() {
    let f = fixture(true, "granted").await;

    for (method, uri, body) in doors() {
        let response = f
            .router
            .clone()
            .oneshot(request(method, uri, &f.admin, Some(WHATSAPP), body))
            .await
            .unwrap();

        assert!(
            response.status().is_success(),
            "{method} {uri} refused a module the owner DID grant: {}",
            response.status()
        );
    }

    assert_eq!(
        f.saas_calls.load(Ordering::SeqCst),
        3,
        "every granted call has to reach the SaaS that talks to Meta"
    );
}

#[tokio::test]
async fn the_shell_names_no_module_and_keeps_passing_exactly_as_before() {
    // The tab the owner opens in the shell, `curl` with an admin session and the QA agent are not
    // modules and name none: the capability half of the gate does not apply to them, and hub#1610's
    // behaviour must not move under them.
    let f = fixture(false, "shell").await;

    for (method, uri, body) in doors() {
        let response = f
            .router
            .clone()
            .oneshot(request(method, uri, &f.admin, None, body))
            .await
            .unwrap();

        assert!(
            response.status().is_success(),
            "{method} {uri} broke the shell, which names no module: {}",
            response.status()
        );
    }

    assert_eq!(f.saas_calls.load(Ordering::SeqCst), 3);
}
