//! **La puerta por la que la galería ve las automatizaciones de fábrica** (hub#1611) —
//! `GET /api/hub/flows/templates`.
//!
//! Un módulo publica sus plantillas en su carpeta `flows/` y desde `module-toolkit#209` viajan
//! dentro del zip; el runtime ya las registra al instalar. Esto es lo que las saca del proceso: sin
//! esta ruta, la única forma de que la plantilla de WhatsApp llegue a un cliente es **copiarla a
//! mano** en la galería del módulo `flows`, y esa copia se quedó atrás tres veces en un solo día.
//!
//! Lo que este fichero clava, en la capa donde viven las puertas de verdad:
//!
//! 1. **La misma puerta que el resto de `/api/hub/flows*`**: sesión de un humano owner/admin.
//!    Anónimo `401`, cajero `403`, API key rechazada. No es cosmética: administrar automatizaciones
//!    ES conseguir el resto de primitivas del hub sin nadie delante (ADR-0283 §9), y una plantilla
//!    dice qué commands va a pedir.
//! 2. **Y `manage_flows` encima** cuando quien llama nombra un módulo (hub#714) — desde hub#1677
//!    como ALCANCE, no como puerta: quien no la tiene recibe **lo suyo y nada más** en vez de un
//!    `403`. Lo que el segundo gate protegía sigue protegido (ningún módulo lee qué automatiza el
//!    negocio) y además la pantalla de un módulo puede saber si su propia receta está puesta, que
//!    es lo que pide ADR-0470 §5.
//! 3. **El módulo de origen viaja con cada plantilla**, porque la galería tiene que decir de dónde
//!    sale lo que ofrece, y porque el suelo de versión se juzga contra los módulos instalados.
//! 4. **Los grants se ENSEÑAN, no se conceden.** Lo que la ruta devuelve es lo que la plantilla va
//!    a pedirle al dueño; una plantilla nace apagada y sin permisos, como cualquier otra (§9.3).
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tower::ServiceExt;

const HUB: &str = "hub-flow-templates-route";
const MODULE_HEADER: &str = "x-erplora-module";
/// El módulo que el dueño instaló para editar automatizaciones: DECLARA `manage_flows`.
const EDITOR: &str = "flows";
/// Un módulo corriente que además trae una automatización de fábrica.
const WHATSAPP: &str = "whatsapp_inbox";
/// El vecino que el suelo de esa plantilla nombra (`requires.json`), y que NO es el `depends_on`
/// del módulo: la plantilla es opcional y `whatsapp_inbox` funciona sin él.
const REQUIRED: &str = "appointments";
const TEMPLATES: &str = "/api/hub/flows/templates";

struct Fixture {
    router: axum::Router,
    admin: String,
    employee: String,
    api_key: String,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// Escribe un módulo en disco. Si `with_templates`, le pone una familia completa en `flows/`.
fn module_dir(root: &Path, id: &str, extra: Value, with_templates: bool) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
    let mut manifest = json!({ "id": id, "name": id, "version": "2.1.31" });
    if let Value::Object(map) = extra {
        for (k, v) in map {
            manifest[k] = v;
        }
    }
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    if with_templates {
        std::fs::create_dir_all(dir.join("flows")).unwrap();
        for (lang, name) in [
            ("en", "Book from WhatsApp"),
            ("es", "Reservar por WhatsApp"),
        ] {
            let doc = json!({
                "schema_version": 1,
                "name": name,
                "triggers": [{ "kind": "manual" }],
                "steps": [{ "id": "s1", "kind": "command", "command": "appointments.appointments.create" }]
            });
            std::fs::write(
                dir.join(format!("flows/appointment-from-whatsapp.{lang}.flow.json")),
                serde_json::to_string(&doc).unwrap(),
            )
            .unwrap();
        }
        // Dos permisos a propósito: uno ancho y uno ACOTADO (hub#1654). El acotado es el caso real
        // de `whatsapp_inbox`: anular una cita **como clienta**, nunca de parte del salón.
        std::fs::write(
            dir.join("flows/appointment-from-whatsapp.grants.json"),
            r#"{"grants":[{"kind":"command","value":"appointments.appointments.create"},{"kind":"command","value":"appointments.appointments.cancel","payload":{"channel":"customer"}}]}"#,
        )
        .unwrap();
        std::fs::write(
            dir.join("flows/appointment-from-whatsapp.requires.json"),
            r#"{"modules":{"appointments":"1.1.69"}}"#,
        )
        .unwrap();
    }
    dir
}

/// `granted` = el dueño marcó `manage_flows` para el editor en Ajustes → Permisos.
async fn fixture(granted: bool) -> Fixture {
    fixture_with(granted, true).await
}

/// `appointments_installed` = está el vecino que el suelo de la plantilla nombra
/// (`requires.json` pide `appointments >= 1.1.69`). Con `false`, el suelo NO se cumple y la
/// plantilla no debe ofrecerse, que es la otra mitad del contrato de la carpeta.
async fn fixture_with(granted: bool, appointments_installed: bool) -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();

    let admin_id = rt.create_user("Ioan", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Marta", "2222", "cashier", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let api_key = rt.ensure_app_api_key().await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-flow-templates-route-{}-{admin_id}",
        std::process::id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&module_dir(
        &modules,
        EDITOR,
        json!({ "capabilities": { "manage_flows": {} } }),
        false,
    ))
    .await
    .unwrap();
    if appointments_installed {
        // Justo EN el suelo (`1.1.69`), no por encima: así este fixture también fija que la
        // comparación es `>=` y no `>`.
        rt.install_from_dir(&module_dir(
            &modules,
            REQUIRED,
            json!({ "version": "1.1.69" }),
            false,
        ))
        .await
        .unwrap();
    }
    rt.install_from_dir(&module_dir(&modules, WHATSAPP, json!({}), true))
        .await
        .unwrap();
    if granted {
        rt.set_module_capability(EDITOR, "manage_flows", true, "hub_user:admin")
            .await
            .unwrap();
    }

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
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        admin,
        employee,
        api_key,
    }
}

fn request(uri: &str, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("GET").uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if let Some(id) = module {
        builder = builder.header(MODULE_HEADER, id);
    }
    builder.body(Body::empty()).unwrap()
}

async fn send(router: &axum::Router, request: Request<Body>) -> axum::response::Response {
    router.clone().oneshot(request).await.unwrap()
}

#[tokio::test]
async fn the_gallery_gets_the_template_its_module_ships() {
    let fx = fixture(true).await;

    let response = send(
        &fx.router,
        request(TEMPLATES, Some(&fx.admin), Some(EDITOR)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert!(
        body["discarded"]
            .as_array()
            .expect("la lista de descartes viaja siempre")
            .is_empty(),
        "control positivo (hub#1649): con todo en su sitio no se descarta nada"
    );
    let items = body["data"].as_array().expect("una lista de plantillas");
    assert_eq!(items.len(), 1, "la familia de `whatsapp_inbox`");
    let tpl = &items[0];
    assert_eq!(
        tpl["module"], WHATSAPP,
        "la galería dice de qué módulo sale lo que ofrece"
    );
    assert_eq!(tpl["family"], "appointment-from-whatsapp");
    // El documento viaja por idioma: el hub sirve los dos y la galería elige, porque
    // `erplora validate` ya garantizó que son la misma automatización con otras palabras.
    assert!(tpl["documents"]["es"].is_object() && tpl["documents"]["en"].is_object());
    assert_eq!(tpl["documents"]["es"]["name"], "Reservar por WhatsApp");
    // Los permisos se ENSEÑAN para que el dueño los autorice, nunca se conceden aquí.
    assert_eq!(tpl["grants"][0]["kind"], "command");
    assert_eq!(
        tpl["grants"][0]["value"],
        "appointments.appointments.create"
    );
    // El suelo de versión es por plantilla, no el `depends_on` del módulo.
    assert_eq!(tpl["requires"]["appointments"], "1.1.69");
}

#[tokio::test]
async fn the_limit_the_module_put_on_a_permission_reaches_the_gallery() {
    // hub#1654 — la pantalla de permisos pide lo que esta ruta le sirve, así que un pin que se
    // pierda aquí es un permiso ANCHO concedido por un dueño que creyó estar acotándolo. El pin
    // que el módulo escribió en su `<family>.grants.json` tiene que salir por el cable ENTERO:
    // es lo que después exige `check_payload_pin` en el dispatcher (hub#1623).
    let fx = fixture(true).await;

    let response = send(
        &fx.router,
        request(TEMPLATES, Some(&fx.admin), Some(EDITOR)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let grants = body["data"][0]["grants"]
        .as_array()
        .expect("los permisos que la plantilla pedirá");
    let pinned = grants
        .iter()
        .find(|g| g["value"] == "appointments.appointments.cancel")
        .expect("el permiso acotado se ofrece");
    assert_eq!(
        pinned["payload"],
        json!({ "channel": "customer" }),
        "«puede anular citas COMO CLIENTA» no puede llegar como «puede anular citas»"
    );
    // Y el que no acota nada sigue viajando como antes de hub#1623: sin `payload`, no con uno vacío.
    let wide = grants
        .iter()
        .find(|g| g["value"] == "appointments.appointments.create")
        .expect("el permiso ancho se ofrece igual");
    assert!(
        wide.get("payload").is_none(),
        "un grant que no fija nada no estrena una clave que nadie escribió"
    );
}

#[tokio::test]
async fn without_the_capability_the_module_reads_none_of_the_business_automations() {
    // hub#1677 enmienda el SEGUNDO gate de hub#714: `manage_flows` deja de ser PUERTA y pasa a ser
    // ALCANCE. Lo que protegía sigue protegido y por eso este test sigue aquí: sin la capability,
    // un módulo NO lee qué automatiza el negocio. Lo que cambia es cómo se le dice — antes un
    // `403`, ahora lo suyo y nada más, que para `flows` sin permiso conceder es NADA.
    //
    // Y es el positivo del filtro: `whatsapp_inbox` SÍ trae una familia en este fixture, así que
    // servirle la lista entera a quien no tiene la capability se vería aquí como un `1`.
    let fx = fixture(false).await;

    let response = send(
        &fx.router,
        request(TEMPLATES, Some(&fx.admin), Some(EDITOR)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert!(
        body["data"]
            .as_array()
            .expect("una lista de plantillas")
            .is_empty(),
        "sin `manage_flows` concedida, la receta del vecino no es asunto suyo"
    );
    assert!(
        body["discarded"]
            .as_array()
            .expect("la lista de descartes viaja siempre")
            .is_empty(),
        "y tampoco por la puerta de atrás: los descartes del vecino también son del vecino"
    );
}

#[tokio::test]
async fn a_module_that_never_declared_the_capability_still_reads_its_own() {
    // `whatsapp_inbox` no declara `manage_flows` a propósito, y aun así su pantalla (wi#123) tiene
    // que saber si su receta ya está puesta: es el `installed` de ADR-0470 §5, que le sería inútil
    // justo a quien lo necesita si esta ruta le contestara `capability_denied`.
    //
    // Leer LO SUYO es mucho más estrecho que administrar automatizaciones; lo de los demás sigue
    // sin ser suyo, y eso lo clava el test de arriba.
    let fx = fixture(true).await;

    let response = send(
        &fx.router,
        request(TEMPLATES, Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let items = body["data"].as_array().expect("una lista de plantillas");
    assert_eq!(items.len(), 1, "su familia, la única que publica");
    assert_eq!(items[0]["module"], WHATSAPP);
    assert_eq!(items[0]["family"], "appointment-from-whatsapp");
    assert!(
        items[0]["installed"].is_null(),
        "nadie la ha encendido todavía, y eso es justo lo que la pantalla necesita leer"
    );
}

#[tokio::test]
async fn anonymous_and_cashier_and_api_key_never_get_in() {
    let fx = fixture(true).await;

    let anon = send(&fx.router, request(TEMPLATES, None, None)).await;
    assert_eq!(anon.status(), StatusCode::UNAUTHORIZED, "sin sesión, 401");

    let cashier = send(&fx.router, request(TEMPLATES, Some(&fx.employee), None)).await;
    assert_eq!(
        cashier.status(),
        StatusCode::FORBIDDEN,
        "un cajero no administra automatizaciones"
    );

    // Una credencial de integración almacenada y copiable no puede leer esta puerta: es la misma
    // regla que protege `PUT …/grants` (ADR-0283 §9).
    let with_key = Request::builder()
        .method("GET")
        .uri(TEMPLATES)
        .header("x-api-key", &fx.api_key)
        .body(Body::empty())
        .unwrap();
    let keyed = send(&fx.router, with_key).await;
    assert_ne!(keyed.status(), StatusCode::OK, "una API key no entra");
}

#[tokio::test]
async fn the_shell_reads_it_with_the_session_alone() {
    // Sin cabecera de módulo la capability no aplica: es el propio shell del hub, que ya tiene la
    // sesión de un admin. Misma regla que la dead-letter (§9.2.2).
    let fx = fixture(false).await;

    let response = send(&fx.router, request(TEMPLATES, Some(&fx.admin), None)).await;

    assert_eq!(response.status(), StatusCode::OK);
}

#[tokio::test]
async fn the_gallery_is_not_offered_a_template_whose_floor_is_not_met() {
    // La otra mitad del contrato de `requires.json`, fijada EN LA PUERTA: el filtro vive en el
    // registro, y esto es lo que impide que alguien vuelva a servir el mapa en crudo más adelante.
    // Mismo hub que el test de arriba, sin `appointments` instalado.
    let fx = fixture_with(true, false).await;

    let response = send(
        &fx.router,
        request(TEMPLATES, Some(&fx.admin), Some(EDITOR)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK, "la ruta responde igual");
    let body = body_json(response).await;
    assert!(
        body["data"].as_array().expect("una lista").is_empty(),
        "sin el módulo que pide el suelo, su plantilla no se ofrece"
    );
    // hub#1649: y la puerta DICE por qué. Una galería que solo enumera lo que hay deja «el módulo
    // no trae ninguna» y «la trae y el hub la ha descartado» exactamente iguales en pantalla.
    let discarded = body["discarded"].as_array().expect("una lista de descartes");
    assert_eq!(discarded.len(), 1, "el descarte se cuenta: {discarded:?}");
    assert_eq!(discarded[0]["module"], "whatsapp_inbox");
    assert_eq!(discarded[0]["family"], "appointment-from-whatsapp");
    assert_eq!(discarded[0]["code"], "template_floor_module_missing");
    assert!(
        discarded[0]["detail"]
            .as_str()
            .is_some_and(|d| d.contains("appointments")),
        "el motivo nombra al vecino que falta: {:?}",
        discarded[0]["detail"]
    );
}
