//! **The hub can ask what the marketplace still OFFERS of a module it already runs** (ADR-0380).
//!
//! Regression test for ERPlora/hub#1134. A module the marketplace has RETIRED keeps working here
//! and keeps updating — that is the half of ADR-0380 that does not break the fleet — but «My apps»
//! painted it exactly like a healthy one. It is the *closed plugin* failure of WordPress.org: the
//! plugin is closed, the site keeps it, and the core shows it as up to date because there is no
//! update to offer, so nobody ever finds out.
//!
//! ⚠️ Why the DETAIL door and not the catalogue, verified against `ERPlora/saas@origin/develop`:
//! `ModuleViewSet.get_queryset` filters `publication_status='listed'` **in the `list` action**, so
//! a retired module is simply not in `/api/v1/marketplace/modules/` — the screen cannot paint from
//! what it never receives. `retrieve` draws from the unfiltered base queryset
//! (`Module.objects.filter(is_published=True)`) and is in `MACHINE_OK_ACTIONS`, so it is the one
//! door that still answers for it, and it answers to the hub's own machine token.
//!
//! What is pinned here: the runtime asks the RIGHT Cloud path, hands the body over untouched
//! (`publication_status` included — the front reads it, the runtime does not interpret it), and
//! the machine credential never leaves the runtime.

use axum::body::Body;
use axum::extract::Path;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::json;
use std::sync::{Arc, Mutex};
use tower::ServiceExt; // oneshot

#[derive(Default)]
struct Seen {
    path: Option<String>,
    hub_token: Option<String>,
}

/// A mock SaaS serving the module DETAIL door, recording the path and credential it was called
/// with, and answering a record whose publication status is `retired`.
async fn mock_cloud() -> (String, Arc<Mutex<Seen>>, tokio::task::JoinHandle<()>) {
    let seen: Arc<Mutex<Seen>> = Arc::new(Mutex::new(Seen::default()));
    let recorder = seen.clone();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let router = Router::new().route(
        "/api/v1/marketplace/modules/:module_id/",
        get(move |Path(module_id): Path<String>, headers: HeaderMap| {
            let recorder = recorder.clone();
            async move {
                {
                    let mut seen = recorder.lock().unwrap();
                    seen.path = Some(module_id.clone());
                    seen.hub_token = headers
                        .get("x-hub-token")
                        .and_then(|v| v.to_str().ok())
                        .map(str::to_string);
                }
                (
                    StatusCode::OK,
                    Json(json!({
                        "module_id": module_id,
                        "name": "Online booking",
                        "publication_status": "retired",
                    })),
                )
            }
        }),
    );
    let task = tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    (format!("http://{address}"), seen, task)
}

fn config(cloud_base_url: String, token: Option<&str>, tag: &str) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: "real-hub".into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join(format!("erplora-publication-{tag}-cache")),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: token.map(str::to_string),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join(format!("erplora-publication-{tag}-media")),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn ask(cfg: HubConfig, module_id: &str) -> (StatusCode, String) {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "real-hub");
    rt.ensure_system_tables().await.unwrap();
    let response = app(AppState::with_config(rt, cfg))
        .oneshot(
            Request::builder()
                .uri(format!("/api/marketplace/modules/{module_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let body = axum::body::to_bytes(response.into_body(), 64 * 1024)
        .await
        .unwrap();
    (status, String::from_utf8(body.to_vec()).unwrap())
}

/// The whole point: `publication_status` reaches the front, so «My apps» can say it.
#[tokio::test]
async fn the_publication_status_of_an_installed_module_reaches_the_front_hub1134() {
    let (url, seen, task) = mock_cloud().await;

    let (status, body) = ask(
        config(url, Some("machine-secret"), "passthrough"),
        "online_booking",
    )
    .await;

    assert_eq!(status, StatusCode::OK);
    assert!(
        body.contains("\"publication_status\":\"retired\""),
        "the runtime must hand the Cloud's record over untouched, got: {body}"
    );
    assert_eq!(
        seen.lock().unwrap().path.clone().unwrap(),
        "online_booking",
        "it must ask the DETAIL door of the module the screen asked about"
    );
    task.abort();
}

/// **The machine secret stays in the runtime** (ADR-0003): the browser calls the runtime, the
/// runtime signs the call to the Cloud. This asserts the credential that reached the SaaS.
#[tokio::test]
async fn the_hub_signs_the_call_with_its_own_machine_token_hub1134() {
    let (url, seen, task) = mock_cloud().await;

    let (status, _) = ask(config(url, Some("machine-secret"), "token"), "payments").await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        seen.lock().unwrap().hub_token.clone().unwrap(),
        "machine-secret"
    );
    task.abort();
}

/// A hub with NO machine credential cannot ask, and it SAYS so — it does not invent a status.
///
/// The answer is the `428` the registration middleware already gives the whole business surface
/// (`machine_registration_required`), not a body: what matters here is that nothing that looks like
/// a publication status comes back, because the screen turns anything that is not a status into
/// silence, and silence is never painted as "retired".
#[tokio::test]
async fn without_a_credential_it_says_so_instead_of_inventing_a_status_hub1134() {
    let (url, _seen, task) = mock_cloud().await;

    let (status, body) = ask(config(url, None, "nocred"), "payments").await;

    assert!(status.is_client_error(), "got {status}");
    assert!(
        body.contains("machine_registration_required"),
        "the reason has to be visible, not a bare code: {body}"
    );
    assert!(
        !body.contains("publication_status"),
        "a hub that could not ask must not report a publication status: {body}"
    );
    task.abort();
}

/// **An id cannot walk the proxy out of the marketplace.** `:id` is percent-decoded by axum and
/// then pasted into a Cloud path that the runtime signs with the hub's own machine token, so a
/// `..` in it would aim that credential at any other Cloud endpoint. It is refused here, before
/// anything is signed — and the mock SaaS is never called at all.
#[tokio::test]
async fn an_id_that_walks_out_of_the_marketplace_is_refused_hub1134() {
    let (url, seen, task) = mock_cloud().await;
    let cfg = config(url, Some("machine-secret"), "traversal");

    // `400` and this code exactly, never "some client error": a `404` from the SaaS would also be
    // a client error, and it would mean the crafted path DID travel with the machine token.
    for id in [
        "..%2f..%2fauth%2fme",
        "payments%2f..%2f..",
        "online%20booking",
        "%2e%2e",
    ] {
        let (status, body) = ask(cfg.clone(), id).await;
        assert_eq!(status, StatusCode::BAD_REQUEST, "`{id}` → {body}");
        assert!(body.contains("module.invalid_id"), "`{id}` → {body}");
    }
    assert!(
        seen.lock().unwrap().path.is_none(),
        "no crafted id may reach the SaaS"
    );
    task.abort();
}

/// A Cloud that is not there is a `502`, never a body the screen could read as a verdict.
#[tokio::test]
async fn a_cloud_that_does_not_answer_is_a_failed_dependency_hub1134() {
    // Port 1 on loopback: nothing listens, so the request fails at connect.
    let (status, body) = ask(
        config("http://127.0.0.1:1".into(), Some("machine-secret"), "down"),
        "payments",
    )
    .await;

    // `424`, not the `502` this door was born with (hub#1763): the hub is the ORIGIN, and an edge
    // is free to replace the body of a `5xx` with its own page — the marketplace would then read
    // `error code: 502` instead of «erplora.com did not answer».
    assert_eq!(status, StatusCode::FAILED_DEPENDENCY);
    assert!(!body.contains("publication_status"), "{body}");
}
