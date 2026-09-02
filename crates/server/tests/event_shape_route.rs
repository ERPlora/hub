//! **The door the flow editor reads event shapes through** (hub#715) —
//! `GET /api/hub/events/shape?name=<event>`.
//!
//! The editor (pm#110) builds its data picker from what an event really carries, and until now
//! nothing served that: `_event_outbox.payload` is stored but only `GET /api/hub/events/dead`
//! returned one, and only for FAILED events. This is the read that unblocks it — and, because the
//! caller is a module from the marketplace, it is the read that has to be careful.
//!
//! What this file pins, at the HTTP layer where the gates actually live:
//!
//! 1. **Same door as the rest of `/api/hub/*`**: a human owner/admin session. Anonymous `401`, a
//!    cashier `403`, an API key refused. A stored credential that could page event payloads is an
//!    export of the customer list with an editor drawn on top.
//! 2. **And `manage_flows` on top of it** when the caller names a module (hub#714). The gate is
//!    the same two-of-two as the flows door: the session says a person who administers this hub is
//!    here, the capability says the owner chose THIS module as the tool. Without the second one,
//!    every installed module could read the shape of every event of the business for free.
//! 3. **The shape, not the payload.** A value that could be about a person arrives redacted; the
//!    field is still there so the owner can map it.
//! 4. **`404` means «no such event», `samples: 0` means «no examples yet»** — two different
//!    answers, because with a ninety-day retention (hub#699) an infrequent event is the second one
//!    and the editor must not tell the owner it does not exist.
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

const HUB: &str = "hub-event-shape";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module the owner installed to edit flows: it DECLARES `manage_flows`.
const EDITOR: &str = "flows_editor";
/// An ordinary installed module. It must not get to read what the business's events carry.
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

/// Writes a module on disk so the installer registers a REAL manifest: the capability gate reads
/// what the module declares, and the shape reads what a module declares it emits.
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
    p.insert("paid".into(), json!(true));
    p.insert(
        "customer".into(),
        json!({ "id": "c-1", "name": "Marta", "email": "marta@example.com" }),
    );
    p
}

/// `granted` = the owner ticked `manage_flows` for the editor in Settings → Permissions.
/// `traded` = a real sale went through the till, so there is something to infer a shape from.
async fn fixture(granted: bool, traded: bool) -> Fixture {
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
        "erplora-event-shape-{}-{admin_id}",
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
    if granted {
        rt.set_module_capability(EDITOR, "manage_flows", true, "hub_user:admin")
            .await
            .unwrap();
    }
    if traded {
        rt.execute_command(
            "inventory.sell",
            &a_sale(),
            &RequestContext::new(HUB, &admin_id, ["*".to_string()]),
        )
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

fn request(uri: &str, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("GET").uri(uri);
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

const SHAPE: &str = "/api/hub/events/shape?name=inventory.sale_completed";

/// The editor asks, and gets the fields of a sale that really happened — with the owner's own
/// number next to `total`, which is the difference between «`total`» and «Total — 42,50 €».
#[tokio::test]
async fn the_route_answers_the_shape_of_a_real_event() {
    let f = fixture(true, true).await;

    let response = send(&f.router, request(SHAPE, Some(&f.admin), Some(EDITOR))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], json!(true));

    let data = &body["data"];
    assert_eq!(data["event_name"], json!("inventory.sale_completed"));
    assert_eq!(data["samples"], json!(1));
    assert_eq!(data["declared_by"], json!(["inventory"]));

    let fields = data["fields"].as_array().expect("fields is a list");
    let by_path = |path: &str| {
        fields
            .iter()
            .find(|f| f["path"] == json!(path))
            .unwrap_or_else(|| panic!("no `{path}` in {fields:?}"))
            .clone()
    };
    assert_eq!(by_path("total")["type"], json!("string"));
    assert_eq!(by_path("total")["sample"], json!("42.50"));
    assert_eq!(by_path("paid")["type"], json!("boolean"));

    // The field is offered so the owner can map it; the value stays in the hub.
    assert_eq!(by_path("customer.email")["redacted"], json!(true));
    assert_eq!(by_path("customer.email")["sample"], Value::Null);
    assert!(
        !body.to_string().contains("marta@example.com"),
        "the reply carried a customer's email: {body}"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// **`404` is «no such event»; `samples: 0` is «no examples yet».** With a ninety-day retention
/// (hub#699) an infrequent event is the second, and an editor that showed «this event does not
/// exist» for it would be lying to the owner about their own business.
#[tokio::test]
async fn an_event_with_no_examples_is_not_an_event_that_does_not_exist() {
    let f = fixture(true, false).await;

    let declared = send(
        &f.router,
        request(
            "/api/hub/events/shape?name=inventory.refund_issued",
            Some(&f.admin),
            Some(EDITOR),
        ),
    )
    .await;
    assert_eq!(declared.status(), StatusCode::OK);
    let body = body_json(declared).await;
    assert_eq!(body["data"]["samples"], json!(0));
    assert_eq!(body["data"]["fields"], json!([]));
    assert_eq!(body["data"]["declared_by"], json!(["inventory"]));

    let unknown = send(
        &f.router,
        request(
            "/api/hub/events/shape?name=nobody.declares.this",
            Some(&f.admin),
            Some(EDITOR),
        ),
    )
    .await;
    assert_eq!(unknown.status(), StatusCode::NOT_FOUND);
    assert_eq!(
        body_json(unknown).await["error"]["code"],
        json!("not_found")
    );

    // And asking for nothing is a bad request, not an empty shape.
    let nameless = send(
        &f.router,
        request("/api/hub/events/shape", Some(&f.admin), Some(EDITOR)),
    )
    .await;
    assert_eq!(nameless.status(), StatusCode::BAD_REQUEST);

    std::fs::remove_dir_all(f.temp).ok();
}

/// **Two gates, and neither replaces the other.** The human door is untouched, and on top of it a
/// module needs `manage_flows` declared and granted — otherwise the inventory app the owner
/// installed could read what every event of the business carries.
#[tokio::test]
async fn the_shape_needs_the_admin_session_and_the_capability() {
    let f = fixture(true, true).await;

    let anon = send(&f.router, request(SHAPE, None, Some(EDITOR))).await;
    assert_eq!(anon.status(), StatusCode::UNAUTHORIZED);

    let cashier = send(&f.router, request(SHAPE, Some(&f.employee), Some(EDITOR))).await;
    assert_eq!(
        cashier.status(),
        StatusCode::FORBIDDEN,
        "the editor loaded in a cashier's session is still a cashier"
    );

    let keyed = send(
        &f.router,
        Request::builder()
            .method("GET")
            .uri(SHAPE)
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

    // Declared and granted → through. Declared by nobody → refused, with the code that lets the
    // editor ask for the grant instead of showing a bare error.
    let ordinary = send(&f.router, request(SHAPE, Some(&f.admin), Some(INVENTORY))).await;
    assert_eq!(ordinary.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(ordinary).await["error"]["code"],
        json!("capability_denied")
    );

    std::fs::remove_dir_all(f.temp).ok();

    // Declaring is not being granted: the same editor, before the owner ticked the box.
    let ungranted = fixture(false, true).await;
    let refused = send(
        &ungranted.router,
        request(SHAPE, Some(&ungranted.admin), Some(EDITOR)),
    )
    .await;
    assert_eq!(refused.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(refused).await["error"]["code"],
        json!("capability_denied")
    );
    std::fs::remove_dir_all(ungranted.temp).ok();
}
