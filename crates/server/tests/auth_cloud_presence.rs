//! E2E del server: **gate de presencia** de `auth_cloud` (ADR-0157, paso 2 — el fix de seguridad).
//!
//! Antes, `auth_cloud` hacía `get_or_link_cloud_user(..., "admin")` = *get-or-create* SIN comprobar
//! pertenencia: cualquier usuario del SaaS con un JWT válido que alcanzara el hub quedaba **admin
//! local**. El modelo objetivo (ADR-0157 §5) es un **gate de presencia**: el Hub solo deja entrar
//! si su `hub_id` está en el claim *coarse* `hubs: [{id, org}]` del JWT. Si no está → **403
//! `not_a_member`** y NO se provisiona el usuario (se pide invitación).
//!
//! El SaaS emite el claim `hubs` en una rama paralela (ADR-0157); aquí lo **mockeamos** firmando el
//! JWT con la clave privada de prueba (mismo par RSA que `entitlement.rs`), contra el contrato.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-1";

// Par de claves RSA de prueba: el "SaaS" firma con la privada, el Hub verifica con la pública.
const PRIV: &str = r#"-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDzGzIyJJGCZ9C6
y6Bm5rDSD6oyPm6vNLbP1XE3JsIdtZx8yRBpfomjsgtl5BNixVgqFAxts5m7odJ1
A3i2oKdBqsVK1wF+jpVaEf8O6+ts+8s3ju8AZCyUSNjCqRUObUC9jjOCW5VSWSnU
sZdGNXU7UTWOtbvOxqy+IdFE0DOeazH+i2SSQ+WV4u37rlidGh0GHYSsnbQeHRyX
Z4iyYxCfQDlqGAYCPp3GCvEdra+TiZXmJfIl7as8/cTqBY3wOuscwCi7pGLGODQy
H8QawNShpzvUHNqtTo5/o4DVTWf3j0LUJDCllswkMIRMX9m9M9Dhvqr6qD9dei+j
uR8WwyGdAgMBAAECggEAEKuWv5V+XODdkVGRSD0dduoYE6XwVRdaSdorD0sbGIpx
lqT6+SDyM0VsPqprIeTCbPA/Ae7E5fbsxZVdW7icf4ZETSN9OL5yQ2DkipNm62xA
vSiR/wbff7OXGZIanYikXds4cQHytVjj42/iHbBgv5aMA6M2o7E/+zG6deuI/p3c
8iq9mBEA8ErV10ybS5lMyo1ZkIXWG2OStP4yXVg4jH9GVVBKrV/vFVDPXgJLY6nv
aOBRu130OwK89STAqI13kBZ3H+wksu6UFc9NoQFPRnTf6pW+NhiO9F0RRAZwVC+N
mJJ4xwKUB8sg9p6/mIfqQTjDuKd1IsvFcaDZgd3KSQKBgQD9BUOv1ok6PnSrSSrU
5RsiJHuJcqR//qvFpyABejsB0Ilmco/dgQN6Knc4JZWX2FVcK8mofTbpQPKc6aOZ
GE+15xP3W62MIgaz5kyltxqa0g9DIRKktmiQtGWHDUkL8kXyLwaNxHjj03h/3ku/
AaiAt8qZ1xhBl4JvBKhmrUOnXwKBgQD1+AtzZ9fHLjN3GOk4SRvIMOt1mB0OOnZY
19jTPJD+Pyw9AH8ohhhdTIQTRMm+TIC5n/G6lMtJu9iSwqY2Kis60UyJa6BxwJpf
WTB1hyRUe9jGtwv9Aj9dyLwAyGAqp00WTkwoF7nRZO6pEpwCntydOsHFLlGR3hG2
+LYU4dkEgwKBgQCgN2QsBSJyMjg4eiVYGBc9YHKlj2Wg8wecKf63UMnqlT1cFPEK
ZvZntlo1wH7gXwl2Svfv7BIIU6sNN1jzyZQ38DIRcQkM8kLiSdOBH9gF7zvg2yFu
EV9XOhQMF5qIqQonmCWDQcT3JuJnvcCjG46yqy7siWp/pkvetslX8yEi6wKBgAdz
MN2Y+pck1hg4X+/9fuLsYGVaax7gNG9ycjXLstSQk0Vxu2g9z4Ub6TAwODAUXx3A
M3EkSpf8IY4oaSJg2phYeIn9AYoQfFyA9g/JPRd1/NXf+3P5WnP7vX4Ek60XDiWr
z3Czb0RhWz0xvBn0N9hnTDEtuvjBEiZJmDI/uPQDAoGBAOIt9bClD86rZ+gQttCH
+IQF7kWpM5sFJ1T99WgzVhh2KcoAbYBJXeNBrDaV5RXH81lgpJCr33UUb6dEH6Ro
jmmYhehBeEknoM0QbKpNkltZHLxv3hOEr3cdJxFhTfF1xtknyuD4PkCQxNCopR1N
2LZnAS37uyj9SuBl2xKDyikA
-----END PRIVATE KEY-----
"#;
const PUB: &str = r#"-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8xsyMiSRgmfQusugZuaw
0g+qMj5urzS2z9VxNybCHbWcfMkQaX6Jo7ILZeQTYsVYKhQMbbOZu6HSdQN4tqCn
QarFStcBfo6VWhH/DuvrbPvLN47vAGQslEjYwqkVDm1AvY4zgluVUlkp1LGXRjV1
O1E1jrW7zsasviHRRNAznmsx/otkkkPlleLt+65YnRodBh2ErJ20Hh0cl2eIsmMQ
n0A5ahgGAj6dxgrxHa2vk4mV5iXyJe2rPP3E6gWN8DrrHMAou6Rixjg0Mh/EGsDU
oac71BzarU6Of6OA1U1n949C1CQwpZbMJDCETF/ZvTPQ4b6q+qg/XXovo7kfFsMh
nQIDAQAB
-----END PUBLIC KEY-----
"#;

/// App en modo `Session` con la clave pública de prueba cargada (para verificar los JWT firmados)
/// y `hub_id = HUB_ID`. Devuelve también el `AppState` para poder introspeccionar `hub_user`.
async fn fixture() -> (axum::Router, AppState, std::path::PathBuf) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-auth-presence-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some(PUB.into()),
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    };
    let state = AppState::with_config(rt, cfg);
    (app(state.clone()), state, temp)
}

/// JWT de usuario firmado (RS256) con los claims dados. `hubs` es el claim *coarse* de ADR-0157.
fn sign_user_jwt(user_id: i64, hubs: Value) -> String {
    let claims = json!({
        "user_id": user_id,
        "token_type": "access",
        "exp": 9_999_999_999_i64,
        "organizations": [{"id": "org-A", "role": "employee"}],
        "hubs": hubs,
    });
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

/// JWT de usuario firmado con un `email` explícito (ADR-0157: el Hub enlaza el login con el
/// `hub_user` sembrado/invitado por email). `hubs` = claim *coarse* de presencia.
/// Como [`sign_user_jwt_email`] pero fijando el ROL del usuario en la organización `org-A`.
/// El Hub lo lee (`organizations` × `hubs[].org`) para decidir con qué rol local se provisiona.
fn sign_user_jwt_role(user_id: i64, email: &str, hubs: Value, org_role: &str) -> String {
    let claims = json!({
        "user_id": user_id,
        "email": email,
        "token_type": "access",
        "exp": 9_999_999_999_i64,
        "organizations": [{"id": "org-A", "role": org_role}],
        "hubs": hubs,
    });
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

fn sign_user_jwt_email(user_id: i64, email: &str, hubs: Value) -> String {
    let claims = json!({
        "user_id": user_id,
        "email": email,
        "token_type": "access",
        "exp": 9_999_999_999_i64,
        "organizations": [{"id": "org-A", "role": "owner"}],
        "hubs": hubs,
    });
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

/// Login cloud con un `bearer` dado (sin `name` ni `email` en el body: el email lo trae el token).
fn cloud_login_bare(bearer: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/cloud")
        .header("authorization", format!("Bearer {bearer}"))
        .header("content-type", "application/json")
        .body(Body::from(json!({}).to_string()))
        .unwrap()
}

/// JWT sin el claim `hubs` (SaaS legacy, previo a ADR-0157).
fn sign_legacy_jwt(user_id: i64) -> String {
    let claims = json!({
        "user_id": user_id,
        "token_type": "access",
        "exp": 9_999_999_999_i64,
    });
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

fn cloud_login(bearer: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/auth/cloud")
        .header("authorization", format!("Bearer {bearer}"))
        .header("content-type", "application/json")
        .body(Body::from(json!({ "name": "Ana" }).to_string()))
        .unwrap()
}

async fn json_body(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// ¿Existe un `hub_user` vinculado a `cloud_user_id`? Introspección directa de la BD del runtime.
async fn cloud_user_exists(state: &AppState, cloud_user_id: &str) -> bool {
    cloud_user_role(state, cloud_user_id).await.is_some()
}

/// Rol LOCAL del `hub_user` vinculado a `cloud_user_id` (o `None` si no existe). Introspección
/// directa de la BD del runtime para verificar el bootstrap «primer usuario = owner».
async fn cloud_user_role(state: &AppState, cloud_user_id: &str) -> Option<String> {
    let rt = state.runtime.lock().await;
    let mut p = erplora_db::Params::new();
    p.insert("cuid".to_string(), json!(cloud_user_id));
    let res = rt
        .db_for_test()
        .query(
            "SELECT role FROM hub_user WHERE cloud_user_id = :cuid",
            &p,
        )
        .await
        .unwrap();
    res.rows
        .first()
        .map(|r| r["role"].as_str().unwrap_or_default().to_string())
}

/// How many `hub_user` rows are linked to `cloud_user_id`. Re-evaluating the role floor must raise
/// the row the user already has, never provision a second one alongside it.
async fn cloud_user_rows(state: &AppState, cloud_user_id: &str) -> usize {
    let rt = state.runtime.lock().await;
    let mut p = erplora_db::Params::new();
    p.insert("cuid".to_string(), json!(cloud_user_id));
    rt.db_for_test()
        .query("SELECT id FROM hub_user WHERE cloud_user_id = :cuid", &p)
        .await
        .unwrap()
        .rows
        .len()
}

/// Is the `hub_user` linked to `cloud_user_id` still active? Rule D (hub#348) turns revoking the
/// membership in the SaaS into `is_active = 0` locally, so this is what "the door is shut" looks
/// like in the database.
async fn cloud_user_is_active(state: &AppState, cloud_user_id: &str) -> bool {
    let rt = state.runtime.lock().await;
    let mut p = erplora_db::Params::new();
    p.insert("cuid".to_string(), json!(cloud_user_id));
    let res = rt
        .db_for_test()
        .query(
            "SELECT is_active FROM hub_user WHERE cloud_user_id = :cuid",
            &p,
        )
        .await
        .unwrap();
    res.rows
        .first()
        .map(|r| r["is_active"].as_i64().unwrap_or(0) != 0)
        .unwrap_or(false)
}

/// An authenticated request with a hub session token (`X-Hub-Session`), to check whether a session
/// opened before a revocation still resolves afterwards.
fn authed_get(path: &str, session: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(path)
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

/// How many `hub_user` rows carry `email`. The invited row must be REUSED by the login that links
/// it, never left behind next to a freshly provisioned twin.
async fn rows_with_email(state: &AppState, email: &str) -> usize {
    let rt = state.runtime.lock().await;
    let mut p = erplora_db::Params::new();
    p.insert("email".to_string(), json!(email));
    rt.db_for_test()
        .query("SELECT id FROM hub_user WHERE email = :email", &p)
        .await
        .unwrap()
        .rows
        .len()
}

#[tokio::test]
async fn member_present_in_hubs_claim_links_and_opens_session() {
    // El hub de esta máquina (HUB_ID) figura en `hubs[]` → el usuario ENTRA y se provisiona local.
    let (router, state, temp) = fixture().await;
    let token = sign_user_jwt(123, json!([{ "id": HUB_ID, "org": "org-A" }]));

    let resp = router.oneshot(cloud_login(&token)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "miembro presente → 200");
    let body = json_body(resp).await;
    assert_eq!(body["ok"], json!(true));
    assert!(body["token"].as_str().is_some(), "abre sesión (token)");

    assert!(
        cloud_user_exists(&state, "123").await,
        "el usuario miembro se provisiona en hub_user"
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn seeded_owner_is_linked_by_email_keeping_owner_role() {
    // ADR-0157 (corrección Ioan): el owner es el CREADOR, **sembrado del env** (`HUB_OWNER_EMAIL`)
    // ANTES del primer login — NO «el primero que entra». En su primer login se ENLAZA por email
    // (el token trae `email`), conservando role=owner. `auth_cloud` ya NO decide el owner.
    let (router, state, temp) = fixture().await;
    // El provisioning del SaaS sembró al owner (aquí lo simulamos con el mismo seam que usa `serve`).
    state
        .runtime
        .lock()
        .await
        .seed_owner("boss@bar.com")
        .await
        .unwrap();

    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);
    let owner = sign_user_jwt_email(1, "boss@bar.com", member);
    let resp = router.oneshot(cloud_login_bare(&owner)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        cloud_user_role(&state, "1").await.as_deref(),
        Some("owner"),
        "el owner sembrado se enlaza por email conservando su rol"
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn member_without_seed_is_never_owner() {
    // Este test decía `employee` y ahora dice `admin`, y el cambio es deliberado.
    //
    // Lo que protege —y sigue protegiendo, más fuerte que antes— es que **el owner del hub NO se
    // deriva de un token**: sale del env sembrado al desplegar (`HUB_OWNER_EMAIL`, ADR-0157). Eso
    // no ha cambiado.
    //
    // Lo que sí cambia: el helper firma a este usuario como **owner de la organización `org-A`**,
    // que es la dueña del hub. Provisionarlo como `employee` era el bug que Ioan encontró el
    // 2026-08-01 — admin de su propia organización, dentro del hub sin poder importar un
    // blueprint ni promocionarse, y sin arreglo posible desde dentro. Ahora entra como `admin`.
    //
    // El auto-admin que cerró ADR-0157 sigue cerrado: ascendía a CUALQUIER usuario del SaaS con un
    // token válido; esto exige un rol administrativo **de la organización dueña de este hub**,
    // firmado por el SaaS. Lo verifica el test de abajo.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);
    let user = sign_user_jwt_email(2, "nuevo@bar.com", member);
    let resp = router.oneshot(cloud_login_bare(&user)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let rol = cloud_user_role(&state, "2").await;
    assert_ne!(rol.as_deref(), Some("owner"), "el owner es del env, NUNCA del token");
    assert_eq!(rol.as_deref(), Some("admin"), "owner/admin de la org → admin local");
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn member_sin_rol_administrativo_en_la_org_se_queda_en_minimo_privilegio() {
    // El guardián de verdad del auto-admin: pertenecer al hub NO basta para administrarlo. Alguien
    // que en el SaaS es `employee` de la organización entra con el mínimo privilegio aunque su
    // token sea válido y pase el gate de presencia.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);
    let user = sign_user_jwt_role(3, "curra@bar.com", member, "employee");
    let resp = router.oneshot(cloud_login_bare(&user)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        cloud_user_role(&state, "3").await.as_deref(),
        Some("employee"),
        "sin rol administrativo en la org → mínimo privilegio"
    );
    std::fs::remove_dir_all(temp).ok();
}

// ── The cloud role is a FLOOR re-evaluated on EVERY login (hub#347, plan step 2b rule C) ────────
//
// Until now the local role was a snapshot taken when the `hub_user` row was created:
// `get_or_link_cloud_user` returned the existing row untouched. Promote somebody in the SaaS and
// the hub never found out, so an account admin who happened to log in before being promoted was
// stuck as `employee` forever, unable to import a blueprint or to fix it from inside.
//
// The bridge between the two role planes is a FLOOR, not a synchronisation: owner/admin of the hub
// in the cloud means *at least* `admin` locally, checked on every login; above the floor the local
// role is left alone, and the floor never lowers anything and never grants `owner`.

#[tokio::test]
async fn a_cloud_promotion_reaches_the_hub_on_the_next_login() {
    // The bug this issue fixes: first login as a plain member, promoted in the SaaS afterwards.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let before = sign_user_jwt_role(7, "socio@bar.com", member.clone(), "employee");
    let resp = router.oneshot(cloud_login_bare(&before)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        cloud_user_role(&state, "7").await.as_deref(),
        Some("employee"),
        "first login: no administrative role in the cloud → least privilege",
    );

    // The account owner promotes them in the SaaS; their next token carries the new role.
    let after = sign_user_jwt_role(7, "socio@bar.com", member, "admin");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&after))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        cloud_user_role(&state, "7").await.as_deref(),
        Some("admin"),
        "the floor is re-evaluated on every login, so the promotion reaches the hub",
    );
    assert_eq!(
        cloud_user_rows(&state, "7").await,
        1,
        "the SAME row is raised: the login must not create a second `hub_user`",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn losing_the_cloud_admin_role_does_not_lower_the_local_role() {
    // A floor raises, it never lowers: dropping somebody to `employee` in the SaaS must not strip
    // the local role they were given inside the hub. Taking access away is a different operation —
    // deactivating the `hub_user` (rule D, hub#348) — and doing it by silent demotion would leave
    // them logged in with a role nobody chose.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let admin = sign_user_jwt_role(8, "jefa@bar.com", member.clone(), "admin");
    let resp = router.oneshot(cloud_login_bare(&admin)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(cloud_user_role(&state, "8").await.as_deref(), Some("admin"));

    let demoted = sign_user_jwt_role(8, "jefa@bar.com", member, "employee");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&demoted))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        cloud_user_role(&state, "8").await.as_deref(),
        Some("admin"),
        "no floor from the cloud leaves the local role exactly as the hub set it",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn the_cloud_floor_never_overwrites_the_seeded_owner() {
    // `owner` is already above the `admin` floor, so the floor is a no-op for the seeded owner.
    // Hub ownership comes from `HUB_OWNER_EMAIL` (ADR-0157) and the floor must not rewrite it —
    // neither up (it never grants `owner`) nor down (it would demote the owner of the hub).
    let (router, state, temp) = fixture().await;
    state
        .runtime
        .lock()
        .await
        .seed_owner("boss@bar.com")
        .await
        .unwrap();
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let owner = sign_user_jwt_role(9, "boss@bar.com", member.clone(), "owner");
    let resp = router.oneshot(cloud_login_bare(&owner)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        cloud_user_role(&state, "9").await.as_deref(),
        Some("owner"),
        "first login links the seeded owner by email and keeps `owner`",
    );

    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&owner))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(
        cloud_user_role(&state, "9").await.as_deref(),
        Some("owner"),
        "re-evaluating the floor must not demote the owner to `admin`",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn the_raised_role_is_the_one_the_session_gets() {
    // Raising the row is only half the fix: the session opened by that very login must already
    // carry the admin permissions, otherwise the promoted user still sees the hub as an employee
    // until they log in a third time.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let before = sign_user_jwt_role(10, "socia@bar.com", member.clone(), "employee");
    router.oneshot(cloud_login_bare(&before)).await.unwrap();

    let after = sign_user_jwt_role(10, "socia@bar.com", member, "admin");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&after))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = json_body(resp).await;
    assert_eq!(
        body["user"]["role"], "admin",
        "the login response reports the raised role, not the stale one",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn an_invited_admin_does_not_land_as_an_employee() {
    // Plan step 7 ("somebody invites you"), the trap it flagged for verification: a partner is
    // invited to run the business, and lands inside it unable to administer anything.
    //
    // The hub already knows their email —the owner had added them as a login user before the SaaS
    // invitation named them admin— so this login takes the *link by email* path, where the row
    // exists and its role was written once, when it was created. That is where the defect lived:
    // `get_or_link_cloud_user` handed the existing row back untouched, so the invited admin landed
    // as `employee` and had no way to fix it from inside.
    //
    // hub#347 made the cloud role a floor re-evaluated on every login; this walks the invitation
    // path end to end —cloud role in the JWT → floor → the invited row— which no e2e covered: the
    // one e2e that links by email seeds an `owner`, for whom the floor is a no-op.
    let (router, state, temp) = fixture().await;

    // The owner had already given them a way in, with the role they had at the time.
    state
        .runtime
        .lock()
        .await
        .create_login_user("socia@bar.com", "employee")
        .await
        .unwrap();

    // The SaaS invitation makes them an admin of THIS hub; their token carries that role.
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);
    let invited = sign_user_jwt_role(11, "socia@bar.com", member, "admin");
    let resp = router.oneshot(cloud_login_bare(&invited)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the invitee gets in");

    let body = json_body(resp).await;
    assert_eq!(
        body["user"]["role"], "admin",
        "the session that the invitation opens is an admin session, not an employee one",
    );
    assert_eq!(
        cloud_user_role(&state, "11").await.as_deref(),
        Some("admin"),
        "the invited row is raised on the very login that links it, not from the second one on",
    );
    assert_eq!(
        rows_with_email(&state, "socia@bar.com").await,
        1,
        "the invited row is REUSED: linking must not leave a second `hub_user` behind",
    );
    assert_eq!(
        cloud_user_rows(&state, "11").await,
        1,
        "and the cloud account is linked to exactly that one row",
    );
    std::fs::remove_dir_all(temp).ok();
}

// ── Revoking the membership SHUTS THE DOOR (hub#348, plan step 2b rule D) ───────────────────────
//
// Rule C made the cloud role a floor that only ever RISES, on purpose: losing the administrative
// role in the SaaS must not silently demote somebody inside the hub. Taking access away is this
// other half — the `hub_user` is DEACTIVATED — and until now it did not exist at all: a revoked
// member kept their local row, their PIN, their trusted device and their open session, and the only
// thing they lost was the ability to open a *new* cloud session.
//
// Deactivating is what actually shuts every door: `resolve_session` joins on `is_active = 1` (open
// sessions die), `verify_pin` and `list_pin_users` filter the same way (no PIN login, gone from the
// pinpad grid), and the device-trust flag is per device, not a way in by itself.

#[tokio::test]
async fn losing_the_membership_deactivates_the_local_user() {
    // The account owner removes somebody from this hub in the SaaS. Their next token no longer
    // lists the hub, and that token is the hub's notice: the local row must be closed, not just
    // refused a new session.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let token = sign_user_jwt_role(20, "socio@bar.com", member, "employee");
    let resp = router.oneshot(cloud_login_bare(&token)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert!(cloud_user_is_active(&state, "20").await, "starts out inside");

    let elsewhere = json!([{ "id": "hub-9", "org": "org-B" }]);
    let revoked = sign_user_jwt_role(20, "socio@bar.com", elsewhere, "employee");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&revoked))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN, "no longer a member");
    assert_eq!(json_body(resp).await["code"], json!("not_a_member"));

    assert!(
        !cloud_user_is_active(&state, "20").await,
        "rule D: the revoked membership DEACTIVATES the local user, it does not merely bounce them",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn losing_the_membership_cuts_a_session_that_is_already_open() {
    // The side door that makes the whole rule worth having: a session lives 30 days, so bouncing
    // the *login* leaves the revoked user working normally until it expires. The session must die
    // with the membership, on the next request, without waiting for the TTL.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let token = sign_user_jwt_role(21, "curra@bar.com", member, "employee");
    let resp = router.oneshot(cloud_login_bare(&token)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let session = json_body(resp).await["token"].as_str().unwrap().to_string();

    let resp = app(state.clone())
        .oneshot(authed_get("/api/hub/users", &session))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the session works before");

    let elsewhere = json!([{ "id": "hub-9", "org": "org-B" }]);
    let revoked = sign_user_jwt_role(21, "curra@bar.com", elsewhere, "employee");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&revoked))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);

    let resp = app(state.clone())
        .oneshot(authed_get("/api/hub/users", &session))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::UNAUTHORIZED,
        "the session opened before the revocation stops resolving immediately",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn insisting_with_a_revoked_token_provisions_nothing_and_leaves_the_row_shut() {
    // Rule D must be a ratchet, not a one-off: retrying with a token that still does not list the
    // hub keeps bouncing them, keeps the row closed and never creates anything. (The hole where a
    // deactivated row was answered with a brand new twin is guarded by the two tests below, which
    // walk the paths where a login actually gets as far as `get_or_link_cloud_user`.)
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let token = sign_user_jwt_role(22, "vuelve@bar.com", member.clone(), "employee");
    router.oneshot(cloud_login_bare(&token)).await.unwrap();

    let elsewhere = json!([{ "id": "hub-9", "org": "org-B" }]);
    let revoked = sign_user_jwt_role(22, "vuelve@bar.com", elsewhere, "employee");
    app(state.clone())
        .oneshot(cloud_login_bare(&revoked))
        .await
        .unwrap();
    assert!(!cloud_user_is_active(&state, "22").await);

    // They try again with the very same revoked token: still out, and still ONE row.
    let revoked_again = sign_user_jwt_role(22, "vuelve@bar.com", json!([]), "employee");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&revoked_again))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        cloud_user_rows(&state, "22").await,
        1,
        "a rejected login never provisions a second `hub_user`",
    );
    assert_eq!(
        rows_with_email(&state, "vuelve@bar.com").await,
        1,
        "nor a twin sharing the email",
    );
    assert!(
        !cloud_user_is_active(&state, "22").await,
        "and the row stays closed",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn regaining_the_membership_reuses_the_row_without_resurrecting_the_role() {
    // Re-admission is an admission, not an undo: the SaaS grants the membership again, so the door
    // rule D closed opens again — on the SAME row, never a duplicate — but the user comes back with
    // the role their CURRENT membership grants, not the one they held when they were shown out.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let boss = sign_user_jwt_role(23, "jefa@bar.com", member.clone(), "admin");
    let resp = router.oneshot(cloud_login_bare(&boss)).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(cloud_user_role(&state, "23").await.as_deref(), Some("admin"));

    let revoked = sign_user_jwt_role(23, "jefa@bar.com", json!([]), "admin");
    app(state.clone())
        .oneshot(cloud_login_bare(&revoked))
        .await
        .unwrap();
    assert!(!cloud_user_is_active(&state, "23").await);

    // Re-added in the SaaS, this time as a plain member.
    let back = sign_user_jwt_role(23, "jefa@bar.com", member, "employee");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&back))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the membership lets them in again");
    assert!(cloud_user_is_active(&state, "23").await, "the row is reinstated");
    assert_eq!(
        cloud_user_rows(&state, "23").await,
        1,
        "the SAME row is reused: no duplicate identity, no orphan history",
    );
    assert_eq!(
        cloud_user_role(&state, "23").await.as_deref(),
        Some("employee"),
        "coming back does NOT resurrect the admin role they no longer have",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn editing_a_revoked_user_without_deciding_about_the_door_keeps_the_revocation_theirs() {
    // Who closed a door is state, and state is easy to lose by accident. Personal writes name, role
    // and `is_active` in one UPDATE, so renaming somebody the SaaS had revoked must not quietly
    // relabel that revocation as a decision of the hub — it would strand them: their membership
    // could come back and the door would stay shut with nobody knowing why. Only an edit that
    // actually *decides* about the door (`is_active` present) touches the mark.
    let (router, state, temp) = fixture().await;
    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);

    let token = sign_user_jwt_role(25, "marta@bar.com", member.clone(), "employee");
    router.oneshot(cloud_login_bare(&token)).await.unwrap();
    let revoked = sign_user_jwt_role(25, "marta@bar.com", json!([]), "employee");
    app(state.clone())
        .oneshot(cloud_login_bare(&revoked))
        .await
        .unwrap();
    assert!(!cloud_user_is_active(&state, "25").await);

    // An admin tidies up the name from Personal. They said nothing about the door.
    let user_id = {
        let rt = state.runtime.lock().await;
        let id = rt
            .list_hub_users()
            .await
            .unwrap()
            .into_iter()
            .find(|u| u.email == "marta@bar.com" || u.name.starts_with("user:25"))
            .expect("the revoked row is still listed")
            .id;
        rt.update_hub_user(
            &id,
            &erplora_runtime::hub_users::UpdateHubUser {
                name: Some("Marta Ruiz".into()),
                ..Default::default()
            },
        )
        .await
        .unwrap();
        id
    };
    assert!(!user_id.is_empty());

    // The SaaS grants the membership again: the door it closed still opens.
    let back = sign_user_jwt_role(25, "marta@bar.com", member, "employee");
    let resp = app(state.clone())
        .oneshot(cloud_login_bare(&back))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "an unrelated edit must not strand a cloud revocation as a hub baja",
    );
    assert!(cloud_user_is_active(&state, "25").await);
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn a_user_the_hub_itself_deactivated_is_not_let_back_in_by_a_token() {
    // The other reason a row can be inactive: the hub's own admin showed them the door (ADR-0157
    // §7 / the Personal screen). That decision belongs to the hub, so a token must never undo it —
    // and the SaaS mirror can lag, because `remove_member` keeps the local baja even when the call
    // to the SaaS fails. Rejected with a stable code, and still without a duplicate row.
    let (router, state, temp) = fixture().await;
    {
        let rt = state.runtime.lock().await;
        rt.create_login_user("ana@bar.com", "manager").await.unwrap();
        assert!(rt.deactivate_login_user("ana@bar.com").await.unwrap());
    }

    let member = json!([{ "id": HUB_ID, "org": "org-A" }]);
    let token = sign_user_jwt_role(24, "ana@bar.com", member, "employee");
    let resp = router.oneshot(cloud_login_bare(&token)).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "a valid membership does not reopen a door the hub closed",
    );
    assert_eq!(json_body(resp).await["code"], json!("user_deactivated"));
    assert_eq!(
        rows_with_email(&state, "ana@bar.com").await,
        1,
        "and the rejected login provisions nothing",
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn non_member_is_rejected_403_and_no_user_created() {
    // El hub de esta máquina NO está en `hubs[]` (solo hub-9) → 403 `not_a_member`, SIN provisionar.
    let (router, state, temp) = fixture().await;
    let token = sign_user_jwt(456, json!([{ "id": "hub-9", "org": "org-B" }]));

    let resp = router.oneshot(cloud_login(&token)).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "no miembro → 403 (no auto-admin)"
    );
    let body = json_body(resp).await;
    assert_eq!(body["ok"], json!(false));
    assert_eq!(body["code"], json!("not_a_member"), "código de error claro");
    assert!(body["token"].is_null(), "no se abre sesión");

    assert!(
        !cloud_user_exists(&state, "456").await,
        "un NO miembro NO se provisiona (cierra el hueco de seguridad)"
    );
    std::fs::remove_dir_all(temp).ok();
}

#[tokio::test]
async fn legacy_token_without_hubs_claim_is_rejected() {
    // Decisión (ADR-0157 §5, gate = presencia): un token sin `hubs` no reconoce pertenencia →
    // rechazo. El gate es de seguridad; el default permisivo reabriría el hueco.
    let (router, state, temp) = fixture().await;
    let token = sign_legacy_jwt(789);

    let resp = router.oneshot(cloud_login(&token)).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "token legacy sin `hubs` → 403"
    );
    let body = json_body(resp).await;
    assert_eq!(body["code"], json!("not_a_member"));

    assert!(
        !cloud_user_exists(&state, "789").await,
        "token legacy tampoco provisiona"
    );
    std::fs::remove_dir_all(temp).ok();
}
