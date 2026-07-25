//! Tests del cliente de pairing device-code (ADR-0154). Cuerpo del módulo `tests` de `pairing.rs`
//! (incluido con `#[path]`). Se escriben ANTES que la implementación (TDD, rojo primero) y
//! describen el contrato de los endpoints `api/v1/bridge/` del SaaS (saas#811).
//!
//! Se guarda en un fichero aparte (no inline) porque el guardarraíl de TDD reconoce este nombre
//! como el test del módulo `pairing` — así el test va, literal y verificablemente, primero.

use super::*;

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::post;
use axum::{Json, Router};

fn tmp_pairing_path() -> PathBuf {
    std::env::temp_dir().join(format!("bridge-pairing-test-{}.json", uuid::Uuid::new_v4()))
}

fn sample_pairing() -> Pairing {
    Pairing {
        hub_id: "hub-42".into(),
        hub_name: "Sur Restaurante".into(),
        hub_url: "https://hub-42.erplora.com".into(),
        bridge_device_token: "dev-token-xyz".into(),
        saas_public_key_url: Some("https://erplora.com/api/v1/auth/public-key/".into()),
    }
}

/// Guion de respuestas para un endpoint mock: una `(status, body)` por llamada; tras agotarse,
/// repite la última (para poll loops que siguen tras aprobar/denegar).
#[derive(Clone)]
struct Script {
    steps: Arc<Vec<(u16, serde_json::Value)>>,
    idx: Arc<AtomicUsize>,
}

impl Script {
    fn new(steps: Vec<(u16, serde_json::Value)>) -> Self {
        Script { steps: Arc::new(steps), idx: Arc::new(AtomicUsize::new(0)) }
    }
}

async fn scripted(State(s): State<Script>) -> Response {
    let i = s.idx.fetch_add(1, Ordering::SeqCst).min(s.steps.len().saturating_sub(1));
    let (code, body) = &s.steps[i];
    (StatusCode::from_u16(*code).unwrap(), Json(body.clone())).into_response()
}

/// Arranca un SaaS mock en un puerto efímero con `router` y devuelve su base URL.
async fn spawn_saas(router: Router) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    tokio::time::sleep(Duration::from_millis(20)).await;
    format!("http://127.0.0.1:{port}")
}

fn approved_body() -> serde_json::Value {
    serde_json::json!({
        "status": "approved",
        "hub_id": "hub-42",
        "hub_name": "Sur Restaurante",
        "hub_url": "https://hub-42.erplora.com",
        "bridge_jwt": "jwt.short.token",
        "bridge_jwt_expires_in": 900,
        "bridge_device_token": "dev-token-xyz",
        "saas_public_key_url": "https://erplora.com/api/v1/auth/public-key/"
    })
}

// ── Persistencia 0600 ────────────────────────────────────────────────────────

#[test]
fn save_then_load_round_trips() {
    let p = tmp_pairing_path();
    assert!(!is_paired(&p));
    let pairing = sample_pairing();
    save_pairing(&p, &pairing).unwrap();
    assert!(is_paired(&p));
    assert_eq!(load_pairing(&p).unwrap(), pairing);
    let _ = std::fs::remove_file(&p);
}

#[cfg(unix)]
#[test]
fn saved_file_is_0600() {
    use std::os::unix::fs::PermissionsExt;
    let p = tmp_pairing_path();
    save_pairing(&p, &sample_pairing()).unwrap();
    let mode = std::fs::metadata(&p).unwrap().permissions().mode() & 0o777;
    assert_eq!(mode, 0o600, "el fichero de emparejamiento debe ser 0600, fue {mode:o}");
    let _ = std::fs::remove_file(&p);
}

#[test]
fn load_missing_file_is_none() {
    assert!(load_pairing(&tmp_pairing_path()).is_none());
}

#[test]
fn load_corrupt_file_is_none() {
    let p = tmp_pairing_path();
    std::fs::write(&p, "not json {{{").unwrap();
    assert!(load_pairing(&p).is_none());
    let _ = std::fs::remove_file(&p);
}

// ── pair_start ───────────────────────────────────────────────────────────────

#[tokio::test]
async fn pair_start_parses_device_code() {
    let router = Router::new().route(
        "/api/v1/bridge/pair/start/",
        post(|| async {
            Json(serde_json::json!({
                "device_code": "dc-1",
                "user_code": "WXYZ-1234",
                "verification_uri": "https://erplora.com/bridge/pair",
                "verification_uri_complete": "https://erplora.com/bridge/pair?code=WXYZ-1234",
                "expires_in": 900,
                "interval": 5
            }))
        }),
    );
    let base = spawn_saas(router).await;
    let start = pair_start(&http_client(), &base, "macos", "0.0.0", "iMac").await.unwrap();
    assert_eq!(start.device_code, "dc-1");
    assert_eq!(start.user_code, "WXYZ-1234");
    assert_eq!(start.interval, 5);
    assert_eq!(start.expires_in, 900);
    assert!(start.verification_uri_complete.contains("code=WXYZ-1234"));
}

// ── pair_poll: cada forma del contrato ───────────────────────────────────────

async fn poll_once(steps: Vec<(u16, serde_json::Value)>) -> PollOutcome {
    let script = Script::new(steps);
    let router = Router::new()
        .route("/api/v1/bridge/pair/poll/", post(scripted))
        .with_state(script);
    let base = spawn_saas(router).await;
    pair_poll(&http_client(), &base, "dc-1").await.unwrap()
}

#[tokio::test]
async fn poll_pending() {
    assert!(matches!(
        poll_once(vec![(200, serde_json::json!({"status": "pending"}))]).await,
        PollOutcome::Pending
    ));
}

#[tokio::test]
async fn poll_slow_down() {
    // El device-code suele devolver 400 con `error` para slow_down; se acepta igual.
    assert!(matches!(
        poll_once(vec![(400, serde_json::json!({"error": "slow_down"}))]).await,
        PollOutcome::SlowDown
    ));
}

#[tokio::test]
async fn poll_expired() {
    assert!(matches!(
        poll_once(vec![(400, serde_json::json!({"error": "expired"}))]).await,
        PollOutcome::Expired
    ));
}

#[tokio::test]
async fn poll_denied() {
    assert!(matches!(
        poll_once(vec![(200, serde_json::json!({"status": "denied"}))]).await,
        PollOutcome::Denied
    ));
}

#[tokio::test]
async fn poll_approved_carries_credentials() {
    match poll_once(vec![(200, approved_body())]).await {
        PollOutcome::Approved(a) => {
            assert_eq!(a.hub_id, "hub-42");
            assert_eq!(a.hub_name, "Sur Restaurante");
            assert_eq!(a.bridge_device_token, "dev-token-xyz");
            assert_eq!(a.bridge_jwt, "jwt.short.token");
        }
        other => panic!("esperaba Approved, fue {other:?}"),
    }
}

// ── poll_until_resolved: pending → slow_down → approved ──────────────────────

#[tokio::test]
async fn poll_loop_pending_then_approved() {
    let script = Script::new(vec![
        (200, serde_json::json!({"status": "pending"})),
        (400, serde_json::json!({"error": "slow_down"})),
        (200, approved_body()),
    ]);
    let router = Router::new()
        .route("/api/v1/bridge/pair/poll/", post(scripted))
        .with_state(script);
    let base = spawn_saas(router).await;
    let a = poll_until_resolved(
        &http_client(),
        &base,
        "dc-1",
        Duration::from_millis(5),
        Duration::from_millis(1), // slow_down_bump pequeño: ejerce la rama sin esperar 5s reales
        Duration::from_secs(5),
    )
    .await
    .unwrap();
    assert_eq!(a.hub_id, "hub-42");
}

#[tokio::test]
async fn poll_loop_times_out_when_always_pending() {
    let script = Script::new(vec![(200, serde_json::json!({"status": "pending"}))]);
    let router = Router::new()
        .route("/api/v1/bridge/pair/poll/", post(scripted))
        .with_state(script);
    let base = spawn_saas(router).await;
    let err = poll_until_resolved(
        &http_client(),
        &base,
        "dc-1",
        Duration::from_millis(2),
        Duration::from_millis(1),
        Duration::from_millis(30),
    )
    .await
    .unwrap_err();
    assert!(matches!(err, PairingError::Timeout(_)), "esperaba Timeout, fue {err:?}");
}

#[tokio::test]
async fn poll_loop_denied_errors() {
    let script = Script::new(vec![(200, serde_json::json!({"status": "denied"}))]);
    let router = Router::new()
        .route("/api/v1/bridge/pair/poll/", post(scripted))
        .with_state(script);
    let base = spawn_saas(router).await;
    let err = poll_until_resolved(
        &http_client(),
        &base,
        "dc-1",
        Duration::from_millis(2),
        Duration::from_millis(1),
        Duration::from_secs(5),
    )
    .await
    .unwrap_err();
    assert!(matches!(err, PairingError::Denied), "esperaba Denied, fue {err:?}");
}

// ── pair_redeem (flujo inverso) ──────────────────────────────────────────────

#[tokio::test]
async fn redeem_approved() {
    let script = Script::new(vec![(200, approved_body())]);
    let router = Router::new()
        .route("/api/v1/bridge/pair/redeem/", post(scripted))
        .with_state(script);
    let base = spawn_saas(router).await;
    match pair_redeem(&http_client(), &base, "WXYZ-1234").await.unwrap() {
        PollOutcome::Approved(a) => assert_eq!(a.hub_id, "hub-42"),
        other => panic!("esperaba Approved, fue {other:?}"),
    }
}

// ── refresh_bridge_jwt: exige X-Bridge-Token ─────────────────────────────────

#[tokio::test]
async fn refresh_sends_bridge_token_header_and_parses() {
    async fn token_handler(headers: HeaderMap) -> Response {
        match headers.get("x-bridge-token").and_then(|v| v.to_str().ok()) {
            Some("dev-token-xyz") => Json(serde_json::json!({
                "token": "fresh.jwt",
                "expires_in": 900,
                "hub_url": "https://hub-42.erplora.com"
            }))
            .into_response(),
            _ => (StatusCode::UNAUTHORIZED, "missing token").into_response(),
        }
    }
    let router = Router::new().route("/api/v1/bridge/token/", post(token_handler));
    let base = spawn_saas(router).await;
    let t = refresh_bridge_jwt(&http_client(), &base, "dev-token-xyz").await.unwrap();
    assert_eq!(t.token, "fresh.jwt");
    assert_eq!(t.expires_in, 900);
    assert_eq!(t.hub_url, "https://hub-42.erplora.com");
}

#[tokio::test]
async fn refresh_rejects_bad_token_with_status_error() {
    async fn token_handler(headers: HeaderMap) -> Response {
        match headers.get("x-bridge-token").and_then(|v| v.to_str().ok()) {
            Some("good") => {
                Json(serde_json::json!({"token":"x","expires_in":1,"hub_url":"u"})).into_response()
            }
            _ => (StatusCode::UNAUTHORIZED, "nope").into_response(),
        }
    }
    let router = Router::new().route("/api/v1/bridge/token/", post(token_handler));
    let base = spawn_saas(router).await;
    let err = refresh_bridge_jwt(&http_client(), &base, "wrong").await.unwrap_err();
    assert!(matches!(err, PairingError::Status { status: 401, .. }), "fue {err:?}");
}

// ── run_direct_pairing: start → poll → persiste (sin abrir navegador) ─────────

#[tokio::test]
async fn direct_pairing_persists_on_approval() {
    let poll_script = Script::new(vec![
        (200, serde_json::json!({"status": "pending"})),
        (200, approved_body()),
    ]);
    let router = Router::new()
        .route(
            "/api/v1/bridge/pair/start/",
            post(|| async {
                Json(serde_json::json!({
                    "device_code": "dc-1",
                    "user_code": "WXYZ-1234",
                    "verification_uri": "https://erplora.com/bridge/pair",
                    "verification_uri_complete": "https://erplora.com/bridge/pair?code=WXYZ-1234",
                    "expires_in": 900,
                    "interval": 0
                }))
            }),
        )
        .route("/api/v1/bridge/pair/poll/", post(scripted))
        .with_state(poll_script);
    let base = spawn_saas(router).await;
    let p = tmp_pairing_path();
    let pairing = run_direct_pairing(
        &http_client(),
        &base,
        &p,
        "macos",
        "0.0.0",
        "iMac",
        false, // no abrir navegador en tests
    )
    .await
    .unwrap();
    assert_eq!(pairing.hub_id, "hub-42");
    assert_eq!(pairing.bridge_device_token, "dev-token-xyz");
    // Persistido y recargable.
    assert_eq!(load_pairing(&p).unwrap(), pairing);
    let _ = std::fs::remove_file(&p);
}

// ── tray: etiqueta de estado ─────────────────────────────────────────────────

#[test]
fn tray_status_label_reflects_pairing() {
    assert_eq!(status_label(None), "Not paired");
    assert_eq!(status_label(Some(&sample_pairing())), "Paired with Sur Restaurante");
}
