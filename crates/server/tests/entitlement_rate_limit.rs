//! `GET /api/entitlement` frente al rate-limit del SaaS (hub#1167).
//!
//! El shell pregunta por el entitlement **muchísimas veces**: cada `focus` de ventana lo
//! recomprueba (`ModuleView.vue`), y cada navegación entre módulos monta una vista que vuelve a
//! preguntar. Hasta hub#1167 el proxy del runtime reenviaba **una llamada al Cloud por cada una
//! de esas veces**, así que un rato de uso normal vaciaba el cubo de tokens del SaaS y el hub
//! empezaba a comer 429 — con una ventana medida en prod de hasta **2828 s** (47 min).
//!
//! La causa raíz del 429 vive en el SaaS (saas#1640: las vistas hub-scoped sin `throttle_classes`
//! caen en `AnonRateThrottle` `anon: 100/hour` **keyed por IP**, y toda la flota sale por la
//! misma). Esto es la OTRA mitad, la del hub, y son dos propiedades distintas:
//!
//!  1. **No amplificar** — N preguntas del shell dentro de la ventana de frescura son UNA sola
//!     llamada al Cloud. Es lo que este fichero mide con un contador, no estima.
//!  2. **Amortiguar** — un 429 del SaaS no puede llegar al navegador. Ni como error (el shell lo
//!     lee como «no hay módulos» y degrada la pantalla), ni como la prosa inglesa cruda del SaaS
//!     dentro de una UI en español. Se sirve el último entitlement bueno y se respeta el
//!     `Retry-After` en vez de seguir golpeando la puerta que ya nos dijo que no.
//!
//! Los tests afirman sobre el **código** de error (ADR-0055), nunca sobre el texto.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

const ENTITLEMENT_URI: &str = "/api/entitlement";
/// La ruta real del SaaS que el proxy del runtime consume (`cloud_client::CloudClient::entitlement`).
const CLOUD_PATH: &str = "/api/v1/hub/device/entitlement/";
/// La prosa EXACTA que DRF devuelve y que se vio pintada en la UI en español (hub#1167).
const SAAS_PROSE: &str = "Request was throttled. Expected available in 2828 seconds.";

fn config(cloud_base_url: String, tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-ent-rl-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-rl".into(),
        cloud_base_url,
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

/// Router con una sesión iniciada, apuntando al Cloud simulado. Devuelve también el `AppState`
/// para poder envejecer la caché desde el test (lo que en producción hace el paso del tiempo).
async fn fixture(cloud_base_url: String, tag: &str) -> (Router, AppState, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-rl");
    rt.ensure_system_tables().await.unwrap();
    let user = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&user, 3600, None).await.unwrap();
    let state = AppState::with_config(rt, config(cloud_base_url, tag));
    (app(state.clone()), state, session)
}

fn signed_in(session: &str) -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri(ENTITLEMENT_URI)
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// El cuerpo entero serializado — para comprobar que la prosa del SaaS no viaja en NINGÚN campo.
fn flat(body: &Value) -> String {
    serde_json::to_string(body).unwrap_or_default()
}

/// Cloud simulado que CUENTA las llamadas al entitlement y responde lo que le diga `script`.
///
/// `script(n)` recibe el número de llamada (1-based) y devuelve el par (status, body JSON). Así un
/// test puede decir «la primera va bien y de la segunda en adelante 429», que es exactamente lo que
/// hace el SaaS cuando el cubo de la hora se vacía.
fn mock_cloud<F>(counter: Arc<AtomicUsize>, script: F) -> Router
where
    F: Fn(usize) -> (StatusCode, Value) + Clone + Send + Sync + 'static,
{
    Router::new().route(
        CLOUD_PATH,
        get(move || {
            let counter = counter.clone();
            let script = script.clone();
            async move {
                let n = counter.fetch_add(1, Ordering::SeqCst) + 1;
                let (status, body) = script(n);
                (status, Json(body))
            }
        }),
    )
}

fn entitled_body() -> Value {
    json!({
        "modules": [
            { "module_id": "inventory", "tier": "premium", "version": "1.0.0" }
        ]
    })
}

fn throttled_body() -> Value {
    json!({ "detail": SAAS_PROSE })
}

/// ⓵ **La medida.** Cinco preguntas seguidas del shell — el criterio de aceptación literal de la
/// issue («navegar 5 rutas seguidas») — tienen que gastar UNA sola llamada al Cloud, no cinco.
///
/// Este es el número que importa y por eso se cuenta en vez de estimarse: con 5/5 la flota entera
/// comparte 100 peticiones/hora (saas#1640), así que el shell de UN hub agota el cupo de TODOS en
/// 20 navegaciones.
#[tokio::test]
async fn cinco_preguntas_del_shell_gastan_una_sola_llamada_al_cloud() {
    let counter = Arc::new(AtomicUsize::new(0));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let cloud = mock_cloud(counter.clone(), |_| (StatusCode::OK, entitled_body()));
    let server = tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });

    let (router, _state, session) = fixture(format!("http://{address}"), "burst").await;

    for i in 1..=5 {
        let response = router.clone().oneshot(signed_in(&session)).await.unwrap();
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "la pregunta {i} del shell tiene que salir bien"
        );
        let body = body_json(response).await;
        assert_eq!(
            body["modules"][0]["module_id"], "inventory",
            "la pregunta {i} tiene que traer los módulos, no una lista vacía"
        );
    }

    assert_eq!(
        counter.load(Ordering::SeqCst),
        1,
        "5 preguntas del shell dentro de la ventana de frescura son UNA llamada al SaaS"
    );
    server.abort();
}

/// ⓶ **El 429 no llega al navegador.** La primera llamada va bien; a partir de ahí el SaaS
/// responde 429 con su prosa inglesa. El shell tiene que seguir viendo su entitlement — el último
/// bueno — y no un error.
#[tokio::test]
async fn un_429_del_saas_se_sirve_con_el_ultimo_entitlement_bueno() {
    let counter = Arc::new(AtomicUsize::new(0));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let cloud = mock_cloud(counter.clone(), |n| {
        if n == 1 {
            (StatusCode::OK, entitled_body())
        } else {
            (StatusCode::TOO_MANY_REQUESTS, throttled_body())
        }
    });
    let server = tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });

    let (router, state, session) = fixture(format!("http://{address}"), "absorb").await;

    // Primera: se puebla la caché.
    let first = router.clone().oneshot(signed_in(&session)).await.unwrap();
    assert_eq!(first.status(), StatusCode::OK);

    // Se envejece la caché para forzar el viaje al Cloud que se va a comer el 429 — lo que en
    // producción hace el reloj cuando el cajero vuelve al hub un minuto después.
    state.entitlement_proxy.write().unwrap().invalidate();

    let second = router.clone().oneshot(signed_in(&session)).await.unwrap();

    assert_eq!(
        second.status(),
        StatusCode::OK,
        "un 429 del SaaS no puede convertirse en un error para el shell"
    );
    let body = body_json(second).await;
    assert_eq!(
        body["modules"][0]["module_id"], "inventory",
        "se sirve el último entitlement bueno; degradar a lista vacía apaga módulos ya comprados"
    );
    assert!(
        !flat(&body).contains(SAAS_PROSE),
        "la prosa inglesa del SaaS no puede viajar a una UI en español: {}",
        flat(&body)
    );
    server.abort();
}

/// ⓷ **Sin nada bueno que servir, un CÓDIGO estable — nunca la prosa del SaaS.**
///
/// Si el 429 llega en el primer viaje (hub recién arrancado) no hay entitlement anterior que
/// enseñar. Entonces la respuesta la tiene que poder traducir la UI: un código estable
/// (`cloud_rate_limited`), no `{"detail":"Request was throttled…"}` pintado en crudo (ADR-0055).
#[tokio::test]
async fn sin_cache_previa_el_429_viaja_como_codigo_estable_y_no_como_prosa() {
    let counter = Arc::new(AtomicUsize::new(0));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let cloud = mock_cloud(counter.clone(), |_| {
        (StatusCode::TOO_MANY_REQUESTS, throttled_body())
    });
    let server = tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });

    let (router, _state, session) = fixture(format!("http://{address}"), "cold").await;

    let response = router.clone().oneshot(signed_in(&session)).await.unwrap();
    let status = response.status();
    let body = body_json(response).await;

    assert_eq!(
        status,
        StatusCode::TOO_MANY_REQUESTS,
        "sin caché el hub no puede inventarse un entitlement: dice que no pudo preguntar"
    );
    assert_eq!(
        body["error"]["code"], "cloud_rate_limited",
        "la UI traduce por CÓDIGO, no parseando la frase del SaaS: {}",
        flat(&body)
    );
    assert!(
        !flat(&body).contains(SAAS_PROSE),
        "la prosa inglesa del SaaS no puede viajar al cliente: {}",
        flat(&body)
    );
    server.abort();
}

/// ⓸ **El backoff.** Tras un 429, el hub deja de llamar durante la ventana que el propio SaaS
/// pidió (`Retry-After`). Seguir golpeando es lo que mantiene el cubo vacío para toda la flota.
#[tokio::test]
async fn tras_un_429_el_hub_deja_de_llamar_durante_la_ventana_pedida() {
    let counter = Arc::new(AtomicUsize::new(0));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let cloud = mock_cloud(counter.clone(), |_| {
        (StatusCode::TOO_MANY_REQUESTS, throttled_body())
    });
    let server = tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });

    let (router, _state, session) = fixture(format!("http://{address}"), "backoff").await;

    // Diez preguntas del shell con el SaaS en 429 desde el primer viaje.
    for _ in 0..10 {
        let _ = router.clone().oneshot(signed_in(&session)).await.unwrap();
    }

    assert_eq!(
        counter.load(Ordering::SeqCst),
        1,
        "el 429 abre una ventana de backoff: las 9 preguntas siguientes no vuelven a salir a la red"
    );
    server.abort();
}
