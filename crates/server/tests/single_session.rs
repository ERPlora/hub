//! E2E del server: **sesión única por dispositivo** con *takeover* (ADR-0154, hub#200).
//!
//! Con el plan de 1 dispositivo (claim `max_devices=1` del entitlement), un login en un 2º
//! dispositivo **desaloja** la sesión del 1º: su token deja de resolver → 401 en la siguiente
//! petición. Con plan ilimitado (`max_devices=0`) ambos dispositivos conviven (comportamiento
//! actual). El estado de entitlement se siembra como lo hace en producción el job de revalidación
//! (`state.entitlement`), no se toca la red.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use cloud_client::{EntitledModule, EntitlementClaims};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// App en modo `Session` con un usuario admin (PIN 1111). Devuelve también el `AppState` para
/// sembrar la celda de revalidación (el `entitlement` es un `Arc` compartido con el router).
async fn fixture() -> (axum::Router, AppState, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-sess");
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-single-session-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-sess".into(),
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
    (app(state.clone()), state, temp)
}

/// Claims verificadas de prueba con un `max_devices` dado (el resto irrelevante para el gate de
/// dispositivos). `grace_until` muy alto para no interferir con la revalidación de pago.
fn claims_with_max_devices(n: u32) -> EntitlementClaims {
    EntitlementClaims {
        hub_id: "hub-sess".into(),
        modules: vec![EntitledModule {
            module_id: "pos".into(),
            tier: "basic".into(),
            version: "1.0.0".into(),
        }],
        iat: 1_000,
        exp: 2_000,
        grace_until: 9_999_999_999,
        paid_grace_until: None,
        plan: Some("restaurant".into()),
        max_devices: n,
        max_database_size_gb: 0,
    }
}

fn pin_login(device: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/pin")
        .header("content-type", "application/json")
        .body(Body::from(
            json!({ "name": "Admin", "pin": "1111", "device_id": device }).to_string(),
        ))
        .unwrap()
}

fn get_with_session(uri: &str, token: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(uri)
        .header("x-hub-session", token)
        .body(Body::empty())
        .unwrap()
}

async fn session_token(resp: axum::response::Response) -> String {
    assert_eq!(resp.status(), StatusCode::OK, "login debe devolver 200");
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    v["token"]
        .as_str()
        .expect("token en la respuesta")
        .to_string()
}

#[tokio::test]
async fn second_device_login_takes_over_and_first_device_gets_401() {
    let (router, state, temp) = fixture().await;
    // Plan de 1 dispositivo (lo publica el job de revalidación; aquí lo sembramos igual).
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims_with_max_devices(1), 1_500);

    // Dispositivo A hace login y su token resuelve en un endpoint autenticado.
    let tok_a = session_token(router.clone().oneshot(pin_login("dev-A")).await.unwrap()).await;
    assert_eq!(
        router
            .clone()
            .oneshot(get_with_session("/api/system", &tok_a))
            .await
            .unwrap()
            .status(),
        StatusCode::OK,
        "A activo antes del takeover"
    );

    // Dispositivo B hace login → desaloja a A (takeover).
    let tok_b = session_token(router.clone().oneshot(pin_login("dev-B")).await.unwrap()).await;

    // La siguiente petición de A ya no resuelve → 401; la de B sí → 200.
    assert_eq!(
        router
            .clone()
            .oneshot(get_with_session("/api/system", &tok_a))
            .await
            .unwrap()
            .status(),
        StatusCode::UNAUTHORIZED,
        "A desalojado tras el login de B"
    );
    assert_eq!(
        router
            .clone()
            .oneshot(get_with_session("/api/system", &tok_b))
            .await
            .unwrap()
            .status(),
        StatusCode::OK,
        "B es la sesión activa"
    );

    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn unlimited_plan_keeps_both_devices() {
    let (router, state, temp) = fixture().await;
    // max_devices = 0 (ilimitado, p. ej. Hub Cloud multi-dispositivo): sin takeover.
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims_with_max_devices(0), 1_500);

    let tok_a = session_token(router.clone().oneshot(pin_login("dev-A")).await.unwrap()).await;
    let tok_b = session_token(router.clone().oneshot(pin_login("dev-B")).await.unwrap()).await;

    assert_eq!(
        router
            .clone()
            .oneshot(get_with_session("/api/system", &tok_a))
            .await
            .unwrap()
            .status(),
        StatusCode::OK,
        "A sigue activo (plan ilimitado)"
    );
    assert_eq!(
        router
            .clone()
            .oneshot(get_with_session("/api/system", &tok_b))
            .await
            .unwrap()
            .status(),
        StatusCode::OK,
        "B activo"
    );

    std::fs::remove_dir_all(temp).ok();
}
