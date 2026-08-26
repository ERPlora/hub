//! hub#1108 — **the door** to the print queue's two recovery gestures, and who may walk through it.
//!
//! `POST /api/print/jobs/{jobId}/retry` and `POST /api/print/jobs/{jobId}/discard` are new surface
//! over a queue that had none: until now nothing at any level could re-humanise a `dead` job or
//! retire one nobody was ever going to print.
//!
//! **Two gates, in this order**, the pattern `outbox_admin` already applies to the hub's other
//! durable queue:
//!
//! 1. **An admin session.** Deliberately asymmetric with READING the queue, which is any local
//!    session (hub#987: whoever is standing next to the printer is who can turn the till on).
//!    Throwing a ticket in the bin, or re-firing one, is the owner's or the manager's gesture — the
//!    same class of decision as the station CRUD next door, and behind the same door.
//! 2. **The `printer` capability, if the caller NAMES a module.** `@erplora/module-sdk` stamps
//!    `X-Erplora-Module`, so without this second gate "an admin is logged in" would mean every
//!    installed module can bin every other one's tickets. A caller that names no module — the shell,
//!    `curl` — passes on the session alone, which is pinned below too: this narrows the door for
//!    modules and for nobody else.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tower::ServiceExt;

const HUB: &str = "hub-print-recovery-door";
const MODULE_HEADER: &str = "x-erplora-module";
/// The module the owner installed to watch the printers: it DECLARES `printer`.
const PRINTING: &str = "printing";
/// An ordinary installed module. It must not get to bin the till's tickets.
const INVENTORY: &str = "inventory";

/// One job per gesture, so the mutating ones do not eat each other's subject.
const JOB_RETRY: &str = "job-retry";
const JOB_DISCARD: &str = "job-discard";

struct Fixture {
    router: axum::Router,
    admin: String,
    cashier: String,
    rt: std::sync::Arc<tokio::sync::Mutex<Runtime>>,
    temp: PathBuf,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// A module on disk, so the installer registers a REAL manifest — the capability gate reads what
/// the module declared, not what a test asserted.
fn module_dir(root: &Path, id: &str, extra: Value) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
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
    dir
}

/// Queues a job and drives it to `dead` the way the machine really does — hand it out
/// `MAX_ATTEMPTS` times and let the host report a failure each time.
async fn seed_dead(rt: &Runtime, job_id: &str) {
    use erplora_runtime::print_queue::{self, MAX_ATTEMPTS};
    let job = serde_json::from_value(json!({
        "jobId": job_id,
        "role": "kitchen",
        "documentType": "kitchen_order",
        "document": { "lines": [] },
    }))
    .unwrap();
    rt.enqueue_print_job(&job).await.unwrap();
    let station = erplora_runtime::print_stations::resolve(rt.db_for_test(), HUB, "kitchen")
        .await
        .unwrap();
    for _ in 0..MAX_ATTEMPTS {
        print_queue::claim_next(rt.db_for_test(), HUB, &station.id, "till-1", 90)
            .await
            .unwrap()
            .expect("there is a job to hand out");
        print_queue::mark_failed(rt.db_for_test(), HUB, job_id, "printer offline")
            .await
            .unwrap();
    }
}

/// `granted` = the owner ticked `printer` for the printing module in Settings → Permissions.
async fn fixture(granted: bool) -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();

    let admin_id = rt.create_user("Ioan", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let cashier_id = rt
        .create_user("Marta", "2222", "employee", None)
        .await
        .unwrap();
    let cashier = rt.create_session(&cashier_id, 3600, None).await.unwrap();

    for job in [JOB_RETRY, JOB_DISCARD] {
        seed_dead(&rt, job).await;
    }

    let temp = std::env::temp_dir().join(format!(
        "erplora-print-recovery-door-{}-{admin_id}",
        std::process::id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(
        &modules,
        PRINTING,
        json!({ "capabilities": { "printer": {} } }),
    ))
    .await
    .unwrap();
    rt.install_from_dir(&module_dir(&modules, INVENTORY, json!({})))
        .await
        .unwrap();
    if granted {
        rt.set_module_capability(PRINTING, "printer", true, "hub_user:admin")
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
    let state = AppState::with_config(rt, cfg);
    let rt = state.runtime_for(HUB).await.unwrap();
    Fixture {
        router: app(state),
        admin,
        cashier,
        rt,
        temp,
    }
}

fn post(uri: &str, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("POST").uri(uri);
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

/// Both gestures, as `(uri, subject)`. The list is here so a route added later without a gate turns
/// this red instead of shipping open.
fn every_gesture() -> Vec<String> {
    vec![
        format!("/api/print/jobs/{JOB_RETRY}/retry"),
        format!("/api/print/jobs/{JOB_DISCARD}/discard"),
    ]
}

async fn status_of(f: &Fixture, job_id: &str) -> String {
    f.rt.lock()
        .await
        .print_queue(None, None, 500)
        .await
        .unwrap()
        .into_iter()
        .find(|j| j.job_id == job_id)
        .map(|j| j.status)
        .unwrap_or_default()
}

/// Gate 1, the anonymous half: no session, no gesture — and nothing moved.
#[tokio::test]
async fn an_anonymous_caller_cannot_touch_the_queue() {
    let f = fixture(true).await;

    for uri in every_gesture() {
        let refused = send(&f.router, post(&uri, None, None)).await;
        assert_eq!(
            refused.status(),
            StatusCode::UNAUTHORIZED,
            "{uri} let an anonymous caller in"
        );
    }
    assert_eq!(status_of(&f, JOB_RETRY).await, "dead");
    assert_eq!(status_of(&f, JOB_DISCARD).await, "dead");
    let _ = std::fs::remove_dir_all(&f.temp);
}

/// Gate 1, the substantive half: a cashier READS the queue (hub#987) but does not re-fire or bin a
/// ticket. `403` and not `401`, because re-authenticating would get her nowhere.
#[tokio::test]
async fn a_cashier_reads_the_queue_but_does_not_bin_a_ticket() {
    let f = fixture(true).await;

    // She can read it — the asymmetry is deliberate, not an oversight.
    let listed = send(
        &f.router,
        Request::builder()
            .method("GET")
            .uri("/api/print/jobs")
            .header("x-hub-session", &f.cashier)
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert_eq!(listed.status(), StatusCode::OK);

    for uri in every_gesture() {
        let refused = send(&f.router, post(&uri, Some(&f.cashier), None)).await;
        assert_eq!(refused.status(), StatusCode::FORBIDDEN, "{uri} let a cashier write");
        let body = body_json(refused).await;
        assert_eq!(body["error"]["code"], json!("forbidden"));
    }
    assert_eq!(status_of(&f, JOB_RETRY).await, "dead");
    assert_eq!(status_of(&f, JOB_DISCARD).await, "dead");
    let _ = std::fs::remove_dir_all(&f.temp);
}

/// Gate 2. An ordinary installed module, calling inside a real admin's session, must not be able to
/// bin the till's tickets.
#[tokio::test]
async fn an_ordinary_module_never_reaches_the_recovery_gestures() {
    let f = fixture(true).await;

    for uri in every_gesture() {
        let refused = send(&f.router, post(&uri, Some(&f.admin), Some(INVENTORY))).await;
        assert_eq!(
            refused.status(),
            StatusCode::FORBIDDEN,
            "{uri} let a module without `printer` in"
        );
        let body = body_json(refused).await;
        assert_eq!(
            body["error"]["code"],
            json!("capability_denied"),
            "the refusal has to be the code that lets a screen ask for the grant: {body}"
        );
    }
    assert_eq!(status_of(&f, JOB_RETRY).await, "dead");
    assert_eq!(status_of(&f, JOB_DISCARD).await, "dead");
    let _ = std::fs::remove_dir_all(&f.temp);
}

/// …and declaring `printer` is not enough: the owner has to have GRANTED it.
#[tokio::test]
async fn declaring_the_capability_is_not_granting_it() {
    let f = fixture(false).await;

    for uri in every_gesture() {
        let refused = send(&f.router, post(&uri, Some(&f.admin), Some(PRINTING))).await;
        assert_eq!(refused.status(), StatusCode::FORBIDDEN, "{uri} passed ungranted");
    }
    assert_eq!(status_of(&f, JOB_RETRY).await, "dead");
    let _ = std::fs::remove_dir_all(&f.temp);
}

/// The module the owner DID grant walks through, and the gesture really happens.
#[tokio::test]
async fn the_granted_module_re_fires_and_retires_a_ticket() {
    let f = fixture(true).await;

    let retried = send(
        &f.router,
        post(
            &format!("/api/print/jobs/{JOB_RETRY}/retry"),
            Some(&f.admin),
            Some(PRINTING),
        ),
    )
    .await;
    assert_eq!(retried.status(), StatusCode::OK);
    let body = body_json(retried).await;
    assert_eq!(body["data"]["jobId"], json!(JOB_RETRY));
    assert_eq!(body["data"]["status"], json!("pending"));
    assert_eq!(status_of(&f, JOB_RETRY).await, "pending");

    let discarded = send(
        &f.router,
        Request::builder()
            .method("POST")
            .uri(format!("/api/print/jobs/{JOB_DISCARD}/discard"))
            .header("x-hub-session", &f.admin)
            .header(MODULE_HEADER, PRINTING)
            .header("content-type", "application/json")
            .body(Body::from(
                json!({ "reason": "  de una sesión de QA  " }).to_string(),
            ))
            .unwrap(),
    )
    .await;
    assert_eq!(discarded.status(), StatusCode::OK);
    let body = body_json(discarded).await;
    assert_eq!(status_of(&f, JOB_DISCARD).await, "discarded");
    assert_eq!(
        body["data"]["discardReason"], json!("de una sesión de QA"),
        "what comes back is what was STORED, trimmed: {body}"
    );
    assert!(
        body["data"]["discardedBy"]
            .as_str()
            .is_some_and(|s| s.starts_with("hub_user:")),
        "the author comes from the resolved session, never the body: {body}"
    );
    let _ = std::fs::remove_dir_all(&f.temp);
}

/// The shell and `curl` name no module and are untouched: this narrows the door for modules and for
/// nobody else.
#[tokio::test]
async fn a_caller_that_names_no_module_passes_on_the_session_alone() {
    let f = fixture(false).await;

    let retried = send(
        &f.router,
        post(
            &format!("/api/print/jobs/{JOB_RETRY}/retry"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(retried.status(), StatusCode::OK);
    assert_eq!(status_of(&f, JOB_RETRY).await, "pending");
    let _ = std::fs::remove_dir_all(&f.temp);
}

/// A `jobId` this hub does not have is `404`, and a job in the wrong state is `409` NAMING that
/// state — never a `200` that reports a move which never happened.
#[tokio::test]
async fn a_refusal_says_which_one_it_is() {
    let f = fixture(true).await;

    let missing = send(
        &f.router,
        post("/api/print/jobs/never-existed/retry", Some(&f.admin), None),
    )
    .await;
    assert_eq!(missing.status(), StatusCode::NOT_FOUND);

    // Put it back to `pending`, then ask for a retry it no longer needs.
    let ok = send(
        &f.router,
        post(
            &format!("/api/print/jobs/{JOB_RETRY}/retry"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(ok.status(), StatusCode::OK);
    let again = send(
        &f.router,
        post(
            &format!("/api/print/jobs/{JOB_RETRY}/retry"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(again.status(), StatusCode::CONFLICT);
    let body = body_json(again).await;
    assert_eq!(body["error"]["code"], json!("print.job_not_requeueable"));
    assert_eq!(
        body["error"]["status"], json!("pending"),
        "the refusal names the state the job is really in: {body}"
    );
    let _ = std::fs::remove_dir_all(&f.temp);
}
