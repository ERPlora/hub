//! **The declared way in for a MODULE** (hub#714, ADR-0283 §9).
//!
//! The visual flow editor is a module (pm#110), and until now a module had no declared way to
//! reach `/api/hub/flows*`: the SDK only speaks `query`/`command`, and flows are core REST on
//! purpose. What it *could* do was read the session token out of `localStorage` and `fetch` the
//! door itself — the module WC lives in the shell's own document, same origin, no sandbox. That
//! works only while the user is an admin and dies the day the shell moves the session to an
//! httpOnly cookie. A contract that leans on that is not a contract.
//!
//! So the SDK gains a typed `flows` surface, and this file pins what the surface may NOT become.
//!
//! 1. **The human door does not move.** `require_admin_session` is untouched: anonymous → 401,
//!    a cashier → 403, an API key → refused. `flows_api_test.rs` owns that contract; here it is
//!    re-checked *with a module identity attached*, because a second gate that accidentally
//!    granted what the first refuses would be the whole point lost.
//! 2. **A module needs `manage_flows` DECLARED in its manifest and GRANTED by the owner.** Two
//!    gates, both mandatory, neither substituting the other: the session says «a person allowed to
//!    administer this hub is here», the capability says «and the owner chose THIS module as the
//!    tool they administer it with». Without it, adding the surface would have handed flow
//!    administration to every installed module for free — the inventory app the owner installed
//!    could write an automation that runs commands in their name while nobody is watching. That is
//!    an escalation this change would have INTRODUCED, so it is gated in the same change.
//! 3. **The gate is on the editor's doors and nowhere else.** `X-Erplora-Module` is not a general
//!    "act as this module" switch: outside `/api/hub/flows*` — and `GET /api/hub/events/shape`,
//!    which hub#715 put behind the same capability because it is the same editor reading what the
//!    business's events carry — it means nothing and changes nothing.
//!
//! ⚠️ Honest limit, written down because pretending otherwise would be worse: in the browser the
//! module id is DECLARED, not authenticated — the shell stamps it when it mounts the component
//! (`ModuleView.vue`), and nothing stops a module from lying about it in the very same document
//! where it can already read the session token. That is one gap, not two, and it closes the day
//! module components are isolated. What this gate buys today is real all the same: the set of
//! modules that may EVER administer flows is fixed at install time by a signed manifest the owner
//! saw and a grant they can revoke, and the enforcement point is already server-side — the day the
//! shell can prove who is calling, only the provenance of the header improves, not the kernel.
use std::path::{Path, PathBuf};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-flows-module-door";

/// The header by which a caller names the module it is acting for.
const MODULE_HEADER: &str = "x-erplora-module";

/// The module the owner installed to edit flows: it DECLARES `manage_flows`.
const EDITOR: &str = "flows_editor";
/// A perfectly ordinary module that declares nothing. It must never reach the kernel.
const INVENTORY: &str = "inventory";

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

/// Writes a minimal module on disk so the installer registers a REAL manifest — the capability
/// gate reads what the module declares, so a hand-built registry entry would prove nothing.
fn module_dir(root: &Path, id: &str, capabilities: Value) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
    let mut manifest = json!({ "id": id, "name": id, "version": "1.0.0" });
    if !capabilities.is_null() {
        manifest["capabilities"] = capabilities;
    }
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    dir
}

/// `granted` = the owner ticked `manage_flows` for the editor in Settings → Permissions.
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
        "erplora-flows-module-door-{}-{admin_id}",
        std::process::id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(
        &modules,
        EDITOR,
        json!({ "manage_flows": {} }),
    ))
    .await
    .unwrap();
    rt.install_from_dir(&module_dir(&modules, INVENTORY, Value::Null))
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
        employee,
        api_key,
        temp,
    }
}

fn request(
    method: &str,
    uri: &str,
    session: Option<&str>,
    module: Option<&str>,
    body: Option<Value>,
) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if let Some(id) = module {
        builder = builder.header(MODULE_HEADER, id);
    }
    match body {
        Some(value) => builder
            .header("content-type", "application/json")
            .body(Body::from(value.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

async fn send(router: &axum::Router, request: Request<Body>) -> axum::response::Response {
    router.clone().oneshot(request).await.unwrap()
}

fn welcome_flow() -> Value {
    json!({
        "name": "Welcome",
        "definition": {
            "schema_version": 1,
            "steps": [{ "id": "wait", "kind": "delay", "seconds": 60 }]
        }
    })
}

/// Every route of the frozen §9 flows door, so a gate that covered ten of eleven goes red.
fn every_flows_route(id: &str) -> Vec<(&'static str, String, Option<Value>)> {
    vec![
        ("GET", "/api/hub/flows".to_string(), None),
        ("POST", "/api/hub/flows".to_string(), Some(welcome_flow())),
        ("GET", format!("/api/hub/flows/{id}"), None),
        (
            "PUT",
            format!("/api/hub/flows/{id}"),
            Some(welcome_flow()),
        ),
        ("DELETE", format!("/api/hub/flows/{id}"), None),
        ("GET", format!("/api/hub/flows/{id}/grants"), None),
        (
            "PUT",
            format!("/api/hub/flows/{id}/grants"),
            Some(json!({ "grants": [] })),
        ),
        ("POST", format!("/api/hub/flows/{id}/run"), None),
        ("GET", format!("/api/hub/flows/{id}/runs"), None),
        ("GET", "/api/hub/flows/runs/whatever".to_string(), None),
        ("GET", "/api/hub/flows/approvals".to_string(), None),
        (
            "POST",
            "/api/hub/flows/approvals/whatever/approve".to_string(),
            None,
        ),
        (
            "POST",
            "/api/hub/flows/approvals/whatever/reject".to_string(),
            None,
        ),
        ("GET", "/api/hub/flows/secrets".to_string(), None),
        (
            "PUT",
            "/api/hub/flows/secrets/API_KEY".to_string(),
            Some(json!({ "value": "sk-live-42" })),
        ),
        ("DELETE", "/api/hub/flows/secrets/API_KEY".to_string(), None),
        // hub#716 — the contract the editor builds its UI from. It is served, not shipped in the
        // module's bundle, so it comes through the same door and under the same gate as the rest.
        ("GET", "/api/hub/flows/schema".to_string(), None),
    ]
}

/// Creates a flow through the admin's own session (no module attached) and returns its id.
async fn create(f: &Fixture) -> String {
    let response = send(
        &f.router,
        request(
            "POST",
            "/api/hub/flows",
            Some(&f.admin),
            None,
            Some(welcome_flow()),
        ),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    body_json(response).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string()
}

/// **Default-deny, and it is the whole point of the issue.** An ordinary installed module, loaded
/// in the session of a real administrator, is refused on every route of the kernel — because its
/// manifest never asked for `manage_flows`. Before this gate it would have gone straight through:
/// the admin session was the only door, and a module inherits the session of whoever is logged in.
#[tokio::test]
async fn a_module_that_never_declared_manage_flows_is_refused_on_every_route() {
    let f = fixture(true).await;
    let id = create(&f).await;

    for (method, uri, body) in every_flows_route(&id) {
        let response = send(
            &f.router,
            request(method, &uri, Some(&f.admin), Some(INVENTORY), body),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::FORBIDDEN,
            "{method} {uri} must refuse a module without `manage_flows`"
        );
        assert_eq!(
            body_json(response).await["error"]["code"],
            "capability_denied",
            "{method} {uri} must say WHY, so the editor can ask for the grant instead of \
             showing a bare error"
        );
    }

    std::fs::remove_dir_all(f.temp).ok();
}

/// Declaring is not enough: the OWNER grants. Same module, same admin, same routes — the only
/// difference is the toggle in Settings → Permissions.
#[tokio::test]
async fn declaring_the_capability_is_not_being_granted_it() {
    let denied = fixture(false).await;
    let response = send(
        &denied.router,
        request(
            "GET",
            "/api/hub/flows",
            Some(&denied.admin),
            Some(EDITOR),
            None,
        ),
    )
    .await;
    assert_eq!(
        response.status(),
        StatusCode::FORBIDDEN,
        "a module whose capability the owner has not granted is refused"
    );
    assert_eq!(
        body_json(response).await["error"]["code"],
        "capability_denied"
    );
    std::fs::remove_dir_all(denied.temp).ok();

    let allowed = fixture(true).await;
    let id = create(&allowed).await;
    for (method, uri, body) in every_flows_route(&id) {
        let response = send(
            &allowed.router,
            request(method, &uri, Some(&allowed.admin), Some(EDITOR), body),
        )
        .await;
        assert_ne!(
            response.status(),
            StatusCode::FORBIDDEN,
            "{method} {uri} must let the granted editor through (a 404 for a missing row is fine)"
        );
    }
    std::fs::remove_dir_all(allowed.temp).ok();
}

/// **The new door does not weaken the old one.** The capability is an EXTRA gate, never an
/// alternative one: a cashier with the blessed module still gets 403, an anonymous caller still
/// gets 401, and an API key is still refused — exactly as `flows_api_test.rs` demands without any
/// module attached. If the module gate had been written as an `or`, this is what would go red.
#[tokio::test]
async fn the_granted_module_does_not_let_a_cashier_or_an_api_key_in() {
    let f = fixture(true).await;
    let id = create(&f).await;

    for (method, uri, body) in every_flows_route(&id) {
        let anon = send(
            &f.router,
            request(method, &uri, None, Some(EDITOR), body.clone()),
        )
        .await;
        assert_eq!(
            anon.status(),
            StatusCode::UNAUTHORIZED,
            "{method} {uri}: a granted module is not a session"
        );

        let cashier = send(
            &f.router,
            request(method, &uri, Some(&f.employee), Some(EDITOR), body.clone()),
        )
        .await;
        assert_eq!(
            cashier.status(),
            StatusCode::FORBIDDEN,
            "{method} {uri}: the editor loaded in a cashier's session is still a cashier"
        );

        let mut with_key = Request::builder()
            .method(method)
            .uri(&uri)
            .header("authorization", format!("Bearer {}", f.api_key))
            .header(MODULE_HEADER, EDITOR);
        let keyed = send(
            &f.router,
            match body.clone() {
                Some(value) => {
                    with_key = with_key.header("content-type", "application/json");
                    with_key.body(Body::from(value.to_string())).unwrap()
                }
                None => with_key.body(Body::empty()).unwrap(),
            },
        )
        .await;
        assert!(
            keyed.status() == StatusCode::UNAUTHORIZED || keyed.status() == StatusCode::FORBIDDEN,
            "{method} {uri}: a stored credential does not become a person by naming a module, \
             got {}",
            keyed.status()
        );
    }

    std::fs::remove_dir_all(f.temp).ok();
}

/// **Not a generic "act as module" switch.** The header is read only where the editor's own
/// surface lives — `/api/hub/flows*`, and `/api/hub/events/*` since hub#715 (`shape`), hub#823
/// (`list`) and hub#953 (the dead-letter queue), all gated by `manage_flows`. Anywhere else in the
/// core it is inert: naming a module (granted or not) must not change a single answer. The day
/// somebody wires this header into a shared middleware, this test is what says no.
///
/// ⚠️ **`/api/hub/events/dead` used to be in the list below, and moving it out was a decision, not
/// an erosion** (ADR-0338, hub#953). It sat here because the dead-letter queue was «an operator's
/// screen, not the editor's» — true while the SHELL was the only caller. Once `@erplora/module-sdk`
/// exposes those six gestures to modules, «an admin is logged in» would mean every installed module
/// can read the full payloads of everybody else's events and replay them with the emitter's
/// authority (hub#686). What guards it now is `dead_letter_module_door.rs`, which pins BOTH halves:
/// an ungranted module refused, and the caller that names no module untouched. If that file ever
/// goes, this comment is the record of what it was protecting.
#[tokio::test]
async fn the_module_header_means_nothing_outside_the_editors_doors() {
    let f = fixture(true).await;

    for uri in ["/api/settings", "/api/hub/context", "/api/modules"] {
        let bare = send(&f.router, request("GET", uri, Some(&f.admin), None, None)).await;
        for module in [EDITOR, INVENTORY, "not_even_installed"] {
            let named = send(
                &f.router,
                request("GET", uri, Some(&f.admin), Some(module), None),
            )
            .await;
            assert_eq!(
                named.status(),
                bare.status(),
                "GET {uri} answered differently just because the caller named `{module}`"
            );
        }
    }

    std::fs::remove_dir_all(f.temp).ok();
}
