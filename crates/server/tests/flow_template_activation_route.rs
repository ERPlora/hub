//! **La puerta de un toque** (hub#1677, ADR-0470) —
//! `POST /api/hub/flows/templates/{module}/{family}/activate|deactivate`.
//!
//! Para dejar funcionando la receta de fábrica que su propio módulo publica, el dueño tenía que
//! salir de la pantalla del módulo, entrar en Automatizaciones, buscar la tarjeta entre otras
//! parecidas, «usarla», abrir la pestaña Permisos, autorizar catorce permisos en crudo y encender
//! el interruptor: nueve pantallas y unos quince toques. Estas dos rutas son lo que lo convierte en
//! un toque, y lo que hace posible la pantalla de tres pasos de whatsapp_inbox#123.
//!
//! Lo que este fichero clava, en la capa donde viven las puertas de verdad:
//!
//! 1. **La misma puerta humana que el resto de `/api/hub/flows*`**: sesión de owner/admin. Anónimo
//!    `401`, cajero `403`. Encender una automatización ES conseguir las primitivas del hub sin
//!    nadie delante (ADR-0283 §9), y eso no lo abre una ruta nueva.
//! 2. **Y NINGUNA capability nueva** (ADR-0470 §1). Quien llama no compone flujos ni permisos:
//!    elige cuál de SUS recetas —ya validadas por la puerta del toolkit y servidas del registro—
//!    se enciende. Lo que sí se exige es que sea SUYA: si la petición nombra un módulo, tiene que
//!    ser el de la ruta (`403 flow.template_not_yours`), y no se escribe nada.
//! 3. **Los grants que quedan son EXACTAMENTE los del sidecar, pines incluidos.** Es lo que separa
//!    «puede anular citas» de «puede anular citas COMO CLIENTA»: un pin perdido aquí es un permiso
//!    ancho concedido por un dueño que creyó estar acotándolo, y sin un solo error en pantalla.
//! 4. **Encender dos veces no duplica nada** y **apagar conserva los permisos**: es una pausa, no
//!    un borrado — el historial de lo que esa automatización hizo tiene que seguir teniendo dueño.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tower::ServiceExt;

const HUB: &str = "hub-flow-template-activation";
const MODULE_HEADER: &str = "x-erplora-module";
/// El módulo que publica la receta y que la enciende desde su propia pantalla.
const WHATSAPP: &str = "whatsapp_inbox";
/// El vecino cuyo command usa la receta, y al que apunta su suelo de versión.
const APPOINTMENTS: &str = "appointments";
/// Un tercer módulo instalado que NO es dueño de la receta.
const INTRUDER: &str = "inventory";
const FAMILY: &str = "appointment-from-whatsapp";
const TEMPLATES: &str = "/api/hub/flows/templates";
const CREATE: &str = "appointments.appointments.create";
const CANCEL: &str = "appointments.appointments.cancel";

struct Fixture {
    router: axum::Router,
    admin: String,
    employee: String,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// El módulo que trae los commands que la receta nombra. Sin él, la receta nombraría un command
/// que el kernel no puede ejecutar y `store::create` la rechazaría antes de escribir nada — que es
/// otra guarda, y no la de este fichero.
fn appointments_dir(root: &Path, version: &str) -> PathBuf {
    let dir = root.join(APPOINTMENTS);
    std::fs::create_dir_all(dir.join("sql")).unwrap();
    std::fs::create_dir_all(dir.join("migrations/postgres")).unwrap();
    std::fs::write(
        dir.join("migrations/postgres/001_init.sql"),
        "CREATE TABLE IF NOT EXISTS appointments_booking (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
         channel TEXT NOT NULL DEFAULT '');",
    )
    .unwrap();
    std::fs::write(
        dir.join("sql/book.sql"),
        "INSERT INTO appointments_booking (id, hub_id, channel) \
         VALUES (:new_id, :hub_id, COALESCE(:channel, ''));",
    )
    .unwrap();
    std::fs::write(
        dir.join("sql/cancel.sql"),
        "UPDATE appointments_booking SET channel = COALESCE(:channel, '') WHERE hub_id = :hub_id;",
    )
    .unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&json!({
            "id": APPOINTMENTS,
            "name": "Appointments",
            "version": version,
            "permissions": ["appointments.manage"],
            "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
            "commands": {
                CREATE: { "permission": "appointments.manage", "sql": ["sql/book.sql"] },
                CANCEL: { "permission": "appointments.manage", "sql": ["sql/cancel.sql"] },
            }
        }))
        .unwrap(),
    )
    .unwrap();
    dir
}

/// El módulo que PUBLICA la receta de fábrica, con su familia completa en `flows/`.
fn whatsapp_dir(root: &Path, floor: &str) -> PathBuf {
    let dir = root.join(WHATSAPP);
    std::fs::create_dir_all(dir.join("flows")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&json!({
            "id": WHATSAPP, "name": "WhatsApp Inbox", "version": "2.1.50"
        }))
        .unwrap(),
    )
    .unwrap();
    for (lang, name) in [
        ("en", "Book from WhatsApp"),
        ("es", "Reservar por WhatsApp"),
    ] {
        let doc = json!({
            "schema_version": 1,
            "name": name,
            "triggers": [{ "kind": "manual" }],
            "steps": [{ "id": "s1", "kind": "command", "command": CREATE }]
        });
        std::fs::write(
            dir.join(format!("flows/{FAMILY}.{lang}.flow.json")),
            serde_json::to_string(&doc).unwrap(),
        )
        .unwrap();
    }
    // Dos permisos a propósito: uno ancho y uno ACOTADO (hub#1623/#1654). El acotado es el caso
    // real: anular una cita **como clienta**, nunca de parte del salón.
    std::fs::write(
        dir.join(format!("flows/{FAMILY}.grants.json")),
        json!({ "grants": [
            { "kind": "command", "value": CREATE },
            { "kind": "command", "value": CANCEL, "payload": { "channel": "customer" } },
        ]})
        .to_string(),
    )
    .unwrap();
    std::fs::write(
        dir.join(format!("flows/{FAMILY}.requires.json")),
        json!({ "modules": { APPOINTMENTS: floor } }).to_string(),
    )
    .unwrap();
    dir
}

fn plain_dir(root: &Path, id: &str) -> PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&json!({ "id": id, "name": id, "version": "1.0.0" })).unwrap(),
    )
    .unwrap();
    dir
}

async fn fixture() -> Fixture {
    fixture_with("1.1.69").await
}

/// `floor` = lo que la receta exige de `appointments`, que se instala en `1.1.69`. Un suelo por
/// encima es el caso «descartada por suelo» (hub#1649), donde la receta NO se ofrece y encenderla
/// tiene que negarse con el motivo del descarte.
async fn fixture_with(floor: &str) -> Fixture {
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

    let temp = std::env::temp_dir().join(format!(
        "erplora-flow-template-activation-{}-{admin_id}",
        std::process::id()
    ));
    let modules = temp.join("modules");
    rt.install_from_dir(&appointments_dir(&modules, "1.1.69"))
        .await
        .unwrap();
    rt.install_from_dir(&plain_dir(&modules, INTRUDER))
        .await
        .unwrap();
    rt.install_from_dir(&whatsapp_dir(&modules, floor))
        .await
        .unwrap();

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
    }
}

fn activate_uri(module: &str, family: &str) -> String {
    format!("{TEMPLATES}/{module}/{family}/activate")
}

fn deactivate_uri(module: &str, family: &str) -> String {
    format!("{TEMPLATES}/{module}/{family}/deactivate")
}

fn post(uri: &str, session: Option<&str>, module: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("POST").uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if let Some(id) = module {
        builder = builder.header(MODULE_HEADER, id);
    }
    builder.body(Body::empty()).unwrap()
}

fn get(uri: &str, session: &str, module: Option<&str>) -> Request<Body> {
    let mut builder = Request::builder().method("GET").uri(uri);
    builder = builder.header("x-hub-session", session);
    if let Some(id) = module {
        builder = builder.header(MODULE_HEADER, id);
    }
    builder.body(Body::empty()).unwrap()
}

async fn send(router: &axum::Router, request: Request<Body>) -> axum::response::Response {
    router.clone().oneshot(request).await.unwrap()
}

/// Los flujos que hay en el hub ahora mismo, por la puerta pública.
async fn flows(fx: &Fixture) -> Vec<Value> {
    let response = send(&fx.router, get("/api/hub/flows", &fx.admin, None)).await;
    assert_eq!(response.status(), StatusCode::OK);
    body_json(response).await["data"]
        .as_array()
        .expect("una lista de flujos")
        .clone()
}

async fn grants_of(fx: &Fixture, flow_id: &str) -> Vec<Value> {
    let uri = format!("/api/hub/flows/{flow_id}/grants");
    let response = send(&fx.router, get(&uri, &fx.admin, None)).await;
    assert_eq!(response.status(), StatusCode::OK);
    body_json(response).await["data"]
        .as_array()
        .expect("una lista de permisos")
        .clone()
}

#[tokio::test]
async fn activating_a_factory_template_leaves_it_running() {
    let fx = fixture().await;
    assert!(
        flows(&fx).await.is_empty(),
        "control negativo: el hub arranca sin ninguna automatización"
    );

    let response = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;

    assert_eq!(
        response.status(),
        StatusCode::CREATED,
        "encender una receta que aún no estaba montada la CREA"
    );
    let flow = body_json(response).await["data"].clone();
    assert_eq!(
        flow["enabled"], true,
        "nace ENCENDIDA: ese es el cambio de ADR-0470 sobre «se crea en pausa»"
    );
    assert_eq!(
        flow["template_ref"],
        format!("{WHATSAPP}/{FAMILY}"),
        "y queda marcada con la receta de la que sale, que es cómo se la reconoce después"
    );
    assert_eq!(
        flows(&fx).await.len(),
        1,
        "y está en el hub, no solo en la respuesta"
    );
}

#[tokio::test]
async fn a_module_cannot_activate_a_template_that_is_not_its_own() {
    let fx = fixture().await;

    let response = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(INTRUDER)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "flow.template_not_yours",
        "el código es lo que lee la pantalla; la prosa no se compara nunca (ADR-0055)"
    );
    assert!(
        flows(&fx).await.is_empty(),
        "y NADA se escribió: una negativa que deja el flujo montado es peor que no negar"
    );
}

#[tokio::test]
async fn the_shell_names_no_module_and_still_gets_through() {
    // El shell del hub no es un módulo y no nombra ninguno (`calling_module` -> None). Sin este
    // caso, la guarda de propiedad se podría escribir como «exige la cabecera», que cerraría la
    // puerta a la única superficie que hoy la usa sin cabecera.
    let fx = fixture().await;

    let response = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), None),
    )
    .await;

    assert_eq!(response.status(), StatusCode::CREATED);
}

#[tokio::test]
async fn the_limit_the_module_put_on_a_permission_survives_the_activation() {
    // hub#1623/#1654 en el camino nuevo: el sidecar acota `cancel` a `channel: "customer"`, y lo
    // que acaba en `_flow_grants` es lo que `check_command_grant` exige después. Un pin que se
    // pierde AQUÍ es un permiso ancho que el dueño creyó estar acotando.
    let fx = fixture().await;

    let response = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    let flow_id = body_json(response).await["data"]["id"]
        .as_str()
        .expect("el flujo montado")
        .to_string();

    let grants = grants_of(&fx, &flow_id).await;
    assert_eq!(grants.len(), 2, "exactamente los dos del sidecar, ni uno más");
    let cancel = grants
        .iter()
        .find(|g| g["value"] == CANCEL)
        .expect("el permiso acotado");
    assert_eq!(
        cancel["payload"]["channel"], "customer",
        "el pin viaja: «puede anular» y «puede anular COMO CLIENTA» son permisos distintos"
    );
}

#[tokio::test]
async fn activating_twice_neither_duplicates_the_flow_nor_its_permissions() {
    let fx = fixture().await;

    let first = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;
    assert_eq!(first.status(), StatusCode::CREATED);
    let first_id = body_json(first).await["data"]["id"].as_str().unwrap().to_string();

    let second = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;
    assert_eq!(
        second.status(),
        StatusCode::OK,
        "la segunda vez REUTILIZA: `200`, no `201`"
    );
    let second_id = body_json(second).await["data"]["id"].as_str().unwrap().to_string();

    assert_eq!(first_id, second_id, "el mismo flujo, no uno nuevo");
    assert_eq!(flows(&fx).await.len(), 1, "y sigue habiendo UNO en el hub");
    assert_eq!(
        grants_of(&fx, &first_id).await.len(),
        2,
        "los permisos se REEMPLAZAN, no se acumulan"
    );
}

#[tokio::test]
async fn deactivating_pauses_it_and_keeps_the_permissions() {
    let fx = fixture().await;
    let activated = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;
    let flow_id = body_json(activated).await["data"]["id"].as_str().unwrap().to_string();

    let response = send(
        &fx.router,
        post(&deactivate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(body_json(response).await["data"]["enabled"], false);
    assert_eq!(
        grants_of(&fx, &flow_id).await.len(),
        2,
        "apagar es una PAUSA: los permisos siguen, y con ellos el dueño del historial"
    );

    let again = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;
    assert_eq!(again.status(), StatusCode::OK);
    let body = body_json(again).await;
    assert_eq!(body["data"]["id"], flow_id, "vuelve a encender el MISMO flujo");
    assert_eq!(body["data"]["enabled"], true);
}

#[tokio::test]
async fn deactivating_a_family_that_was_never_activated_is_a_not_found() {
    let fx = fixture().await;

    let response = send(
        &fx.router,
        post(&deactivate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert_eq!(body_json(response).await["error"]["code"], "flow.not_found");
}

#[tokio::test]
async fn a_template_this_hub_discarded_refuses_with_the_reason_it_discarded_it() {
    // hub#1649: la receta pide un vecino más nuevo del que hay, así que este hub NO la ofrece.
    // Encenderla no puede «funcionar igual»: el flujo nombraría un command que quizá no existe.
    // Y el motivo viaja para que el módulo pinte la frase en cristiano en vez de un fallo mudo.
    let fx = fixture_with("9.9.9").await;

    let response = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "template_floor_module_too_old",
        "el código del descarte, el mismo que ya sirve el listado"
    );
    assert!(
        flows(&fx).await.is_empty(),
        "y no se montó nada a medias"
    );
}

#[tokio::test]
async fn a_family_no_module_ships_is_a_not_found() {
    let fx = fixture().await;

    let response = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, "there-is-no-such-family"), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "flow.template_not_found"
    );
}

#[tokio::test]
async fn without_a_human_admin_session_the_door_is_shut() {
    let fx = fixture().await;

    for (session, expected) in [
        (None, StatusCode::UNAUTHORIZED),
        (Some(fx.employee.clone()), StatusCode::FORBIDDEN),
    ] {
        for uri in [activate_uri(WHATSAPP, FAMILY), deactivate_uri(WHATSAPP, FAMILY)] {
            let response = send(&fx.router, post(&uri, session.as_deref(), Some(WHATSAPP))).await;
            assert_eq!(
                response.status(),
                expected,
                "{uri}: encender una automatización es la misma puerta que escribirla"
            );
        }
    }
    assert!(
        flows(&fx).await.is_empty(),
        "y ninguna de las cuatro llamadas escribió nada"
    );
}

#[tokio::test]
async fn the_listing_says_which_templates_are_already_running() {
    // Es lo que la tarjeta del módulo pinta como «Activo», y lo que retira la heurística por
    // evento + command de wi#79 — que no distingue familias: con dos recetas de cita y una sola
    // montada, las dos decían «ya tienes esta».
    let fx = fixture().await;

    let before = send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await;
    let body = body_json(before).await;
    assert_eq!(
        body["data"][0]["installed"],
        Value::Null,
        "sin montar, `installed` es null — no ausente: la pantalla distingue «no» de «no lo sé»"
    );

    let activated = send(
        &fx.router,
        post(&activate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;
    let flow_id = body_json(activated).await["data"]["id"].as_str().unwrap().to_string();

    let after = send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await;
    let body = body_json(after).await;
    assert_eq!(body["data"][0]["installed"]["flow_id"], flow_id);
    assert_eq!(body["data"][0]["installed"]["enabled"], true);

    send(
        &fx.router,
        post(&deactivate_uri(WHATSAPP, FAMILY), Some(&fx.admin), Some(WHATSAPP)),
    )
    .await;
    let paused = send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await;
    let body = body_json(paused).await;
    assert_eq!(
        body["data"][0]["installed"]["enabled"], false,
        "una receta en pausa SIGUE montada: la tarjeta dice «pausada», no «actívala»"
    );
}
