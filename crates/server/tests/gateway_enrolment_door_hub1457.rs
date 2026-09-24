//! hub#1457: la puerta del runtime para el alta de la identidad de máquina.
//!
//! Lo que se prueba aquí es lo que NO se puede probar dentro del módulo: que la ruta existe, que
//! está detrás de una sesión de **admin** —el `X-Hub-Token` que viaja al otro lado es un secreto
//! del runtime (ADR-0003) y quien lo dispara tiene que ser alguien con permiso— y que un plano de
//! control inalcanzable sale por un CÓDIGO, no por un 500.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use tower::ServiceExt;

const ROUTE: &str = "/api/business/gateway-identity/enrol";

async fn fixture() -> (axum::Router, String, String, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-enrol");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let cashier_id = rt
        .create_user("Cashier", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let cashier = rt.create_session(&cashier_id, 3600, None).await.unwrap();
    let temp = std::env::temp_dir().join(format!(
        "erplora-enrol-door-{}-{admin_id}",
        std::process::id()
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-enrol".into(),
        // Unreachable on purpose: the door must answer a code, never a stack trace.
        cloud_base_url: "http://127.0.0.1:1".into(),
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
    (app(AppState::with_config(rt, cfg)), admin, cashier, temp)
}

fn post(session: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("POST").uri(ROUTE);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    builder.body(Body::empty()).unwrap()
}

/// 🔒 La puerta la abre un admin. Sin sesión, y con la de un cajero, no se dispara: al otro lado
/// viaja el `X-Hub-Token`, que es secreto del runtime.
#[tokio::test]
async fn the_enrolment_door_is_only_open_to_an_admin_session() {
    let (router, _admin, cashier, temp) = fixture().await;

    let anonymous = router.clone().oneshot(post(None)).await.unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let as_cashier = router.oneshot(post(Some(&cashier))).await.unwrap();
    assert_eq!(as_cashier.status(), StatusCode::UNAUTHORIZED);

    let _ = std::fs::remove_dir_all(&temp);
}

/// Un plano de control inalcanzable no es un 500: la pantalla del módulo lee un CÓDIGO estable
/// (ADR-0055) y puede decir qué pasa.
#[tokio::test]
async fn an_unreachable_control_plane_answers_a_code_not_a_crash() {
    let (router, admin, _cashier, temp) = fixture().await;

    let response = router.oneshot(post(Some(&admin))).await.unwrap();
    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);

    let body = axum::body::to_bytes(response.into_body(), 64 * 1024)
        .await
        .unwrap();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(json["code"], "enrolment.cloud_unreachable");

    let _ = std::fs::remove_dir_all(&temp);
}
