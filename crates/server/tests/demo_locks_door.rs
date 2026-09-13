//! **What an ephemeral DEMO hub can and cannot change**, through the real HTTP doors (ADR-0197 §4,
//! amended by hub#1848).
//!
//! A demo is a REAL hub handed to a stranger for an hour, and every PRE hub carries the same flag
//! (`HUB_DEMO`). Since hub#1848 its admin saves the business's fiscal identity and its own
//! certificate exactly like a real hub does: blocking them left PRE unable to test the one flow a
//! paying business needs on day one (address by parts, representation grant, own certificate).
//!
//! The only closure left is the one that keeps a demo away from the real AEAT: the fiscal
//! environment stays pinned to `testing` (`demo_fiscal_environment_locked`, tested in the
//! dispatcher, `commands.rs`).
//!
//! What this file pins, and what runtime tests cannot:
//!
//!  - that the demo answers the identity and certificate doors **exactly like a real hub** — same
//!    status, same code — so a demo-only refusal cannot creep back in with the suite green;
//!  - that the flag is **not set by the caller**: no header, no body, no session. The deployment
//!    writes it (`HUB_DEMO`) and `AppState` seals it when it is built.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

type Response = axum::response::Response;

async fn body_json(response: Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

fn config(hub_id: &str, demo: bool, tag: &str) -> HubConfig {
    let temp =
        std::env::temp_dir().join(format!("erplora-demo-locks-{}-{tag}", std::process::id()));
    HubConfig {
        demo,
        hub_id: hub_id.into(),
        cloud_base_url: "https://example.invalid".into(),
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
    }
}

/// Router + sesión de **admin**, que es el rol con el que se entra a la demo.
async fn fixture(demo: bool, tag: &str) -> (axum::Router, String) {
    let hub_id = "hub-demo";
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    // Arranca como arranca en producción (hub#684): un hub de demo se siembra su identidad fiscal
    // y un hub real NO. Sin esto los tests de abajo probarían un estado que no existe.
    rt.set_demo_hub(demo);
    rt.ensure_demo_fiscal_identity().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let state = AppState::with_config(rt, config(hub_id, demo, tag));
    (app(state), admin)
}

async fn put(router: &axum::Router, uri: &str, session: &str, body: Value) -> Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri(uri)
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

async fn delete(router: &axum::Router, uri: &str, session: &str) -> Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("DELETE")
                .uri(uri)
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap()
}

/// El `error` estable que viaja al cliente, sea cual sea la envoltura del endpoint.
fn error_code(body: &Value) -> String {
    body.get("error")
        .and_then(|e| e.get("code").or(Some(e)))
        .and_then(|c| c.as_str())
        .unwrap_or_default()
        .to_string()
}

async fn get_settings(router: &axum::Router, session: &str) -> Value {
    let read = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/settings")
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    body_json(read).await
}

/// 🔴 hub#1848, the symptom as it was reported: in Settings → Business the screen sends the WHOLE
/// form — tax id and legal name unchanged, the address by parts new — and a demo answered
/// `409 demo_fiscal_identity_locked`, so nothing was saved and the representation grant could never
/// get the address it asks for.
#[tokio::test]
async fn a_demo_admin_saves_the_business_form_with_its_address_by_parts() {
    let (router, admin) = fixture(true, "address-parts").await;

    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({
            "business_tax_id": erplora_runtime::settings::DEMO_BUSINESS_TAX_ID,
            "business_legal_name": erplora_runtime::settings::DEMO_BUSINESS_LEGAL_NAME,
            "business_street": "Calle Mayor",
            "business_street_number": "7",
            "business_postal_code": "28013",
            "business_city": "Madrid",
        }),
    )
    .await;

    let status = response.status();
    let body = body_json(response).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let settings = get_settings(&router, &admin).await;
    assert_eq!(settings["business_street"], json!("Calle Mayor"));
    assert_eq!(settings["business_city"], json!("Madrid"));
}

/// 🔴 hub#1848: the admin of a demo writes its OWN fiscal identity, through the door that writes
/// it, and it stays written.
#[tokio::test]
async fn a_demo_admin_saves_the_fiscal_identity_over_http() {
    let (router, admin) = fixture(true, "identity").await;

    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({ "business_tax_id": "B12345674", "business_legal_name": "Bar Manolo SL" }),
    )
    .await;

    let status = response.status();
    let body = body_json(response).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let settings = get_settings(&router, &admin).await;
    assert_eq!(settings["business_tax_id"], json!("B12345674"));
    assert_eq!(settings["business_legal_name"], json!("Bar Manolo SL"));
}

/// 🔴 **hub#684 and hub#1848 in the same test.** The demo boots with a fiscal identity —so the
/// checklist does not stop the visitor and their first sale issues a document— and that identity is
/// a DEFAULT, not a lock: the admin replaces it with their own and the replacement sticks.
#[tokio::test]
async fn the_demo_boots_with_an_identity_and_its_admin_can_replace_it() {
    let (router, admin) = fixture(true, "seeded").await;

    // (a) The identity is there: it is what the fiscal gate of ADR-0203 reads and what the
    //     checklist marks as done. Without it, `invoice.create_from_sale` died in the outbox.
    let settings = get_settings(&router, &admin).await;
    assert_eq!(
        settings["business_tax_id"],
        json!(erplora_runtime::settings::DEMO_BUSINESS_TAX_ID),
        "a demo boots with a tax id: {settings}"
    );
    assert_eq!(
        settings["business_legal_name"],
        json!(erplora_runtime::settings::DEMO_BUSINESS_LEGAL_NAME),
        "…and with a legal name: {settings}"
    );

    // (b) …and the admin replaces it with their own.
    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({ "business_tax_id": "B12345674" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let settings = get_settings(&router, &admin).await;
    assert_eq!(settings["business_tax_id"], json!("B12345674"));
}

/// 🔴 La otra dirección de hub#684: **un hub REAL nace con la identidad VACÍA**. Es su ⛔ pendiente
/// y el dueño tiene que resolverlo; un NIF que apareciese solo se congelaría en el primer registro
/// (ADR-0273) y el negocio facturaría con una identidad que no es la suya.
#[tokio::test]
async fn a_real_hub_is_never_handed_a_fiscal_identity_at_boot() {
    let (router, admin) = fixture(false, "real-empty").await;
    let read = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/settings")
                .header("x-hub-session", &admin)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let settings = body_json(read).await;
    assert_eq!(settings["business_tax_id"], json!(""));
    assert_eq!(settings["business_legal_name"], json!(""));
}

/// Status and stable error code of a response: what a client can tell apart.
async fn outcome(response: Response) -> (StatusCode, String) {
    let status = response.status();
    (status, error_code(&body_json(response).await))
}

/// 🔴 hub#1848: the business certificate door answers a demo **exactly like a real hub**, uploading
/// and removing. The payload is not a valid PKCS#12, so both hubs refuse it — for the same reason,
/// which is the point: whatever a real hub says about a certificate, a demo says too, and there is
/// no `demo_business_certificate_locked` left to say.
#[tokio::test]
async fn a_demo_answers_the_certificate_door_exactly_like_a_real_hub() {
    let (demo, demo_admin) = fixture(true, "cert-demo").await;
    let (real, real_admin) = fixture(false, "cert-real").await;
    let upload = json!({ "pkcs12_b64": "Zm9v", "password": "s3cret" });

    let demo_upload = outcome(
        put(
            &demo,
            "/api/business/certificate",
            &demo_admin,
            upload.clone(),
        )
        .await,
    )
    .await;
    let real_upload =
        outcome(put(&real, "/api/business/certificate", &real_admin, upload).await).await;
    assert_ne!(demo_upload.1, "demo_business_certificate_locked");
    assert_eq!(
        demo_upload, real_upload,
        "upload: a demo is refused only what a real hub is"
    );

    let demo_delete = outcome(delete(&demo, "/api/business/certificate", &demo_admin).await).await;
    let real_delete = outcome(delete(&real, "/api/business/certificate", &real_admin).await).await;
    assert_ne!(demo_delete.1, "demo_business_certificate_locked");
    assert_eq!(
        demo_delete, real_delete,
        "delete: a demo is refused only what a real hub is"
    );
}

/// The demo **is still a hub**: everything else is configured as usual too.
#[tokio::test]
async fn a_demo_configures_everything_else_as_usual() {
    let (router, admin) = fixture(true, "usable").await;
    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({ "language": "en", "currency": "USD", "theme_palette": "ocean" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["language"], json!("en"));
    assert_eq!(body["currency"], json!("USD"));
}

/// 🔴 La otra dirección: un hub **REAL** escribe su identidad fiscal como siempre. Este test es el
/// que impide «cerrar por si acaso»: sin él, una guarda escapada dejaría a un negocio de pago sin
/// poder configurar el NIF con el que factura, y sin ningún síntoma más que un 409.
#[tokio::test]
async fn a_real_hub_writes_its_fiscal_identity_over_http_as_always() {
    let (router, admin) = fixture(false, "real").await;
    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({ "business_tax_id": "B12345674", "business_legal_name": "Bar Manolo SL" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["business_tax_id"], json!("B12345674"));
    assert_eq!(body["business_legal_name"], json!("Bar Manolo SL"));
}

/// 🔴 **Ningún cliente puede declarar que su hub es una demo.** Ni una cabecera, ni un campo en el
/// cuerpo, ni el contexto: la bandera es del despliegue. Si se pudiera, cualquier admin de un hub
/// real apagaría sus propias obligaciones fiscales — que es exactamente el agujero de hub#485.
#[tokio::test]
async fn no_caller_can_declare_its_own_hub_a_demo() {
    let (router, admin) = fixture(false, "spoof").await;

    // (a) por el cuerpo, junto a la escritura que querría bloquear.
    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({ "business_tax_id": "B99999997", "demo": true, "is_demo": true }),
    )
    .await;
    assert_eq!(
        response.status(),
        StatusCode::UNPROCESSABLE_ENTITY,
        "`demo` no es un setting: la escritura se rechaza por clave desconocida, no se acepta"
    );

    // (b) por cabecera, en una escritura por lo demás legítima.
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri("/api/settings")
                .header("content-type", "application/json")
                .header("x-hub-session", &admin)
                .header("x-hub-demo", "1")
                .header("x-demo", "true")
                .body(Body::from(
                    json!({ "business_tax_id": "B12345674" }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        response.status(),
        StatusCode::OK,
        "una cabecera del navegador no convierte el hub en una demo"
    );
    assert_eq!(
        body_json(response).await["business_tax_id"],
        json!("B12345674")
    );
}

/// 🔴 **Las dos claves son INDEPENDIENTES, y esta es la mitad que lo demuestra.** Un hub de
/// desarrollo sin enrolar (`HUB_AUTH=dev` + el `hub_id` placeholder) sale con `demo: true` —el
/// contrato de siempre, el que gobierna el fallback de login por PIN del SPA— y con
/// `ephemeral_demo: false`, porque **no** es la demo de ADR-0197.
///
/// Sin este test, el renombrado de `is_demo()` a `is_dev_hub()` podría haber colapsado los dos
/// conceptos en uno y nadie se enteraría: el resto del fichero solo mira el lado `false`.
#[tokio::test]
async fn a_dev_hub_is_reported_as_dev_and_never_as_the_ephemeral_demo() {
    let hub_id = erplora_server::DEV_HUB_ID;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let mut cfg = config(hub_id, false, "dev-hub");
    cfg.auth_mode = AuthMode::Dev;
    let router = app(AppState::with_config(rt, cfg));

    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let body = body_json(response).await;
    assert_eq!(
        body["demo"],
        json!(true),
        "`HUB_AUTH=dev` + hub_id placeholder = hub de DEV, y el contrato con el SPA lo dice: {body}"
    );
    assert_eq!(
        body["ephemeral_demo"],
        json!(false),
        "…y NO es la demo efímera de ADR-0197: son dos banderas con dos dueños: {body}"
    );
    assert_eq!(
        body["registration_required"],
        json!(false),
        "un hub de dev es la excepción al registro de máquina — lo que decide `is_dev_hub`: {body}"
    );
}

/// 🔴 Ser hub de dev exige **las dos mitades**: `HUB_AUTH=dev` **Y** el `hub_id` placeholder.
///
/// Un hub REAL —con su UUID del Cloud— arrancado con `HUB_AUTH=dev` **no** es la excepción al
/// registro de máquina. Es la mitad que separa «estoy desarrollando en local» de «este hub tiene
/// identidad propia», y la que impide que una variable de entorno mal puesta en un despliegue de
/// verdad abra el hub a las cabeceras del navegador.
#[tokio::test]
async fn dev_auth_on_a_hub_with_a_real_id_is_not_a_dev_hub() {
    let hub_id = "hub-real-uuid";
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let mut cfg = config(hub_id, false, "dev-auth-real-id");
    cfg.auth_mode = AuthMode::Dev; // una mitad SÍ…
    let router = app(AppState::with_config(rt, cfg)); // …pero el hub_id NO es el placeholder

    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/hub/context")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let body = body_json(response).await;
    assert_eq!(
        body["demo"],
        json!(false),
        "con un hub_id real, `HUB_AUTH=dev` NO basta para ser hub de dev: {body}"
    );
    assert_eq!(body["ephemeral_demo"], json!(false), "{body}");
}

/// El contexto de arranque dice si este hub es la demo efímera — y lo dice en **su propia clave**.
/// `demo` lleva años significando *modo dev* y el SPA la usa para el fallback de login por PIN:
/// reutilizarla habría abierto ese fallback en cada demo pública.
#[tokio::test]
async fn the_boot_context_reports_the_ephemeral_demo_in_its_own_key() {
    let (demo_router, _) = fixture(true, "ctx-demo").await;
    let (real_router, _) = fixture(false, "ctx-real").await;

    for (router, expected) in [(demo_router, true), (real_router, false)] {
        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/hub/context")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let body = body_json(response).await;
        assert_eq!(body["ephemeral_demo"], json!(expected), "{body}");
        assert_eq!(
            body["demo"],
            json!(false),
            "`demo` sigue siendo el modo dev (aquí `HUB_AUTH=session`), no la demo efímera: {body}"
        );
    }
}
