//! **No answer of the hub ever names the address it calls the SaaS on** (hub#1689).
//!
//! When the SaaS does not answer — it is down, the datacentre network fails, a timeout — the
//! runtime's proxy helpers used to hand the caller the `Display` of the `reqwest` error, and that
//! text carries the URL it was dialling:
//!
//! ```text
//! {"ok":false,"error":"error sending request for url (http://127.0.0.1:1/api/v1/hub/device/entitlement/)"}
//! ```
//!
//! The person reading it is the owner or an admin of the business, on the marketplace, on «my
//! apps», on the subscription, on the WhatsApp connection. They have no use for the control
//! plane's host and port, and it is not ours to publish: it is the same class of leak that
//! hub#1074 closed for `/api/command` and `/api/query` (`error_redaction_door`) and that hub#1688
//! closed for the three WhatsApp template doors (`cloud_envelope_error_response`).
//!
//! 🔴 **This is a PATTERN, not a point.** `cloud_get_error_response` is shared by every proxy
//! route, so the fix cannot be «the routes we remembered»: the next proxy door added would leak
//! again. Like `module_doors_answer_in_one_shape`, this guard names no route — it walks **every**
//! route in `contracts/kernel/routes.snapshot`, drives it against a control plane that is not
//! listening, and refuses any answer that names it.
//!
//! What it asserts is the ADDRESS, not the prose (ADR-0055): the sentence may be reworded, the
//! host and port may never travel.
use std::collections::BTreeSet;
use std::time::Duration;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use tower::ServiceExt;

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;

/// The routes that publish `cloud_base_url` **on purpose**, and why. Anything else that starts
/// naming the control plane is a leak until somebody adds it here with its reason.
///
///  - `/api/hub/context` — the shell is handed the address it may log in against, and the CSP
///    `connect-src` is built from that very value (`hub_context_cloud_base_url`).
///  - `/api/system/declaration` — the «declaración responsable» link VeriFactu obliges the system
///    to show; it is a page of erplora.com meant to be opened by a human.
const PUBLISHES_THE_ADDRESS_ON_PURPOSE: [(&str, &str); 2] = [
    ("GET", "/api/hub/context"),
    ("GET", "/api/system/declaration"),
];

/// Every (method, path) the runtime serves, straight from the committed kernel contract.
fn every_route() -> Vec<(String, String)> {
    let snapshot = std::fs::read_to_string(kernel_snapshot::snapshot_path("routes.snapshot"))
        .expect("contracts/kernel/routes.snapshot is part of the kernel contract and is committed");
    let routes: Vec<(String, String)> = snapshot
        .lines()
        .filter(|line| !line.starts_with('#') && !line.trim().is_empty())
        .filter_map(|line| {
            let mut parts = line.split_whitespace();
            Some((parts.next()?.to_string(), parts.next()?.to_string()))
        })
        .collect();
    assert!(
        routes.len() >= 150,
        "the runtime's surface cannot have shrunk to {} routes — the snapshot is not being read",
        routes.len()
    );
    routes
}

/// A path with its `:params` filled in. Nothing must EXIST: a `404` is an answer like any other,
/// and this test is about what an answer may CONTAIN, not about finding a row.
fn concrete(path: &str) -> String {
    path.split('/')
        .map(|segment| match segment {
            ":name" | ":slug" | ":module" | ":family" => "not_here",
            s if s.starts_with(':') => "00000000-0000-0000-0000-000000000000",
            s => s,
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn config(cloud_base_url: String) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-no-leak-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-leak".into(),
        cloud_base_url,
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
    }
}

/// An address on the loopback with **nothing listening**: every call to it fails at connect, which
/// is the cheap, deterministic stand-in for «the SaaS did not answer». The port is bound only long
/// enough to be handed out and is closed again before the hub is built.
async fn a_control_plane_that_is_not_listening() -> (String, String) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    (format!("http://{address}"), address.to_string())
}

#[tokio::test]
async fn no_answer_of_the_hub_ever_names_the_address_of_the_control_plane() {
    let (cloud_base_url, address) = a_control_plane_that_is_not_listening().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-leak");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    // One session per door, minted BEFORE the runtime moves into the router. `POST /api/auth/logout`
    // is itself one of the doors, and with a single shared session every door alphabetically after
    // it answers 401 — the sweep would read green because it stopped signing in, which is the
    // quietest way to test nothing at all.
    let routes = every_route();
    let mut sessions = Vec::with_capacity(routes.len());
    for _ in &routes {
        sessions.push(rt.create_session(&admin, 3600, None).await.unwrap());
    }
    let router = app(AppState::with_config(rt, config(cloud_base_url.clone())));

    let allowed: BTreeSet<(&str, &str)> = PUBLISHES_THE_ADDRESS_ON_PURPOSE.into_iter().collect();
    let mut leaks: Vec<String> = Vec::new();
    let mut never_answered: Vec<String> = Vec::new();
    let mut checked = 0;

    for ((method, path), session) in routes.into_iter().zip(sessions) {
        let door = format!("{method} {path}");
        let carries_body = matches!(method.as_str(), "POST" | "PUT" | "PATCH");
        let mut request = Request::builder()
            .method(method.as_str())
            .uri(concrete(&path))
            .header("x-hub-session", &session);
        if carries_body {
            request = request.header("content-type", "application/json");
        }
        let request = request
            .body(if carries_body {
                Body::from("{}")
            } else {
                Body::empty()
            })
            .unwrap();

        // A door that streams (SSE, a websocket upgrade) never ends, and a body that never ends
        // cannot be read whole. It is recorded, not skipped in silence.
        let answered = tokio::time::timeout(Duration::from_secs(20), async {
            let response = router.clone().oneshot(request).await.unwrap();
            let status = response.status();
            let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
                .await
                .unwrap_or_default();
            (status, bytes)
        })
        .await;
        let Ok((status, bytes)) = answered else {
            never_answered.push(door);
            continue;
        };

        checked += 1;
        if allowed.contains(&(method.as_str(), path.as_str())) {
            continue;
        }
        let text = String::from_utf8_lossy(&bytes);
        // The ADDRESS, not the SaaS's path space: `/api/v1/hub/device/legal-documents/` is a
        // public, documented route of erplora.com and naming it SITUATES a failure, whereas the
        // host and port say where our control plane lives and help only somebody attacking it.
        for needle in [address.as_str(), cloud_base_url.as_str()] {
            if text.contains(needle) {
                leaks.push(format!(
                    "{door} answered {status} naming the control plane (`{needle}`): {text}"
                ));
                break;
            }
        }
    }

    assert!(
        leaks.is_empty(),
        "{} door(s) publish the address the hub calls erplora.com on. The business has nothing to \
         do with it and it is not ours to hand out: send the `reqwest` detail to the log and answer \
         a stable code, as `cloud_envelope_error_response` already does.\n  - {}",
        leaks.len(),
        leaks.join("\n  - ")
    );
    assert!(
        checked >= 140,
        "only {checked} doors were driven; the ones that never answered: {never_answered:?}"
    );
}

/// The control of the control: with the redaction removed, the guard above has to see the leak.
/// Driving one door by hand is not the guard — it is the proof that the guard is not green by
/// accident, which is what makes «no door leaks» worth reading.
#[tokio::test]
async fn the_guard_sees_a_door_that_hands_back_the_dialled_url() {
    let (cloud_base_url, address) = a_control_plane_that_is_not_listening().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-leak-positive");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = app(AppState::with_config(rt, config(cloud_base_url)));

    let response = router
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/marketplace/catalog")
                .header("x-hub-session", &session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let text = String::from_utf8_lossy(&bytes);

    assert_eq!(
        status,
        StatusCode::BAD_GATEWAY,
        "a control plane that does not answer is a 502, not a catalogue: {text}"
    );
    assert!(
        !text.contains(&address),
        "the marketplace catalogue hands the business the address of the control plane: {text}"
    );
}

/// The doors the sweep above cannot open with `{}`: each refuses the empty body BEFORE it dials
/// erplora.com, so a leak behind its validation is invisible to the sweep. They are driven by hand
/// with the smallest body that gets past the door, and held to the same rule (hub#1689, review).
///
///  - `POST /api/auth/courier` — the native shell's boot courier; needs a `code`.
///  - `POST /api/modules/request-install` — the marketplace's «Install»; needs a module and a
///    version. `/api/modules/:id/update` and «update all» share its pipeline and its error body.
///
/// The fourth column is **the answer that proves the door actually dialled erplora.com**, and it
/// is per door on purpose: it is what keeps this guard from going green on a door that refused the
/// body before ever calling out — a rule that is never reached is green for nothing. It is NOT the
/// same status everywhere: since hub#1720 the install pipeline reports a Cloud that did not answer
/// as `424 Failed Dependency`, precisely so the edge stops swallowing its body.
const DRIVEN_BY_HAND: [(&str, &str, &str, StatusCode); 2] = [
    (
        "POST",
        "/api/auth/courier",
        r#"{"code":"abc"}"#,
        StatusCode::BAD_GATEWAY,
    ),
    (
        "POST",
        "/api/modules/request-install",
        r#"{"module_id":"not_here","version":"1.0.0"}"#,
        StatusCode::FAILED_DEPENDENCY,
    ),
];

#[tokio::test]
async fn the_doors_the_sweep_cannot_open_with_an_empty_body_are_driven_by_hand() {
    let (cloud_base_url, address) = a_control_plane_that_is_not_listening().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-leak-by-hand");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = app(AppState::with_config(rt, config(cloud_base_url.clone())));

    let mut leaks: Vec<String> = Vec::new();
    for (method, path, body, dialled_and_failed) in DRIVEN_BY_HAND {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method(method)
                    .uri(path)
                    .header("x-hub-session", &session)
                    .header("content-type", "application/json")
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let text = String::from_utf8_lossy(&bytes);
        // The control of THIS control: each door has ONE answer that proves the body got past its
        // validation and the hub actually dialled erplora.com. Anything else is the door refusing
        // the body, and a rule that is never reached is green for nothing.
        assert_eq!(
            status, dialled_and_failed,
            "{method} {path} did not get as far as dialling erplora.com: {text}"
        );
        if [address.as_str(), cloud_base_url.as_str()]
            .iter()
            .any(|needle| text.contains(needle))
        {
            leaks.push(format!(
                "{method} {path} answered {status} naming the control plane: {text}"
            ));
        }
    }
    assert!(
        leaks.is_empty(),
        "{} hand-driven door(s) publish the address the hub calls erplora.com on:\n  - {}",
        leaks.len(),
        leaks.join("\n  - ")
    );
}

/// The same rule for the two sources that never answer over HTTP but whose `Display` reaches a
/// person all the same: the module storage — its error travels in the `/api/command` envelope to
/// the module's own screen — and the notify transport — its error is the reason on the dead-letter
/// row the owner reads. Neither is a route, so the sweep cannot see them (hub#1689, review).
#[tokio::test]
async fn the_sources_that_do_not_answer_over_http_keep_the_address_out_of_their_errors() {
    use erplora_runtime::host_notify::{Channel, NotifyIntent, NotifyTransport, Routing};
    use erplora_runtime::module_storage::ModuleStorage;
    use erplora_server::module_storage::ModuleMediaStorage;
    use erplora_server::notify_transport::CloudNotifyTransport;
    use std::sync::{Arc, RwLock};

    let (cloud_base_url, address) = a_control_plane_that_is_not_listening().await;
    let machine_token = Arc::new(RwLock::new(Some("machine-secret".to_string())));

    let storage =
        ModuleMediaStorage::cloud(cloud_base_url.clone(), "hub-leak", machine_token.clone());
    let error = storage
        .write_module_file("hub-leak", "products", "a.txt", b"x", "text/plain")
        .await
        .expect_err("nobody is listening on that address");
    let text = error.to_string();
    assert!(
        !text.contains(&address) && !text.contains(&cloud_base_url),
        "the module storage names the control plane: {text}"
    );

    let transport = CloudNotifyTransport::new(
        reqwest::Client::new(),
        &cloud_base_url,
        Arc::new(RwLock::new("hub-leak".to_string())),
        machine_token,
    );
    let intent = NotifyIntent {
        channel: Channel::Whatsapp,
        to: "+34600000000".into(),
        template: "reminder".into(),
        vars: serde_json::Value::Null,
        interactive: serde_json::Value::Null,
    };
    let error = transport
        .send(&intent, Routing::CloudProxy)
        .await
        .expect_err("nobody is listening on that address");
    let text = error.to_string();
    assert!(
        !text.contains(&address) && !text.contains(&cloud_base_url),
        "the notify transport names the control plane: {text}"
    );
}
