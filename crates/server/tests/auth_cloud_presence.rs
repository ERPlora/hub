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
