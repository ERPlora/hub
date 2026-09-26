//! A ticket queued with nobody to print it leaves a line in the hub log (hub#1781).
//!
//! hub#1777 made the enqueue answer carry `liveHosts`, so the cashier and the home panel see a
//! ticket that is waiting for a printer that does not exist. Whoever watches the fleet saw
//! nothing: a business could go on charging without paper for days and the only trace lived on
//! its own screen. These tests pin the third channel — the log — to the same fact the answer
//! carries, and keep it quiet where it would be noise.
//!
//! The capture is a **global** subscriber installed once for this binary: `tracing` caches
//! callsite interest process-wide (hub#1796), so a thread-local capture can come back empty on a
//! healthy commit. Each test queues its own `jobId` and only reads the lines that name it, which
//! is what keeps the tests independent while they share one sink.
use std::sync::{Arc, Mutex, OnceLock};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-print-log";

/// The stable code the line carries; alerts and these tests match on it, never on the prose.
const EVENT_CODE: &str = "print.job_unattended";

#[derive(Clone, Default)]
struct Sink(Arc<Mutex<Vec<u8>>>);

impl std::io::Write for Sink {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0
            .lock()
            .map_err(|_| std::io::Error::other("poisoned log sink"))?
            .extend_from_slice(buf);
        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for Sink {
    type Writer = Self;

    fn make_writer(&'a self) -> Self::Writer {
        self.clone()
    }
}

fn sink() -> &'static Sink {
    static SINK: OnceLock<Sink> = OnceLock::new();
    SINK.get_or_init(|| {
        let sink = Sink::default();
        let subscriber = tracing_subscriber::fmt()
            .with_writer(sink.clone())
            .with_ansi(false)
            .with_max_level(tracing::Level::TRACE)
            .finish();
        tracing::subscriber::set_global_default(subscriber)
            .expect("this test binary installs the only global subscriber");
        sink
    })
}

/// The log lines that carry the unattended code AND name `job_id`.
fn unattended_lines(job_id: &str) -> Vec<String> {
    let text = String::from_utf8_lossy(&sink().0.lock().unwrap()).to_string();
    text.lines()
        .filter(|l| l.contains(EVENT_CODE) && l.contains(&format!("job_id=\"{job_id}\"")))
        .map(str::to_owned)
        .collect()
}

async fn fixture() -> (axum::Router, String) {
    sink();
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let user = rt
        .create_user("Cashier", "1111", "employee", None)
        .await
        .unwrap();
    let session = rt.create_session(&user, 3600, None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-print-log-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
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
    };
    (app(AppState::with_config(rt, cfg)), session)
}

async fn enqueue(router: &axum::Router, session: &str, job_id: &str, role: &str) -> Value {
    let req = Request::builder()
        .method("POST")
        .uri("/api/print/jobs")
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from(
            json!({
                "jobId": job_id,
                "role": role,
                "documentType": "receipt",
                "document": { "receipt_id": job_id, "total": 12.5 },
            })
            .to_string(),
        ))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the job is accepted");
    let bytes = http_body_util::BodyExt::collect(resp.into_body())
        .await
        .unwrap()
        .to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn register_host(router: &axum::Router, session: &str, device_id: &str, role: &str) {
    let req = Request::builder()
        .method("POST")
        .uri("/api/print/hosts")
        .header("x-hub-session", session)
        .header("x-device-id", device_id)
        .header("content-type", "application/json")
        .body(Body::from(
            json!({ "role": role, "label": device_id }).to_string(),
        ))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the host registers");
}

/// The state in the report: no printer set up. The ticket queues and the hub log says so, at
/// WARN, with the station it is waiting on.
#[tokio::test]
async fn a_ticket_queued_with_nobody_to_print_it_warns_in_the_hub_log() {
    let (router, session) = fixture().await;

    let body = enqueue(&router, &session, "unattended-1", "receipt").await;
    assert_eq!(
        body["liveHosts"],
        json!(0),
        "precondition: nobody drains `receipt`"
    );

    let lines = unattended_lines("unattended-1");
    assert_eq!(lines.len(), 1, "exactly one line for the ticket: {lines:?}");
    assert!(lines[0].contains("WARN"), "it is a warning: {}", lines[0]);
    assert!(
        lines[0].contains("role=\"receipt\""),
        "the line names the station nobody drains: {}",
        lines[0]
    );
}

/// The healthy hub stays quiet: with a device draining the station, a ticket is not news.
#[tokio::test]
async fn a_ticket_for_a_station_a_device_is_draining_writes_no_warning() {
    let (router, session) = fixture().await;
    register_host(&router, &session, "till-1", "receipt").await;

    let body = enqueue(&router, &session, "attended-1", "receipt").await;
    assert_eq!(
        body["liveHosts"],
        json!(1),
        "precondition: `till-1` drains `receipt`"
    );

    assert!(
        unattended_lines("attended-1").is_empty(),
        "a drained station is not an incident"
    );
}

/// A device draining ANOTHER station does not cover this ticket: the kitchen printer being
/// alive says nothing about the receipt nobody is going to print.
#[tokio::test]
async fn a_device_on_another_station_does_not_silence_the_warning() {
    let (router, session) = fixture().await;
    register_host(&router, &session, "kds-1", "kitchen").await;

    enqueue(&router, &session, "unattended-2", "receipt").await;

    assert_eq!(unattended_lines("unattended-2").len(), 1);
}

/// A retry of the same `jobId` is one ticket, so it is one line: a till that re-sends on a flaky
/// network must not multiply the incident.
#[tokio::test]
async fn a_duplicate_of_an_unattended_ticket_does_not_warn_twice() {
    let (router, session) = fixture().await;

    let first = enqueue(&router, &session, "unattended-3", "receipt").await;
    let again = enqueue(&router, &session, "unattended-3", "receipt").await;
    assert_eq!(first["status"], json!("queued"));
    assert_eq!(again["status"], json!("duplicate"));

    assert_eq!(unattended_lines("unattended-3").len(), 1);
}

/// The line names the STATION the ticket landed on, not the word the producer sent: the alert
/// that reads `role` has to match the same key the hosts register under, and ` Kitchen ` is not
/// a station anybody drains.
#[tokio::test]
async fn the_warning_names_the_resolved_station_not_the_producers_spelling() {
    let (router, session) = fixture().await;

    let body = enqueue(&router, &session, "unattended-4", " Kitchen ").await;
    assert_eq!(
        body["role"],
        json!("kitchen"),
        "precondition: the answer resolves it"
    );

    let lines = unattended_lines("unattended-4");
    assert_eq!(lines.len(), 1, "exactly one line: {lines:?}");
    assert!(
        lines[0].contains("role=\"kitchen\""),
        "the canonical station key, never the producer's spelling: {}",
        lines[0]
    );
}
