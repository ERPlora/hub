//! E2E del server: `GET /api/system/metrics` — telemetría de recursos vs límites del plan
//! (ADR-0154, hub#203). Verifica el contrato JSON, la autorización de **sesión admin** y que
//! plan/límites/sesiones salen del entitlement + la BD del hub. El estado de entitlement se siembra
//! como en producción lo hace el job de revalidación (`state.entitlement`); no hay red.
//!
//! Memoria/CPU salen del cgroup v2 y NO se asertan a un valor: dentro de un contenedor Linux traen
//! números; fuera (Mac dev, CI sin cgroup) traen `null` («n/a»). El test solo comprueba que el
//! objeto y sus claves existen — el cálculo puro está cubierto por los unit tests del módulo.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use cloud_client::{EntitledModule, EntitlementClaims};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// App en modo `Session` con un usuario admin (PIN 1111) y otro no-admin (cajero, PIN 2222).
/// Devuelve también el `AppState` para sembrar la celda de revalidación.
async fn fixture() -> (axum::Router, AppState, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-metrics");
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    rt.create_user("Cajero", "2222", "cashier", None).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-system-metrics-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: "hub-metrics".into(),
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

/// Claims verificadas de prueba con los límites del plan dados.
fn claims(plan: &str, max_devices: u32, max_database_size_gb: u32) -> EntitlementClaims {
    EntitlementClaims {
        hub_id: "hub-metrics".into(),
        modules: vec![EntitledModule {
            module_id: "pos".into(),
            tier: "basic".into(),
            version: "1.0.0".into(),
        }],
        iat: 1_000,
        exp: 2_000,
        grace_until: 9_999_999_999,
        paid_grace_until: None,
        plan: Some(plan.into()),
        max_devices,
        max_database_size_gb,
    }
}

fn pin_login(name: &str, pin: &str, device: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/pin")
        .header("content-type", "application/json")
        .body(Body::from(
            json!({ "name": name, "pin": pin, "device_id": device }).to_string(),
        ))
        .unwrap()
}

fn get_metrics(session: Option<&str>) -> Request<Body> {
    let mut b = Request::builder().method("GET").uri("/api/system/metrics");
    if let Some(tok) = session {
        b = b.header("x-hub-session", tok);
    }
    b.body(Body::empty()).unwrap()
}

async fn session_token(resp: axum::response::Response) -> String {
    assert_eq!(resp.status(), StatusCode::OK, "login debe devolver 200");
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    v["token"].as_str().expect("token en la respuesta").to_string()
}

async fn json_body(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

#[tokio::test]
async fn metrics_returns_plan_and_session_telemetry_for_admin() {
    let (router, state, temp) = fixture().await;
    // Plan free con 1 dispositivo (lo publica el job de revalidación; aquí lo sembramos igual).
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims("free", 1, 1), 1_500);

    let tok = session_token(router.clone().oneshot(pin_login("Admin", "1111", "dev-A")).await.unwrap()).await;
    let resp = router.clone().oneshot(get_metrics(Some(&tok))).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "admin puede leer las métricas");
    let body = json_body(resp).await;
    assert_eq!(body["ok"], json!(true));
    let data = &body["data"];

    // Plan del claim.
    assert_eq!(data["plan"], json!("free"));

    // Sesiones/dispositivos vs el límite del plan.
    assert_eq!(data["sessions"]["maxDevices"], json!(1));
    assert_eq!(data["sessions"]["active"], json!(1), "una sesión activa (el propio admin)");
    assert_eq!(data["sessions"]["devices"], json!(1), "un dispositivo distinto (dev-A)");

    // Base de datos Postgres aislada del harness, con tamaño real medido y cuota firmada de 1 GiB.
    assert_eq!(data["database"]["engine"], json!("postgres"));
    assert!(
        data["database"]["sizeBytes"].as_u64().is_some_and(|n| n > 0),
        "tamaño de BD medido: {:?}",
        data["database"]["sizeBytes"]
    );
    assert_eq!(data["database"]["limitBytes"], json!(1_073_741_824));
    let db_fraction = data["database"]["fraction"]
        .as_f64()
        .expect("fracción frente a cuota de BD");
    assert!(db_fraction > 0.0 && db_fraction <= 1.0);

    // Memoria/CPU: objeto presente con sus claves (valor null fuera de contenedor).
    for metric in ["memory", "cpu"] {
        assert!(data[metric].is_object(), "{metric} debe ser un objeto");
        assert!(data[metric].as_object().unwrap().contains_key("fraction"), "{metric}.fraction presente");
    }
    assert!(data["memory"].as_object().unwrap().contains_key("usedBytes"));
    assert!(data["memory"].as_object().unwrap().contains_key("limitBytes"));
    assert!(data["cpu"].as_object().unwrap().contains_key("usedCores"));
    assert!(data["cpu"].as_object().unwrap().contains_key("limitCores"));

    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn metrics_requires_a_session() {
    let (router, _state, temp) = fixture().await;
    let resp = router.oneshot(get_metrics(None)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "sin sesión → 401");
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn metrics_rejects_non_admin_session() {
    let (router, state, temp) = fixture().await;
    // Plan ilimitado para no desalojar sesiones entre logins (irrelevante para el gate de rol).
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims("free", 0, 0), 1_500);

    let tok = session_token(router.clone().oneshot(pin_login("Cajero", "2222", "dev-C")).await.unwrap()).await;
    let resp = router.clone().oneshot(get_metrics(Some(&tok))).await.unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "un cajero no puede leer métricas de gestión");
    std::fs::remove_dir_all(temp).ok();
}
