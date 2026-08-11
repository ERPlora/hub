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
//!    code (`flow.unknown_schema_version`, `flow.invalid_definition`) so the editor can say
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
    build_fixture(false).await
}

/// The same hub with a real module installed, for the tests that need the registry to have
/// something in it: `agenda` ships a public command **and** an internal one (`agenda._purge_slots`),
/// which is the pair hub#824 is about.
async fn fixture_with_modules() -> Fixture {
    build_fixture(true).await
}

async fn build_fixture(install_modules: bool) -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    if install_modules {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_agent/agenda");
        rt.install_from_dir(&dir).await.unwrap();
    }

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
        // The secrets, hub#662: the same door, and the one whose stakes are highest — an API key
        // able to write one would be a credential that installs credentials.
        ("GET", "/api/hub/flows/secrets".to_string(), None),
        (
            "PUT",
            "/api/hub/flows/secrets/API_KEY".to_string(),
            Some(json!({ "value": "sk-live-42" })),
        ),
        ("DELETE", "/api/hub/flows/secrets/API_KEY".to_string(), None),
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
            // Every kind runs now (`notify` since hub#821), so each one is parsed as strictly as
            // the rest: an empty `notify` is refused for its OWN missing key, not as unavailable.
            json!({
                "name": "To nobody",
                "definition": {
                    "schema_version": 1,
                    "steps": [{ "id": "tell", "kind": "notify" }]
                }
            }),
            "flow.invalid_definition",
        ),
        (
            // An `ai` step that DOES run is parsed as strictly as any other kind, so an empty one
            // is refused for its own missing key rather than as unavailable.
            json!({
                "name": "Thinks",
                "definition": {
                    "schema_version": 1,
                    "steps": [{ "id": "ask", "kind": "ai" }]
                }
            }),
            "flow.invalid_definition",
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

// hub#730 (reopened 2026-08-10): a freshly-provisioned Cloud Hub accepted `esto no es un cron`
// and `manana por la tarde` with `201 Created` and armed them — because the published image
// predates fix #737, which lives in `develop` behind the still-open release PR #743. The unit
// tests in `scheduler::cron` cover the parser; NOTHING here pinned that the API is the door. This
// is the contract the reopen asks for: the same POSTs a QA can make against any hub must be
// refused at THIS layer with the kernel's stable code, and nothing may land. If the door is ever
// bypassed again (a seed path, a new route), this goes red against the real router.
#[tokio::test]
async fn a_trigger_the_engine_cannot_read_is_refused_at_the_door_with_its_stable_code() {
    let f = fixture().await;

    // Each is a real trigger a person writes, and each is one the engine cannot run. The refusal
    // carries the stable code the editor programs against, exactly like the step/operator refusals
    // above — never `201 Created`.
    let cases = [
        // Free text is not a schedule (hub#730 reopen: returned `201` on a freshly-made hub).
        (
            json!({
                "name": "Not a cron",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "cron", "cron": "esto no es un cron" }],
                    "steps": [{ "id": "c", "kind": "condition", "when": { "input.x": { "exists": false } } }]
                }
            }),
            "flow.invalid_cron",
        ),
        // Six fields is a different calendar (crontab-with-seconds); this hub reads five.
        (
            json!({
                "name": "Six fields",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "cron", "cron": "0 0 9 * * *" }],
                    "steps": [{ "id": "c", "kind": "condition", "when": { "input.x": { "exists": false } } }]
                }
            }),
            "flow.invalid_cron",
        ),
        // A value out of range names itself; the author fixes the line, not the whole document.
        (
            json!({
                "name": "Out of range",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "cron", "cron": "70 * * * *" }],
                    "steps": [{ "id": "c", "kind": "condition", "when": { "input.x": { "exists": false } } }]
                }
            }),
            "flow.invalid_cron",
        ),
        // A date that never happens (February has no 30th) is refused, not saved-and-silent.
        (
            json!({
                "name": "Never",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "cron", "cron": "0 0 30 2 *" }],
                    "steps": [{ "id": "c", "kind": "condition", "when": { "input.x": { "exists": false } } }]
                }
            }),
            "flow.invalid_cron",
        ),
        // The `at` twin (hub#730 reopen): prose was copied verbatim into `next_run` and armed.
        (
            json!({
                "name": "Not a date",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "at", "at": "manana por la tarde" }],
                    "steps": [{ "id": "c", "kind": "condition", "when": { "input.x": { "exists": false } } }]
                }
            }),
            "flow.invalid_at",
        ),
    ];

    for (body, code) in cases {
        let response = send(
            &f.router,
            request("POST", "/api/hub/flows", Some(&f.admin), Some(body)),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::CONFLICT,
            "a trigger the engine cannot read must not be saved as active"
        );
        let json = body_json(response).await;
        assert_eq!(
            json["error"]["code"], code,
            "the editor programs against the CODE: {json}"
        );
        // The message has to be actionable — it names what is wrong and what the grammar is.
        let message = json["error"]["message"].as_str().unwrap_or("");
        assert!(!message.is_empty(), "the refusal must explain itself: {json}");
    }

    // …and NOTHING landed: none of the unreadable triggers is armed.
    let listed = body_json(send(
        &f.router,
        request("GET", "/api/hub/flows", Some(&f.admin), None),
    )
    .await)
    .await;
    assert!(
        listed["data"].as_array().unwrap().is_empty(),
        "an unreadable trigger must not appear in the list as active: {listed}"
    );

    // The other half of the same contract: a cron this hub CAN read saves. The grammar grew in
    // #737 (ranges, lists, names) so that what people write works; this is the floor, not the
    // ceiling, and it must keep saving or the refusal above has become a lie the editor repeats.
    let saved = send(
        &f.router,
        request(
            "POST",
            "/api/hub/flows",
            Some(&f.admin),
            Some(json!({
                "name": "Every five minutes",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "cron", "cron": "*/5 * * * *" }],
                    "steps": [{ "id": "c", "kind": "condition", "when": { "input.x": { "exists": false } } }]
                }
            })),
        ),
    )
    .await;
    assert_eq!(saved.status(), StatusCode::CREATED, "a readable cron saves");

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

    // Every kind of the frozen vocabulary is creatable now (hub#821 brought the last two), so what
    // is refused by name is a VALUE the kernel cannot enforce — the same rule, one level down.
    // `sms` is in ADR-0012's vocabulary and no transport can send it.
    let no_transport = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "notify", "value": "sms" }] })),
        ),
    )
    .await;
    assert_eq!(no_transport.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(no_transport).await["error"]["code"],
        "flow.invalid_notify_grant"
    );

    // …and a recipient grant that is not «one field of one declared read» is refused too.
    let loose_recipient = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "recipient_query", "value": "crm.customer.get" }] })),
        ),
    )
    .await;
    assert_eq!(loose_recipient.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(loose_recipient).await["error"]["code"],
        "flow.invalid_recipient_grant"
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

/// **hub#824 — the door does not promise what the engine will refuse.**
///
/// An INTERNAL command exists in the registry, so "does it exist" waved it through: `PUT …/grants`
/// answered `200` and the grants screen said «granted», the document saved with `201`, and only the
/// run said no — `failed`, at 3 AM, on a permission the owner believed they had given. Both doors
/// now refuse it here, with the SAME stable code, so the editor can say «that one is internal»
/// instead of «error». (A command that does not exist keeps its own `404`: different question,
/// different remedy.)
#[tokio::test]
async fn an_internal_command_is_refused_at_the_grants_door_and_at_the_save_door() {
    let f = fixture_with_modules().await;
    const INTERNAL: &str = "agenda._purge_slots";

    // 1. The DOCUMENT. A step naming it never lands.
    let saved = send(
        &f.router,
        request(
            "POST",
            "/api/hub/flows",
            Some(&f.admin),
            Some(json!({
                "name": "QA internal",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "manual" }],
                    "steps": [{ "id": "i", "kind": "command", "command": INTERNAL, "params": {} }]
                }
            })),
        ),
    )
    .await;
    assert_eq!(saved.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(saved).await["error"]["code"],
        "flow.internal_command"
    );
    let listed = body_json(send(
        &f.router,
        request("GET", "/api/hub/flows", Some(&f.admin), None),
    )
    .await)
    .await;
    assert!(
        listed["data"].as_array().unwrap().is_empty(),
        "a document the hub can never execute is not stored: {listed}"
    );

    // 2. The GRANT, on a flow that is otherwise fine.
    let id = create(&f, welcome_flow()).await;
    let granted = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "command", "value": INTERNAL }] })),
        ),
    )
    .await;
    assert_eq!(granted.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(granted).await["error"]["code"],
        "flow.internal_command"
    );
    let live = body_json(send(
        &f.router,
        request("GET", &format!("/api/hub/flows/{id}/grants"), Some(&f.admin), None),
    )
    .await)
    .await;
    assert!(
        live["data"].as_array().unwrap().is_empty(),
        "the screen must never read «granted» about this: {live}"
    );

    // 3. …and the PUBLIC command of the same module still goes through both doors, which is the
    // half that must not regress.
    let ok = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "command", "value": "agenda.booking.create" }] })),
        ),
    )
    .await;
    assert_eq!(ok.status(), StatusCode::OK);
    let public_step = send(
        &f.router,
        request(
            "POST",
            "/api/hub/flows",
            Some(&f.admin),
            Some(json!({
                "name": "QA public",
                "definition": {
                    "schema_version": 1,
                    "triggers": [{ "kind": "manual" }],
                    "steps": [{ "id": "i", "kind": "command",
                                "command": "agenda.booking.create", "params": {} }]
                }
            })),
        ),
    )
    .await;
    assert_eq!(public_step.status(), StatusCode::CREATED);

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

/// **The history is paged, and the page is a cursor** (hub#666). A hub with live flows produces
/// runs forever; a listing that answers with all of them is a screen that stops loading in a month.
/// The cursor is the last row of the page, not an offset — runs keep arriving at the head while
/// somebody reads, and `OFFSET` would shift the page under them and duplicate a row.
#[tokio::test]
async fn the_run_history_is_paged_by_cursor_and_never_serves_the_same_run_twice() {
    let f = fixture().await;
    let id = create(&f, welcome_flow()).await;

    let mut started = Vec::new();
    for _ in 0..5 {
        let response = send(
            &f.router,
            request(
                "POST",
                &format!("/api/hub/flows/{id}/run"),
                Some(&f.admin),
                Some(json!({ "input": { "total": "120.50" } })),
            ),
        )
        .await;
        started.push(
            body_json(response).await["data"]["run_id"]
                .as_str()
                .unwrap()
                .to_string(),
        );
    }

    let mut seen: Vec<String> = Vec::new();
    let mut uri = format!("/api/hub/flows/{id}/runs?limit=2");
    for _ in 0..4 {
        let page = body_json(send(&f.router, request("GET", &uri, Some(&f.admin), None)).await).await;
        let rows = page["data"].as_array().unwrap().clone();
        if rows.is_empty() {
            break;
        }
        assert!(rows.len() <= 2, "`limit` is honoured, not advisory");
        seen.extend(rows.iter().map(|r| r["id"].as_str().unwrap().to_string()));
        let Some(cursor) = page["next_cursor"].as_str() else {
            break;
        };
        // The cursor is the id of the last run of the page — URL-safe by construction, and
        // meaningful to whoever reads the request in a log.
        uri = format!("/api/hub/flows/{id}/runs?limit=2&before={cursor}");
    }

    assert_eq!(seen.len(), 5, "the pages covered every run: {seen:?}");
    let mut unique = seen.clone();
    unique.sort();
    unique.dedup();
    assert_eq!(unique.len(), 5, "no run came back twice: {seen:?}");
    assert_eq!(
        seen[0],
        *started.last().unwrap(),
        "newest first — the run somebody is looking for is the one that just failed"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// The run detail answers «what did this set off?»: the steps it took **and** the events it emitted,
/// which is where the chain continues into other modules.
#[tokio::test]
async fn the_run_detail_carries_the_events_the_run_emitted() {
    let f = fixture().await;
    let id = create(&f, welcome_flow()).await;
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
    let run_id = body_json(started).await["data"]["run_id"]
        .as_str()
        .unwrap()
        .to_string();

    let body = body_json(send(
        &f.router,
        request("GET", &format!("/api/hub/flows/runs/{run_id}"), Some(&f.admin), None),
    )
    .await)
    .await;

    assert_eq!(body["data"]["run"]["id"], run_id);
    assert!(body["data"]["steps"].is_array());
    assert!(
        body["data"]["events"].is_array(),
        "the events a run emitted are the link to everything downstream of it"
    );

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


/// hub#662 — the write-only credential store, through the real router.
///
/// Two things only a router test can catch: that `secrets` is not swallowed by `/flows/{id}` (it is
/// one static segment away from being read as a flow whose id is literally "secrets"), and that no
/// response anywhere on this surface can carry a value back out.
#[tokio::test]
async fn a_secret_goes_in_and_only_its_name_comes_back() {
    // A secret is refused without a master key (hub#114, fail-closed), so the test provides one.
    // SAFETY: no other test in this binary reads or writes this variable.
    unsafe { std::env::set_var("HUB_SECRETS_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=") };
    let f = fixture().await;

    let created = send(
        &f.router,
        request(
            "PUT",
            "/api/hub/flows/secrets/API_KEY",
            Some(&f.admin),
            Some(json!({ "value": "sk-live-42" })),
        ),
    )
    .await;
    assert_eq!(created.status(), StatusCode::OK);
    let payload = body_json(created).await;
    assert_eq!(payload["data"]["name"], "API_KEY");
    assert!(
        !payload.to_string().contains("sk-live-42"),
        "not even the response to the write echoes it: {payload}"
    );

    // The listing is names. There is no endpoint that returns a value, and that absence IS the
    // design (ADR-0283 §4): one admin session must not be a copy of every key the hub holds.
    let listed = send(
        &f.router,
        request("GET", "/api/hub/flows/secrets", Some(&f.admin), None),
    )
    .await;
    assert_eq!(listed.status(), StatusCode::OK, "`secrets` is not read as a flow id");
    let listing = body_json(listed).await;
    assert_eq!(listing["data"][0]["name"], "API_KEY");
    assert!(!listing.to_string().contains("sk-live-42"), "{listing}");

    // A name a step could never reference is refused where it was typed.
    let bad = send(
        &f.router,
        request(
            "PUT",
            "/api/hub/flows/secrets/api.key",
            Some(&f.admin),
            Some(json!({ "value": "x" })),
        ),
    )
    .await;
    assert_eq!(bad.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(bad).await["error"]["code"],
        "flow.invalid_secret_name"
    );

    let removed = send(
        &f.router,
        request("DELETE", "/api/hub/flows/secrets/API_KEY", Some(&f.admin), None),
    )
    .await;
    assert_eq!(removed.status(), StatusCode::OK);
    let empty = send(
        &f.router,
        request("GET", "/api/hub/flows/secrets", Some(&f.admin), None),
    )
    .await;
    assert_eq!(body_json(empty).await["data"].as_array().unwrap().len(), 0);

    std::fs::remove_dir_all(f.temp).ok();
}

/// The list of what this hub cannot do had to shrink as each issue landed — `http` with hub#662,
/// `ai` with hub#665, `notify` with hub#821 — or the refusal becomes a lie the editor repeats.
/// It is empty now: what is left refused is a bad VALUE, not an unimplemented kind.
#[tokio::test]
async fn every_step_kind_saves_now_and_what_is_refused_is_a_bad_value() {
    let f = fixture().await;

    let id = create(
        &f,
        json!({
            "name": "Webhook",
            "definition": {
                "schema_version": 1,
                "steps": [{
                    "id": "call", "kind": "http", "method": "POST",
                    "url": "https://api.example.com/v1/hook",
                    "headers": { "Authorization": "Bearer {{secret.API_KEY}}" }
                }]
            }
        }),
    )
    .await;

    // And its grant is creatable, which is what makes the step able to do anything.
    let granted = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "http", "value": "https://api.example.com/v1/*" }] })),
        ),
    )
    .await;
    assert_eq!(granted.status(), StatusCode::OK);
    assert_eq!(body_json(granted).await["data"][0]["kind"], "http");

    // A pattern that does not contain anything is refused on the screen where it was typed.
    let loose = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/flows/{id}/grants"),
            Some(&f.admin),
            Some(json!({ "grants": [{ "kind": "http", "value": "*" }] })),
        ),
    )
    .await;
    assert_eq!(loose.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(loose).await["error"]["code"],
        "flow.invalid_http_pattern"
    );

    // A `notify` step SAVES now (hub#821) — with its recipient named as one field of one query,
    // which is the only shape there is.
    let notifying = send(
        &f.router,
        request(
            "POST",
            "/api/hub/flows",
            Some(&f.admin),
            Some(json!({
                "name": "Reminds the customer",
                "definition": {
                    "schema_version": 1,
                    "steps": [{
                        "id": "remind", "kind": "notify", "channel": "whatsapp",
                        "to": {
                            "query": "crm.customer.get",
                            "params": { "id": "input.customer_id" },
                            "field": "phone"
                        },
                        "template": "appointment_reminder",
                        "vars": { "text": "Te esperamos" }
                    }]
                }
            })),
        ),
    )
    .await;
    assert_eq!(notifying.status(), StatusCode::CREATED, "a `notify` step saves since hub#821");

    // …and the same step with a free address does NOT, which is the refusal that matters: there is
    // no syntax for one, so nothing an author writes can put an address from the event payload in
    // front of the transport.
    let by_hand = send(
        &f.router,
        request(
            "POST",
            "/api/hub/flows",
            Some(&f.admin),
            Some(json!({
                "name": "To whoever",
                "definition": {
                    "schema_version": 1,
                    "steps": [{
                        "id": "remind", "kind": "notify", "channel": "email",
                        "to": "{{input.email}}", "vars": { "text": "hola" }
                    }]
                }
            })),
        ),
    )
    .await;
    assert_eq!(by_hand.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(by_hand).await["error"]["code"],
        "flow.invalid_definition"
    );

    // …and an `ai` step SAVES now (hub#665), which is the other half of the same contract: the
    // list of what this hub cannot do must shrink as each issue lands, or the refusal becomes a
    // lie the editor repeats.
    let response = send(
        &f.router,
        request(
            "POST",
            "/api/hub/flows",
            Some(&f.admin),
            Some(json!({
                "name": "Answers WhatsApp",
                "definition": {
                    "schema_version": 1,
                    "steps": [{
                        "id": "agent", "kind": "ai",
                        "prompt": "Answer {{input.text}} and book the appointment",
                        "tools": { "queries": ["agenda.slots.list"] }
                    }]
                }
            })),
        ),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED, "an `ai` flow saves since hub#665");

    std::fs::remove_dir_all(f.temp).ok();
}
