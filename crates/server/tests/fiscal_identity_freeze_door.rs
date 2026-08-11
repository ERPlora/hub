//! **El NIF del negocio deja de ser editable cuando el hub ya ha EMITIDO** — por la puerta HTTP
//! real (`PUT /api/settings`), ERPlora/hub#554.
//!
//! La cadena VeriFactu está anclada por `(hub_id, issuer_nif, environment)` (guarda R4, hub#313):
//! el ancla, la secuencia y el `PrimerRegistro` se resuelven por ese NIF. Cambiarlo después de
//! haber emitido **bifurca la cadena en silencio** —arranca una nueva desde 1 y abandona la vieja a
//! mitad— y, para la AEAT, convierte al hub en **otro obligado tributario**.
//!
//! Y esta puerta es doblemente cara: el mismo NIF que ancla la cadena es el que
//! `POST /api/business/fiscal-identity` publica al SaaS como `BillingProfile` (ADR-0201 decisión
//! 5). Un cambio aquí no solo bifurca la cadena: reescribe a quién factura ERPlora.
//!
//! Lo que fija este fichero, y que los tests del runtime no pueden fijar:
//!
//!  - el **código de estado y el código estable** que ve el cliente (`409` + `business_tax_id_frozen`),
//!    porque es contra eso contra lo que la UI se explica;
//!  - que se distingue del cierre de la DEMO (`demo_fiscal_identity_locked`): son dos guardas
//!    distintas en la misma clave, y si contestaran lo mismo se podría borrar una con la suite en
//!    verde;
//!  - las **dos mitades que no pueden romperse**: un hub que aún NO ha emitido escribe su NIF como
//!    siempre, y uno que SÍ ha emitido sigue pudiendo corregir el resto del formulario de Negocio
//!    (razón social y dirección) — que va en el MISMO `PUT`.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

type Response = axum::response::Response;

const HUB_ID: &str = "hub-frozen";

async fn body_json(response: Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

fn config(tag: &str) -> HubConfig {
    let temp =
        std::env::temp_dir().join(format!("erplora-taxid-freeze-{}-{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
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

/// Router + sesión de **admin** (el rol que configura la identidad fiscal), con el hub ya
/// arrancado. `emitted` estampa el perfil fiscal como lo hace la salida a producción: este hub ya
/// mandó su primer registro bajo `B12345678`.
async fn fixture(tag: &str, emitted: bool) -> (axum::Router, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();

    let mut updates = serde_json::Map::new();
    updates.insert("business_tax_id".into(), json!("B12345678"));
    updates.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    rt.set_settings(&updates, "hub_user:seed").await.unwrap();

    if emitted {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB_ID));
        rt.db()
            .execute(
                "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production', \
                   activated_at = '2026-08-08T09:00:00Z', \
                   first_record_at = '2026-08-08T10:00:00Z', taxpayer_id = 'B12345678' \
                 WHERE hub_id = :hub_id",
                &p,
            )
            .await
            .unwrap();
    }

    (app(AppState::with_config(rt, config(tag))), admin)
}

async fn put(router: &axum::Router, session: &str, body: Value) -> Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri("/api/settings")
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

async fn get(router: &axum::Router, session: &str) -> Value {
    let response = router
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
    body_json(response).await
}

/// El `error` estable que viaja al cliente, sea cual sea la envoltura del endpoint.
fn error_code(body: &Value) -> String {
    body.get("error")
        .and_then(|e| e.get("code").or(Some(e)))
        .and_then(|c| c.as_str())
        .unwrap_or_default()
        .to_string()
}

/// 🔴 Con un registro ya emitido, un NIF **distinto** se rechaza con `409` y código propio — y no
/// se escribe: la lectura sigue devolviendo el NIF con el que la cadena está anclada.
#[tokio::test]
async fn a_hub_that_already_emitted_refuses_a_new_tax_id_over_http() {
    let (router, admin) = fixture("frozen", true).await;

    let response = put(&router, &admin, json!({ "business_tax_id": "B99999999" })).await;

    assert_eq!(response.status(), StatusCode::CONFLICT);
    let body = body_json(response).await;
    assert_eq!(
        error_code(&body),
        "business_tax_id_frozen",
        "la UI tiene que poder decir POR QUÉ se negó, no un 409 mudo: {body}"
    );

    let settings = get(&router, &admin).await;
    assert_eq!(
        settings["business_tax_id"],
        json!("B12345678"),
        "el ancla de la cadena emitida no se movió: {settings}"
    );
}

/// 🔴 La mitad que no puede romperse: un hub que **aún no ha emitido** escribe su NIF como
/// siempre. Sin este test, cerrar «por si acaso» dejaría a un negocio recién dado de alta sin poder
/// configurar el NIF con el que va a facturar, y sin más síntoma que un 409.
#[tokio::test]
async fn a_hub_that_has_not_emitted_writes_its_tax_id_over_http_as_always() {
    let (router, admin) = fixture("editable", false).await;

    let response = put(&router, &admin, json!({ "business_tax_id": "B99999999" })).await;

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        body_json(response).await["business_tax_id"],
        json!("B99999999")
    );
}

/// 🔴 La otra mitad: **el formulario de Negocio sigue funcionando**. Ajustes → Negocio manda el
/// NIF, la razón social y la dirección en un ÚNICO `PUT` (`saveTaxSettings`), así que si reenviar
/// el mismo NIF contara como cambio, un hub que ya emitió no podría volver a corregir su dirección.
#[tokio::test]
async fn the_business_form_still_saves_with_the_tax_id_unchanged() {
    let (router, admin) = fixture("form", true).await;

    let response = put(
        &router,
        &admin,
        json!({
            "business_tax_id": "B12345678",
            "business_legal_name": "Bar Manolo SLU",
            "business_address": "Calle Nueva 1",
        }),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["business_legal_name"], json!("Bar Manolo SLU"));
    assert_eq!(body["business_address"], json!("Calle Nueva 1"));
}

/// El congelado y el cierre de la DEMO son **dos guardas distintas** sobre la misma clave, con dos
/// respuestas distintas. Si contestaran lo mismo, borrar una pasaría inadvertido — y significan
/// cosas opuestas: «este hub no es de nadie» vs «este hub ya emitió y no puede cambiar de dueño».
#[tokio::test]
async fn the_freeze_is_not_the_demo_lock() {
    let (router, admin) = fixture("codes", true).await;
    let code = error_code(
        &body_json(put(&router, &admin, json!({ "business_tax_id": "B1" })).await).await,
    );

    assert_eq!(code, "business_tax_id_frozen");
    assert_ne!(code, "demo_fiscal_identity_locked");
}
