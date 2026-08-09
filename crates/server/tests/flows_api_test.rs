//! HTTP contract of the **automation kernel** (hub#661 — ADR-0283 K7 / §9). It is FROZEN, so this
//! file is where "frozen" stops being a word in an ADR and becomes something that goes red.
//!
//! Three things it pins that nothing else can:
//!
//! 1. **The routes exist and do not shadow each other.** `/flows/runs/{run_id}` and
//!    `/flows/{id}/runs` are one static segment apart; a router that resolved the first as a flow
//!    whose id is literally `runs` would answer `404` forever, and only a request against the real
//!    router can tell.
//! 2. **The door is the local session of a human owner/admin** — never an API key, never the
//!    machine token, and a valid cashier gets `403`. Grants are the screen where a person decides
//!    what the hub may do unattended; a copyable integration credential able to write them could
//!    grant itself every command in the hub through a flow.
//! 3. **A document that does not parse never lands.** The refusal carries the kernel's stable
//!    code (`flow.unknown_schema_version`, `flow.step_kind_not_available`) so the editor can say
//!    which line is wrong instead of "error".
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-flows-api";

struct Fixture {
    router: axum::Router,
    /// Session of an owner/admin — the only one who may see or write any of this.
    admin: String,
    admin_id: String,
    /// A perfectly valid cashier who does not administer the hub.
    employee: String,
    /// A real, active API key of this hub. Valid where it is meant to be — not here.
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
    let employee_id = rt.create_user("Marta", "2222", "cashier", None).await.unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let api_key = rt.ensure_app_api_key().await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-flows-api-{}-{admin_id}",
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
        bootstrap_blueprint: None,
    };
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        admin,
        admin_id,
        employee,
        api_key,
        temp,
    }
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
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
            "triggers": [{
                "kind": "event",
                "event": "sale.completed",
                "filter": { "event.total": { "gte": "100" } }
            }],
            "steps": [
                { "id": "guard", "kind": "condition", "when": { "input.total": { "exists": true } } },
                { "id": "wait", "kind": "delay", "seconds": 60 }
            ]
        }
    })
}

/// Creates a flow and returns its id.
async fn create(f: &Fixture, body: Value) -> String {
    let response = send(
        &f.router,
        request("POST", "/api/hub/flows", Some(&f.admin), Some(body)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    body_json(response).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string()
}

#[tokio::test]
async fn the_crud_round_trips_and_the_definition_comes_back_as_json() {
    let f = fixture().await;

    let id = create(&f, welcome_flow()).await;

    let listed = body_json(send(
        &f.router,
        request("GET", "/api/hub/flows", Some(&f.admin), None),
    )
    .await)
    .await;
    assert_eq!(listed["data"].as_array().unwrap().len(), 1);

    let got = body_json(send(
        &f.router,
        request("GET", &format!("/api/hub/flows/{id}"), Some(&f.admin), None),
    )
    .await)
    .await;
    assert_eq!(got["data"]["name"], "Welcome");
    assert_eq!(got["data"]["enabled"], true, "a saved flow is meant to run");
    assert_eq!(
        got["data"]["definition"]["steps"][1]["kind"], "delay",
        "the document travels as JSON, not as an escaped string"
    );
    assert_eq!(
        got["data"]["created_by"],
        format!("hub_user:{}", f.admin_id),
        "attribution comes from the session, never from the body"
    );

    // Rename, then delete.
    let mut renamed = welcome_flow();
    renamed["name"] = json!("Welcome v2");
    let updated = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}"),
            Some(&f.admin),
            Some(renamed),
        ),
    )
    .await;
    assert_eq!(updated.status(), StatusCode::OK);
    assert_eq!(body_json(updated).await["data"]["name"], "Welcome v2");

    let deleted = send(
        &f.router,
        request("DELETE", &format!("/api/hub/flows/{id}"), Some(&f.admin), None),
    )
    .await;
    assert_eq!(deleted.status(), StatusCode::OK);
    let gone = send(
        &f.router,
        request("GET", &format!("/api/hub/flows/{id}"), Some(&f.admin), None),
    )
    .await;
    assert_eq!(
        gone.status(),
        StatusCode::NOT_FOUND,
        "a deleted flow is gone for the API, even though the row survives for the audit"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

#[tokio::test]
async fn only_a_human_admin_session_gets_through_this_door() {
    let f = fixture().await;
    let id = create(&f, welcome_flow()).await;

    for (method, uri, body) in [
        ("GET", "/api/hub/flows".to_string(), None),
        ("POST", "/api/hub/flows".to_string(), Some(welcome_flow())),
        ("GET", format!("/api/hub/flows/{id}"), None),
        ("GET", format!("/api/hub/flows/{id}/grants"), None),
        (
            "PUT",
            format!("/api/hub/flows/{id}/grants"),
            Some(json!({ "grants": [] })),
        ),
        ("POST", format!("/api/hub/flows/{id}/run"), None),
        ("GET", format!("/api/hub/flows/{id}/runs"), None),
        ("GET", "/api/hub/flows/runs/whatever".to_string(), None),
    ] {
        // No session at all.
        let anon = send(&f.router, request(method, &uri, None, body.clone())).await;
        assert_eq!(
            anon.status(),
            StatusCode::UNAUTHORIZED,
            "{method} {uri} must refuse an anonymous caller"
        );
        // A valid cashier: authenticated, and still not an administrator of the hub.
        let cashier = send(
            &f.router,
            request(method, &uri, Some(&f.employee), body.clone()),
        )
        .await;
        assert_eq!(
            cashier.status(),
            StatusCode::FORBIDDEN,
            "{method} {uri} must refuse a non-admin session"
        );
        // An API key is a stored, copyable credential; it does not decide what the hub may do
        // unattended, and it certainly does not write grants.
        let mut with_key = Request::builder().method(method).uri(&uri);
        with_key = with_key.header("authorization", format!("Bearer {}", f.api_key));
        let response = send(
            &f.router,
            match body.clone() {
                Some(value) => with_key
                    .header("content-type", "application/json")
                    .body(Body::from(value.to_string()))
                    .unwrap(),
                None => with_key.body(Body::empty()).unwrap(),
            },
        )
        .await;
        assert!(
            response.status() == StatusCode::UNAUTHORIZED
                || response.status() == StatusCode::FORBIDDEN,
            "{method} {uri} must refuse an API key, got {}",
            response.status()
        );
    }

    std::fs::remove_dir_all(f.temp).ok();
}

#[tokio::test]
async fn a_document_the_hub_does_not_understand_is_refused_with_its_stable_code() {
    let f = fixture().await;

    let cases = [
        (
            json!({ "name": "V2", "definition": { "schema_version": 2, "steps": [] } }),
            "flow.unknown_schema_version",
        ),
        (
            json!({
                "name": "Calls out",
                "definition": {
                    "schema_version": 1,
                    "steps": [{ "id": "call", "kind": "http" }]
                }
            }),
            "flow.step_kind_not_available",
        ),
        (
            json!({
                "name": "Bad filter",
                "definition": {
                    "schema_version": 1,
                    "steps": [{ "id": "g", "kind": "condition",
                                "when": { "input.total": { "greater_than": 1 } } }]
                }
            }),
            "flow.unknown_operator",
        ),
    ];

    for (body, code) in cases {
        let response = send(
            &f.router,
            request("POST", "/api/hub/flows", Some(&f.admin), Some(body)),
        )
        .await;
        assert_eq!(response.status(), StatusCode::CONFLICT);
        let json = body_json(response).await;
        assert_eq!(
            json["error"]["code"], code,
            "the editor programs against the CODE, not against prose: {json}"
        );
    }

    // And nothing landed.
    let listed = body_json(send(
        &f.router,
        request("GET", "/api/hub/flows", Some(&f.admin), None),
    )
    .await)
    .await;
    assert!(listed["data"].as_array().unwrap().is_empty());

    std::fs::remove_dir_all(f.temp).ok();
}

#[tokio::test]
async fn grants_are_replaced_whole_and_a_command_that_does_not_exist_refuses_the_list() {
    let f = fixture().await;
    let id = create(&f, welcome_flow()).await;

    // Nothing granted is the default answer, and the API says so out loud.
    let empty = body_json(send(
        &f.router,
        request("GET", &format!("/api/hub/flows/{id}/grants"), Some(&f.admin), None),
    )
    .await)
    .await;
    assert!(empty["data"].as_array().unwrap().is_empty());

    // A command nobody installed: the WHOLE list is refused, so the owner never believes they
    // granted something they did not.
    let refused = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "command", "value": "ghost.command" }] })),
        ),
    )
    .await;
    assert_eq!(refused.status(), StatusCode::NOT_FOUND);

    // A kind the kernel cannot enforce yet is refused BY NAME rather than stored as a promise.
    let not_yet = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "http", "value": "https://example.com/*" }] })),
        ),
    )
    .await;
    assert_eq!(not_yet.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(not_yet).await["error"]["code"],
        "flow.grant_kind_not_available"
    );

    // And a typo in `kind` is refused, not silently dropped into "denied".
    let typo = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "commnd", "value": "x" }] })),
        ),
    )
    .await;
    assert_eq!(typo.status(), StatusCode::CONFLICT);

    std::fs::remove_dir_all(f.temp).ok();
}

/// The two run routes are one static segment apart. If `runs` were swallowed by `:id`, asking for
/// a run would look up a flow called "runs" and answer `404` forever.
#[tokio::test]
async fn the_run_routes_do_not_shadow_each_other() {
    let f = fixture().await;
    let id = create(&f, welcome_flow()).await;

    // Manual start: the request returns immediately with the run id; the tick does the work.
    let started = send(
        &f.router,
        request(
            "POST",
            &format!("/api/hub/flows/{id}/run"),
            Some(&f.admin),
            Some(json!({ "input": { "total": "120.50" } })),
        ),
    )
    .await;
    assert_eq!(started.status(), StatusCode::ACCEPTED);
    let run_id = body_json(started).await["data"]["run_id"]
        .as_str()
        .unwrap()
        .to_string();

    let listed = body_json(send(
        &f.router,
        request("GET", &format!("/api/hub/flows/{id}/runs"), Some(&f.admin), None),
    )
    .await)
    .await;
    assert_eq!(listed["data"].as_array().unwrap().len(), 1);
    assert_eq!(listed["data"][0]["id"], run_id);
    assert_eq!(listed["data"][0]["trigger_kind"], "manual");
    assert_eq!(
        listed["data"][0]["input"]["total"], "120.50",
        "the input travels parsed"
    );

    let one = send(
        &f.router,
        request(
            "GET",
            &format!("/api/hub/flows/runs/{run_id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(
        one.status(),
        StatusCode::OK,
        "`/flows/runs/{{id}}` must not be read as the flow whose id is `runs`"
    );
    let body = body_json(one).await;
    assert_eq!(body["data"]["run"]["id"], run_id);
    assert!(
        body["data"]["steps"].is_array(),
        "a run is only explainable with its steps"
    );

    // A run of another hub — or none at all — is a 404, never a 409.
    let missing = send(
        &f.router,
        request("GET", "/api/hub/flows/runs/nope", Some(&f.admin), None),
    )
    .await;
    assert_eq!(missing.status(), StatusCode::NOT_FOUND);

    std::fs::remove_dir_all(f.temp).ok();
}

#[tokio::test]
async fn a_disabled_flow_refuses_to_be_run_by_hand() {
    let f = fixture().await;
    let mut off = welcome_flow();
    off["enabled"] = json!(false);
    let id = create(&f, off).await;

    let response = send(
        &f.router,
        request("POST", &format!("/api/hub/flows/{id}/run"), Some(&f.admin), None),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert_eq!(body_json(response).await["error"]["code"], "flow.disabled");

    std::fs::remove_dir_all(f.temp).ok();
}
