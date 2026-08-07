//! HTTP surface of the hub's print queue (hub#341, ADR-0196 §6).
//!
//! Any device enqueues here — the PWA on a phone included, which is precisely the client that
//! cannot talk to a printer. Draining the queue (the print host over the WS) is hub#342/#343; this
//! file covers the producer side: **enqueue** and **observe**.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-print";

/// A hub in `Session` auth mode (the production gate) with one employee session open.
async fn fixture() -> (axum::Router, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let user = rt
        .create_user("Cashier", "1111", "employee", None)
        .await
        .unwrap();
    let session = rt.create_session(&user, 3600, None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-print-queue-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
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
        bootstrap_blueprint: None,
    };
    (app(AppState::with_config(rt, cfg)), session)
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    match body {
        Some(b) => builder
            .header("content-type", "application/json")
            .body(Body::from(b.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn ticket(job_id: &str, role: &str) -> Value {
    json!({ "jobId": job_id, "role": role, "html": "<p>ticket</p>" })
}

/// Enqueueing is not anonymous: the print queue is hub data behind the same session gate as the
/// rest of the core API.
#[tokio::test]
async fn the_print_queue_requires_a_user_session() {
    let (router, _session) = fixture().await;

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/jobs",
            None,
            Some(ticket("j1", "receipt")),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

    let resp = router
        .oneshot(request("GET", "/api/print/jobs", None, None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}

/// The happy path: a job posted by any session waits in the queue for a print host of its role.
#[tokio::test]
async fn a_posted_job_waits_in_the_queue() {
    let (router, session) = fixture().await;

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/jobs",
            Some(&session),
            Some(ticket("j1", "kitchen")),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    assert_eq!(body["jobId"], json!("j1"));
    assert_eq!(body["status"], json!("queued"));

    let resp = router
        .oneshot(request("GET", "/api/print/jobs", Some(&session), None))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    let jobs = body["jobs"].as_array().expect("the queue is observable");
    assert_eq!(jobs.len(), 1);
    assert_eq!(jobs[0]["jobId"], json!("j1"));
    assert_eq!(jobs[0]["role"], json!("kitchen"));
    assert_eq!(jobs[0]["status"], json!("pending"));
    assert_eq!(jobs[0]["attempts"], json!(0));
}

/// **Idempotency over HTTP.** A retried POST (lost response, double tap on "print") is answered
/// `duplicate` with `200`, not with an error and not with a second ticket.
#[tokio::test]
async fn posting_the_same_job_id_twice_queues_one_job() {
    let (router, session) = fixture().await;

    for _ in 0..2 {
        let resp = router
            .clone()
            .oneshot(request(
                "POST",
                "/api/print/jobs",
                Some(&session),
                Some(ticket("j1", "receipt")),
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/jobs",
            Some(&session),
            Some(ticket("j1", "receipt")),
        ))
        .await
        .unwrap();
    assert_eq!(body_json(resp).await["status"], json!("duplicate"));

    let resp = router
        .oneshot(request("GET", "/api/print/jobs", Some(&session), None))
        .await
        .unwrap();
    assert_eq!(body_json(resp).await["jobs"].as_array().unwrap().len(), 1);
}

/// The listing is a **status** view: it must not ship the document of every queued ticket to a
/// screen that only wants to know what is stuck. The document travels to the print host that
/// claims the job (hub#343), not to whoever polls the queue.
#[tokio::test]
async fn the_queue_listing_does_not_carry_the_document() {
    let (router, session) = fixture().await;
    router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/jobs",
            Some(&session),
            Some(ticket("j1", "receipt")),
        ))
        .await
        .unwrap();

    let resp = router
        .oneshot(request("GET", "/api/print/jobs", Some(&session), None))
        .await
        .unwrap();
    let body = body_json(resp).await;
    assert!(
        body["jobs"][0].get("html").is_none(),
        "the queue listing is a status view, not a document dump"
    );
}

/// The listing can be narrowed to one role — what a print host asks about its own work.
#[tokio::test]
async fn the_queue_listing_can_be_filtered_by_role() {
    let (router, session) = fixture().await;
    for (id, role) in [("j1", "receipt"), ("j2", "kitchen")] {
        router
            .clone()
            .oneshot(request(
                "POST",
                "/api/print/jobs",
                Some(&session),
                Some(ticket(id, role)),
            ))
            .await
            .unwrap();
    }

    let resp = router
        .oneshot(request(
            "GET",
            "/api/print/jobs?role=kitchen",
            Some(&session),
            None,
        ))
        .await
        .unwrap();
    let body = body_json(resp).await;
    let jobs = body["jobs"].as_array().unwrap();
    assert_eq!(jobs.len(), 1);
    assert_eq!(jobs[0]["jobId"], json!("j2"));
}

/// A malformed job is rejected with the stable `invalid_payload` contract, and nothing is queued.
#[tokio::test]
async fn an_incomplete_job_is_rejected_and_queues_nothing() {
    let (router, session) = fixture().await;

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/jobs",
            Some(&session),
            Some(json!({ "jobId": "j1", "role": "receipt", "html": "" })),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(
        body_json(resp).await["error"]["code"],
        json!("invalid_payload")
    );

    let resp = router
        .oneshot(request("GET", "/api/print/jobs", Some(&session), None))
        .await
        .unwrap();
    assert!(body_json(resp).await["jobs"].as_array().unwrap().is_empty());
}
