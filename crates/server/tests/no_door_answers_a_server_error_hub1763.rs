//! **No door of the hub answers a `5xx` because erplora.com failed** (ERPlora/hub#1763).
//!
//! The hub is the ORIGIN, not a gateway. A `5xx` minted here is indistinguishable from the `5xx`
//! the proxy in front of it mints on its own, so the edge answers with **its own page** and
//! REPLACES the body — taking with it the stable `code` of hub#139 that the shell translates. What
//! the owner of the business reads is `error code: 502 · Bad Gateway`, on the marketplace, on the
//! photos of the business, on the staff tab, on the plan usage, on a blueprint import, on the
//! assistant and on the account screen. Three very different facts — erplora.com is down (wait),
//! this hub's credential was refused (waiting fixes nothing), what you asked for does not exist —
//! all read the same, so the answer is to retry forever on a sentence that says nothing.
//!
//! hub#1720 closed this for the install pipeline and left the mold: `install_error_status` maps
//! every failure of the pipeline to a `4xx`, and `no_install_failure_is_reported_as_a_server_error`
//! walks every variant of the error enum so a new one cannot quietly map back to a `502`. That
//! guard is exhaustive over an ENUM; this issue is the same defect spread over DOORS, so the guard
//! has to be exhaustive over doors: it names no route and walks **every** route in
//! `contracts/kernel/routes.snapshot`, exactly as `cloud_errors_never_name_the_control_plane` does.
//!
//! Two outages, because they are different code paths and only one of them was ever measured:
//!
//!  1. **erplora.com does not answer** — the hub mints the status itself.
//!  2. **erplora.com answers a `5xx`** — the hub RELAYS a status it did not mint. A passthrough is
//!     just as invisible to the person: `cloud_json_passthrough` hands the Cloud's `500` straight
//!     out, and the edge replaces that body too.
//!
//! And a third outage that is the hub's OWN, not erplora.com's: **no machine credential**. Same
//! screen, same edge in front of it — and the doors that report it minted a `503` until hub#1763
//! while nothing drove them bare, because the two sweeps above run enrolled. It is only reachable
//! as the DEV hub: a production hub without a credential is stopped by
//! `require_machine_registration` (`428`) before any handler runs, so those branches only ever
//! answer on `pnpm dev`. The sweep runs as that hub to reach them.
//!
//! The rule is the whole `5xx` class and not the `502` that was counted: hub#1763's own inventory
//! missed `Outcome::Lost` on `POST /api/modules/:id/update` — an update that failed AND could not
//! roll back, the gravest answer the door has — because it answers `500` rather than `502`.
//!
//! What is asserted is the STATUS CLASS, never the prose (ADR-0055).

use std::collections::BTreeSet;
use std::time::Duration;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::routing::any;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig, DEV_HUB_ID};
use serde_json::json;
use tower::ServiceExt;

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;

/// The doors that answer a `5xx` **on purpose**, and why. Anything else that starts minting one is
/// the defect of hub#1763 until somebody adds it here with its reason.
///
///  - `GET /readyz` — the readiness probe. Its reader is the orchestrator, not a person, and
///    `503` is the whole point of the door: an edge replacing that body changes nothing, because
///    what is read is the status.
const ANSWERS_A_SERVER_ERROR_ON_PURPOSE: [(&str, &str); 1] = [("GET", "/readyz")];

/// Suelo de puertas que el barrido tiene que llegar a conducir.
///
/// No es un número redondo puesto a ojo: medido el 2026-09-10, `routes.snapshot` da **166** puertas
/// que contestan. El suelo deja ~26 de holgura para las rutas que entran y salen, y sigue cazando
/// lo que de verdad rompe este test sin ponerlo rojo — que deje de ENTRAR (una sesión que caduca
/// hunde el recuento a casi cero y todo lo demás saldría verde por `401`).
const DOORS_THE_SWEEP_MUST_DRIVE: usize = 140;

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
/// and this test is about the CLASS of the answer, not about finding a row.
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

/// The machine credential of an ENROLLED hub. `None` is the third outage: the hub's own.
const MACHINE_TOKEN: &str = "machine-secret";

/// Without a credential the sweep has to BE the dev hub (`AuthMode::Dev` + [`DEV_HUB_ID`]): it is
/// the only hub `require_machine_registration` lets through without one, and therefore the only
/// place the «not enrolled» branches of the doors ever run.
fn hub_id(machine_token: Option<&str>) -> &'static str {
    if machine_token.is_some() {
        "hub-1763"
    } else {
        DEV_HUB_ID
    }
}

fn config(cloud_base_url: String, tag: &str, machine_token: Option<&str>) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-1763-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: hub_id(machine_token).into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: if machine_token.is_some() {
            AuthMode::Session
        } else {
            AuthMode::Dev
        },
        jwt_public_key: None,
        cloud_api_token: machine_token.map(str::to_string),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// An address on the loopback with **nothing listening**: every call to it fails at connect, which
/// is the cheap, deterministic stand-in for «erplora.com did not answer».
async fn a_control_plane_that_is_not_listening() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{address}")
}

/// An erplora.com that answers `500` to every path, with the shape DRF gives a crash. This is the
/// outage the hub RELAYS instead of minting, and it is the half that was never measured.
async fn a_control_plane_that_answers_a_server_error() -> String {
    let cloud: Router = Router::new().fallback(any(|| async {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "detail": "Server Error (500)" })),
        )
    }));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });
    format!("http://{address}")
}

/// Drives every door of the kernel contract against `cloud_base_url` and returns the ones that
/// answered a `5xx`, formatted for the failure message.
async fn doors_that_answer_a_server_error(
    cloud_base_url: String,
    tag: &str,
    machine_token: Option<&str>,
) -> (Vec<String>, usize) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id(machine_token));
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    // One session per door, minted BEFORE the runtime moves into the router: `POST /api/auth/logout`
    // is itself a door, and with a single shared session every door after it answers 401 — the
    // sweep would read green because it stopped signing in, which tests nothing at all.
    let routes = every_route();
    let mut sessions = Vec::with_capacity(routes.len());
    for _ in &routes {
        sessions.push(rt.create_session(&admin, 3600, None).await.unwrap());
    }
    let router = app(AppState::with_config(
        rt,
        config(cloud_base_url, tag, machine_token),
    ));

    let allowed: BTreeSet<(&str, &str)> = ANSWERS_A_SERVER_ERROR_ON_PURPOSE.into_iter().collect();
    let mut offenders: Vec<String> = Vec::new();
    let mut checked = 0usize;

    for ((method, path), session) in routes.into_iter().zip(sessions) {
        if allowed.contains(&(method.as_str(), path.as_str())) {
            continue;
        }
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

        // A door that streams (SSE, a websocket upgrade) never ends: it is timed out, not skipped
        // in silence — the count below is what says how many really answered.
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
            continue;
        };

        checked += 1;
        if status.is_server_error() {
            offenders.push(format!(
                "{door} answered {status}: {}",
                String::from_utf8_lossy(&bytes)
            ));
        }
    }
    (offenders, checked)
}

/// A `multipart/form-data` with one file, hand-written so `POST /api/media/upload` gets past its
/// extractor: the sweep sends `{}` as JSON, which the multipart extractor refuses long before the
/// hub dials erplora.com.
const MULTIPART: &str = "multipart/form-data; boundary=X1763";
const ONE_FILE: &str = "--X1763\r\nContent-Disposition: form-data; name=\"folder\"\r\n\r\n\r\n\
                        --X1763\r\nContent-Disposition: form-data; name=\"files\"; \
                        filename=\"logo.png\"\r\nContent-Type: image/png\r\n\r\nPNG\r\n\
                        --X1763--\r\n";

/// The doors the sweep cannot open with `{}`: each refuses that body BEFORE it dials erplora.com —
/// a missing query parameter, a required field, a multipart extractor — so whatever they answer
/// when the control plane is down is invisible to the sweep above. They are driven by hand with the
/// smallest body that gets past the door, and held to the same rule.
///
/// Every one of them is expected to answer **[`FAILED_DEPENDENCY`]**, and that is the control of
/// this control: it is the answer that proves the door got as far as calling erplora.com. A door
/// that refused the body first answers `400`/`403`/`404` and fails this table instead of going
/// green for nothing — which is exactly how a guard ends up covering a rule it never reaches.
const DRIVEN_BY_HAND: [(&str, &str, &str, &str); 5] = [
    // `Query<PathQuery>`: without `path` the extractor answers `400` and nothing is dialled.
    ("DELETE", "/api/media?path=logo.png", "application/json", ""),
    (
        "GET",
        "/api/media/raw?path=logo.png",
        "application/json",
        "",
    ),
    // `name` has no `#[serde(default)]`: `{}` never deserialises.
    (
        "POST",
        "/api/media/folder",
        "application/json",
        r#"{"name":"nueva"}"#,
    ),
    (
        "POST",
        "/api/media/rename",
        "application/json",
        r#"{"path":"logo.png","name":"otro.png"}"#,
    ),
    ("POST", "/api/media/upload", MULTIPART, ONE_FILE),
];

/// Drives [`DRIVEN_BY_HAND`] against `cloud_base_url` and returns the doors that did NOT answer
/// [`StatusCode::FAILED_DEPENDENCY`], with what they answered instead.
async fn hand_driven_doors_that_do_not_report_the_outage(
    cloud_base_url: String,
    tag: &str,
) -> Vec<String> {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-1763");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = app(AppState::with_config(
        rt,
        config(cloud_base_url, tag, Some(MACHINE_TOKEN)),
    ));

    let mut wrong: Vec<String> = Vec::new();
    for (method, uri, content_type, body) in DRIVEN_BY_HAND {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method(method)
                    .uri(uri)
                    .header("x-hub-session", &session)
                    .header("content-type", content_type)
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        if status == StatusCode::FAILED_DEPENDENCY {
            continue;
        }
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap_or_default();
        wrong.push(format!(
            "{method} {uri} answered {status}: {}",
            String::from_utf8_lossy(&bytes)
        ));
    }
    wrong
}

#[tokio::test]
async fn the_doors_the_sweep_cannot_open_with_an_empty_body_are_driven_by_hand() {
    for (outage, cloud) in [
        ("silent", a_control_plane_that_is_not_listening().await),
        (
            "crashing",
            a_control_plane_that_answers_a_server_error().await,
        ),
    ] {
        let wrong = hand_driven_doors_that_do_not_report_the_outage(cloud, outage).await;
        assert!(
            wrong.is_empty(),
            "with erplora.com {outage}, {} hand-driven door(s) did not report the outage as a \
             `424 Failed Dependency`. Either the door mints a 5xx the edge will swallow, or it \
             never got as far as dialling erplora.com — and a rule that is never reached is green \
             for nothing.\n  - {}",
            wrong.len(),
            wrong.join("\n  - ")
        );
    }
}

#[tokio::test]
async fn no_door_answers_a_server_error_when_erplora_com_does_not_answer() {
    let cloud = a_control_plane_that_is_not_listening().await;
    let (offenders, checked) =
        doors_that_answer_a_server_error(cloud, "silent", Some(MACHINE_TOKEN)).await;
    assert!(
        offenders.is_empty(),
        "{} door(s) answer a server error because erplora.com did not answer. The hub is the \
         ORIGIN: an edge is free to replace the body of a 5xx with its own page, so the `code` \
         never reaches the browser and «it is down», «your credential was refused» and «that does \
         not exist» all read as `error code: 502`. Answer a 4xx with its code, as \
         `install_error_status` does since hub#1720.\n  - {}",
        offenders.len(),
        offenders.join("\n  - ")
    );
    assert!(
        checked >= DOORS_THE_SWEEP_MUST_DRIVE,
        "only {checked} doors answered (floor {DOORS_THE_SWEEP_MUST_DRIVE}); the sweep is \
         not driving the surface"
    );
}

#[tokio::test]
async fn no_door_answers_a_server_error_when_erplora_com_answers_one() {
    let cloud = a_control_plane_that_answers_a_server_error().await;
    let (offenders, checked) =
        doors_that_answer_a_server_error(cloud, "crashing", Some(MACHINE_TOKEN)).await;
    assert!(
        offenders.is_empty(),
        "{} door(s) RELAY the server error of erplora.com. A passthrough is as invisible as a \
         minted 5xx: the edge replaces that body too, so what the business reads is the proxy's \
         page and not «erplora.com refused». Downgrade the relayed status and keep the code.\n  - {}",
        offenders.len(),
        offenders.join("\n  - ")
    );
    assert!(
        checked >= DOORS_THE_SWEEP_MUST_DRIVE,
        "only {checked} doors answered (floor {DOORS_THE_SWEEP_MUST_DRIVE}); the sweep is \
         not driving the surface"
    );
}

/// The third outage is the hub's OWN: it has no machine credential. Not erplora.com failing, but
/// the same screen and the same edge in front of it: the doors that report it minted a `503` until
/// hub#1763 (`GET /api/fiscal/representation-grant`, `POST /api/business/fiscal-identity`,
/// `POST /api/auth/courier`, `GET /api/system/usage-series`) and NOTHING drove them bare — the two
/// sweeps above run enrolled, so a `503` on that branch stayed green. Driven as the dev hub, the
/// only one that reaches those branches (see [`hub_id`]); reverting any of them to a `5xx` is red
/// here (checked against `GET /api/fiscal/representation-grant` on 2026-09-10).
#[tokio::test]
async fn no_door_answers_a_server_error_when_the_hub_has_no_machine_credential() {
    let cloud = a_control_plane_that_is_not_listening().await;
    let (offenders, checked) = doors_that_answer_a_server_error(cloud, "bare", None).await;
    assert!(
        offenders.is_empty(),
        "{} door(s) answer a server error because this hub has no machine credential. That is a \
         fact about the hub, not an outage of the server: answer a 4xx with `hub_not_enrolled` so \
         the edge leaves the body alone and the screen can say «this hub is not connected \
         yet».\n  - {}",
        offenders.len(),
        offenders.join("\n  - ")
    );
    assert!(
        checked >= DOORS_THE_SWEEP_MUST_DRIVE,
        "only {checked} doors answered (floor {DOORS_THE_SWEEP_MUST_DRIVE}); the sweep is \
         not driving the surface"
    );
}
