//! Contrato HTTP de **Personal (core)**: `/api/hub/users` + `/api/hub/roles`.
//!
//! La pantalla de Personal del Hub pinta los usuarios REALES de la BD del hub (`hub_user`), no los
//! miembros del módulo `staff` — que es un módulo de negocio con su propia navegación y que en la
//! mayoría de hubs no está instalado. Aquí se fija quién puede leer (cualquier sesión) y quién
//! puede escribir (owner/admin), y las dos barandillas de la baja: no puedes darte de baja a ti
//! mismo ni dejar el hub sin ningún administrador.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

struct Fixture {
    router: axum::Router,
    /// Sesión del owner (identidad cloud, sin PIN) — el administrador del hub.
    owner: String,
    owner_id: String,
    /// Sesión de una cajera solo-local (sin permisos de gestión).
    cashier: String,
    cashier_id: String,
    media: std::path::PathBuf,
}

async fn fixture() -> Fixture {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-users");
    rt.ensure_system_tables().await.unwrap();
    let owner = rt
        .get_or_link_cloud_user("cloud-1", "Ioan Beilic", "owner", None, None)
        .await
        .unwrap();
    let cashier = rt
        .create_user("Marta Ruiz", "1234", "cashier", None)
        .await
        .unwrap();
    let owner_token = rt.create_session(&owner.id, 3600, None).await.unwrap();
    let cashier_token = rt.create_session(&cashier, 3600, None).await.unwrap();
    let media = std::env::temp_dir().join(format!(
        "erplora-hub-users-api-{}-{}",
        std::process::id(),
        owner.id
    ));
    let cfg = HubConfig {
        hub_id: "hub-users".into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: media.join("modules"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: media.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    };
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        owner: owner_token,
        owner_id: owner.id,
        cashier: cashier_token,
        cashier_id: cashier,
        media,
    }
}

async fn get(router: &axum::Router, uri: &str, session: Option<&str>) -> axum::response::Response {
    let mut builder = Request::builder().uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    router
        .clone()
        .oneshot(builder.body(Body::empty()).unwrap())
        .await
        .unwrap()
}

async fn send(
    router: &axum::Router,
    method: &str,
    uri: &str,
    session: &str,
    body: Value,
) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method(method)
                .uri(uri)
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

#[tokio::test]
async fn lists_every_hub_user_including_the_owner_for_any_session() {
    let f = fixture().await;

    // Cualquier usuario logueado ve el personal (la pantalla está en la nav de todos).
    let response = get(&f.router, "/api/hub/users", Some(&f.cashier)).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true);
    let users = body["data"].as_array().unwrap();
    assert_eq!(users.len(), 2, "salen los DOS usuarios de la BD del hub");

    let owner = users
        .iter()
        .find(|u| u["id"] == f.owner_id.as_str())
        .expect("el owner/administrador tiene que salir aunque no tenga PIN");
    assert_eq!(owner["name"], "Ioan Beilic");
    assert_eq!(owner["role"], "owner");
    assert_eq!(owner["has_pin"], false);
    assert_eq!(owner["is_active"], true);
    assert_eq!(owner["cloud_user_id"], "cloud-1");

    let cashier = users
        .iter()
        .find(|u| u["id"] == f.cashier_id.as_str())
        .unwrap();
    assert_eq!(cashier["has_pin"], true);
    assert!(cashier["cloud_user_id"].is_null(), "solo-local");

    // Sin sesión no se listan usuarios.
    assert_eq!(
        get(&f.router, "/api/hub/users", None).await.status(),
        StatusCode::UNAUTHORIZED
    );
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn owner_creates_edits_and_deactivates_users() {
    let f = fixture().await;

    let created = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Luis Prat", "role": "employee", "pin": "4242" }),
    )
    .await;
    assert_eq!(created.status(), StatusCode::OK);
    let created = body_json(created).await;
    let id = created["data"]["id"].as_str().unwrap().to_string();
    assert_eq!(created["data"]["email"], "", "personal solo-local: sin cuenta online");
    assert_eq!(created["data"]["has_pin"], true);

    let updated = send(
        &f.router,
        "PUT",
        &format!("/api/hub/users/{id}"),
        &f.owner,
        json!({ "name": "Luis Prat Roig", "role": "manager" }),
    )
    .await;
    assert_eq!(updated.status(), StatusCode::OK);
    let updated = body_json(updated).await;
    assert_eq!(updated["data"]["name"], "Luis Prat Roig");
    assert_eq!(updated["data"]["role"], "manager");
    assert_eq!(updated["data"]["has_pin"], true, "editar no borra el PIN");

    // Baja = desactivar: el usuario sigue en la lista, marcado inactivo.
    let deleted = send(
        &f.router,
        "DELETE",
        &format!("/api/hub/users/{id}"),
        &f.owner,
        json!({}),
    )
    .await;
    assert_eq!(deleted.status(), StatusCode::OK);
    assert_eq!(body_json(deleted).await["data"]["is_active"], false);

    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    let listed = users["data"].as_array().unwrap();
    assert_eq!(listed.len(), 3, "el dado de baja NO desaparece");
    assert_eq!(
        listed.iter().find(|u| u["id"] == id.as_str()).unwrap()["is_active"],
        false
    );

    // Un payload inválido se rechaza con el mensaje del runtime (422, como el resto del server),
    // no con un 500.
    let bad = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Sin rol", "role": "" }),
    )
    .await;
    assert_eq!(bad.status(), StatusCode::UNPROCESSABLE_ENTITY);
    assert!(body_json(bad).await["error"].to_string().contains("rol"));
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn a_non_admin_cannot_manage_users() {
    let f = fixture().await;
    for (method, uri) in [
        ("POST", "/api/hub/users".to_string()),
        ("PUT", format!("/api/hub/users/{}", f.owner_id)),
        ("DELETE", format!("/api/hub/users/{}", f.owner_id)),
    ] {
        let response = send(
            &f.router,
            method,
            &uri,
            &f.cashier,
            json!({ "name": "Hackeo", "role": "owner" }),
        )
        .await;
        assert_eq!(
            response.status(),
            StatusCode::UNAUTHORIZED,
            "{method} {uri} no puede hacerlo una cajera"
        );
    }
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn the_hub_can_never_be_left_without_an_administrator() {
    let f = fixture().await;

    // Ni a uno mismo…
    let self_delete = send(
        &f.router,
        "DELETE",
        &format!("/api/hub/users/{}", f.owner_id),
        &f.owner,
        json!({}),
    )
    .await;
    assert_eq!(self_delete.status(), StatusCode::BAD_REQUEST);

    // …ni al último admin que quede (aquí, por la vía del PUT).
    let demote = send(
        &f.router,
        "PUT",
        &format!("/api/hub/users/{}", f.owner_id),
        &f.owner,
        json!({ "role": "employee" }),
    )
    .await;
    assert_eq!(demote.status(), StatusCode::BAD_REQUEST);
    assert!(body_json(demote)
        .await
        .to_string()
        .to_lowercase()
        .contains("administrador"));

    // Con un segundo admin, degradar al primero ya es legítimo.
    let second = body_json(
        send(
            &f.router,
            "POST",
            "/api/hub/users",
            &f.owner,
            json!({ "name": "Ana Soto", "role": "admin", "pin": "9999" }),
        )
        .await,
    )
    .await;
    assert!(second["data"]["id"].is_string());
    let demote = send(
        &f.router,
        "PUT",
        &format!("/api/hub/users/{}", f.owner_id),
        &f.owner,
        json!({ "role": "employee" }),
    )
    .await;
    assert_eq!(demote.status(), StatusCode::OK);
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn roles_are_served_by_the_core_without_any_module() {
    let f = fixture().await;
    let response = get(&f.router, "/api/hub/roles", Some(&f.cashier)).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let roles = body["data"].as_array().unwrap();
    let names: Vec<&str> = roles.iter().filter_map(|r| r["name"].as_str()).collect();
    for base in ["owner", "admin", "manager", "employee"] {
        assert!(names.contains(&base), "falta el rol base {base} en {names:?}");
    }
    let owner = roles.iter().find(|r| r["name"] == "owner").unwrap();
    assert_eq!(owner["members"], 1);
    assert!(owner["permissions"].is_number());
    std::fs::remove_dir_all(f.media).ok();
}

// ── El acceso lo administra el SaaS (ADR-0157 §7): un alta con email no puede quedarse local ──
// El SaaS es la fuente de verdad del ACCESO: si el hub crea el `hub_user` y NO avisa, el invitado
// nunca recibe la invitación ni la membresía → tiene ficha pero no puede entrar. `/api/members` ya
// hacía las dos cosas; la pantalla de Personal (que es la UI que le faltaba) tiene que hacerlas
// también, o habría dos altas divergentes.

#[tokio::test]
async fn creating_a_user_with_email_provisions_the_access_in_the_saas() {
    let f = fixture().await;
    // El fixture apunta a un SaaS inalcanzable a propósito: se comprueba que se INTENTA y que el
    // fallo se reporta (no un 200 silencioso que dejaría al invitado sin poder entrar nunca).
    let res = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Ana Soto", "email": "ana@example.com", "role": "manager" }),
    )
    .await;
    assert_eq!(
        res.status(),
        StatusCode::BAD_GATEWAY,
        "el hub no puede fingir que dio de alta el acceso"
    );
    let body = body_json(res).await;
    assert_eq!(body["code"], "cloud_unreachable");

    // …y el alta LOCAL persiste (idempotente por email), como en /api/members: el admin reintenta.
    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    let ana = users["data"]
        .as_array()
        .unwrap()
        .iter()
        .find(|u| u["name"] == "Ana Soto")
        .expect("el usuario local se creó igualmente");
    assert_eq!(ana["email"], "ana@example.com");
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn a_pin_only_user_never_touches_the_saas() {
    let f = fixture().await;
    // Personal de tienda sin cuenta online: es identidad LOCAL pura, el SaaS no pinta nada.
    let res = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Luis Prat", "role": "cashier", "pin": "4242" }),
    )
    .await;
    assert_eq!(res.status(), StatusCode::OK, "no debe intentar hablar con el SaaS");
    let created = body_json(res).await;
    assert_eq!(created["data"]["has_pin"], true);
    assert_eq!(created["data"]["email"], "");
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn deactivating_a_cloud_user_revokes_the_access_too() {
    let f = fixture().await;
    // Alta con email: el SaaS no responde (502) pero el usuario local queda creado.
    send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Ana Soto", "email": "ana@example.com", "role": "manager" }),
    )
    .await;
    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    let ana = users["data"]
        .as_array()
        .unwrap()
        .iter()
        .find(|u| u["name"] == "Ana Soto")
        .expect("alta local")
        .clone();

    // Simetría del alta: si el hub solo desactivase en local, el usuario seguiría viendo este hub
    // en su payload del SaaS. Se INTENTA revocar y el fallo se reporta.
    let res = send(
        &f.router,
        "DELETE",
        &format!("/api/hub/users/{}", ana["id"].as_str().unwrap()),
        &f.owner,
        json!({}),
    )
    .await;
    assert_eq!(res.status(), StatusCode::BAD_GATEWAY);

    // Y la baja LOCAL se aplicó igualmente (el acceso local muere ya; el SaaS se reintenta).
    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    let ana = users["data"]
        .as_array()
        .unwrap()
        .iter()
        .find(|u| u["name"] == "Ana Soto")
        .unwrap();
    assert_eq!(ana["is_active"], false);
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn the_profile_publishes_the_same_permissions_the_gate_grants() {
    // El shell decide qué enseña con los permisos que le devuelve el perfil/login. Si el servidor
    // concede `hub.users.view` a la sesión pero el perfil no lo lista, la UI esconde acciones que
    // el runtime sí permite — una divergencia silenciosa entre las dos caras del mismo gate.
    let f = fixture().await;
    let profile = body_json(
        get(&f.router, "/api/profile", Some(&f.cashier)).await,
    )
    .await;
    let perms: Vec<&str> = profile["permissions"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|p| p.as_str())
        .collect();
    assert!(
        perms.contains(&"hub.users.view"),
        "el perfil no publica el permiso del core: {perms:?}"
    );
    std::fs::remove_dir_all(f.media).ok();
}

