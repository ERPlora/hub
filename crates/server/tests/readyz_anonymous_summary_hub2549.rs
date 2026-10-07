//! 🔴 hub#2549: whoever has not signed in reads only whether each part of the hub is up.
//!
//! `/readyz` stays open — Swarm's `HEALTHCHECK`, Traefik, the load balancer and the SaaS ask it
//! without any credential, and its HTTP status (200/503) and `status` are their whole contract. But
//! its body carried the inside of the hub to anyone who typed the address: the database driver's
//! own error text, the count of system migrations, which modules are missing and the filesystem
//! path and reason of each one that failed to install. That is what an attacker uses to map the
//! hub, and nobody outside the hub needs it to decide «send traffic or not».
//!
//! The market pattern (Spring Boot `show-details: when-authorized`, the shape this endpoint already
//! copies): an anonymous caller gets the verdict and each part's status; the detail is for an owner
//! or an administrator, through the same gate as the System screen (`require_admin_session`,
//! hub#2519). The status code never depends on who asks.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::TestDb;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt;

const HUB: &str = "hub-readyz-2549";

struct Fixture {
    router: axum::Router,
    state: AppState,
    admin: String,
    cashier: String,
    _db: TestDb,
}

/// A hub in production mode (`AuthMode::Session`). With `broken = true` the system-migrations
/// ledger is gone, so the `migrations` check fails with the database's own error text — the
/// internal detail hub#2549 is about.
async fn fixture(broken: bool) -> Fixture {
    fixture_without(if broken {
        Some("_hub_migrations")
    } else {
        None
    })
    .await
}

/// The same hub with `table` dropped after the sessions are open.
async fn fixture_without(table: Option<&str>) -> Fixture {
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("admin", "1111", "admin", None)
        .await
        .unwrap();
    let cashier_id = rt
        .create_user("cashier", "4444", "cashier", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let cashier = rt.create_session(&cashier_id, 3600, None).await.unwrap();
    if let Some(table) = table {
        rt.db_for_test()
            .execute(&format!("DROP TABLE {table}"), &Params::new())
            .await
            .unwrap();
    }

    let temp = std::env::temp_dir().join(format!("erplora-readyz-2549-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB.into(),
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
    let state = AppState::with_config(rt, cfg);
    Fixture {
        router: app(state.clone()),
        state,
        admin,
        cashier,
        _db: test_db,
    }
}

async fn readyz(router: &axum::Router, session: Option<&str>) -> (StatusCode, Value) {
    let mut request = Request::builder().uri("/readyz");
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
    (status, serde_json::from_slice(&bytes).unwrap())
}

/// Every check of an anonymous answer is `{status}` and nothing else.
fn assert_only_statuses(body: &Value, who: &str) {
    let checks = body["checks"].as_object().expect("checks is an object");
    assert!(
        !checks.is_empty(),
        "{who}: the parts are still listed: {body}"
    );
    for (name, check) in checks {
        let keys: Vec<&String> = check
            .as_object()
            .expect("a check is an object")
            .keys()
            .collect();
        assert_eq!(
            keys,
            vec!["status"],
            "{who} read the inside of the `{name}` check (hub#2549): {body}"
        );
    }
}

#[tokio::test]
async fn an_anonymous_caller_reads_whether_the_hub_is_ready_but_not_its_internal_errors_hub2549() {
    let f = fixture(true).await;

    let (status, body) = readyz(&f.router, None).await;

    // The contract with Swarm and Traefik does not move: a hub that cannot serve is 503 DOWN.
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE, "{body}");
    assert_eq!(body["status"], "DOWN");
    assert_eq!(body["checks"]["migrations"]["status"], "DOWN");
    assert_only_statuses(&body, "an anonymous caller");
    assert!(
        !body.to_string().contains("_hub_migrations"),
        "the database's error text reached an anonymous caller: {body}"
    );
}

#[tokio::test]
async fn a_healthy_hub_tells_an_anonymous_caller_up_and_nothing_of_its_inside_hub2549() {
    let f = fixture(false).await;

    let (status, body) = readyz(&f.router, None).await;

    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["status"], "UP");
    assert_eq!(body["checks"]["database"]["status"], "UP");
    assert_eq!(body["checks"]["migrations"]["status"], "UP");
    assert_eq!(body["checks"]["modules"]["status"], "UP");
    assert_only_statuses(&body, "an anonymous caller");
}

/// A session that does not administer the hub is not the System screen's audience either
/// (hub#2519): it reads what an anonymous caller reads.
#[tokio::test]
async fn a_cashier_session_reads_only_the_statuses_hub2549() {
    let f = fixture(true).await;

    let (status, body) = readyz(&f.router, Some(&f.cashier)).await;

    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE, "{body}");
    assert_only_statuses(&body, "a cashier");
}

/// A token that resolves to nothing is an anonymous caller — never a `401`: the probe's status code
/// is the orchestrator's verdict, and a rejection there would read as «this hub is broken».
#[tokio::test]
async fn an_unknown_session_is_an_anonymous_caller_not_a_rejection_hub2549() {
    let f = fixture(false).await;

    let (status, body) = readyz(&f.router, Some("not-a-session")).await;

    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["status"], "UP");
    assert_only_statuses(&body, "an unknown session");
}

/// The owner or an administrator keeps the whole diagnosis: the error text, the counts and the
/// modules — what the detail is for.
#[tokio::test]
async fn an_administrator_keeps_the_whole_diagnosis_hub2549() {
    let f = fixture(true).await;

    let (status, body) = readyz(&f.router, Some(&f.admin)).await;

    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE, "{body}");
    assert!(
        body["checks"]["migrations"]["error"]
            .as_str()
            .is_some_and(|error| error.contains("_hub_migrations")),
        "the administrator lost the diagnosis: {body}"
    );
    assert!(body["checks"]["modules"]["expected"].is_number(), "{body}");
    assert!(body["version"].is_string(), "{body}");
}

/// A session this hub cannot look up because its own database fails is not an invented token.
/// Counting it would lock a shop's address out of its PIN door during an outage — the rule the
/// door-wide count already follows (`track_rejected_credentials`, hub#2282).
#[tokio::test]
async fn a_session_the_hub_cannot_look_up_is_not_counted_as_invented_hub2549() {
    let f = fixture_without(Some("hub_session")).await;
    let shop = "198.51.100.80";

    for i in 0..erplora_server::address_guard::MAX_FORGED_SESSIONS {
        let request = Request::builder()
            .uri("/readyz")
            .header("x-hub-session", format!("unreadable-{i:054}"))
            .header("x-forwarded-for", format!("10.9.9.9, {shop}"))
            .body(Body::empty())
            .unwrap();
        let response = f.router.clone().oneshot(request).await.unwrap();
        assert_ne!(response.status(), StatusCode::UNAUTHORIZED);
    }

    assert!(
        f.state.address_guard.locked_for(shop).is_none(),
        "a database outage locked the address as if its sessions were invented"
    );
}
