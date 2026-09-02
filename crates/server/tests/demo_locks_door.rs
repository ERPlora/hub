//! **Qué NO puede cambiar un hub de DEMO efímera**, por las puertas HTTP reales (ADR-0197 §4 —
//! ERPlora/hub#376).
//!
//! La demo es un hub DE VERDAD que se le entrega a un desconocido durante una hora, sin registro y
//! sin tarjeta. Lo único que no puede hacer es actuar como el negocio de alguien: `PUT
//! /api/settings` y `PUT /api/business/certificate` son las dos puertas por las que un admin
//! configura precisamente eso, y en la demo el que está al otro lado es `admin` (ADR-0197 §4: los
//! cierres son del HUB, no del rol — abrir `is_admin_role` habría dado ajustes, usuarios, API keys
//! y módulos a cada `manager` de **cada hub real**).
//!
//! Lo que fija este fichero, y que los tests del runtime no pueden fijar:
//!
//!  - el **código de estado y el código estable** que ve el cliente (`409` + el sujeto del cierre),
//!    porque es contra eso contra lo que la UI se explica;
//!  - que los **tres cierres se distinguen** entre sí: si los tres contestaran lo mismo, dos se
//!    podrían borrar con la suite en verde;
//!  - que la bandera **no la pone el que llama**: ni cabecera, ni cuerpo, ni sesión. La escribe el
//!    despliegue (`HUB_DEMO`) y el `AppState` la sella al construirse.
//!
//! Y la mitad que no puede romperse: **un hub REAL configura su identidad fiscal como siempre**.
//! Un cierre que se escapase a un hub de pago le impediría facturar, y en silencio.
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

/// 🔴 Identidad fiscal: **de solo lectura** en una demo, por la puerta que la escribe.
#[tokio::test]
async fn a_demo_refuses_to_write_the_fiscal_identity_over_http() {
    let (router, admin) = fixture(true, "identity").await;

    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({ "business_tax_id": "B12345674", "business_legal_name": "Bar Manolo SL" }),
    )
    .await;

    assert_eq!(response.status(), StatusCode::CONFLICT);
    let body = body_json(response).await;
    assert_eq!(
        error_code(&body),
        "demo_fiscal_identity_locked",
        "el cliente tiene que poder distinguir CUÁL de los tres cierres se negó: {body}"
    );

    // Y no se escribió: la demo conserva la identidad con la que ARRANCÓ (hub#684). Antes aquí se
    // afirmaba que seguía vacía; ahora la demo nace con la suya puesta y lo que este test fija es
    // que el 409 no la mueve — el cierre sigue siendo un cierre, no un hueco.
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
    assert_eq!(
        settings["business_tax_id"],
        json!(erplora_runtime::settings::DEMO_BUSINESS_TAX_ID)
    );
    assert_eq!(
        settings["business_legal_name"],
        json!(erplora_runtime::settings::DEMO_BUSINESS_LEGAL_NAME)
    );
}

/// 🔴 **Las DOS mitades de hub#684, en la misma prueba.** La demo arranca con identidad fiscal —así
/// la checklist no le pide al visitante lo único que el producto le prohíbe, y su venta llega a
/// emitir documento— **y los tres cierres siguen puestos**. Si un día alguien "arregla" la demo
/// abriendo el cierre en vez de sembrar el dato, este test se cae.
#[tokio::test]
async fn the_demo_boots_with_an_identity_and_still_refuses_to_let_anyone_change_it() {
    let (router, admin) = fixture(true, "seeded").await;

    // (a) La identidad está puesta: es lo que lee el gate fiscal de ADR-0203 y lo que la checklist
    //     marca como hecho. Sin ella, `invoice.create_from_sale` moría en el outbox.
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
    assert!(
        !settings["business_tax_id"]
            .as_str()
            .unwrap_or_default()
            .is_empty(),
        "una demo arranca con NIF: {settings}"
    );
    assert!(
        !settings["business_legal_name"]
            .as_str()
            .unwrap_or_default()
            .is_empty(),
        "…y con razón social: {settings}"
    );

    // (b) …y sigue siendo de solo lectura. Sembrar el dato NO es abrir la puerta.
    let response = put(
        &router,
        "/api/settings",
        &admin,
        json!({ "business_tax_id": "B12345674" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert_eq!(
        error_code(&body_json(response).await),
        "demo_fiscal_identity_locked"
    );

    // (c) …y el certificado propio sigue cerrado. Es uno de los dos cierres que de verdad impiden
    //     que una venta de la demo llegue a la AEAT real, y no se ha tocado.
    let response = put(
        &router,
        "/api/business/certificate",
        &admin,
        json!({ "pkcs12_b64": "Zm9v", "password": "x" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert_eq!(
        error_code(&body_json(response).await),
        "demo_business_certificate_locked"
    );
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

/// 🔴 Certificado del negocio: ni se sube ni se reemplaza en una demo.
#[tokio::test]
async fn a_demo_refuses_to_take_a_business_certificate_over_http() {
    let (router, admin) = fixture(true, "cert").await;

    let response = put(
        &router,
        "/api/business/certificate",
        &admin,
        json!({ "pkcs12_b64": "Zm9v", "password": "s3cret" }),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CONFLICT);
    let body = body_json(response).await;
    assert_eq!(
        error_code(&body),
        "demo_business_certificate_locked",
        "{body}"
    );

    // Borrar tampoco: si no, reemplazar sería borrar y volver a subir.
    let response = delete(&router, "/api/business/certificate", &admin).await;
    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert_eq!(
        error_code(&body_json(response).await),
        "demo_business_certificate_locked"
    );
}

/// Los tres cierres tienen **códigos distintos**. Es lo que impide que borrar uno pase inadvertido
/// porque otro contesta lo mismo — y lo que le permite a la UI decir qué pasa en vez de «409».
#[tokio::test]
async fn the_three_locks_answer_with_three_different_codes() {
    let (router, admin) = fixture(true, "codes").await;

    let identity = error_code(
        &body_json(
            put(
                &router,
                "/api/settings",
                &admin,
                json!({ "business_tax_id": "B1" }),
            )
            .await,
        )
        .await,
    );
    let certificate = error_code(
        &body_json(
            put(
                &router,
                "/api/business/certificate",
                &admin,
                json!({ "pkcs12_b64": "Zm9v", "password": "x" }),
            )
            .await,
        )
        .await,
    );

    assert_ne!(identity, certificate, "dos cierres, dos respuestas");
    assert_eq!(identity, "demo_fiscal_identity_locked");
    assert_eq!(certificate, "demo_business_certificate_locked");
    // El tercero (entorno fiscal) vive en el dispatcher y se prueba en `commands.rs`; su código
    // completa el trío y aquí solo se afirma que no colisiona con estos dos.
    for taken in [identity.as_str(), certificate.as_str()] {
        assert_ne!(taken, "demo_fiscal_environment_locked");
    }
}

/// La demo **sigue siendo un hub**: todo lo que no es identidad fiscal se configura igual. El
/// cierre no es un modo de solo lectura — si lo fuera, el visitante no podría ni cambiar el idioma.
#[tokio::test]
async fn a_demo_configures_everything_that_is_not_the_fiscal_identity() {
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
