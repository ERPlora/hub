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
        hub_id: "hub-1".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: token.map(|s| s.to_string()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
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
