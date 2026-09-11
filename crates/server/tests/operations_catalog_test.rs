//! **The door that LISTS what this hub can be asked to do** (hub#1757) — `GET /api/hub/operations`.
//!
//! `POST /api/command` and `POST /api/query` take a `name`, and until now nothing on a running hub
//! said which names exist. The names are module-specific and live in each installed `module.json`,
//! so anybody outside the module's source — QA, a script, the owner with `curl` — had to guess, and
//! guessing answers `404` every time. `contracts/kernel/routes.snapshot` lists HTTP routes, not
//! dispatch names; the Postman collection ships `POST /api/command` with an empty `{{command}}`
//! variable; and `/api/v1/openapi.json` covers ONLY the operations a module opted into with
//! `expose_api` (and answers `404` while the `api_docs_enabled` setting is off, its default).
//!
//! What this file pins, at the HTTP layer where the gates actually live:
//!
//! 1. **The catalogue is the dispatcher's own contract**: every operation carries the EXACT name
//!    the dispatcher takes, the permission it checks, and the payload shape it validates — and a
//!    name taken from the catalogue and posted straight to `/api/command` is not answered `404`.
//!    That round trip is the whole point of the issue.
//! 2. **It never announces what the dispatcher would refuse.** Internal commands (`_` prefix or
//!    `internal: true`, hub#131/hub#145) and the operations of a DEACTIVATED module are absent —
//!    the same rule `Registry::exposed_commands` already applies to the OpenAPI generator, and for
//!    the same reason: the runtime must not advertise what it then rejects.
//! 3. **The reserved `hub.*` core namespace is in it** (ADR-0192). Those queries are served by the
//!    runtime itself and belong to no module, so no module manifest can reveal them.
//! 4. **Same two gates as `/api/hub/events`** (ADR-0312): a human owner/admin session, and
//!    `manage_flows` on top when the caller names a module. The map of every write command in the
//!    hub, with its payload schema, is not readable by every installed module just because an
//!    administrator happens to be logged in.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tower::ServiceExt;

const HUB: &str = "hub-operations-catalog";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module the owner installed to edit flows: it DECLARES `manage_flows`.
const EDITOR: &str = "flows_editor";
/// An ordinary installed module. It must not get to read the map of the hub's doors.
const SALES: &str = "sales";
const INVENTORY: &str = "inventory";
/// Installed and then switched OFF: the dispatcher answers `module_inactive` for its operations,
/// so the catalogue must not offer them.
const LEGACY: &str = "legacy";

const CATALOG: &str = "/api/hub/operations";

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

/// Writes a module on disk so the installer registers a REAL manifest: the catalogue reads the
/// registry the dispatcher reads, not a fixture handed to it.
fn module_dir(root: &Path, id: &str, extra: Value) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(dir.join("sql")).unwrap();
    std::fs::create_dir_all(dir.join("schemas")).unwrap();
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
    // No business effect: the operations exist to be *named*, which is what the catalogue serves.
    std::fs::write(dir.join("sql/noop.sql"), "SELECT 1;").unwrap();
    std::fs::write(
        dir.join("schemas/sale.json"),
        r#"{"type":"object","properties":{"total":{"type":"string"}},"required":["total"]}"#,
    )
    .unwrap();
    dir
}

/// The manifest of `sales`: one public command with a schema, one internal by the legacy `_`
/// convention, one internal by the explicit flag, and one list query.
fn sales_manifest() -> Value {
    json!({
        "commands": {
            "sales.complete_sale": {
                "permission": "sales.create_sale",
                "transaction": true,
                "sql": ["sql/noop.sql"],
                "schema": "schemas/sale.json",
                "expose_api": true
            },
            // hub#131: internal by the last segment's `_` prefix.
            "sales._reverse_sale": {
                "permission": "sales.create_sale",
                "transaction": true,
                "sql": ["sql/noop.sql"]
            },
            // hub#145: internal by the explicit flag, no `_` in the name.
            "sales.settle_drawer": {
                "permission": "sales.create_sale",
                "transaction": true,
                "sql": ["sql/noop.sql"],
                "internal": true
            }
        },
        "queries": {
            "sales.orders.list": {
                "permission": "sales.view_sale",
                "sql": "sql/noop.sql",
                "list": {
                    "search": ["customer_name"],
                    "sort": ["created_at", "total"],
                    "default_sort": "created_at",
                    "default_dir": "desc",
                    "filters": { "status": { "op": "eq" }, "created_at": { "op": "range" } },
                    "page_size": 25
                }
            }
        }
    })
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
        "erplora-operations-catalog-{}-{admin_id}",
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
    rt.install_from_dir(&module_dir(&modules, SALES, sales_manifest()))
        .await
        .unwrap();
    rt.install_from_dir(&module_dir(
        &modules,
        INVENTORY,
        json!({
            "queries": {
                "inventory.products.list": {
                    "permission": "inventory.view_product",
                    "sql": "sql/noop.sql"
                }
            }
        }),
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
                    "sql": ["sql/noop.sql"]
                }
            }
        }),
    ))
    .await
    .unwrap();
    // Switched OFF, not uninstalled: its rows stay in the registry, and the dispatcher answers
    // `module_inactive`. The catalogue must agree with the dispatcher, not with the registry.
    rt.deactivate(LEGACY).await.unwrap();
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

fn request(session: Option<&str>, module: Option<&str>, query: &str) -> Request<Body> {
    let mut builder = Request::builder()
        .method("GET")
        .uri(format!("{CATALOG}{query}"));
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

/// Reads the catalogue as the shell does (admin session, no module named).
async fn catalogue(f: &Fixture, query: &str) -> Vec<Value> {
    let response = send(&f.router, request(Some(&f.admin), None, query)).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], json!(true));
    body["data"].as_array().expect("data is a list").clone()
}

fn names(entries: &[Value]) -> Vec<&str> {
    entries
        .iter()
        .map(|e| e["name"].as_str().expect("every entry has a name"))
        .collect()
}

fn by_name<'a>(entries: &'a [Value], name: &str) -> &'a Value {
    entries
        .iter()
        .find(|e| e["name"] == json!(name))
        .unwrap_or_else(|| panic!("no `{name}` in {:?}", names(entries)))
}

/// What the issue asked for: the exact names, what each one checks, and what each one takes.
#[tokio::test]
async fn the_catalogue_carries_the_exact_name_permission_and_payload_shape() {
    let f = fixture(true).await;
    let data = catalogue(&f, "").await;

    let listed = names(&data);
    let mut sorted = listed.clone();
    sorted.sort();
    assert_eq!(listed, sorted, "the catalogue is sorted by name");

    // A command: the name the dispatcher takes, its permission, and the schema it validates the
    // payload against — emitted raw, so it can be read as the JSON Schema it is.
    let sale = by_name(&data, "sales.complete_sale");
    assert_eq!(sale["kind"], json!("command"));
    assert_eq!(sale["module"], json!("sales"));
    assert_eq!(sale["permission"], json!("sales.create_sale"));
    assert_eq!(sale["expose_api"], json!(true));
    assert_eq!(sale["payload"]["required"], json!(["total"]));
    assert_eq!(sale["payload"]["properties"]["total"]["type"], json!("string"));

    // A list query: what it can be searched, sorted and filtered by is the shape of ITS payload,
    // and it is the half a caller cannot guess from the name.
    let orders = by_name(&data, "sales.orders.list");
    assert_eq!(orders["kind"], json!("query"));
    assert_eq!(orders["module"], json!("sales"));
    assert_eq!(orders["permission"], json!("sales.view_sale"));
    assert_eq!(orders["expose_api"], json!(false));
    assert_eq!(orders["list"]["search"], json!(["customer_name"]));
    assert_eq!(orders["list"]["sort"], json!(["created_at", "total"]));
    assert_eq!(orders["list"]["default_sort"], json!("created_at"));
    assert_eq!(orders["list"]["default_dir"], json!("desc"));
    assert_eq!(orders["list"]["page_size"], json!(25));
    assert_eq!(
        orders["list"]["filters"],
        json!({ "status": "eq", "created_at": "range" })
    );

    // A query with neither schema nor list block says so, rather than omitting the keys: a caller
    // reading `payload: null` knows it takes nothing, where a missing key means "look elsewhere".
    let products = by_name(&data, "inventory.products.list");
    assert!(products["payload"].is_null(), "{products}");
    assert!(products["list"].is_null(), "{products}");

    // The reserved `hub.*` namespace (ADR-0192): served by the runtime, declared by no module, so
    // no manifest could ever reveal it.
    for core in [
        "hub.setup.status",
        "hub.users.list",
        "hub.roles.list",
        "hub.approvals.list",
        "hub.fiscal.limits",
        "hub.fiscal.transmission",
        "hub.print.coverage",
        "hub.print.jobs",
    ] {
        let entry = by_name(&data, core);
        assert_eq!(entry["kind"], json!("query"));
        assert_eq!(entry["module"], json!("hub"), "the core is not a module");
    }
    // Who may ask is per-query, and the catalogue says which: the audit of who approved what is
    // admin's, the rest open with any local session.
    assert_eq!(
        by_name(&data, "hub.approvals.list")["permission"],
        json!("hub.administer")
    );
    assert_eq!(
        by_name(&data, "hub.setup.status")["permission"],
        json!("hub.users.view")
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// The round trip the issue is about: a name read from the catalogue and posted to the dispatcher
/// is **not** answered `404`. Without this the catalogue could drift into a list of plausible
/// strings and still look right.
#[tokio::test]
async fn a_name_taken_from_the_catalogue_is_not_a_404_at_the_dispatcher() {
    let f = fixture(true).await;
    let data = catalogue(&f, "").await;

    for entry in &data {
        let name = entry["name"].as_str().unwrap();
        let (uri, body) = match entry["kind"].as_str().unwrap() {
            "query" => ("/api/query", json!({ "name": name, "params": {} })),
            _ => ("/api/command", json!({ "name": name, "payload": {} })),
        };
        let response = send(
            &f.router,
            Request::builder()
                .method("POST")
                .uri(uri)
                .header("x-hub-session", &f.admin)
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await;
        let status = response.status();
        let answer = body_json(response).await;
        let code = answer["error"]["code"].as_str().unwrap_or("");
        assert!(
            !matches!(code, "not_found" | "module_inactive" | "internal_command"),
            "`{name}` is in the catalogue and the dispatcher does not know it: {status} {answer}"
        );
    }

    std::fs::remove_dir_all(f.temp).ok();
}

/// The rule `Registry::exposed_commands` already applies to the OpenAPI generator: the runtime
/// never ANNOUNCES what it would then refuse.
#[tokio::test]
async fn the_catalogue_never_announces_what_the_dispatcher_would_refuse() {
    let f = fixture(true).await;
    let data = catalogue(&f, "").await;
    let listed = names(&data);

    // Internal, both spellings (hub#131 the `_` convention, hub#145 the explicit flag). Neither is
    // reachable from `POST /api/command`, and publishing their names and payloads would undo
    // exactly what those two closed.
    for internal in ["sales._reverse_sale", "sales.settle_drawer"] {
        assert!(
            !listed.contains(&internal),
            "`{internal}` is internal and must not be advertised: {listed:?}"
        );
    }
    // The module the owner switched off: the dispatcher answers `module_inactive`, so offering its
    // command would be offering a `404`.
    assert!(
        !listed.contains(&"legacy.migrate"),
        "`legacy` is deactivated: {listed:?}"
    );
    // And the SQL each operation runs is not part of the contract a caller needs — the catalogue
    // says what to call and with what, never how the hub does it.
    let text = json!(data).to_string();
    assert!(
        !text.contains("sql/noop.sql") && !text.contains("SELECT 1"),
        "the catalogue leaked the module's implementation: {text}"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// A hub runs 27 modules; testing one of them should not mean reading all of them.
#[tokio::test]
async fn the_catalogue_can_be_narrowed_to_one_module() {
    let f = fixture(true).await;

    let only_sales = catalogue(&f, "?module=sales").await;
    assert!(!only_sales.is_empty(), "sales has operations");
    for entry in &only_sales {
        assert_eq!(entry["module"], json!("sales"), "{entry}");
    }

    // The core answers to its own name, so `hub.*` is reachable the same way.
    let only_core = catalogue(&f, "?module=hub").await;
    assert!(
        names(&only_core).contains(&"hub.setup.status"),
        "{:?}",
        names(&only_core)
    );

    // A module this hub does not have is an empty catalogue, not an error: asking what `payroll`
    // exposes on a hub without `payroll` has a true answer, and it is "nothing".
    let unknown = catalogue(&f, "?module=payroll").await;
    assert!(unknown.is_empty(), "{unknown:?}");

    std::fs::remove_dir_all(f.temp).ok();
}

/// **Same two gates as `/api/hub/events`** (ADR-0312), and neither replaces the other.
#[tokio::test]
async fn the_catalogue_needs_the_admin_session_and_the_capability() {
    let f = fixture(true).await;

    let anon = send(&f.router, request(None, Some(EDITOR), "")).await;
    assert_eq!(anon.status(), StatusCode::UNAUTHORIZED);

    let cashier = send(&f.router, request(Some(&f.employee), Some(EDITOR), "")).await;
    assert_eq!(
        cashier.status(),
        StatusCode::FORBIDDEN,
        "the map of every door in the hub is not a cashier's"
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

    // An ordinary module that never declared the capability: refused with the code that lets a
    // caller ask for the grant instead of showing a bare error.
    let ordinary = send(&f.router, request(Some(&f.admin), Some(SALES), "")).await;
    assert_eq!(ordinary.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(ordinary).await["error"]["code"],
        json!("capability_denied")
    );

    // No module named: the shell, `curl` with an admin session and the QA agent are not modules.
    let shell = send(&f.router, request(Some(&f.admin), None, "")).await;
    assert_eq!(shell.status(), StatusCode::OK);

    std::fs::remove_dir_all(f.temp).ok();

    // Declaring is not being granted: the same editor, before the owner ticked the box.
    let ungranted = fixture(false).await;
    let refused = send(
        &ungranted.router,
        request(Some(&ungranted.admin), Some(EDITOR), ""),
    )
    .await;
    assert_eq!(refused.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(refused).await["error"]["code"],
        json!("capability_denied")
    );
    std::fs::remove_dir_all(ungranted.temp).ok();
}
