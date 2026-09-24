//! E2E del server: **tope de usuarios del plan** (hub#1685, ADR-0474 punto 1).
//!
//! El plan Gratis promete «3 usuarios» y hasta ahora el hub no lo aplicaba: el cuarto se creaba
//! sin que nadie dijese nada. El tope llega en el claim `max_users` del entitlement (gemelo exacto
//! de `max_devices`, ADR-0154): `0` = ilimitado, y **sin claim conocido no se aplica nada**
//! (fail-open) — la autoridad es el SaaS, igual que en el resto del gate.
//!
//! Se cuentan los usuarios **activos** del hub: dar de baja libera plaza, que es lo que espera
//! quien rota personal. Por eso se prueban las TRES puertas que suman un activo — el alta de
//! Personal, el alta de un usuario-login y la **reactivación** de una baja—: dejar una abierta es
//! dejar el tope sin aplicar.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use cloud_client::{EntitledModule, EntitlementClaims};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB: &str = "hub-users";

/// App en modo `Session` con un usuario **admin** (PIN 1111) — el primero de los tres del plan
/// Gratis. Devuelve el `AppState` para sembrar la celda de revalidación, como `single_session.rs`.
async fn fixture() -> (axum::Router, AppState, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-user-limit-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB.into(),
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

/// Claims verificadas con un `max_users` dado (el resto irrelevante para este gate).
fn claims_with_max_users(n: u32) -> EntitlementClaims {
    EntitlementClaims {
        hub_id: HUB.into(),
        modules: vec![EntitledModule {
            module_id: "pos".into(),
            tier: "basic".into(),
            version: "1.0.0".into(),
        }],
        iat: 1_000,
        exp: 2_000,
        grace_until: 9_999_999_999,
        paid_grace_until: None,
        plan: Some("free".into()),
        max_devices: 0,
        max_database_size_gb: 0,
        max_users: n,
    }
}

async fn admin_token(router: &axum::Router) -> String {
    let resp = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/pin")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({ "name": "Admin", "pin": "1111" }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "login admin debe devolver 200"
    );
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    v["token"].as_str().expect("token").to_string()
}

/// `POST /api/hub/users` con un alta **local** (nombre + PIN): no llama al SaaS.
async fn create_local_user(
    router: &axum::Router,
    token: &str,
    name: &str,
    pin: &str,
) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/users")
                .header("content-type", "application/json")
                .header("x-hub-session", token)
                .body(Body::from(
                    json!({ "name": name, "role": "employee", "pin": pin, "local": true })
                        .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap()
}

async fn error_code(resp: axum::response::Response) -> String {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let v: Value = serde_json::from_slice(&bytes).unwrap();
    v["error"]["code"].as_str().unwrap_or_default().to_string()
}

#[tokio::test]
async fn free_plan_refuses_the_fourth_user_and_names_the_limit() {
    let (router, state, temp) = fixture().await;
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims_with_max_users(3), 1_500);
    let token = admin_token(&router).await;

    // Admin (1) + estos dos = los 3 del plan Gratis: hasta aquí, todo entra.
    for (name, pin) in [("Marta", "4729"), ("Bruno", "5183")] {
        assert_eq!(
            create_local_user(&router, &token, name, pin).await.status(),
            StatusCode::OK,
            "{name} cabe en el plan de 3"
        );
    }

    // El cuarto NO: hoy se creaba sin que nadie dijese nada (hub#1685).
    let resp = create_local_user(&router, &token, "Lucía", "7261").await;
    // `409`, no `400`: un rechazo de NEGOCIO del core viaja como `RuntimeError::Domain`, y `Domain`
    // es Conflict en todo el hub (`dispatch_api::shape`) — el mismo estado con el que ya salen
    // `pin_in_use` o `name_taken`. La pantalla se guía por el CÓDIGO, no por el número.
    assert_eq!(
        resp.status(),
        StatusCode::CONFLICT,
        "el cuarto usuario debe rechazarse en el plan de 3"
    );
    assert_eq!(
        error_code(resp).await,
        "hub.users.user_limit_reached",
        "el motivo tiene que ser distinguible para que la pantalla ofrezca ampliar el plan"
    );

    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn unlimited_plan_keeps_creating_users() {
    let (router, state, temp) = fixture().await;
    // `0` = sin tope (plan de pago), igual que `max_devices`.
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims_with_max_users(0), 1_500);
    let token = admin_token(&router).await;

    for (name, pin) in [("Marta", "4729"), ("Bruno", "5183"), ("Lucía", "7261")] {
        assert_eq!(
            create_local_user(&router, &token, name, pin).await.status(),
            StatusCode::OK,
            "{name} entra: el plan no tiene tope de usuarios"
        );
    }

    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn without_a_verified_token_the_hub_enforces_nothing() {
    // Fail-open: sin refresh exitoso previo (hub recién arrancado, dev sin enrolar) la autoridad
    // es el SaaS y el hub no inventa un tope. Misma dirección que el gate de entitlement.
    let (router, _state, temp) = fixture().await;
    let token = admin_token(&router).await;

    for (name, pin) in [("Marta", "4729"), ("Bruno", "5183"), ("Lucía", "7261")] {
        assert_eq!(
            create_local_user(&router, &token, name, pin).await.status(),
            StatusCode::OK,
            "{name} entra: sin claim no hay tope que aplicar"
        );
    }

    std::fs::remove_dir_all(temp).ok();
}

// ── Las otras dos puertas que suman un activo ───────────────────────────────────────────────

async fn json_body(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn add_member(router: &axum::Router, token: &str, email: &str) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/members")
                .header("content-type", "application/json")
                .header("x-hub-session", token)
                .body(Body::from(
                    json!({ "email": email, "role": "employee" }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap()
}

async fn set_active(
    router: &axum::Router,
    token: &str,
    id: &str,
    active: bool,
) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri(format!("/api/hub/users/{id}"))
                .header("content-type", "application/json")
                .header("x-hub-session", token)
                .body(Body::from(json!({ "is_active": active }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

/// La otra puerta del mismo alta (`/api/members`, ADR-0157 §7): invitar a alguien nuevo cuando el
/// plan está lleno tampoco puede colarse. Y el tope se mira ANTES de escribir en local y ANTES de
/// llamar al SaaS, porque una invitación que el hub no puede sostener no debería salir.
#[tokio::test]
async fn the_members_door_also_refuses_a_new_person_when_the_plan_is_full() {
    let (router, state, temp) = fixture().await;
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims_with_max_users(3), 1_500);
    let token = admin_token(&router).await;
    for (name, pin) in [("Marta", "4729"), ("Bruno", "5183")] {
        assert_eq!(
            create_local_user(&router, &token, name, pin).await.status(),
            StatusCode::OK
        );
    }

    let resp = add_member(&router, &token, "lucia@example.com").await;
    assert_eq!(
        resp.status(),
        StatusCode::CONFLICT,
        "invitar a una cuarta persona con el plan lleno tiene que rechazarse"
    );
    assert_eq!(error_code(resp).await, "hub.users.user_limit_reached");

    std::fs::remove_dir_all(temp).ok();
}

/// **Reactivar es dar de alta.** Si la baja liberó la plaza y otro la ocupó, reincorporar a quien se
/// fue vuelve a ser un alta y pasa por el mismo tope; si no, el contador se saltaría dando de baja
/// y volviendo a activar.
#[tokio::test]
async fn bringing_a_deactivated_user_back_is_refused_when_the_plan_is_full() {
    let (router, state, temp) = fixture().await;
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims_with_max_users(3), 1_500);
    let token = admin_token(&router).await;

    // Admin + Marta + Bruno = 3. Bruno se va (2), entra Lucía en su plaza (3).
    assert_eq!(
        create_local_user(&router, &token, "Marta", "4729")
            .await
            .status(),
        StatusCode::OK
    );
    let bruno = json_body(create_local_user(&router, &token, "Bruno", "5183").await).await;
    let bruno_id = bruno["data"]["id"]
        .as_str()
        .expect("id de Bruno")
        .to_string();
    assert_eq!(
        set_active(&router, &token, &bruno_id, false).await.status(),
        StatusCode::OK,
        "la baja de Bruno libera su plaza"
    );
    assert_eq!(
        create_local_user(&router, &token, "Lucía", "7261")
            .await
            .status(),
        StatusCode::OK,
        "Lucía entra en la plaza que dejó Bruno"
    );

    // Reincorporar a Bruno serían 4: se rechaza con el mismo motivo que el alta.
    let resp = set_active(&router, &token, &bruno_id, true).await;
    assert_eq!(
        resp.status(),
        StatusCode::CONFLICT,
        "reincorporar a Bruno con el plan lleno serían cuatro activos"
    );
    assert_eq!(error_code(resp).await, "hub.users.user_limit_reached");

    std::fs::remove_dir_all(temp).ok();
}

/// Y al revés: **editar a quien ya está dentro no gasta plaza**. Guardar un cambio de rol o de
/// nombre con el plan lleno es lo normal, no un alta — si el tope se mirase en toda escritura, un
/// hub Gratis con sus tres usuarios no podría volver a tocar ninguno.
#[tokio::test]
async fn editing_somebody_already_inside_does_not_need_a_free_seat() {
    let (router, state, temp) = fixture().await;
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(claims_with_max_users(3), 1_500);
    let token = admin_token(&router).await;
    assert_eq!(
        create_local_user(&router, &token, "Marta", "4729")
            .await
            .status(),
        StatusCode::OK
    );
    let bruno = json_body(create_local_user(&router, &token, "Bruno", "5183").await).await;
    let bruno_id = bruno["data"]["id"]
        .as_str()
        .expect("id de Bruno")
        .to_string();

    let resp = router
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri(format!("/api/hub/users/{bruno_id}"))
                .header("content-type", "application/json")
                .header("x-hub-session", &token)
                .body(Body::from(json!({ "name": "Bruno Díaz" }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "renombrar a alguien que ya ocupa su plaza no es un alta"
    );

    std::fs::remove_dir_all(temp).ok();
}
