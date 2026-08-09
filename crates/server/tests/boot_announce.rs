//! El hub avisa al Cloud en cuanto atiende (hub#712) — contra un Cloud de verdad, por HTTP.
//!
//! El SaaS no puede saber cuándo un hub empieza a servir: Dokploy no está en el camino del
//! tráfico y no emite eventos, así que hasta ahora **preguntaba cada 15 s** y un hub ya vivo
//! seguía marcado `deploying` hasta un cuarto de minuto más tarde. El hub, en cambio, lo sabe
//! exactamente — y ya tiene el canal abierto (`POST /api/v1/hub/device/heartbeat/`, hub#199).
//!
//! Lo que se fija aquí es **cuándo** sale ese aviso, que es lo único delicado:
//!
//! * sale cuando `/readyz` diría `UP`, usando ese mismo agregado y no un criterio propio;
//! * **no** sale si al hub le falta un módulo — eso marcaría `active` un TPV que no vende;
//! * es *best-effort* de verdad: sin credencial de máquina, o con el Cloud caído, el hub
//!   arranca igual. Para eso sigue existiendo el sondeo del SaaS.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::{boot_announce, AppState, AuthMode, HubConfig, DEV_HUB_ID};
use serde_json::{json, Value};

/// Latidos recibidos por el Cloud de mentira: `(cabeceras, cuerpo)`.
type Beats = Arc<Mutex<Vec<(HeaderMap, Value)>>>;

/// Un Cloud que solo sabe hacer una cosa: apuntar quién le ha latido.
async fn spawn_cloud() -> (String, Beats) {
    async fn capture(State(beats): State<Beats>, headers: HeaderMap, Json(body): Json<Value>) -> StatusCode {
        beats.lock().unwrap().push((headers, body));
        StatusCode::OK
    }

    let beats: Beats = Arc::new(Mutex::new(Vec::new()));
    let app = Router::new()
        .route("/api/v1/hub/device/heartbeat/", post(capture))
        .with_state(beats.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (format!("http://{address}"), beats)
}

/// Un hub arrancado del todo, hablando con `cloud_base_url`. `token` a `None` = sin enrolar.
async fn booted_hub(cloud_base_url: &str, token: Option<&str>) -> AppState {
    let db = fresh_db().await;
    erplora_runtime::migrations::ensure_table(&db).await.unwrap();
    erplora_runtime::installer::ensure_hub_module_table(&db).await.unwrap();
    erplora_runtime::identity::ensure_tables(&db).await.unwrap();
    erplora_runtime::system_migrations::apply(&db, DEV_HUB_ID).await.unwrap();

    let mut config = HubConfig::from_env_with_auth(AuthMode::Dev);
    config.cloud_base_url = cloud_base_url.to_string();
    config.cloud_api_token = token.map(str::to_owned);
    AppState::with_config(Runtime::new(Box::new(db)), config)
}

/// Deja constancia en `hub_module` de que este hub tiene ese módulo — sin cargarlo.
async fn record_installed(state: &AppState, module_id: &str) {
    let runtime = state.runtime.lock().await;
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(state.hub_id()));
    params.insert("module_id".into(), json!(module_id));
    runtime
        .db()
        .execute(
            "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
             VALUES (:hub_id, :module_id, '1.0.0', 'active', '2026-08-10T00:00:00Z', '2026-08-10T00:00:00Z')",
            &params,
        )
        .await
        .unwrap();
}

/// Ventana corta: estos tests no esperan a un hub que nunca va a estar listo.
const IMPATIENT: Duration = Duration::from_millis(600);
const POLL: Duration = Duration::from_millis(20);

/// **El caso que existe para esto.** El hub está listo, así que lo dice — y el SaaS puede
/// marcarlo `active` sin esperar a su siguiente sondeo.
#[tokio::test]
async fn a_hub_that_is_ready_tells_the_cloud_with_its_machine_credential() {
    let (cloud, beats) = spawn_cloud().await;
    let state = booted_hub(&cloud, Some("machine-token")).await;

    boot_announce::announce_when_ready(state, IMPATIENT, POLL).await;

    let beats = beats.lock().unwrap();
    assert_eq!(beats.len(), 1, "el hub tenía que latir exactamente una vez al arrancar");
    let (headers, body) = &beats[0];
    assert_eq!(headers["x-hub-id"], DEV_HUB_ID);
    assert_eq!(headers["x-hub-token"], "machine-token");
    // Va la versión que corre, como en el latido periódico: el Cloud se entera de qué imagen
    // sirve este hub al arrancar, no hasta 24 h después.
    assert!(body.get("hub_version").is_some(), "cuerpo: {body}");
}

/// **La dirección cara.** A este hub le falta un módulo que `hub_module` dice que debería tener:
/// `/readyz` respondería `DOWN`. Avisar aquí sería mandar al cliente a un TPV que no vende, así
/// que el hub se calla y deja que el sondeo (y el rollback de Swarm) hagan su trabajo.
#[tokio::test]
async fn a_hub_missing_a_module_never_announces_itself() {
    let (cloud, beats) = spawn_cloud().await;
    let state = booted_hub(&cloud, Some("machine-token")).await;
    record_installed(&state, "sales").await;

    boot_announce::announce_when_ready(state, IMPATIENT, POLL).await;

    assert!(beats.lock().unwrap().is_empty(), "un hub incompleto no puede declararse listo");
}

/// Un `pnpm dev` local no está enrolado: no hay credencial de máquina, no hay a quién avisar.
/// Ni una petición — y desde luego ningún intento de hablar con el Cloud sin credencial.
#[tokio::test]
async fn a_hub_that_is_not_enrolled_says_nothing() {
    let (cloud, beats) = spawn_cloud().await;
    let state = booted_hub(&cloud, None).await;

    boot_announce::announce_when_ready(state, IMPATIENT, POLL).await;

    assert!(beats.lock().unwrap().is_empty());
}

/// **Avisar es una cortesía, no un requisito para arrancar.** Con el Cloud inalcanzable el hub
/// sigue su camino: la llamada termina, no cuelga y no explota. El sondeo del SaaS existe justo
/// para este caso.
#[tokio::test]
async fn a_cloud_that_is_down_cannot_stop_the_hub() {
    // Puerto cerrado: nadie escucha ahí.
    let state = booted_hub("http://127.0.0.1:1", Some("machine-token")).await;

    tokio::time::timeout(
        Duration::from_secs(20),
        boot_announce::announce_when_ready(state, IMPATIENT, POLL),
    )
    .await
    .expect("un Cloud caído no puede dejar el arranque colgado");
}
