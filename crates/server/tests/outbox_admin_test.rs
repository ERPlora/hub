//! HTTP contract of the **operable dead-letter** (hub#660 — ADR-0127 phase 2, ADR-0283 K6a).
//!
//! `_event_outbox.status='dead'` used to be the end of the line: after `MAX_ATTEMPTS` the row
//! stopped moving, and the only window onto it was `GET /api/system` — 50 rows, no payload, nothing
//! to press. Production already has STRUCTURAL dead-letters (an employee closes a sale, the
//! `verifactu.records.ingest_invoice` listener demands a manager permission the emitter's
//! reconstructed context does not carry, eight attempts later the invoice event is dead), so what
//! this surface decides is whether that work is recoverable at all.
//!
//! Auth is the same door as `/api/keys` (ADR-0057): the **local session of a human owner/admin**,
//! never an API key and never the machine token. Replaying an event re-runs somebody else's
//! command with the emitter's permissions, and discarding one closes a fiscal record for good;
//! neither is something an integration token gets to do.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-outbox";
const DEAD_ID: &str = "evt-dead";
const DELIVERED_ID: &str = "evt-delivered";

struct Fixture {
    router: axum::Router,
    /// Session of an owner/admin — the only one who may operate the queue.
    admin: String,
    admin_id: String,
    /// Session of a cashier: a perfectly valid user who does not administer the hub.
    employee: String,
    /// A real, active API key of this hub. Valid everywhere it is meant to be — not here.
    api_key: String,
    temp: std::path::PathBuf,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// Seeds one row of `_event_outbox` straight into the hub's database — the state a relay leaves
/// behind after it gives up, without having to burn eight real attempts through the dispatcher.
async fn seed_event(db: &dyn DatabaseAdapter, id: &str, status: &str, attempts: i64) {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(HUB));
    p.insert("status".into(), json!(status));
    p.insert("attempts".into(), json!(attempts));
    p.insert("payload".into(), json!(r#"{"invoice_id":"F2-1","total":"12.10"}"#));
    p.insert("at".into(), json!("2026-08-09T10:00:00+00:00"));
    db.execute(
        "INSERT INTO _event_outbox \
         (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, status, \
          attempts, next_attempt_at, last_error, created_at) \
         VALUES (:id, :hub_id, 'cashier-1', '[]', 'sale.closed', 'sales', :payload, 1, :status, \
                 :attempts, :at, 'verifactu.records.ingest_invoice: permission_denied', :at)",
        &p,
    )
    .await
    .unwrap();
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

    // One dead-letter to operate on, and one delivered event that must never show up in the queue.
    seed_event(rt.db_for_test(), DEAD_ID, "dead", 7).await;
    seed_event(rt.db_for_test(), DELIVERED_ID, "delivered", 1).await;

    let temp = std::env::temp_dir().join(format!(
        "erplora-outbox-admin-{}-{admin_id}",
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

fn request(method: &str, uri: &str, session: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    builder.body(Body::empty()).unwrap()
}

async fn send(router: &axum::Router, request: Request<Body>) -> axum::response::Response {
    router.clone().oneshot(request).await.unwrap()
}

/// The queue is VISIBLE: what died, why, how many attempts it burnt and — the part `/api/system`
/// never had — the payload it was carrying, so an operator can tell a lost invoice from noise.
#[tokio::test]
async fn an_admin_sees_every_dead_letter_with_its_payload_and_error() {
    let f = fixture().await;

    let response = send(&f.router, request("GET", "/api/hub/events/dead", Some(&f.admin))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true);

    let dead = body["data"].as_array().unwrap();
    assert_eq!(dead.len(), 1, "only the dead one is queued, never the delivered one");
    let row = &dead[0];
    assert_eq!(row["id"], DEAD_ID);
    assert_eq!(row["event_name"], "sale.closed");
    assert_eq!(row["module_id"], "sales", "the EMITTING module");
    assert_eq!(row["user_id"], "cashier-1", "the cashier behind the structural dead-letter");
    assert_eq!(row["attempts"], 7);
    assert!(
        row["last_error"].as_str().unwrap().contains("ingest_invoice"),
        "the error names the listener that refused"
    );
    assert_eq!(
        row["payload"]["invoice_id"], "F2-1",
        "the payload is inspectable, parsed — not an opaque string"
    );

    std::fs::remove_dir_all(f.temp).ok();
}

/// Retry puts the row back in front of the relay; discard closes it and stamps WHO closed it —
/// taken from the session, never from the body.
#[tokio::test]
async fn retry_requeues_and_discard_stamps_the_session_user() {
    let f = fixture().await;

    // Retry → the row is `pending` again and disappears from the queue.
    let uri = format!("/api/hub/events/{DEAD_ID}/retry");
    let response = send(&f.router, request("POST", &uri, Some(&f.admin))).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(body_json(response).await["ok"], true);

    let listed = body_json(send(&f.router, request("GET", "/api/hub/events/dead", Some(&f.admin))).await).await;
    assert!(
        listed["data"].as_array().unwrap().is_empty(),
        "a retried event is no longer a dead-letter: it is queued work again"
    );

    // It is dead again (the relay is not running in this test, so put it back by hand) and this
    // time the admin closes it for good.
    let f2 = fixture().await;
    let uri = format!("/api/hub/events/{DEAD_ID}/discard");
    let response = send(&f2.router, request("POST", &uri, Some(&f2.admin))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true);
    assert_eq!(
        body["data"]["discarded_by"], format!("hub_user:{}", f2.admin_id),
        "the author comes from the SESSION, never from the request body"
    );

    let listed = body_json(send(&f2.router, request("GET", "/api/hub/events/dead", Some(&f2.admin))).await).await;
    assert!(listed["data"].as_array().unwrap().is_empty(), "discarded leaves the queue");

    // An id that is not a dead-letter of this hub is a 404 for both gestures — never a silent 200.
    for gesture in ["retry", "discard"] {
        for id in [DELIVERED_ID, "no-such-event"] {
            let uri = format!("/api/hub/events/{id}/{gesture}");
            let response = send(&f2.router, request("POST", &uri, Some(&f2.admin))).await;
            assert_eq!(response.status(), StatusCode::NOT_FOUND, "{gesture} {id}");
        }
    }

    std::fs::remove_dir_all(f.temp).ok();
    std::fs::remove_dir_all(f2.temp).ok();
}

/// The door: anonymous is 401, a logged-in NON-admin is 403 (authenticated, just not allowed), and
/// a valid API key is refused outright — the key only ever speaks `/api/v1`.
#[tokio::test]
async fn only_an_owner_or_admin_session_operates_the_queue() {
    let f = fixture().await;
    let routes = [
        ("GET", "/api/hub/events/dead".to_string()),
        ("GET", "/api/hub/events/dead/count".to_string()),
        ("POST", "/api/hub/events/retry-all".to_string()),
        ("POST", format!("/api/hub/events/{DEAD_ID}/retry")),
        ("POST", format!("/api/hub/events/{DEAD_ID}/discard")),
    ];

    for (method, uri) in &routes {
        let anonymous = send(&f.router, request(method, uri, None)).await;
        assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED, "anonymous {uri}");

        let cashier = send(&f.router, request(method, uri, Some(&f.employee))).await;
        assert_eq!(
            cashier.status(),
            StatusCode::FORBIDDEN,
            "a valid session without owner/admin is FORBIDDEN, not unauthenticated: {uri}"
        );

        // A real, active API key of this very hub. It authenticates everywhere it is supposed to;
        // replaying somebody else's command is not one of those places.
        let with_key = send(
            &f.router,
            Request::builder()
                .method(method.to_owned())
                .uri(uri)
                .header("authorization", format!("Bearer {}", f.api_key))
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(
            with_key.status(),
            StatusCode::UNAUTHORIZED,
            "an API key never reaches the dead-letter queue: {uri}"
        );
    }

    // And nothing the refused callers did touched the row.
    let listed = body_json(send(&f.router, request("GET", "/api/hub/events/dead", Some(&f.admin))).await).await;
    assert_eq!(listed["data"].as_array().unwrap().len(), 1, "the dead-letter is untouched");

    std::fs::remove_dir_all(f.temp).ok();
}

/// The count is the cheap number the topbar bell polls (no payloads). It counts ONLY `dead` rows,
/// and it drops to zero once the queue is cleared — the badge the operator trusts to mean "nothing
/// needs you". Then `retry-all` clears the whole queue in one gesture (the case a transient outage
/// killed several events), and the count reflects it immediately.
#[tokio::test]
async fn the_count_feeds_the_bell_and_retry_all_clears_the_queue() {
    let f = fixture().await;

    // The fixture seeds one dead row; the delivered one does not count.
    let response = send(&f.router, request("GET", "/api/hub/events/dead/count", Some(&f.admin))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true);
    assert_eq!(body["data"]["count"], 1, "one dead-letter, the delivered one does not count");

    // retry-all clears the whole queue: the dead row goes back to the relay, the count drops to 0.
    let response = send(&f.router, request("POST", "/api/hub/events/retry-all", Some(&f.admin))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true);
    assert_eq!(body["data"]["retried"], 1, "the one dead row moved back to the relay");

    let response = send(&f.router, request("GET", "/api/hub/events/dead/count", Some(&f.admin))).await;
    let body = body_json(response).await;
    assert_eq!(body["data"]["count"], 0, "the queue is clear — the bell reads zero");

    // Idempotent: a second retry-all moves nothing, still 200 (0 is a valid "nothing to do").
    let response = send(&f.router, request("POST", "/api/hub/events/retry-all", Some(&f.admin))).await;
    let body = body_json(response).await;
    assert_eq!(body["data"]["retried"], 0, "the queue was already clear");

    std::fs::remove_dir_all(f.temp).ok();
}
