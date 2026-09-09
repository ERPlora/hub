#![allow(non_snake_case)] // the names shout the part that matters, like the rest of the battery
//! **The HTTP door of the owner's rules** (hub#1701, ADR-0476).
//!
//! ```text
//! GET/POST        /api/hub/policies              list / create
//! GET             /api/hub/policies/checkpoints  where a rule may be put
//! GET/PUT/DELETE  /api/hub/policies/{id}
//! ```
//!
//! Three things that can only be checked against the REAL router:
//!
//! 1. **`checkpoints` is not eaten by `:id`.** It is a static segment and matchit resolves it
//!    before the parameter; if it ever slipped through `:id`, the answer would be «no such rule»
//!    instead of the list, and the owner's screen would be left with nothing to offer.
//! 2. **The door is the local session of an owner/admin**, never an API key nor the machine token.
//!    Whoever writes the business rules is a PERSON: a rule decides whether a sale can be charged,
//!    and a copyable integration credential does not decide that.
//! 3. **Every refusal of the core arrives with ITS status.** `404` what does not exist, `501` what
//!    this core cannot apply yet, `400` what the caller sent wrong — a `409` for everything would
//!    leave the screen unable to tell «fix the rule» from «wait for a release».
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-policies-api";

struct Fixture {
    router: axum::Router,
    /// Session of an owner/admin — the only one who may see or write any of this.
    admin: String,
    /// Who that person is. What the audit columns have to end up storing.
    admin_id: String,
    /// A perfectly valid cashier who does not administer the hub.
    employee: String,
    /// A real, active API key of this hub. It works where it has to; not here.
    api_key: String,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn fixture() -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    // The same module as the runtime battery: it declares `p1701/discount_limit` over
    // `p1701.order.set_discount`. Reused and not copied — a second fixture with the same rules is
    // one more place where the contract can drift apart without anyone noticing.
    let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../runtime/tests/fixture_1701");
    rt.install_from_dir(&dir).await.unwrap();

    let admin_id = rt.create_user("Ioan", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Marta", "2222", "cashier", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let api_key = rt.ensure_app_api_key().await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-policies-api-{}-{admin_id}",
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
        media_dir: temp,
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

fn over_20() -> Value {
    json!({
        "checkpoint": "p1701/discount_limit",
        "condition": { "discount_percent": { "gt": 20 } },
        "outcome": "block",
        "message": "Los descuentos de más del 20 % los autoriza el encargado",
        "mode": "enforce"
    })
}

async fn create(f: &Fixture, body: Value) -> String {
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(body)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    body_json(response).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string()
}

#[tokio::test]
async fn the_owner_lists_where_a_rule_may_go_hub1701() {
    // 🔴 Against the REAL router: `checkpoints` is static and has to beat `:id`. Served by
    // `/policies/:id` this would answer `404 policy.not_found` — the owner's screen would be left
    // with no places to offer and the failure would look like «there are no modules».
    let f = fixture().await;
    let response = send(
        &f.router,
        request(
            "GET",
            "/api/hub/policies/checkpoints",
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let list = body["data"].as_array().unwrap();
    assert_eq!(list.len(), 2, "{body}");
    assert_eq!(list[0]["id"], "p1701/discount_limit");
    assert_eq!(list[0]["command"], "p1701.order.set_discount");
    assert_eq!(list[0]["facts"][0], "discount_percent");
    assert_eq!(list[0]["outcomes"][0], "block");
}

#[tokio::test]
async fn a_rule_round_trips_through_the_door_hub1701() {
    let f = fixture().await;
    let id = create(&f, over_20()).await;

    let listed = send(
        &f.router,
        request("GET", "/api/hub/policies", Some(&f.admin), None),
    )
    .await;
    assert_eq!(listed.status(), StatusCode::OK);
    let body = body_json(listed).await;
    assert_eq!(body["data"].as_array().unwrap().len(), 1, "{body}");
    // The condition comes back as a DOCUMENT, not as the string stored: the caller sent JSON.
    assert_eq!(body["data"][0]["condition"]["discount_percent"]["gt"], 20);

    let one = send(
        &f.router,
        request(
            "GET",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(one.status(), StatusCode::OK);

    let mut promoted = over_20();
    promoted["mode"] = json!("warn");
    let updated = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            Some(promoted),
        ),
    )
    .await;
    assert_eq!(updated.status(), StatusCode::OK);
    assert_eq!(body_json(updated).await["data"]["mode"], "warn");

    let deleted = send(
        &f.router,
        request(
            "DELETE",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(deleted.status(), StatusCode::OK);

    let gone = send(
        &f.router,
        request(
            "GET",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(gone.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn only_a_human_who_administers_the_hub_gets_in_hub1701() {
    let f = fixture().await;
    for (label, session) in [
        ("sin sesión", None),
        ("cajero", Some(f.employee.as_str())),
    ] {
        let response = send(
            &f.router,
            request("GET", "/api/hub/policies", session, None),
        )
        .await;
        assert!(
            response.status() == StatusCode::UNAUTHORIZED
                || response.status() == StatusCode::FORBIDDEN,
            "{label}: {}",
            response.status()
        );
    }
    // And a REAL, active API key of this hub does not get in either: whoever writes the business
    // rules is a person, not a copyable credential stored inside an integration.
    let with_key = send(
        &f.router,
        Request::builder()
            .method("POST")
            .uri("/api/hub/policies")
            .header("x-api-key", &f.api_key)
            .header("content-type", "application/json")
            .body(Body::from(over_20().to_string()))
            .unwrap(),
    )
    .await;
    assert!(
        with_key.status() == StatusCode::UNAUTHORIZED || with_key.status() == StatusCode::FORBIDDEN,
        "api key: {}",
        with_key.status()
    );
}

#[tokio::test]
async fn each_refusal_of_the_core_arrives_with_ITS_own_status_hub1701() {
    let f = fixture().await;

    // 404 — a checkpoint no module offers.
    let mut ghost = over_20();
    ghost["checkpoint"] = json!("p1701/ghost");
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(ghost)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "policy.checkpoint_not_found"
    );

    // 501 — the checkpoint DOES offer it and this core cannot apply it yet (hub#1710). That is
    // the distinction that matters: one is fixed by changing the rule, the other by waiting for a
    // release.
    let mut elevate = over_20();
    elevate["outcome"] = json!("elevate:p1701.order.discount");
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(elevate)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::NOT_IMPLEMENTED);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "policy.outcome_not_available"
    );

    // 501 too, and for the same reason: a window judges the clock and the gate only sees what the
    // command carries (hub#1713). The owner cannot fix it by rewriting the rule.
    let mut window = over_20();
    window["condition"] = json!({ "discount_percent": { "within_last": 3600 } });
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(window)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::NOT_IMPLEMENTED);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "policy.condition_needs_clock"
    );

    // 400 — what the caller sent wrong.
    let mut mute = over_20();
    mute["message"] = json!("   ");
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(mute)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "policy.message_required"
    );
}

#[tokio::test]
async fn a_rule_written_through_the_door_is_in_force_for_the_TILL_hub1701() {
    // The positive control of the whole door: without this, a CRUD that stores lovely rows and
    // gates nothing would pass for «done». The rule is written over HTTP and checked where it
    // matters, which is the command.
    let f = fixture().await;
    create(&f, over_20()).await;

    // The hub's command door is ONE single door (`POST /api/command`, ADR-0005) and the name
    // travels in the body, not as a path segment: the dispatcher's per-hub routing is what decides
    // which runtime runs it, and a name in the URL would have opened a second door with its own
    // authentication. Asking through `/api/commands/<name>` gave `404` with an empty body, which
    // is exactly what a gate that does not apply would have given: this test proved nothing.
    let response = send(
        &f.router,
        request(
            "POST",
            "/api/command",
            Some(&f.admin),
            Some(json!({
                "name": "p1701.order.set_discount",
                "payload": { "order_id": "o1", "discount_percent": 35 }
            })),
        ),
    )
    .await;
    let status = response.status();
    let body = body_json(response).await;
    assert_eq!(body["error"]["code"], "policy.blocked", "{status} {body}");
    // And the text the person at the counter reads is the one the owner wrote.
    assert_eq!(
        body["error"]["message"],
        "Los descuentos de más del 20 % los autoriza el encargado"
    );
}

#[tokio::test]
async fn the_author_of_a_rule_is_the_SESSION_never_the_body_hub1701() {
    // 🔴 `created_by`/`updated_by` come from the resolved session and NEVER from the body — the
    // same rule as `granted_by` in flows and `discarded_by` in the dead-letter. Here it is the
    // essential part: a rule decides whether a sale can be charged, so its row IS the record of
    // who decided that. A caller able to sign for someone else would turn the audit trail into a
    // text field.
    //
    // MUTANT: read the author from the body in `policies_api::create_policy` — this test falls.
    let f = fixture().await;
    let mut forged = over_20();
    forged["created_by"] = json!("hub_user:otro");
    forged["updated_by"] = json!("hub_user:otro");
    let id = create(&f, forged).await;

    let response = send(
        &f.router,
        request(
            "GET",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    let body = body_json(response).await;
    let mine = format!("hub_user:{}", f.admin_id);
    assert_eq!(body["data"]["created_by"], mine, "{body}");
    assert_eq!(body["data"]["updated_by"], mine, "{body}");

    // 🔴 And the SAME through the PUT, which is the door carrying a body every time the owner
    // touches a rule — promoting it from `warn` to `enforce`, fixing its wording. Asserting it
    // only at creation left the mutant «`update_policy` reads the author from the body» alive with
    // the battery green (measured in the review of PR #1741), and it is the EDIT — not the
    // creation — that the audit trail gets asked about afterwards.
    let mut forged = over_20();
    forged["mode"] = json!("warn");
    forged["created_by"] = json!("hub_user:otro");
    forged["updated_by"] = json!("hub_user:otro");
    let response = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            Some(forged),
        ),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["data"]["updated_by"], mine, "{body}");
    assert_eq!(body["data"]["created_by"], mine, "{body}");
}
