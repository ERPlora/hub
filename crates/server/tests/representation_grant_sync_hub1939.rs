//! **hub#1939 — a grant revoked at ERPlora closes the till without anybody opening a screen.**
//!
//! The hub's copy of the representation grant (`_hub_fiscal_profile.representation_status`) decides
//! whether a live hub on ERPlora's road may charge (hub#1935, `fiscal_profile::filing_gap`). Before
//! this, the only writer of that copy was the grant SCREEN (`GET`/`POST
//! /api/fiscal/representation-grant`): a grant revoked or rejected at ERPlora stayed `vigente` in
//! the hub until somebody happened to open it, and the till kept charging tickets the fiscal cell
//! refuses (`hub_not_authorized`) — tickets that never reach the AEAT.
//!
//! `representation_grant::sync_once` is the background door: it asks the control plane with the
//! machine credential and mirrors the answer, the same way the screen does. These tests drive it
//! against a fake control plane and read the result where the TPV reads it —
//! `hub.fiscal.transmission`, the core query it asks before charging.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use axum::extract::State;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::certificate::CertificateKind;
use erplora_runtime::fiscal_profile::{self, NO_REPRESENTATION};
use erplora_runtime::{RequestContext, Runtime};
use erplora_server::representation_grant::{self, SyncOutcome};
use erplora_server::{AppState, AuthMode, HubConfig};
use serde_json::{json, Value};

const HUB: &str = "hub-es-1939";

/// A fake control plane answering the grant's `GET` with a fixed status and body, counting calls.
/// The path is the one `cloud_client::representation_grant` builds, so a rename there fails here.
async fn fake_cloud(status: StatusCode, answer: Value) -> (String, Arc<AtomicUsize>) {
    #[derive(Clone)]
    struct Fake {
        status: StatusCode,
        answer: Value,
        calls: Arc<AtomicUsize>,
    }
    async fn grant(State(fake): State<Fake>) -> axum::response::Response {
        fake.calls.fetch_add(1, Ordering::SeqCst);
        (fake.status, Json(fake.answer)).into_response()
    }
    let calls = Arc::new(AtomicUsize::new(0));
    let router = Router::new()
        .route(
            "/api/v1/hub/device/fiscal/representation-grant/",
            get(grant),
        )
        .with_state(Fake {
            status,
            answer,
            calls: calls.clone(),
        });
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{addr}"), calls)
}

/// A control plane nobody answers at: a port that was bound and released.
async fn dead_cloud() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{addr}")
}

#[derive(Clone, Copy)]
struct Hub {
    environment: &'static str,
    own_certificate: bool,
    grant: &'static str,
    enrolled_with_cloud: bool,
}

/// A hub filing for real through ERPlora's road with an approved grant — the one that must learn.
const LIVE_ON_ERPLORA: Hub = Hub {
    environment: fiscal_profile::ENV_PRODUCTION,
    own_certificate: false,
    grant: fiscal_profile::REPRESENTATION_VIGENTE,
    enrolled_with_cloud: true,
};

async fn state(hub: Hub, cloud_base_url: String) -> AppState {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    let db = rt.db();
    fiscal_profile::ensure(db, HUB).await.unwrap();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("environment".into(), json!(hub.environment));
    db.execute(
        "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = :environment \
         WHERE hub_id = :hub_id",
        &p,
    )
    .await
    .unwrap();
    fiscal_profile::record_representation(db, HUB, hub.grant, "2026-09-19T09:00:00Z")
        .await
        .unwrap();
    enrol_machine_identity(db).await;
    if hub.own_certificate {
        store_own_certificate(db).await;
    }
    let temp = std::env::temp_dir().join(format!(
        "erplora-hub1939-{}-{:?}",
        std::process::id(),
        std::thread::current().id()
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB.into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: hub.enrolled_with_cloud.then(|| "machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    AppState::with_config(rt, cfg)
}

async fn enrol_machine_identity(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    db.execute(
        "INSERT INTO _hub_gateway_identity \
         (hub_id, private_key_pem, certificate_pem, ca_pem, common_name, created_at, updated_at) \
         VALUES (:hub_id, 'v1:ciphertext', '-----BEGIN CERTIFICATE-----\nhub\n-----END CERTIFICATE-----', \
                 '-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----', 'hub.fiscal.erplora.internal', \
                 '2026-09-19T09:00:00Z', '2026-09-19T09:00:00Z')",
        &p,
    )
    .await
    .unwrap();
}

async fn store_own_certificate(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("kind".into(), json!(CertificateKind::Own.as_str()));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :kind, 'v1:ciphertext', 'v1:ciphertext', '2026-09-19T09:00:00Z', 'x')",
        &p,
    )
    .await
    .unwrap();
}

/// What the TPV reads before charging.
async fn transmission(st: &AppState) -> Value {
    let runtime = st.runtime.read().await;
    let rows = runtime
        .execute_query(
            "hub.fiscal.transmission",
            &Params::new(),
            &RequestContext::new(HUB, "u1", ["*".to_string()]),
        )
        .await
        .expect("the core answers hub.fiscal.transmission");
    rows[0].clone()
}

// ── The case the issue names ──────────────────────────────────────────────────────────────────

/// 🔴 A grant revoked at ERPlora reaches the hub with no screen open, and the till stops charging
/// with the code it already translates.
#[tokio::test]
async fn a_grant_revoked_at_erplora_closes_the_till_without_opening_the_screen() {
    let (cloud, calls) = fake_cloud(
        StatusCode::OK,
        json!({ "status": "revocado", "at": "2026-09-22T10:00:00Z" }),
    )
    .await;
    let st = state(LIVE_ON_ERPLORA, cloud).await;
    assert_eq!(transmission(&st).await["filing_blocked"], "");

    let outcome = representation_grant::sync_once(&st).await;

    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_eq!(
        outcome,
        SyncOutcome::Mirrored {
            previous: "vigente".into(),
            current: "revocado".into(),
        }
    );
    let after = transmission(&st).await;
    assert_eq!(after["representation_status"], "revocado");
    assert_eq!(after["representation_at"], "2026-09-22T10:00:00Z");
    assert_eq!(after["filing_blocked"], NO_REPRESENTATION);
}

/// A reviewer's refusal counts the same: only `vigente` opens the road.
#[tokio::test]
async fn a_grant_rejected_at_erplora_closes_the_till_too() {
    let (cloud, _) = fake_cloud(StatusCode::OK, json!({ "status": "rechazado" })).await;
    let st = state(LIVE_ON_ERPLORA, cloud).await;

    representation_grant::sync_once(&st).await;

    assert_eq!(transmission(&st).await["filing_blocked"], NO_REPRESENTATION);
}

/// The other direction, by the same door: a grant approved again reopens the till on its own.
#[tokio::test]
async fn a_grant_approved_again_reopens_the_till() {
    let (cloud, _) = fake_cloud(
        StatusCode::OK,
        json!({ "status": "vigente", "at": "2026-09-23T08:00:00Z" }),
    )
    .await;
    let st = state(
        Hub {
            grant: fiscal_profile::REPRESENTATION_REVOKED,
            ..LIVE_ON_ERPLORA
        },
        cloud,
    )
    .await;
    assert_eq!(transmission(&st).await["filing_blocked"], NO_REPRESENTATION);

    representation_grant::sync_once(&st).await;

    assert_eq!(transmission(&st).await["filing_blocked"], "");
}

// ── "I could not ask" is not "you have not signed" ───────────────────────────────────────────

/// A control plane that is down leaves the copy as it was: a network blip must not close a till.
#[tokio::test]
async fn an_unreachable_control_plane_leaves_the_copy_untouched() {
    let st = state(LIVE_ON_ERPLORA, dead_cloud().await).await;

    let outcome = representation_grant::sync_once(&st).await;

    assert_eq!(outcome, SyncOutcome::Failed);
    let after = transmission(&st).await;
    assert_eq!(after["representation_status"], "vigente");
    assert_eq!(after["filing_blocked"], "");
}

/// A refusal (the hub's credential rejected, a 5xx) is not an answer about the grant either.
#[tokio::test]
async fn a_control_plane_that_refuses_the_question_leaves_the_copy_untouched() {
    let (cloud, calls) = fake_cloud(
        StatusCode::UNAUTHORIZED,
        json!({ "detail": "hub_not_found" }),
    )
    .await;
    let st = state(LIVE_ON_ERPLORA, cloud).await;

    let outcome = representation_grant::sync_once(&st).await;

    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_eq!(outcome, SyncOutcome::Failed);
    assert_eq!(transmission(&st).await["representation_status"], "vigente");
}

// ── Only the hubs the copy decides for ask ───────────────────────────────────────────────────

/// In pruebas nothing is authorised (ADR-0360): the copy decides nothing, so nobody is asked.
#[tokio::test]
async fn a_hub_in_testing_does_not_ask() {
    let (cloud, calls) = fake_cloud(StatusCode::OK, json!({ "status": "revocado" })).await;
    let st = state(
        Hub {
            environment: fiscal_profile::ENV_TESTING,
            ..LIVE_ON_ERPLORA
        },
        cloud,
    )
    .await;

    let outcome = representation_grant::sync_once(&st).await;

    assert_eq!(outcome, SyncOutcome::NotNeeded);
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert_eq!(transmission(&st).await["representation_status"], "vigente");
}

/// A business filing with its own certificate delegates nothing (ADR-0320 §1): no grant to watch.
#[tokio::test]
async fn a_hub_filing_with_its_own_certificate_does_not_ask() {
    let (cloud, calls) = fake_cloud(StatusCode::OK, json!({ "status": "revocado" })).await;
    let st = state(
        Hub {
            own_certificate: true,
            ..LIVE_ON_ERPLORA
        },
        cloud,
    )
    .await;

    let outcome = representation_grant::sync_once(&st).await;

    assert_eq!(outcome, SyncOutcome::NotNeeded);
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

/// Without the machine credential there is nobody to ask as; the copy stays and nothing is sent.
#[tokio::test]
async fn a_hub_without_its_machine_credential_does_not_ask() {
    let (cloud, calls) = fake_cloud(StatusCode::OK, json!({ "status": "revocado" })).await;
    let st = state(
        Hub {
            enrolled_with_cloud: false,
            ..LIVE_ON_ERPLORA
        },
        cloud,
    )
    .await;

    let outcome = representation_grant::sync_once(&st).await;

    assert_eq!(outcome, SyncOutcome::NotEnrolled);
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

// ── The cadence ──────────────────────────────────────────────────────────────────────────────

/// Hourly by default: a revocation closes the till within the hour, not the next day.
#[test]
fn the_sync_runs_hourly_unless_configured() {
    assert_eq!(representation_grant::sync_interval_secs(None), 3600);
    assert_eq!(representation_grant::sync_interval_secs(Some("600")), 600);
    assert_eq!(representation_grant::sync_interval_secs(Some("0")), 3600);
    assert_eq!(representation_grant::sync_interval_secs(Some("nope")), 3600);
}

// ── Wired into the real boot ─────────────────────────────────────────────────────────────────

/// `serve` starts the sync on its own: a hub booted live on ERPlora's road learns of the
/// revocation with nobody touching it. Without this, `sync_once` could be correct and never run.
#[tokio::test(flavor = "multi_thread")]
async fn a_booted_hub_learns_of_the_revocation_on_its_own() {
    let db = erplora_db::testutil::TestDb::new().await;
    let base = erplora_db::testutil::test_database_url();
    let sep = if base.contains('?') { '&' } else { '?' };
    let dsn = format!("{base}{sep}options=-c%20search_path%3D{}", db.schema());
    {
        let rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
        rt.ensure_system_tables().await.unwrap();
        fiscal_profile::ensure(rt.db(), HUB).await.unwrap();
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB));
        rt.db()
            .execute(
                "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production' \
                 WHERE hub_id = :hub_id",
                &p,
            )
            .await
            .unwrap();
        fiscal_profile::record_representation(
            rt.db(),
            HUB,
            fiscal_profile::REPRESENTATION_VIGENTE,
            "2026-09-19T09:00:00Z",
        )
        .await
        .unwrap();
        enrol_machine_identity(rt.db()).await;
    }
    let (cloud, calls) = fake_cloud(
        StatusCode::OK,
        json!({ "status": "revocado", "at": "2026-09-22T10:00:00Z" }),
    )
    .await;

    let port = {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.local_addr().unwrap().port()
    };
    let temp = std::env::temp_dir().join(format!("erplora-hub1939-boot-{}", std::process::id()));
    let cfg = erplora_server::ServeConfig {
        database_url: dsn.clone(),
        bind: format!("127.0.0.1:{port}"),
        modules_dir: None,
        hub: HubConfig {
            hub_id: HUB.into(),
            cloud_base_url: cloud.clone(),
            cloud_api_token: Some("machine-secret".into()),
            module_cache: temp.join("module_cache"),
            media_dir: temp.join("media"),
            dev_mode: false,
            dev_modules_dir: None,
            ..HubConfig::from_env_with_auth(AuthMode::Dev)
        },
        machine_token_cell: None,
        hub_id_cell: None,
        web_dir: None,
        csp: erplora_server::default_csp(&cloud),
    };
    // hub#2036: `serve()` reports on this channel if it ever returns, so a boot that fails is a
    // red with its reason instead of a silent wait.
    let (ended_tx, ended_rx) = std::sync::mpsc::channel::<String>();
    std::thread::spawn(move || {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .unwrap();
        let outcome = match rt.block_on(erplora_server::serve(cfg)) {
            Ok(()) => "serve() returned".to_string(),
            Err(error) => format!("serve() ended: {error}"),
        };
        ended_tx.send(outcome).ok();
    });

    // hub#2036: the clock for the sync starts when the hub is READY, not when the thread starts.
    // A loaded CI runner can take longer than any fixed budget to migrate and boot; the signal is
    // the listener accepting connections, and `serve` binds it only after `spawn_sync` ran. The
    // boot ceiling only exists so a hung boot cannot hang the suite.
    let boot_deadline = std::time::Instant::now() + std::time::Duration::from_secs(300);
    loop {
        if let Ok(outcome) = ended_rx.try_recv() {
            panic!("the hub never became ready: {outcome}");
        }
        if tokio::net::TcpStream::connect(("127.0.0.1", port))
            .await
            .is_ok()
        {
            break;
        }
        assert!(
            std::time::Instant::now() < boot_deadline,
            "the hub did not start listening within the boot ceiling"
        );
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }

    // Ready: the first sync tick fires at boot, so the revocation lands within seconds or never.
    let reader = erplora_db::PgAdapter::connect(&dsn).await.unwrap();
    let sync_deadline = std::time::Instant::now() + std::time::Duration::from_secs(15);
    let mut status;
    loop {
        status = fiscal_profile::load(&reader, HUB)
            .await
            .unwrap()
            .map(|p| p.representation_status)
            .unwrap_or_default();
        if status == fiscal_profile::REPRESENTATION_REVOKED
            || std::time::Instant::now() >= sync_deadline
        {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }
    assert_eq!(status, fiscal_profile::REPRESENTATION_REVOKED);
    assert!(calls.load(Ordering::SeqCst) >= 1);
    std::fs::remove_dir_all(temp).ok();
}
