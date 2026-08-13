//! **The door that LISTS the events this hub emits** (hub#823) — `GET /api/hub/events`.
//!
//! `GET /api/hub/events/shape?name=…` (hub#715) answers what an event carries — but the caller has
//! to know its name to ask. Until now nothing listed the names, so the flow editor's «Cuando
//! pase…» dropdown was seeded from a hand-written file that can never offer an event this hub
//! emits and that file does not know. The data already existed in the runtime (the manifests'
//! `events.emits` + `commands[].emit`, and the real rows of `_event_outbox`); this is the surface
//! that exposes it.
//!
//! What this file pins, at the HTTP layer where the gates actually live:
//!
//! 1. **The catalogue is the union of what is DECLARED and what was SEEN.** An event a module
//!    declares and that never fired is still offered (`last_seen_at` absent); an event that
//!    really happened and that no installed module declares any more (the module was
//!    uninstalled, or a core event) is still listed — the editor must be able to offer what the
//!    hub really emits, which is exactly what the hand-written file could not do.
//! 2. **Names only, never payloads.** The listing carries `name`, `declared_by` and
//!    `last_seen_at`; what an event carries stays behind `…/shape`, with its redaction.
//! 3. **Same two gates as `…/shape`** (ADR-0312): a human owner/admin session, and `manage_flows`
//!    on top when the caller names a module. What a business emits is the shape of that business,
//!    and it is not readable by every installed module just because an admin is logged in.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tower::ServiceExt;

const HUB: &str = "hub-events-catalog";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module the owner installed to edit flows: it DECLARES `manage_flows`.
const EDITOR: &str = "flows_editor";
/// An ordinary installed module. It must not get to read what the business emits.
const INVENTORY: &str = "inventory";
/// A module that emitted a real event and was then uninstalled: its event is SEEN but no longer
/// declared, and the catalogue must still offer it.
const LEGACY: &str = "legacy";

const CATALOG: &str = "/api/hub/events";

struct Fixture {
    router: axum::Router,
    admin: String,
    employee: String,
    api_key: String,
    temp: PathBuf,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// Writes a module on disk so the installer registers a REAL manifest: the capability gate reads
/// what the module declares, and the catalogue reads what a module declares it emits.
fn module_dir(root: &Path, id: &str, extra: Value) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(dir.join("sql")).unwrap();
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
    // No business effect: the command exists to emit, and the payload it emits is its params.
    std::fs::write(dir.join("sql/sell.sql"), "SELECT 1;").unwrap();
    dir
}

fn a_sale() -> Params {
    let mut p = Params::new();
    p.insert("total".into(), json!("42.50"));
    p.insert(
        "customer".into(),
        json!({ "id": "c-1", "name": "Marta", "email": "marta@example.com" }),
    );
    p
}

/// `granted` = the owner ticked `manage_flows` for the editor in Settings → Permissions.
///
/// The hub it builds has, through real doors only (`install_from_dir`, `execute_command`,
/// `uninstall`):
/// - `inventory.sale_completed` — declared by TWO modules and really fired once;
/// - `inventory.refund_issued` — declared, never fired;
/// - `legacy.migrated` — really fired, then its declaring module was uninstalled.
async fn fixture(granted: bool) -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();

    let admin_id = rt.create_user("Ioan", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Marta", "2222", "cashier", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let api_key = rt.ensure_app_api_key().await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-events-catalog-{}-{admin_id}",
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
    rt.install_from_dir(&module_dir(
        &modules,
        INVENTORY,
        json!({
            "commands": {
                "inventory.sell": {
                    "permission": "",
                    "transaction": true,
                    "sql": ["sql/sell.sql"],
                    "emit": ["inventory.sale_completed"]
                }
            },
            "events": { "emits": ["inventory.sale_completed", "inventory.refund_issued"] }
        }),
    ))
    .await
    .unwrap();
    // A second declarer of the same event: `declared_by` must merge and sort, not pick one.
    rt.install_from_dir(&module_dir(
        &modules,
        "analytics",
        json!({ "events": { "emits": ["inventory.sale_completed"] } }),
    ))
    .await
    .unwrap();
    rt.install_from_dir(&module_dir(
        &modules,
        LEGACY,
        json!({
            "commands": {
                "legacy.migrate": {
                    "permission": "",
                    "transaction": true,
                    "sql": ["sql/sell.sql"],
                    "emit": ["legacy.migrated"]
                }
            }
        }),
    ))
    .await
    .unwrap();
    if granted {
        rt.set_module_capability(EDITOR, "manage_flows", true, "hub_user:admin")
            .await
            .unwrap();
    }
    let ctx = RequestContext::new(HUB, &admin_id, ["*".to_string()]);
    rt.execute_command("inventory.sell", &a_sale(), &ctx)
        .await
        .unwrap();
    rt.execute_command("legacy.migrate", &Params::new(), &ctx)
        .await
        .unwrap();
    // The event outlives the module: after this, `legacy.migrated` is seen but declared by nobody.
    rt.uninstall(LEGACY).await.unwrap();

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
        employee,
        api_key,
        temp,
    }
}

fn request(session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("GET").uri(CATALOG);
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

/// The dropdown's data: every event this hub can speak of, by name, with who declares it and when
/// it last happened — declared-and-never-fired, fired-and-no-longer-declared, both offered.
#[tokio::test]
async fn the_catalogue_is_the_union_of_declared_and_seen_events() {
    let f = fixture(true).await;

    let response = send(&f.router, request(Some(&f.admin), Some(EDITOR))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], json!(true));

    let data = body["data"].as_array().expect("data is a list");
    let names: Vec<&str> = data
        .iter()
        .map(|e| e["name"].as_str().expect("every entry has a name"))
        .collect();
    let mut sorted = names.clone();
    sorted.sort();
    assert_eq!(names, sorted, "the catalogue is sorted by name");

    let by_name = |name: &str| {
        data.iter()
            .find(|e| e["name"] == json!(name))
            .unwrap_or_else(|| panic!("no `{name}` in {names:?}"))
            .clone()
    };

    // Declared by two modules and really fired: merged, sorted, with a real timestamp.
    let sale = by_name("inventory.sale_completed");
    assert_eq!(sale["declared_by"], json!(["analytics", "inventory"]));
    assert!(
        sale["last_seen_at"].as_str().is_some_and(|s| !s.is_empty()),
        "a sale went through the till: {sale}"
    );

    // Declared and never fired: offered anyway, with no sighting to report.
    let refund = by_name("inventory.refund_issued");
    assert_eq!(refund["declared_by"], json!(["inventory"]));
    assert!(
        refund.get("last_seen_at").is_none_or(Value::is_null),
        "never fired, so no last_seen_at: {refund}"
    );

    // Fired and then its module uninstalled: the hand-written file could never offer this one.
    let migrated = by_name("legacy.migrated");
    assert_eq!(migrated["declared_by"], json!([]));
    assert!(
        migrated["last_seen_at"]
            .as_str()
            .is_some_and(|s| !s.is_empty()),
        "it really happened: {migrated}"
    );

    // Names only: what an event carries stays behind `…/shape`, with its redaction.
    let text = body.to_string();
    assert!(
        !text.contains("marta@example.com") && !text.contains("42.50"),
        "the catalogue leaked a payload: {body}"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// **Same two gates as `…/shape`** (ADR-0312), and neither replaces the other: the human door
/// first, and on top of it a module needs `manage_flows` declared and granted.
#[tokio::test]
async fn the_catalogue_needs_the_admin_session_and_the_capability() {
    let f = fixture(true).await;

    let anon = send(&f.router, request(None, Some(EDITOR))).await;
    assert_eq!(anon.status(), StatusCode::UNAUTHORIZED);

    let cashier = send(&f.router, request(Some(&f.employee), Some(EDITOR))).await;
    assert_eq!(
        cashier.status(),
        StatusCode::FORBIDDEN,
        "the editor loaded in a cashier's session is still a cashier"
    );

    let keyed = send(
        &f.router,
        Request::builder()
            .method("GET")
            .uri(CATALOG)
            .header("authorization", format!("Bearer {}", f.api_key))
            .header(MODULE_HEADER, EDITOR)
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert!(
        keyed.status() == StatusCode::UNAUTHORIZED || keyed.status() == StatusCode::FORBIDDEN,
        "a stored credential does not become a person by naming a module: got {}",
        keyed.status()
    );

    // A module that never declared the capability: refused, with the code that lets the editor
    // ask for the grant instead of showing a bare error.
    let ordinary = send(&f.router, request(Some(&f.admin), Some(INVENTORY))).await;
    assert_eq!(ordinary.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(ordinary).await["error"]["code"],
        json!("capability_denied")
    );

    // No module named: the shell itself and `curl` with an admin session pass on the session.
    let shell = send(&f.router, request(Some(&f.admin), None)).await;
    assert_eq!(shell.status(), StatusCode::OK);

    std::fs::remove_dir_all(f.temp).ok();

    // Declaring is not being granted: the same editor, before the owner ticked the box.
    let ungranted = fixture(false).await;
    let refused = send(
        &ungranted.router,
        request(Some(&ungranted.admin), Some(EDITOR)),
    )
    .await;
    assert_eq!(refused.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(refused).await["error"]["code"],
        json!("capability_denied")
    );
    std::fs::remove_dir_all(ungranted.temp).ok();
}
