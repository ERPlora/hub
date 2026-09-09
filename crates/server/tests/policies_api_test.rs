#![allow(non_snake_case)] // los nombres gritan la parte que importa, como el resto de la batería
//! **La puerta HTTP de las normas del dueño** (hub#1701, ADR-0476).
//!
//! ```text
//! GET/POST        /api/hub/policies              lista / crea
//! GET             /api/hub/policies/checkpoints  dónde se puede poner una norma
//! GET/PUT/DELETE  /api/hub/policies/{id}
//! ```
//!
//! Tres cosas que solo se pueden comprobar contra el router de VERDAD:
//!
//! 1. **`checkpoints` no se lo come `:id`.** Es un segmento estático y matchit lo resuelve antes
//!    que el parámetro; si algún día se colara por `:id`, la respuesta sería «no existe esa norma»
//!    en vez de la lista, y la pantalla del dueño se quedaría sin nada que ofrecer.
//! 2. **La puerta es la sesión local de un owner/admin**, nunca una API key ni el token de máquina.
//!    Quien escribe las normas del negocio es una PERSONA: una norma decide si una venta se puede
//!    cobrar, y una credencial de integración copiable no decide eso.
//! 3. **Cada negativa del núcleo llega con SU status.** `404` lo que no existe, `501` lo que este
//!    core todavía no sabe aplicar, `400` lo que el llamador mandó mal — un `409` para todo dejaría
//!    a la pantalla sin poder distinguir «arregla la norma» de «espera una release».
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-policies-api";

struct Fixture {
    router: axum::Router,
    /// Sesión de un owner/admin — el único que puede ver o escribir nada de esto.
    admin: String,
    /// Quién es esa persona. Lo que las columnas de auditoría tienen que acabar guardando.
    admin_id: String,
    /// Un cajero perfectamente válido que no administra el hub.
    employee: String,
    /// Una API key real y activa de este hub. Vale donde tiene que valer; aquí no.
    api_key: String,
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn fixture() -> Fixture {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    // El mismo módulo de la batería del runtime: declara `p1701/discount_limit` sobre
    // `p1701.order.set_discount`. Reutilizado y no copiado — un segundo fixture con las mismas
    // reglas es un sitio donde el contrato puede divergir sin que nadie lo note.
    let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../runtime/tests/fixture_1701");
    rt.install_from_dir(&dir).await.unwrap();

    let admin_id = rt.create_user("Ioan", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Marta", "2222", "cashier", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();
    let api_key = rt.ensure_app_api_key().await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-policies-api-{}-{admin_id}",
        std::process::id()
    ));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB.into(),
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
    };
    Fixture {
        router: app(AppState::with_config(rt, cfg)),
        admin,
        admin_id,
        employee,
        api_key,
    }
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    match body {
        Some(value) => builder
            .header("content-type", "application/json")
            .body(Body::from(value.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

async fn send(router: &axum::Router, request: Request<Body>) -> axum::response::Response {
    router.clone().oneshot(request).await.unwrap()
}

fn over_20() -> Value {
    json!({
        "checkpoint": "p1701/discount_limit",
        "condition": { "discount_percent": { "gt": 20 } },
        "outcome": "block",
        "message": "Los descuentos de más del 20 % los autoriza el encargado",
        "mode": "enforce"
    })
}

async fn create(f: &Fixture, body: Value) -> String {
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(body)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    body_json(response).await["data"]["id"]
        .as_str()
        .unwrap()
        .to_string()
}

#[tokio::test]
async fn the_owner_lists_where_a_rule_may_go_hub1701() {
    // 🔴 Contra el router REAL: `checkpoints` es estático y tiene que ganarle a `:id`. Servido por
    // `/policies/:id` esto respondería `404 policy.not_found` — la pantalla del dueño se quedaría
    // sin sitios que ofrecer y el fallo parecería «no hay módulos».
    let f = fixture().await;
    let response = send(
        &f.router,
        request(
            "GET",
            "/api/hub/policies/checkpoints",
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let list = body["data"].as_array().unwrap();
    assert_eq!(list.len(), 2, "{body}");
    assert_eq!(list[0]["id"], "p1701/discount_limit");
    assert_eq!(list[0]["command"], "p1701.order.set_discount");
    assert_eq!(list[0]["facts"][0], "discount_percent");
    assert_eq!(list[0]["outcomes"][0], "block");
}

#[tokio::test]
async fn a_rule_round_trips_through_the_door_hub1701() {
    let f = fixture().await;
    let id = create(&f, over_20()).await;

    let listed = send(
        &f.router,
        request("GET", "/api/hub/policies", Some(&f.admin), None),
    )
    .await;
    assert_eq!(listed.status(), StatusCode::OK);
    let body = body_json(listed).await;
    assert_eq!(body["data"].as_array().unwrap().len(), 1, "{body}");
    // La condición vuelve como DOCUMENTO, no como la cadena que se guardó: el llamador mandó JSON.
    assert_eq!(body["data"][0]["condition"]["discount_percent"]["gt"], 20);

    let one = send(
        &f.router,
        request(
            "GET",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(one.status(), StatusCode::OK);

    let mut promoted = over_20();
    promoted["mode"] = json!("warn");
    let updated = send(
        &f.router,
        request(
            "PUT",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            Some(promoted),
        ),
    )
    .await;
    assert_eq!(updated.status(), StatusCode::OK);
    assert_eq!(body_json(updated).await["data"]["mode"], "warn");

    let deleted = send(
        &f.router,
        request(
            "DELETE",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(deleted.status(), StatusCode::OK);

    let gone = send(
        &f.router,
        request(
            "GET",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    assert_eq!(gone.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn only_a_human_who_administers_the_hub_gets_in_hub1701() {
    let f = fixture().await;
    for (label, session) in [
        ("sin sesión", None),
        ("cajero", Some(f.employee.as_str())),
    ] {
        let response = send(
            &f.router,
            request("GET", "/api/hub/policies", session, None),
        )
        .await;
        assert!(
            response.status() == StatusCode::UNAUTHORIZED
                || response.status() == StatusCode::FORBIDDEN,
            "{label}: {}",
            response.status()
        );
    }
    // Y una API key REAL y activa de este hub tampoco entra: quien escribe las normas del negocio
    // es una persona, no una credencial copiable guardada en una integración.
    let with_key = send(
        &f.router,
        Request::builder()
            .method("POST")
            .uri("/api/hub/policies")
            .header("x-api-key", &f.api_key)
            .header("content-type", "application/json")
            .body(Body::from(over_20().to_string()))
            .unwrap(),
    )
    .await;
    assert!(
        with_key.status() == StatusCode::UNAUTHORIZED || with_key.status() == StatusCode::FORBIDDEN,
        "api key: {}",
        with_key.status()
    );
}

#[tokio::test]
async fn each_refusal_of_the_core_arrives_with_ITS_own_status_hub1701() {
    let f = fixture().await;

    // 404 — un punto de control que ningún módulo ofrece.
    let mut ghost = over_20();
    ghost["checkpoint"] = json!("p1701/ghost");
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(ghost)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "policy.checkpoint_not_found"
    );

    // 501 — el checkpoint SÍ lo ofrece y este core todavía no lo sabe aplicar (hub#1708). Es la
    // distinción que importa: una se arregla cambiando la norma, la otra esperando una release.
    let mut elevate = over_20();
    elevate["outcome"] = json!("elevate:p1701.order.discount");
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(elevate)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::NOT_IMPLEMENTED);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "policy.outcome_not_available"
    );

    // 400 — lo que el llamador mandó mal.
    let mut mute = over_20();
    mute["message"] = json!("   ");
    let response = send(
        &f.router,
        request("POST", "/api/hub/policies", Some(&f.admin), Some(mute)),
    )
    .await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        body_json(response).await["error"]["code"],
        "policy.message_required"
    );
}

#[tokio::test]
async fn a_rule_written_through_the_door_is_in_force_for_the_TILL_hub1701() {
    // El control positivo de toda la puerta: sin esto, un CRUD que guarda filas preciosas y no
    // gatea nada pasaría por «hecho». La norma se escribe por HTTP y se comprueba donde importa,
    // que es el comando.
    let f = fixture().await;
    create(&f, over_20()).await;

    // La puerta de los comandos del hub es UNA sola (`POST /api/command`, ADR-0005) y el nombre
    // viaja en el body, no como segmento de la ruta: el enrutado por hub del dispatcher es lo que
    // decide qué runtime ejecuta, y un nombre en la URL habría abierto una segunda puerta con su
    // propia autenticación. Pedirlo por `/api/commands/<nombre>` daba `404` con el cuerpo vacío,
    // que es lo mismo que habría dado un gate que no aplica: este test no probaba nada.
    let response = send(
        &f.router,
        request(
            "POST",
            "/api/command",
            Some(&f.admin),
            Some(json!({
                "name": "p1701.order.set_discount",
                "payload": { "order_id": "o1", "discount_percent": 35 }
            })),
        ),
    )
    .await;
    let status = response.status();
    let body = body_json(response).await;
    assert_eq!(body["error"]["code"], "policy.blocked", "{status} {body}");
    // Y el texto que lee la persona del mostrador es el que escribió el dueño.
    assert_eq!(
        body["error"]["message"],
        "Los descuentos de más del 20 % los autoriza el encargado"
    );
}

#[tokio::test]
async fn the_author_of_a_rule_is_the_SESSION_never_the_body_hub1701() {
    // 🔴 `created_by`/`updated_by` salen de la sesión resuelta y JAMÁS del body — misma regla que
    // `granted_by` en los flujos y `discarded_by` en la dead-letter. Aquí es lo esencial: una norma
    // decide si una venta se puede cobrar, así que su fila ES el registro de quién decidió eso. Un
    // llamador que pudiera firmar por otro convertiría la auditoría en un campo de texto.
    //
    // MUTANTE: leer el autor del body en `policies_api::create_policy` — este test cae.
    let f = fixture().await;
    let mut forged = over_20();
    forged["created_by"] = json!("hub_user:otro");
    forged["updated_by"] = json!("hub_user:otro");
    let id = create(&f, forged).await;

    let response = send(
        &f.router,
        request(
            "GET",
            &format!("/api/hub/policies/{id}"),
            Some(&f.admin),
            None,
        ),
    )
    .await;
    let body = body_json(response).await;
    let mine = format!("hub_user:{}", f.admin_id);
    assert_eq!(body["data"]["created_by"], mine, "{body}");
    assert_eq!(body["data"]["updated_by"], mine, "{body}");
}
