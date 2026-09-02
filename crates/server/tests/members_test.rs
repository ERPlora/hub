//! Tests de contrato del wiring de **miembros** (ADR-0157 §7): el runtime notifica al SaaS las
//! altas/bajas de usuarios locales con la credencial de máquina (`X-Hub-Token`). Aquí se verifica
//! la construcción del body del alta y el **gate del token de máquina** (sin él no se puede
//! administrar el acceso en el SaaS), sin tocar la red. La ejecución HTTP real la cubre la rama
//! SaaS en paralelo (el endpoint `members/` lo implementa allí).
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::members::{
    member_add_body, notify_member_added, notify_member_removed, MembersError,
};
use erplora_server::{AppState, AuthMode, HubConfig};

/// `AppState` mínimo con `cloud_api_token` configurable, para probar el gate del token de máquina
/// sin tocar la red.
async fn state_with_token(token: Option<&str>) -> AppState {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-1");
    let temp = std::env::temp_dir().join(format!("erplora-members-test-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-1".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: token.map(|s| s.to_string()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    AppState::with_config(rt, cfg)
}

#[test]
fn member_add_body_carries_email_and_role() {
    // El alta identifica al usuario por email + su rol Hub (ADR-0157 §7).
    let body = member_add_body("ana@bar.com", "manager");
    assert_eq!(body["email"], serde_json::json!("ana@bar.com"));
    assert_eq!(body["role"], serde_json::json!("manager"));
}

#[tokio::test]
async fn add_requires_machine_token() {
    // Sin credencial de máquina el hub NO puede administrar el acceso en el SaaS: falla claro
    // (bootstrap incompleto), no en silencio.
    let st = state_with_token(None).await;
    let err = notify_member_added(&st, "ana@bar.com", "employee")
        .await
        .unwrap_err();
    assert!(matches!(err, MembersError::NoMachineToken));
}

#[tokio::test]
async fn remove_requires_machine_token() {
    let st = state_with_token(None).await;
    let err = notify_member_removed(&st, "ana@bar.com").await.unwrap_err();
    assert!(matches!(err, MembersError::NoMachineToken));
}

// ── Handlers HTTP del panel admin (ADR-0157 checklist core #2) ────────────────────────────────

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::routing::{delete, post};
use axum::{Json, Router};
use erplora_server::app;
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::sync::Arc;
use tokio::sync::Mutex as AsyncMutex;
use tower::ServiceExt; // oneshot

/// SaaS de mentira que **registra** las llamadas de alta/baja de miembros y exige la credencial de
/// **máquina** (`X-Hub-Token`), para verificar que el runtime firma con el token de máquina y que la
/// simetría alta/baja llega al SaaS. Devuelve el address + el buffer de llamadas registradas.
async fn spawn_mock_saas() -> (String, Arc<AsyncMutex<Vec<String>>>) {
    let calls: Arc<AsyncMutex<Vec<String>>> = Arc::new(AsyncMutex::new(Vec::new()));
    let add_calls = calls.clone();
    let del_calls = calls.clone();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let mock = Router::new()
        .route(
            "/api/v1/hub/device/members/",
            post(
                move |headers: axum::http::HeaderMap, Json(body): Json<Value>| {
                    let calls = add_calls.clone();
                    async move {
                        if headers.get("x-hub-token").and_then(|v| v.to_str().ok())
                            != Some("machine-secret")
                        {
                            return (
                                StatusCode::UNAUTHORIZED,
                                Json(json!({ "error": "no machine" })),
                            );
                        }
                        let email = body["email"].as_str().unwrap_or_default().to_string();
                        let role = body["role"].as_str().unwrap_or_default().to_string();
                        calls.lock().await.push(format!("add:{email}:{role}"));
                        (StatusCode::CREATED, Json(json!({ "ok": true })))
                    }
                },
            ),
        )
        .route(
            "/api/v1/hub/device/members/:email/",
            delete(
                move |headers: axum::http::HeaderMap,
                      axum::extract::Path(email): axum::extract::Path<String>| {
                    let calls = del_calls.clone();
                    async move {
                        if headers.get("x-hub-token").and_then(|v| v.to_str().ok())
                            != Some("machine-secret")
                        {
                            return (
                                StatusCode::UNAUTHORIZED,
                                Json(json!({ "error": "no machine" })),
                            );
                        }
                        calls.lock().await.push(format!("del:{email}"));
                        (StatusCode::OK, Json(json!({ "ok": true })))
                    }
                },
            ),
        );
    tokio::spawn(async move {
        axum::serve(listener, mock).await.unwrap();
    });
    (format!("http://{addr}"), calls)
}

/// `AppState` en modo Session, con el esquema de sistema montado (incl. `hub_user.email`, v9),
/// token de máquina y `cloud_base_url` apuntando al SaaS de mentira.
async fn admin_state(cloud_base_url: &str) -> AppState {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-1");
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-members-http-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-1".into(),
        cloud_base_url: cloud_base_url.to_string(),
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
    AppState::with_config(rt, cfg)
}

/// Abre una sesión server-side para un `hub_user` con el `role` dado; devuelve el token opaco
/// (cabecera `X-Hub-Session`).
async fn open_session(state: &AppState, role: &str) -> String {
    let rt = state.runtime.read().await;
    let uid = rt.create_user("U", "", role, None).await.unwrap();
    rt.create_session(&uid, 3600, None).await.unwrap()
}

fn add_req(session: &str, email: &str, role: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/members")
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from(
            json!({ "email": email, "role": role }).to_string(),
        ))
        .unwrap()
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

#[tokio::test]
async fn add_member_rejects_non_admin_and_touches_nothing() {
    // Gate owner/admin: una sesión de `employee` NO puede dar de alta. No crea usuario local ni
    // llama al SaaS.
    let (cloud, calls) = spawn_mock_saas().await;
    let state = admin_state(&cloud).await;
    let session = open_session(&state, "employee").await;

    let resp = app(state.clone())
        .oneshot(add_req(&session, "hacker@bar.com", "owner"))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::UNAUTHORIZED,
        "employee no pasa el gate admin"
    );

    // No se creó ningún usuario-login y el SaaS no recibió nada.
    let listed = state.runtime.read().await.list_login_users().await.unwrap();
    assert!(listed.is_empty(), "no se creó el hub_user local");
    assert!(calls.lock().await.is_empty(), "no se notificó al SaaS");
}

#[tokio::test]
async fn add_member_as_admin_creates_local_user_and_notifies_saas() {
    // Un owner/admin da de alta a un usuario-login: se crea el `hub_user` local con su rol Y se
    // notifica el alta al SaaS (con la credencial de máquina).
    let (cloud, calls) = spawn_mock_saas().await;
    let state = admin_state(&cloud).await;
    let session = open_session(&state, "owner").await;

    let resp = app(state.clone())
        .oneshot(add_req(&session, "ana@bar.com", "manager"))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    assert_eq!(body["user"]["role"], json!("manager"));

    // Usuario-login creado localmente con su email + rol.
    let listed = state.runtime.read().await.list_login_users().await.unwrap();
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0].email, "ana@bar.com");
    assert_eq!(listed[0].role, "manager");

    // El SaaS recibió el alta (fuente de verdad del acceso).
    assert_eq!(
        *calls.lock().await,
        vec!["add:ana@bar.com:manager".to_string()]
    );
}

#[tokio::test]
async fn remove_member_as_admin_deactivates_local_and_notifies_saas() {
    // Simetría del alta: un owner/admin da de baja → desactiva el `hub_user` local Y revoca la
    // membresía en el SaaS.
    let (cloud, calls) = spawn_mock_saas().await;
    let state = admin_state(&cloud).await;
    let session = open_session(&state, "admin").await;

    // Alta previa (para poder darlo de baja).
    app(state.clone())
        .oneshot(add_req(&session, "ana@bar.com", "manager"))
        .await
        .unwrap();

    let resp = app(state.clone())
        .oneshot(
            Request::builder()
                .method("DELETE")
                .uri("/api/members/ana@bar.com")
                .header("x-hub-session", &session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["ok"], json!(true));

    // El usuario-login queda inactivo (sigue listado para audit).
    let listed = state.runtime.read().await.list_login_users().await.unwrap();
    assert_eq!(listed.len(), 1);
    assert!(!listed[0].is_active, "desactivado");

    // El SaaS recibió alta + baja (simetría).
    assert_eq!(
        *calls.lock().await,
        vec![
            "add:ana@bar.com:manager".to_string(),
            "del:ana@bar.com".to_string()
        ]
    );
}

#[tokio::test]
async fn list_members_requires_admin() {
    // GET /api/members: gate admin; un owner ve la lista, un employee es rechazado.
    let (cloud, _calls) = spawn_mock_saas().await;
    let state = admin_state(&cloud).await;
    let admin = open_session(&state, "owner").await;
    app(state.clone())
        .oneshot(add_req(&admin, "ana@bar.com", "manager"))
        .await
        .unwrap();

    // Owner: 200 con la lista.
    let resp = app(state.clone())
        .oneshot(
            Request::builder()
                .uri("/api/members")
                .header("x-hub-session", &admin)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["members"].as_array().unwrap().len(), 1);
    assert_eq!(body["members"][0]["email"], json!("ana@bar.com"));

    // Employee: rechazado.
    let emp = open_session(&state, "employee").await;
    let resp = app(state.clone())
        .oneshot(
            Request::builder()
                .uri("/api/members")
                .header("x-hub-session", &emp)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
}
