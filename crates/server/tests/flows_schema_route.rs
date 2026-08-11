//! **The flow contract, SERVED** (hub#716) — `GET /api/hub/flows/schema`.
//!
//! `schemas/flow.schema.json` is the frozen contract of what a flow document may say, and until
//! now it was a file in the repository and nothing else: no HTTP route, no npm package. The visual
//! editor (pm#110) is a module installed from the marketplace, updated on its own clock
//! (hub#516), so the only thing it could do was **carry a copy** in its bundle and hope. The day
//! the runtime widens the grammar, a hub on a newer core would keep being told by its editor that
//! a step it accepts is invalid — or, worse, the editor would stop offering something that works.
//!
//! The runtime is already protected from drifting away from the file
//! (`crates/runtime/tests/flow_schema_matches_the_runtime.rs`, hub#661). What had nothing checking
//! it was **schema ↔ consumer**. Serving it is what closes that: the editor asks the hub it is
//! running inside, so the answer is what THIS core enforces, at this version.
//!
//! What this file pins:
//!
//! 1. **What is served IS the contract, not a copy of it.** Byte-for-byte the document the
//!    runtime's own agreement test judges, and re-checked here against the runtime's vocabulary —
//!    a handler that returned a lovingly hand-written schema would go red.
//! 2. **The version travels with it.** A park of hubs on different cores is the whole reason this
//!    route exists; an answer that does not say which core answered is a foot-gun.
//! 3. **`schema` is a static segment, not a flow id.** `/api/hub/flows/{id}` is one route away.
//! 4. **Same door as the rest of §9**: a human owner/admin session. A cashier gets `403`, an
//!    anonymous caller `401`, an API key is refused. (The `manage_flows` capability of a calling
//!    module is pinned in `flows_module_door.rs`, which walks every route of the table.)
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::flows::def::{Op, StepKind, TriggerKind, SCHEMA_VERSION};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::collections::BTreeSet;
use tower::ServiceExt;

const HUB: &str = "hub-flows-schema-route";

struct Fixture {
    router: axum::Router,
    admin: String,
    employee: String,
    api_key: String,
    temp: std::path::PathBuf,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn fixture() -> Fixture {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
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
        "erplora-flows-schema-route-{}-{admin_id}",
        std::process::id()
    ));
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

fn request(uri: &str, session: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("GET").uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    builder.body(Body::empty()).unwrap()
}

async fn send(router: &axum::Router, request: Request<Body>) -> axum::response::Response {
    router.clone().oneshot(request).await.unwrap()
}

/// The file as it ships, read from disk — the same one `flow_schema_matches_the_runtime.rs` reads.
fn schema_on_disk() -> Value {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/flow.schema.json")
        .canonicalize()
        .expect("schemas/flow.schema.json ships with the hub");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn enum_at(schema: &Value, pointer: &str) -> BTreeSet<String> {
    schema
        .pointer(pointer)
        .unwrap_or_else(|| panic!("the served schema has nothing at {pointer}"))
        .get("enum")
        .and_then(|e| e.as_array())
        .unwrap_or_else(|| panic!("the served schema declares no enum at {pointer}"))
        .iter()
        .filter_map(|v| v.as_str().map(str::to_string))
        .collect()
}

fn keys_at(schema: &Value, pointer: &str) -> BTreeSet<String> {
    schema
        .pointer(pointer)
        .unwrap_or_else(|| panic!("the served schema has nothing at {pointer}"))
        .as_object()
        .unwrap_or_else(|| panic!("{pointer} is not an object in the served schema"))
        .keys()
        .cloned()
        .collect()
}

/// **What is served is the contract the runtime enforces**, and it says which core said so.
///
/// The two assertions are deliberately different in kind. The first is identity: the served
/// document *is* `schemas/flow.schema.json`, so it inherits the agreement test that already
/// guards that file against `flows::def`. The second re-derives the vocabulary from the runtime
/// and checks it against **what came down the wire** — because the failure this route exists to
/// prevent is a consumer validating against something the hub does not enforce, and a copy that
/// happens to be equal today is exactly how that starts.
#[tokio::test]
async fn the_served_schema_is_the_contract_the_runtime_enforces() {
    let f = fixture().await;

    let response = send(&f.router, request("/api/hub/flows/schema", Some(&f.admin))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], json!(true));

    let served = &body["data"]["schema"];
    assert_eq!(
        served,
        &schema_on_disk(),
        "the route must serve the shipped contract, not a second copy of it"
    );

    // The vocabulary, re-derived from the runtime and checked against the wire.
    assert_eq!(
        enum_at(served, "/$defs/step/properties/kind"),
        StepKind::ALL
            .iter()
            .map(|k| k.as_str().to_string())
            .collect::<BTreeSet<String>>(),
        "the editor builds its step palette from this: a served list the runtime does not know is \
         a flow the hub refuses to save"
    );
    assert_eq!(
        enum_at(served, "/$defs/trigger/properties/kind"),
        TriggerKind::ALL
            .iter()
            .map(|k| k.as_str().to_string())
            .collect::<BTreeSet<String>>()
    );
    assert_eq!(
        keys_at(served, "/$defs/condition/additionalProperties/properties"),
        Op::ALL
            .iter()
            .map(|o| o.as_str().to_string())
            .collect::<BTreeSet<String>>()
    );

    // Which core answered. A park of hubs on different versions is the entire reason the editor
    // asks instead of carrying a copy, so an answer with no version is a copy with extra steps.
    assert_eq!(body["data"]["schema_version"], json!(SCHEMA_VERSION));
    assert_eq!(
        body["data"]["core_version"],
        json!(erplora_runtime::CORE_VERSION),
        "the editor has to be able to say «this hub is older than what you are drawing»"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// `schema` is a **static segment**, and `/api/hub/flows/{id}` is one route away. A router that
/// resolved it as a flow whose id is literally `schema` would answer `404` forever — the same trap
/// `/flows/runs/{run_id}` and `/flows/secrets` already have a test for.
#[tokio::test]
async fn the_static_segment_wins_over_a_flow_id() {
    let f = fixture().await;

    let response = send(&f.router, request("/api/hub/flows/schema", Some(&f.admin))).await;
    assert_eq!(
        response.status(),
        StatusCode::OK,
        "`schema` must not be read as a flow id"
    );
    let body = body_json(response).await;
    assert!(
        body["data"]["schema"].is_object(),
        "it answered something, but not the schema: {body}"
    );

    // And the neighbouring route still behaves: a flow that genuinely does not exist is a 404.
    let missing = send(
        &f.router,
        request("/api/hub/flows/does-not-exist", Some(&f.admin)),
    )
    .await;
    assert_eq!(missing.status(), StatusCode::NOT_FOUND);

    std::fs::remove_dir_all(f.temp).ok();
}

/// **Same door as the rest of §9.** The document is not a secret, but the route is: an
/// unauthenticated endpoint that reports the exact core version is a fingerprint of the hub for
/// anybody who can reach the origin, and the surface is uniform on purpose — one rule for
/// `/api/hub/flows*`, so nobody has to remember which of them is the exception.
#[tokio::test]
async fn the_schema_route_keeps_the_admin_door() {
    let f = fixture().await;

    let anon = send(&f.router, request("/api/hub/flows/schema", None)).await;
    assert_eq!(anon.status(), StatusCode::UNAUTHORIZED);

    let cashier = send(
        &f.router,
        request("/api/hub/flows/schema", Some(&f.employee)),
    )
    .await;
    assert_eq!(
        cashier.status(),
        StatusCode::FORBIDDEN,
        "a valid session that does not administer the hub is a 403, not a 401"
    );

    let keyed = send(
        &f.router,
        Request::builder()
            .method("GET")
            .uri("/api/hub/flows/schema")
            .header("authorization", format!("Bearer {}", f.api_key))
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert!(
        keyed.status() == StatusCode::UNAUTHORIZED || keyed.status() == StatusCode::FORBIDDEN,
        "a stored integration credential is not a person: got {}",
        keyed.status()
    );

    std::fs::remove_dir_all(f.temp).ok();
}
