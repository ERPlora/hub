//! 🔴 hub#2519: the System screen's state is read by an owner or an administrator only.
//!
//! `GET /api/system` answers the last 50 events between apps with their `last_error`, the server's
//! usage and the storage details. A rejected VeriFactu record leaves the tax agency's Fault in
//! `last_error`, with the customer's tax id and name. The door only asked for a session of the hub,
//! so a cashier who typed the address read it — while the dead-letter queue, which holds the very
//! same rows, has answered `403` to anyone who does not administer the hub since hub#660.
//!
//! Now it is the same gate as the dead-letter queue: no session is `401`, a valid session that does
//! not administer the hub is `403` with the stable code `forbidden` and nothing of the state.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-system-2519";
/// What a refused record leaves behind: the AEAT Fault, with the customer's tax id and name.
const AEAT_FAULT: &str =
    "verifactu.records.ingest_invoice: AEAT 4102 NIF B12345674 LAVANDERIA GARCIA SL no identificado";

struct Fixture {
    router: axum::Router,
    sessions: Vec<(&'static str, String)>,
    _db: TestDb,
}

async fn seed_refused_record(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("last_error".into(), json!(AEAT_FAULT));
    p.insert("at".into(), json!("2026-10-06T10:00:00+00:00"));
    db.execute(
        "INSERT INTO _event_outbox \
         (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, status, \
          attempts, next_attempt_at, last_error, created_at) \
         VALUES ('evt-refused', :hub_id, 'cashier-1', '[]', 'sale.closed', 'sales', '{}', 1, \
                 'dead', 8, :at, :last_error, :at)",
        &p,
    )
    .await
    .unwrap();
}

async fn fixture() -> Fixture {
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    seed_refused_record(rt.db_for_test()).await;

    let mut sessions = Vec::new();
    for (role, pin) in [
        ("admin", "1111"),
        ("manager", "2222"),
        ("employee", "3333"),
        ("cashier", "4444"),
    ] {
        let id = rt.create_user(role, pin, role, None).await.unwrap();
        sessions.push((role, rt.create_session(&id, 3600, None).await.unwrap()));
    }

    let temp = std::env::temp_dir().join(format!("erplora-system-2519-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB.into(),
        // A closed port: the storage half fails at once, so the answer is the hub's own state.
        cloud_base_url: "http://127.0.0.1:9".into(),
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
        sessions,
        _db: test_db,
    }
}

impl Fixture {
    fn session(&self, role: &str) -> &str {
        &self.sessions.iter().find(|(r, _)| *r == role).unwrap().1
    }
}

async fn get_system(router: &axum::Router, session: Option<&str>) -> (StatusCode, String) {
    let mut request = Request::builder().uri("/api/system");
    if let Some(session) = session {
        request = request.header("x-hub-session", session);
    }
    let response = router
        .clone()
        .oneshot(request.body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (status, String::from_utf8_lossy(&bytes).into_owned())
}

#[tokio::test]
async fn a_cashier_is_refused_the_system_state_and_never_reads_the_tax_fault() {
    let f = fixture().await;
    for role in ["cashier", "employee", "manager"] {
        let (status, body) = get_system(&f.router, Some(f.session(role))).await;
        assert_eq!(
            status,
            StatusCode::FORBIDDEN,
            "{role} must not read System: {body}"
        );
        let json: Value = serde_json::from_str(&body).unwrap();
        assert_eq!(json["error"]["code"], "forbidden", "{role}: {body}");
        assert!(
            !body.contains("B12345674"),
            "{role} read the customer's tax id: {body}"
        );
        assert!(
            json.get("data").is_none(),
            "{role} got part of the state: {body}"
        );
    }
}

#[tokio::test]
async fn an_administrator_still_reads_the_system_state_with_its_logs() {
    let f = fixture().await;
    let (status, body) = get_system(&f.router, Some(f.session("admin"))).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let json: Value = serde_json::from_str(&body).unwrap();
    let logs = json["data"]["logs"].as_array().expect("logs");
    assert_eq!(logs.len(), 1, "{body}");
    assert_eq!(logs[0]["level"], "ERROR");
    assert_eq!(logs[0]["meta"], AEAT_FAULT);
}

#[tokio::test]
async fn without_a_session_it_is_still_unauthorized() {
    let f = fixture().await;
    let (status, body) = get_system(&f.router, None).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED, "{body}");
    assert!(!body.contains("B12345674"), "{body}");
}
