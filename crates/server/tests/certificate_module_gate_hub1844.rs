//! The gate that keeps the certificate doors from becoming PUBLIC doors the day a module can
//! reach them (hub#1844).
//!
//! The three routes under `/api/business/certificate` have always been behind a session: the shell
//! fetches them itself from Ajustes → Negocio, and nothing else could call them, so the session was
//! the whole gate and that was enough. hub#1844 gives `@erplora/module-sdk` a typed surface for
//! exactly those routes — because the SCREEN belongs to the compliance module (the hub is
//! country-agnostic, ADR-0424) even though the CUSTODY stays in the core (ADR-0081) — and the
//! moment that surface exists, EVERY installed module can reach them whenever an admin happens to
//! be logged in. The inventory app the owner installed could delete the business certificate and
//! leave its invoices with no road to the tax authority, silently.
//!
//! So the surface arrives WITH its gate, in the same change, and the gate is the one the kernel
//! already has (`flows_api::require_module_capability`), hung here on **`certificate`** — the
//! capability the owner already grants as «the module may sign with the business certificate»
//! (ADR-0079). No new capability: a module that can sign with the key is already trusted with it,
//! so reading its subject or replacing it is the same risk the owner weighed, not a different one.
//!
//! What is asserted: a module that has NOT been granted `certificate` is refused on all three
//! doors and nothing is written; the same module WITH the grant gets through; and the shell —
//! which names no module — keeps passing exactly as it did before this change.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::Router;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::path::{Path as FsPath, PathBuf};
use tower::ServiceExt;

const HUB: &str = "hub-cert-gate";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module that owns the fiscal screen and therefore the one that calls these doors.
const VERIFACTU: &str = "verifactu";
/// A module that has NO business with the certificate: the one this gate exists to keep out.
const INVENTORY: &str = "inventory";

/// A module on disk that DECLARES `certificate`. Declaring is not being granted: the owner still
/// has to tick it in Settings → Permissions, which is what `grant` does below.
fn module_dir(root: &FsPath, id: &str, declares_certificate: bool) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
    let mut manifest = json!({ "id": id, "name": id, "version": "1.0.0" });
    if declares_certificate {
        manifest["capabilities"] = json!({ "certificate": { "purpose": "fiscal-sign" } });
    }
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
}

async fn fixture(granted: bool, tag: &str) -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-cert-gate-{tag}-{}-{granted}",
        std::process::id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(&modules, VERIFACTU, true))
        .await
        .unwrap();
    // The neighbour is installed too, and it does NOT declare the capability: «refused» has to mean
    // «this module may not», not «no module may».
    rt.install_from_dir(&module_dir(&modules, INVENTORY, false))
        .await
        .unwrap();
    if granted {
        rt.set_module_capability(VERIFACTU, "certificate", true, "hub_user:admin")
            .await
            .unwrap();
    }

    let config = HubConfig {
        demo: false,
        hub_id: HUB.into(),
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
    };
    Fixture {
        router: app(AppState::with_config(rt, config)),
        admin,
    }
}

/// The three doors, exactly as `CertificateApi` in the SDK calls them.
fn doors() -> [(&'static str, Option<Value>); 3] {
    [
        ("GET", None),
        (
            "PUT",
            Some(json!({ "pkcs12_b64": "bm90LWEtcDEy", "password": "x" })),
        ),
        ("DELETE", None),
    ]
}

async fn call(
    router: &Router,
    method: &str,
    session: &str,
    module: Option<&str>,
    body: Option<Value>,
) -> (StatusCode, Value) {
    let mut request = Request::builder()
        .method(method)
        .uri("/api/business/certificate")
        .header("x-hub-session", session);
    if let Some(module) = module {
        request = request.header(MODULE_HEADER, module);
    }
    let request = match &body {
        Some(b) => request
            .header("content-type", "application/json")
            .body(Body::from(b.to_string()))
            .unwrap(),
        None => request.body(Body::empty()).unwrap(),
    };
    let response = router.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

fn error_code(body: &Value) -> String {
    body.get("error")
        .and_then(|e| e.get("code"))
        .and_then(|c| c.as_str())
        .unwrap_or_default()
        .to_string()
}

/// 🔴 Without the grant, all three doors are shut — and they are shut BEFORE anything is written.
#[tokio::test]
async fn a_module_without_the_grant_is_refused_on_every_certificate_door() {
    let fx = fixture(false, "denied").await;

    for (method, body) in doors() {
        let (status, response) =
            call(&fx.router, method, &fx.admin, Some(VERIFACTU), body.clone()).await;
        assert_ne!(
            status,
            StatusCode::OK,
            "{method} /api/business/certificate let a module through without the grant: {response}"
        );
        assert_eq!(
            error_code(&response),
            "capability_denied",
            "the module needs the CODE to offer «grant it in Settings → Permissions» instead of \
             «error»: {method} answered {response}"
        );
    }
}

/// 🟢 With the grant, the module passes the gate. The PUT still fails — «bm90LWEtcDEy» is not a
/// `.p12` — and that is the point: the refusal it earns is about the FILE, not about permission.
#[tokio::test]
async fn the_granted_module_passes_the_gate() {
    let fx = fixture(true, "granted").await;

    let (status, response) = call(&fx.router, "GET", &fx.admin, Some(VERIFACTU), None).await;
    assert_eq!(status, StatusCode::OK, "{response}");
    assert_eq!(
        response["data"]["present"], false,
        "a hub with no certificate answers «there is none», inside the envelope: {response}"
    );

    let (_, refusal) = call(
        &fx.router,
        "PUT",
        &fx.admin,
        Some(VERIFACTU),
        Some(json!({ "pkcs12_b64": "bm90LWEtcDEy", "password": "x" })),
    )
    .await;
    assert_ne!(
        error_code(&refusal),
        "capability_denied",
        "past the gate, a bad file must be refused as a bad FILE: {refusal}"
    );
}

/// A module that never declared the capability cannot borrow the granted one's road.
#[tokio::test]
async fn a_neighbour_module_cannot_reach_the_certificate_at_all() {
    let fx = fixture(true, "neighbour").await;

    let (status, response) = call(&fx.router, "DELETE", &fx.admin, Some(INVENTORY), None).await;

    assert_ne!(
        status,
        StatusCode::OK,
        "the inventory app deleted the business certificate: {response}"
    );
    assert_eq!(error_code(&response), "capability_denied", "{response}");
}

/// The shell is not a module and names none. Nothing about this change may narrow its road: the
/// owner still uploads and removes their certificate from Ajustes → Negocio.
#[tokio::test]
async fn the_shell_names_no_module_and_keeps_passing() {
    let fx = fixture(false, "shell").await;

    let (status, response) = call(&fx.router, "GET", &fx.admin, None, None).await;

    assert_eq!(
        status,
        StatusCode::OK,
        "the shell must keep reading the certificate with no capability at all: {response}"
    );
    assert_eq!(response["ok"], true, "{response}");
    assert_eq!(response["data"]["present"], false, "{response}");
}
