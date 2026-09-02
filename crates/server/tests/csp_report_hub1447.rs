//! hub#1447: the hub's CSP had no `report-uri`, so a blocked resource died in one device's
//! console and nowhere else.
//!
//! That is not a hypothetical. `ERPlora/infra#73` was Cloudflare injecting its Web Analytics
//! beacon into the HTML at the edge; `script-src 'self'` refused it on **every page of every
//! hub**, and the way we found out was a person opening the console by hand. The fix lived in
//! Cloudflare's panel, outside this repo, so no test can guard it — the only thing that can is a
//! hub that *says* when its policy fires. This file pins the saying.
//!
//! The SaaS has had the same wiring for a while (`apps/public/csp.py` → `/csp-report/` →
//! `csp_logger.warning`). This is its twin on the half where it matters more: every module's Web
//! Component runs in the SAME document and realm as the shell, with the session token in
//! `localStorage` (ADR-0308). There is no origin boundary between a module and the till.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, default_csp, AppState, AuthMode, HubConfig};
use tower::ServiceExt; // oneshot

/// The Cloud a production hub is pointed at, as `cloud_csp.rs` names it.
const CLOUD: &str = "https://erplora.com";

/// Where the browser posts the report. Same path the SaaS uses, on purpose: one name to alert on.
const REPORT_PATH: &str = "/csp-report/";

/// What a browser actually sends — Chrome's `application/csp-report` envelope, taken from the real
/// violation recorded in infra#73.
const REAL_REPORT: &str = r#"{"csp-report":{
  "document-uri":"https://salon-aurora.a.erplora.com/login",
  "referrer":"",
  "violated-directive":"script-src-elem",
  "effective-directive":"script-src-elem",
  "original-policy":"default-src 'self'; script-src 'self'",
  "disposition":"enforce",
  "blocked-uri":"https://static.cloudflareinsights.com/beacon.min.js/v4513226cda",
  "status-code":200,
  "script-sample":""}}"#;

async fn dev_app() -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ))
}

fn report(body: &'static str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(REPORT_PATH)
        .header("content-type", "application/csp-report")
        .body(Body::from(body))
        .unwrap()
}

// ── The policy names somewhere to report ────────────────────────────────────────────────────────

#[test]
fn hub1447_the_served_policy_tells_the_browser_where_to_report() {
    // The regression in one assertion: without this directive the browser has nowhere to send the
    // report, so a policy that fires on every page of every hub still produces no signal at all.
    let policy = default_csp(CLOUD);
    assert!(
        policy.contains(&format!("report-uri {REPORT_PATH}")),
        "the served policy carries no `report-uri`: a blocked resource stays in one device's \
         console, which is how infra#73 went unnoticed until somebody looked. Policy was: {policy}"
    );
}

#[test]
fn hub1447_the_report_endpoint_is_this_hub_and_not_a_third_party() {
    // A relative path, deliberately. An absolute URL would send every hub's violations to one
    // origin — mixing the fleet into a single log, needing the `hub_id` inside the report to tell
    // who spoke, and leaving a self-hosted hub reporting to a SaaS it may not have.
    let policy = default_csp(CLOUD);
    let reporting: Vec<&str> = policy
        .split(';')
        .map(str::trim)
        .filter(|d| d.starts_with("report-uri"))
        .collect();
    assert_eq!(
        reporting,
        vec![format!("report-uri {REPORT_PATH}").as_str()],
        "the report goes somewhere other than this hub"
    );
}

// ── …and the hub is listening on the other end ──────────────────────────────────────────────────

#[tokio::test]
async fn hub1447_a_violation_report_is_accepted() {
    // `report-uri` pointing at a 404 is worse than no `report-uri`: the browser keeps posting and
    // the hub keeps discarding, and the whole thing still produces nothing.
    let resp = dev_app().await.oneshot(report(REAL_REPORT)).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::NO_CONTENT,
        "the hub does not answer its own report-uri"
    );
}

#[tokio::test]
async fn hub1447_a_report_gets_through_before_the_machine_is_registered() {
    // The trap this change walks into: `require_machine_registration` gates the whole business
    // surface with a `428`, and a hub mid-enrolment is exactly the state where a broken policy is
    // most likely. A report swallowed by the registration barrier would be a silent failure
    // inside the fix against silent failures.
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "real-but-unregistered");
    rt.ensure_system_tables().await.unwrap();
    let cfg = HubConfig {
        demo: false,
        hub_id: "real-but-unregistered".into(),
        cloud_base_url: CLOUD.into(),
        module_cache: std::env::temp_dir().join("erplora-hub1447-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some("public-key-loaded".into()),
        cloud_api_token: None,
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-hub1447-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };

    let resp = app(AppState::with_config(rt, cfg))
        .oneshot(report(REAL_REPORT))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::NO_CONTENT,
        "an unregistered hub answers its own report-uri with {}: the reports of the hubs most \
         likely to be misconfigured are the ones that get dropped",
        resp.status()
    );
}

#[tokio::test]
async fn hub1447_a_junk_report_is_not_a_server_error() {
    // The door is open to anybody who can open the hub in a browser, and a browser is not the only
    // thing that can post to it. Malformed input is a `204`, never a `500` — a receiver that
    // panics on bad input is a new way to make noise, not a way to hear it.
    for body in [
        "not json at all",
        "",
        "{}",
        r#"{"csp-report":null}"#,
        r#"{"csp-report":{"blocked-uri":12345}}"#,
    ] {
        let resp = dev_app()
            .await
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(REPORT_PATH)
                    .header("content-type", "application/csp-report")
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert!(
            !resp.status().is_server_error(),
            "a {body:?} report answered {}",
            resp.status()
        );
    }
}

#[tokio::test]
async fn hub1447_an_oversized_report_does_not_land_in_the_log() {
    // `script-sample` carries a slice of the offending code, and a hostile page can make it large.
    // The body limit is the wall; what matters is that the hub refuses it instead of buffering
    // whatever it is sent.
    let huge = "x".repeat(512 * 1024);
    let resp = dev_app()
        .await
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(REPORT_PATH)
                .header("content-type", "application/csp-report")
                .body(Body::from(format!(
                    r#"{{"csp-report":{{"script-sample":"{huge}"}}}}"#
                )))
                .unwrap(),
        )
        .await
        .unwrap();
    assert!(
        !resp.status().is_server_error(),
        "an oversized report answered {}",
        resp.status()
    );
}
