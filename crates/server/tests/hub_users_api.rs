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
        .get_or_link_cloud_user("cloud-1", "Ioan Beilic", "admin", None, None)
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
    assert_eq!(owner["role"], "admin");
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
        // `local: true` desde hub#356: sin la casilla el alta es la de un usuario de CUENTA y pide
        // email. Este es personal de barra —nombre + PIN—, que es justo lo que la casilla dice.
        json!({ "name": "Luis Prat", "role": "employee", "pin": "4242", "local": true }),
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

    // Con un segundo admin, degradar al primero ya es legítimo. Un administrador es siempre un
    // usuario de CUENTA (hub#356: administrar sale de una cuenta de ERPlora, nunca de un PIN), así
    // que el alta lleva email e intenta invitarlo — el SaaS del fixture no responde y el 502 es lo
    // esperado; la fila local queda creada igualmente, que es lo que esta barandilla mira.
    let second = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Ana Soto", "email": "ana@example.com", "role": "admin" }),
    )
    .await;
    assert_eq!(second.status(), StatusCode::BAD_GATEWAY);
    let census = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    assert!(census["data"]
        .as_array()
        .unwrap()
        .iter()
        .any(|u| u["name"] == "Ana Soto" && u["role"] == "admin" && u["is_active"] == true));
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
    for base in ["admin", "manager", "employee"] {
        assert!(names.contains(&base), "falta el rol base {base} en {names:?}");
    }
    // `owner` salió del catálogo base (hub#349): es del plano CUENTA, no del de NEGOCIO, y ningún
    // módulo le concede nada. Nadie lo lleva en este hub, así que la API no lo ofrece.
    assert!(
        !names.contains(&"owner"),
        "`owner` ya no es un rol del hub: {names:?}"
    );
    let admin = roles.iter().find(|r| r["name"] == "admin").unwrap();
    assert_eq!(admin["members"], 1);
    assert!(admin["permissions"].is_number());
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
        json!({ "name": "Luis Prat", "role": "cashier", "pin": "4242", "local": true }),
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

// ── Local user alta: name + PIN, nothing in the SaaS (plan step 2b, hub#355) ───────────────────
// The alta of somebody who can work the till, so the HTTP door matters as much as the rules: only
// an administrator opens it, and it never talks to the SaaS — there is no account to invite.

#[tokio::test]
async fn only_an_administrator_creates_a_local_user() {
    // Resolved on the conservative side (hub#355): the write gate of Personal stays
    // `require_admin_session`, the same one that guards settings, files, API keys and the module
    // lifecycle. The role matrix of the plan hands local staff to the `manager` too, but widening
    // the gate GRANTS access, so it belongs to the step that builds `manager` deliberately — not
    // to this one as a side effect.
    let f = fixture().await;
    let response = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.cashier,
        json!({ "name": "Luis Prat", "role": "employee", "pin": "5390", "local": true }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    assert_eq!(
        users["data"].as_array().unwrap().len(),
        2,
        "a rejected alta creates nobody"
    );
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn a_local_user_is_created_without_ever_calling_the_saas() {
    // The fixture points at an unreachable SaaS on purpose: an alta that tried to invite anybody
    // would answer `502 cloud_unreachable`, like the alta with email does. A local user has no
    // account, so the call must not happen at all.
    let f = fixture().await;
    let res = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Luis Prat", "role": "employee", "pin": "5390", "local": true }),
    )
    .await;
    assert_eq!(res.status(), StatusCode::OK);
    let created = body_json(res).await;
    assert_eq!(created["data"]["has_pin"], true);
    assert_eq!(created["data"]["email"], "");
    assert!(created["data"]["cloud_user_id"].is_null());
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn a_rejected_local_alta_answers_with_a_stable_code() {
    // The UI has to know WHY, not just that it failed: a duplicate PIN is fixed by typing another
    // one, an administrative role is not fixable at all. `RuntimeError::Domain` carries the code
    // verbatim (409) so the shell translates it instead of showing a runtime sentence.
    let f = fixture().await;
    for (payload, expected) in [
        (
            json!({ "name": "Luis Prat", "role": "admin", "pin": "5390", "local": true }),
            "hub.users.local_cannot_administer",
        ),
        (
            json!({ "name": "Luis Prat", "role": "employee", "pin": "", "local": true }),
            "hub.users.local_needs_pin",
        ),
        (
            json!({ "name": "Luis Prat", "role": "employee", "pin": "1111", "local": true }),
            "hub.users.pin_too_simple",
        ),
        (
            json!({ "name": "Marta Ruiz", "role": "employee", "pin": "5390", "local": true }),
            "hub.users.name_taken",
        ),
        (
            json!({
                "name": "Luis Prat", "role": "employee", "pin": "5390",
                "email": "luis@example.com", "local": true
            }),
            "hub.users.local_has_email",
        ),
    ] {
        let res = send(&f.router, "POST", "/api/hub/users", &f.owner, payload).await;
        assert_eq!(res.status(), StatusCode::CONFLICT);
        assert_eq!(body_json(res).await["error"]["code"], expected);
    }
    std::fs::remove_dir_all(f.media).ok();
}

// ── Account user alta: email + invitation (plan step 2b, hub#356) ─────────────────────────────
// The other half of the same alta. Here the identity lives in the SaaS, so the door is the SaaS's
// too: who may open it, and what they may grant through it, is decided BEFORE anything is written.

#[tokio::test]
async fn only_an_administrator_invites_anybody() {
    // Same conservative answer as hub#355: the write gate of Personal stays
    // `require_admin_session`. It matters more here than for a local user — this alta creates an
    // ERPlora account with a membership, so widening the gate would let somebody hand out access
    // to a hub they only work in.
    let f = fixture().await;
    let response = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.cashier,
        json!({ "name": "Luis Prat", "email": "luis@example.com", "role": "manager" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    assert_eq!(
        users["data"].as_array().unwrap().len(),
        2,
        "a rejected invitation creates nobody, locally or in the SaaS"
    );
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn a_rejected_account_alta_answers_with_a_stable_code_and_never_calls_the_saas() {
    // Every one of these is refused BEFORE the invitation goes out — the fixture's SaaS is
    // unreachable, so anything that reached it would answer `502 cloud_unreachable` instead of the
    // `409` with its code. Refusing first is the point: half a provisioning (a local row with an
    // email and no membership) is worse than no alta at all.
    let f = fixture().await;
    for (payload, expected) in [
        (
            json!({ "name": "Luis Prat", "role": "employee" }),
            "hub.users.account_needs_email",
        ),
        (
            json!({ "name": "Luis Prat", "email": "luis@example.com", "role": "kitchen" }),
            "hub.users.account_role_not_grantable",
        ),
        (
            json!({ "name": "Luis Prat", "email": "luis@example.com", "role": "owner" }),
            "hub.users.account_role_not_grantable",
        ),
        (
            json!({
                "name": "Luis Prat", "email": "luis@example.com",
                "role": "employee", "pin": "1234"
            }),
            "hub.users.pin_too_simple",
        ),
    ] {
        let res = send(&f.router, "POST", "/api/hub/users", &f.owner, payload).await;
        assert_eq!(res.status(), StatusCode::CONFLICT);
        assert_eq!(body_json(res).await["error"]["code"], expected);
    }
    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    assert_eq!(users["data"].as_array().unwrap().len(), 2);
    std::fs::remove_dir_all(f.media).ok();
}

#[tokio::test]
async fn the_same_email_is_never_invited_into_this_hub_twice() {
    let f = fixture().await;
    // First invitation: the SaaS is unreachable (502) but the local row is created — that is the
    // documented order (local → SaaS, honest status, idempotent by email).
    send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Ana Soto", "email": "ana@example.com", "role": "employee" }),
    )
    .await;

    let again = send(
        &f.router,
        "POST",
        "/api/hub/users",
        &f.owner,
        json!({ "name": "Ana S.", "email": "ana@example.com", "role": "admin" }),
    )
    .await;
    assert_eq!(again.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(again).await["error"]["code"],
        "hub.users.email_taken"
    );

    let users = body_json(get(&f.router, "/api/hub/users", Some(&f.owner)).await).await;
    let anas: Vec<&Value> = users["data"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|u| u["email"] == "ana@example.com")
        .collect();
    assert_eq!(anas.len(), 1, "one email, one row");
    assert_eq!(anas[0]["role"], "employee", "and no role was re-granted");
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

