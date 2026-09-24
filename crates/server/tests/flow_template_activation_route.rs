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
/// Un tercer módulo instalado que NO es dueño de la receta y no trae ninguna.
const INTRUDER: &str = "inventory";
/// Otro módulo que SÍ trae la suya: lo que un módulo sin `manage_flows` no puede llegar a ver.
const NEIGHBOUR: &str = "reservations";
const NEIGHBOUR_FAMILY: &str = "table-from-whatsapp";
/// La galería de Automatizaciones: el módulo que SÍ declara `manage_flows` y al que el dueño se lo
/// concedió. Es quien tiene que seguir viendo la lista entera.
const EDITOR: &str = "flows";
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
    // Dos permisos a propósito: uno ancho y uno ACOTADO (hub#1623/#1654). El acotado es el caso
    // real: anular una cita **como clienta**, nunca de parte del salón.
    whatsapp_dir_with_grants(
        root,
        floor,
        json!({ "grants": [
            { "kind": "command", "value": CREATE },
            { "kind": "command", "value": CANCEL, "payload": { "channel": "customer" } },
        ]}),
    )
}

/// El mismo módulo con el sidecar de permisos que se le pase, que es lo que permite construir el
/// caso en el que `grants::replace` FALLA a mitad de la activación.
fn whatsapp_dir_with_grants(root: &Path, floor: &str, grants: Value) -> PathBuf {
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
    std::fs::write(
        dir.join(format!("flows/{FAMILY}.grants.json")),
        grants.to_string(),
    )
    .unwrap();
    std::fs::write(
        dir.join(format!("flows/{FAMILY}.requires.json")),
        json!({ "modules": { APPOINTMENTS: floor } }).to_string(),
    )
    .unwrap();
    dir
}

/// Un vecino que publica **su** receta. Sirve para una sola cosa: que «solo lo suyo» pueda fallar.
/// Sin él, servir la lista entera y servir la del que llama son indistinguibles.
fn neighbour_dir(root: &Path) -> PathBuf {
    let dir = root.join(NEIGHBOUR);
    std::fs::create_dir_all(dir.join("flows")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&json!({
            "id": NEIGHBOUR, "name": "Reservations", "version": "1.0.0"
        }))
        .unwrap(),
    )
    .unwrap();
    std::fs::write(
        dir.join(format!("flows/{NEIGHBOUR_FAMILY}.en.flow.json")),
        json!({
            "schema_version": 1,
            "name": "Book a table from WhatsApp",
            "triggers": [{ "kind": "manual" }],
            "steps": [{ "id": "s1", "kind": "command", "command": CREATE }]
        })
        .to_string(),
    )
    .unwrap();
    std::fs::write(
        dir.join(format!("flows/{NEIGHBOUR_FAMILY}.grants.json")),
        json!({ "grants": [{ "kind": "command", "value": CREATE }] }).to_string(),
    )
    .unwrap();
    std::fs::write(
        dir.join(format!("flows/{NEIGHBOUR_FAMILY}.requires.json")),
        json!({ "modules": { APPOINTMENTS: "1.0.0" } }).to_string(),
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
    fixture_with_grants(floor, None).await
}

/// `grants` = el sidecar de permisos de la familia, cuando el caso lo necesita distinto del real.
async fn fixture_with_grants(floor: &str, grants: Option<Value>) -> Fixture {
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
    rt.install_from_dir(&neighbour_dir(&modules)).await.unwrap();
    // La galería: declara `manage_flows` y el dueño se lo concedió en Ajustes → Permisos.
    std::fs::create_dir_all(modules.join(EDITOR)).unwrap();
    std::fs::write(
        modules.join(EDITOR).join("module.json"),
        serde_json::to_string_pretty(&json!({
            "id": EDITOR, "name": "Automations", "version": "1.0.0",
            "capabilities": { "manage_flows": {} }
        }))
        .unwrap(),
    )
    .unwrap();
    rt.install_from_dir(&modules.join(EDITOR)).await.unwrap();
    rt.set_module_capability(EDITOR, "manage_flows", true, "hub_user:admin")
        .await
        .unwrap();
    let whatsapp = match grants {
        Some(sidecar) => whatsapp_dir_with_grants(&modules, floor, sidecar),
        None => whatsapp_dir(&modules, floor),
    };
    rt.install_from_dir(&whatsapp).await.unwrap();

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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(INTRUDER),
        ),
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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    let flow_id = body_json(response).await["data"]["id"]
        .as_str()
        .expect("el flujo montado")
        .to_string();

    let grants = grants_of(&fx, &flow_id).await;
    assert_eq!(
        grants.len(),
        2,
        "exactamente los dos del sidecar, ni uno más"
    );
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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    assert_eq!(first.status(), StatusCode::CREATED);
    let first_id = body_json(first).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string();

    let second = send(
        &fx.router,
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    assert_eq!(
        second.status(),
        StatusCode::OK,
        "la segunda vez REUTILIZA: `200`, no `201`"
    );
    let second_id = body_json(second).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string();

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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    let flow_id = body_json(activated).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string();

    let response = send(
        &fx.router,
        post(
            &deactivate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    assert_eq!(again.status(), StatusCode::OK);
    let body = body_json(again).await;
    assert_eq!(
        body["data"]["id"], flow_id,
        "vuelve a encender el MISMO flujo"
    );
    assert_eq!(body["data"]["enabled"], true);
}

#[tokio::test]
async fn deactivating_a_family_that_was_never_activated_is_a_not_found() {
    let fx = fixture().await;

    let response = send(
        &fx.router,
        post(
            &deactivate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;

    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "template_floor_module_too_old",
        "el código del descarte, el mismo que ya sirve el listado"
    );
    assert!(flows(&fx).await.is_empty(), "y no se montó nada a medias");
}

#[tokio::test]
async fn a_family_no_module_ships_is_a_not_found() {
    let fx = fixture().await;

    let response = send(
        &fx.router,
        post(
            &activate_uri(WHATSAPP, "there-is-no-such-family"),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
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
        for uri in [
            activate_uri(WHATSAPP, FAMILY),
            deactivate_uri(WHATSAPP, FAMILY),
        ] {
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
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    let flow_id = body_json(activated).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string();

    let after = send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await;
    let body = body_json(after).await;
    assert_eq!(body["data"][0]["installed"]["flow_id"], flow_id);
    assert_eq!(body["data"][0]["installed"]["enabled"], true);

    send(
        &fx.router,
        post(
            &deactivate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    let paused = send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await;
    let body = body_json(paused).await;
    assert_eq!(
        body["data"][0]["installed"]["enabled"], false,
        "una receta en pausa SIGUE montada: la tarjeta dice «pausada», no «actívala»"
    );
}

/// Los módulos de los que la respuesta habla, en orden.
fn modules_of(list: &Value) -> Vec<String> {
    list.as_array()
        .expect("una lista")
        .iter()
        .map(|t| t["module"].as_str().unwrap_or_default().to_string())
        .collect()
}

#[tokio::test]
async fn a_recipe_whose_permissions_are_refused_is_never_left_running() {
    // 🔴 **El ORDEN es la garantía, y NO hay transacción.** `DatabaseAdapter` solo ofrece
    // `execute_tx(&[(String, Params)])` —una lista de sentencias armada de antemano— y crear la
    // receta, sembrar sus triggers y conceder sus permisos LEEN por el medio, así que activar no
    // cabe en una. Lo que sustituye a la transacción es el orden: validar → crear/reutilizar EN
    // PAUSA → `replace` de los grants (que ya es todo-o-nada) → encender.
    //
    // Lo que ese orden compra es exactamente este test: si los permisos se caen a mitad, lo que
    // queda es una receta APAGADA y sin permisos —el estado que ADR-0463 §5 llama normal, y que el
    // siguiente toque reutiliza—. Lo que no puede pasar nunca es lo contrario: una automatización
    // CORRIENDO con la mitad de sus permisos, disparándose sola con un `flow.grant_denied` en cada
    // paso. Crear ya encendida y apagar después no sería lo mismo: entre las dos escrituras la
    // automatización está viva.
    //
    // El fallo se provoca por donde se provoca de verdad: un sidecar que pide un command que
    // ningún módulo instalado publica. `wanted_grants` no puede verlo (solo mira el KIND) y
    // `store::create` tampoco (los pasos sí son válidos), así que revienta dentro de
    // `grants::replace`, ya con la fila escrita — que es el único sitio donde este orden importa.
    let fx = fixture_with_grants(
        "1.1.69",
        Some(json!({ "grants": [
            { "kind": "command", "value": CREATE },
            { "kind": "command", "value": "nobody.ships.this" },
        ]})),
    )
    .await;

    let response = send(
        &fx.router,
        post(
            &activate_uri(WHATSAPP, FAMILY),
            Some(&fx.admin),
            Some(WHATSAPP),
        ),
    )
    .await;
    assert!(
        !response.status().is_success(),
        "un permiso que no existe no se concede a medias: la activación se niega entera"
    );

    // Y lo que quedó en el hub no está corriendo. Se pregunta por la MISMA puerta que lee la
    // pantalla del módulo, que es donde se notaría.
    let listing = send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await;
    assert_eq!(listing.status(), StatusCode::OK);
    let body = body_json(listing).await;
    let card = body["data"]
        .as_array()
        .expect("una lista de plantillas")
        .iter()
        .find(|t| t["family"] == FAMILY)
        .expect("su receta sigue ofreciéndose: lo que falló es encenderla, no publicarla")
        .clone();
    assert_ne!(
        card["installed"]["enabled"],
        json!(true),
        "una automatización CORRIENDO con la mitad de sus permisos es lo único que el orden \
         validar → crear en pausa → grants → encender existe para impedir"
    );

    // Y el control positivo de que este test puede fallar: la receta del vecino, con sus permisos
    // en su sitio, SÍ se queda corriendo por esta misma puerta.
    let ok = send(
        &fx.router,
        post(
            &activate_uri(NEIGHBOUR, NEIGHBOUR_FAMILY),
            Some(&fx.admin),
            Some(NEIGHBOUR),
        ),
    )
    .await;
    assert!(
        ok.status().is_success(),
        "control: una receta sana sí se enciende"
    );
    assert_eq!(body_json(ok).await["data"]["enabled"], json!(true));
}

#[tokio::test]
async fn a_module_without_manage_flows_is_served_only_its_own_recipes() {
    // La pantalla de tres pasos de whatsapp_inbox#123 tiene que saber si su receta ya está puesta,
    // y `whatsapp_inbox` NO declara `manage_flows` a propósito («la capability con más alcance de
    // todas», y su `whatsapp-uses.ts` lo explica). Sin esto, el `installed` que pide ADR-0470 §5 le
    // sería inútil justo a quien lo necesita: la ruta le contestaba `capability_denied`.
    //
    // Lo que se le sirve es estrictamente LO SUYO: es el mismo principio que ya rige activar («solo
    // SUS recetas») y es mucho más estrecho que `manage_flows`.
    let fx = fixture().await;

    let everything = send(&fx.router, get(TEMPLATES, &fx.admin, None)).await;
    assert_eq!(everything.status(), StatusCode::OK);
    let everything = body_json(everything).await;
    assert_eq!(
        modules_of(&everything["data"]),
        vec![NEIGHBOUR, WHATSAPP],
        "control: el shell no nombra módulo y sigue viendo la galería entera"
    );

    let mine = send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await;
    assert_eq!(
        mine.status(),
        StatusCode::OK,
        "y ya no es un 403: leer las recetas propias no necesita administrar flujos"
    );
    assert_eq!(
        modules_of(&body_json(mine).await["data"]),
        vec![WHATSAPP],
        "solo lo suyo: la receta del vecino no es asunto de este módulo"
    );
}

#[tokio::test]
async fn the_gallery_still_gets_the_whole_list_because_it_holds_manage_flows() {
    // La otra mitad, y la que impide «arreglarlo» acotando siempre: Automatizaciones ES un módulo
    // y nombra el suyo en la cabecera. Si el acotado se le aplicara también, la galería se quedaría
    // vacía — que es exactamente la regresión que hub#1611 vino a arreglar.
    let fx = fixture().await;

    let response = send(&fx.router, get(TEMPLATES, &fx.admin, Some(EDITOR))).await;

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        modules_of(&body_json(response).await["data"]),
        vec![NEIGHBOUR, WHATSAPP],
        "con `manage_flows` concedido se sirve la galería entera, como hasta hoy"
    );
}

#[tokio::test]
async fn a_module_is_told_about_its_own_discards_and_nobody_elses() {
    // `discarded[]` es la otra mitad de la respuesta (hub#1649) y se acota igual: el motivo por el
    // que ESTE hub no ofrece MI receta es mío y lo tengo que pintar; por qué no ofrece la del
    // vecino, no.
    let fx = fixture_with("9.9.9").await;

    let mine = body_json(send(&fx.router, get(TEMPLATES, &fx.admin, Some(WHATSAPP))).await).await;
    assert!(
        mine["data"].as_array().expect("una lista").is_empty(),
        "su receta está descartada por suelo, así que no se le ofrece"
    );
    assert_eq!(
        modules_of(&mine["discarded"]),
        vec![WHATSAPP],
        "y se le dice por qué — solo de la suya"
    );

    let neighbour =
        body_json(send(&fx.router, get(TEMPLATES, &fx.admin, Some(NEIGHBOUR))).await).await;
    assert_eq!(
        modules_of(&neighbour["data"]),
        vec![NEIGHBOUR],
        "el vecino ve la suya, que este hub sí ofrece"
    );
    assert!(
        neighbour["discarded"]
            .as_array()
            .expect("una lista")
            .is_empty(),
        "y no se entera del descarte ajeno"
    );
}
