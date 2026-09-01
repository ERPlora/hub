//! `/readyz` sobre el router REAL — los casos de la definición de hecho de hub#538.
//!
//! Se prueba por la puerta que Swarm va a usar (una petición HTTP al router construido igual que en
//! producción), no llamando a la función de agregado: el agregado ya tiene sus tests unitarios, y lo
//! que aquí puede romperse es justo lo de alrededor — que la ruta esté montada, que conteste **antes
//! de enrolar la máquina**, y que el código HTTP sea el que Swarm interpreta.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::Runtime;
use erplora_server::{build_router, AppState, AuthMode, HubConfig, DEV_HUB_ID};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

async fn get(state: AppState, path: &str) -> (StatusCode, Value) {
    let response = build_router(state, None)
        .oneshot(Request::get(path).body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    let body = serde_json::from_slice(&bytes).unwrap_or_else(|_| json!(String::from_utf8_lossy(&bytes)));
    (status, body)
}


/// Un hub **arrancado del todo**: lo que hace el boot real, en el mismo orden.
///
/// Ojo con el orden: `ensure_hub_module_table` crea la BASELINE v0 de `hub_module`, que **no tiene
/// `hub_id`** — esa columna la añade la migración de sistema v1. Un fixture que se quede en la
/// baseline no representa a ningún hub vivo, y hace fallar al chequeo de módulos por una razón que
/// en producción no existe.
async fn booted_hub() -> AppState {
    let db = fresh_db().await;
    erplora_runtime::migrations::ensure_table(&db).await.unwrap();
    erplora_runtime::installer::ensure_hub_module_table(&db).await.unwrap();
    erplora_runtime::identity::ensure_tables(&db).await.unwrap();
    erplora_runtime::system_migrations::apply(&db, DEV_HUB_ID).await.unwrap();
    AppState::with_config(
        Runtime::new(Box::new(db)),
        HubConfig::from_env_with_auth(AuthMode::Dev),
    )
}

/// Deja constancia en `hub_module` de que este hub tiene ese módulo — sin cargarlo.
async fn record_installed(state: &AppState, module_id: &str, status: &str) {
    let runtime = state.runtime.read().await;
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(state.hub_id()));
    params.insert("module_id".into(), json!(module_id));
    params.insert("status".into(), json!(status));
    runtime
        .db()
        .execute(
            "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
             VALUES (:hub_id, :module_id, '1.0.0', :status, '2026-08-09T00:00:00Z', '2026-08-09T00:00:00Z')",
            &params,
        )
        .await
        .unwrap();
}

#[tokio::test]
async fn a_hub_that_booted_fully_is_ready() {
    let (status, body) = get(booted_hub().await, "/readyz").await;

    assert_eq!(status, StatusCode::OK, "cuerpo: {body}");
    assert_eq!(body["status"], "UP");
    assert_eq!(body["checks"]["database"]["status"], "UP");
    assert_eq!(body["checks"]["migrations"]["status"], "UP");
    assert_eq!(body["checks"]["modules"]["status"], "UP");
}

/// **Le falta un módulo que `hub_module` dice que debería estar → NO está listo.**
///
/// Es el caso que hace que el rollback de Swarm sirva de algo: sin él, un hub que se actualiza y
/// pierde `sales` responde `ok`, Swarm lo da por sano y mata la tarea vieja que vendía.
#[tokio::test]
async fn a_missing_module_is_not_ready_and_says_which_one() {
    let state = booted_hub().await;
    record_installed(&state, "sales", "active").await;

    let (status, body) = get(state, "/readyz").await;

    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE, "cuerpo: {body}");
    assert_eq!(body["status"], "DOWN");
    assert_eq!(body["checks"]["modules"]["missing"], json!(["sales"]));
}

/// **Un hub cuyas migraciones de sistema no han corrido tampoco está listo.**
///
/// Y llega ahí por «no lo sé», no por «falta un módulo»: sin la v1, `hub_module` ni siquiera tiene
/// la columna `hub_id`, así que la lista de lo que DEBERÍA estar no se puede leer. Pintar eso de
/// verde sería exactamente el fallo que esta issue arregla — y pintarlo de `DOWN` mandaría a buscar
/// un módulo perdido que no existe.
#[tokio::test]
async fn a_hub_with_migrations_half_applied_is_not_ready() {
    let db = fresh_db().await;
    erplora_runtime::migrations::ensure_table(&db).await.unwrap();
    erplora_runtime::installer::ensure_hub_module_table(&db).await.unwrap();
    let state = AppState::with_config(
        Runtime::new(Box::new(db)),
        HubConfig::from_env_with_auth(AuthMode::Dev),
    );

    let (status, body) = get(state, "/readyz").await;

    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE, "cuerpo: {body}");
    assert_eq!(body["checks"]["modules"]["status"], "UNKNOWN");
}

/// **`/readyz` contesta ANTES de enrolar la máquina.**
///
/// Si cayera detrás del guard de registro, un hub recién creado devolvería 401 en cada sonda: Swarm
/// lo daría por muerto y lo reiniciaría en bucle sin llegar nunca a enrolarse.
#[tokio::test]
async fn readyz_answers_before_the_machine_is_registered() {
    let (status, _) = get(booted_hub().await, "/readyz").await;

    assert_ne!(status, StatusCode::UNAUTHORIZED);
    assert_ne!(status, StatusCode::FORBIDDEN);
}

/// **Liveness y readiness contestan cosas distintas, y por eso son dos rutas.**
///
/// Con un módulo perdido el proceso está perfectamente vivo —reiniciarlo no arregla nada— pero no
/// puede atender. `/healthz` sigue en 200 y `/readyz` en 503: si fueran la misma, Swarm reiniciaría
/// en bucle un proceso sano, o daría por bueno uno que no sirve.
#[tokio::test]
async fn liveness_stays_up_while_readiness_is_down() {
    let state = booted_hub().await;
    record_installed(&state, "sales", "active").await;

    let (ready, _) = get(state.clone(), "/readyz").await;
    let (alive, _) = get(state, "/healthz").await;

    assert_eq!(ready, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(alive, StatusCode::OK, "el proceso vive: reiniciarlo no traeria el modulo de vuelta");
}

/// Un módulo **desactivado a propósito** no bloquea: está instalado y apagado, así que no cargar es
/// lo correcto. Confundirlo con uno perdido dejaría `DOWN` a cualquier hub que desactive algo.
#[tokio::test]
async fn an_intentionally_inactive_module_does_not_block() {
    let state = booted_hub().await;
    record_installed(&state, "sales", "inactive").await;

    let (status, body) = get(state, "/readyz").await;

    assert_eq!(status, StatusCode::OK, "cuerpo: {body}");
}

/// **El caso que rompió el provisioning en producción (2026-08-09): un hub RECIÉN NACIDO, cero
/// módulos, arrancado por el camino REAL (`Runtime::ensure_system_tables`) — debe estar READY.**
///
/// El fixture `booted_hub()` de arriba llamaba a `migrations::ensure_table` a mano… y el boot
/// real NO lo hacía: `_hub_migrations` solo nacía con la primera migración de módulo. En un hub
/// virgen el chequeo de migraciones petaba con «relation does not exist» → DOWN → 503 → el
/// healthcheck de Swarm mataba la tarea → `deployment_status=error`. Ningún hub nuevo podía
/// aprovisionarse, y los tests seguían verdes porque el fixture no era el boot real.
#[tokio::test]
async fn a_fresh_hub_with_zero_modules_booted_the_real_way_is_ready() {
    let db = fresh_db().await;
    let mut runtime = Runtime::new(Box::new(db));
    // El camino REAL del arranque (`serve()`), no una recreación a mano pieza a pieza.
    runtime.ensure_system_tables().await.unwrap();
    let state = AppState::with_config(runtime, HubConfig::from_env_with_auth(AuthMode::Dev));

    let (status, body) = get(state, "/readyz").await;

    assert_eq!(status, StatusCode::OK, "un hub virgen debe estar READY; cuerpo: {body}");
    assert_eq!(body["checks"]["migrations"]["status"], "UP", "cuerpo: {body}");
    assert_eq!(body["checks"]["modules"]["status"], "UP", "cero módulos esperados = cero cargados: {body}");
    // Y **cero de verdad**: desde ADR-0293 un hub nace vacío, así que este ya no es el caso raro de
    // un provisioning a medias — es el estado normal del primer arranque de todo hub. Contarlo aquí
    // deja el número a la vista: si algo volviera a instalar módulos al nacer, se vería en el 0.
    assert_eq!(body["checks"]["modules"]["expected"], json!(0), "cuerpo: {body}");
    assert_eq!(body["checks"]["modules"]["registered"], json!(0), "cuerpo: {body}");
}

/// **…y sigue READY en cuanto instala el primero.** El otro extremo de ADR-0293: nacer vacío solo
/// vale si el camino de salida —el usuario elige su blueprint y lo importa— no deja el hub en
/// `DOWN`. Instalar escribe la fila de `hub_module` **y** registra el módulo en el mismo gesto, así
/// que esperados y cargados se mueven juntos; el test lo fija para que no puedan separarse.
#[tokio::test]
async fn installing_the_first_module_keeps_the_hub_ready() {
    let db = fresh_db().await;
    let mut runtime = Runtime::new(Box::new(db));
    runtime.ensure_system_tables().await.unwrap();

    // Un módulo mínimo en disco: lo que importa aquí es que entre por `install_from_dir`, que es la
    // puerta por la que pasa cualquier install (marketplace o import de blueprint).
    let dir = std::env::temp_dir().join(format!("erplora-readyz-first-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        r#"{"id":"first","name":"First","version":"1.0.0"}"#,
    )
    .unwrap();
    runtime.install_from_dir(&dir).await.unwrap();

    let state = AppState::with_config(runtime, HubConfig::from_env_with_auth(AuthMode::Dev));
    let (status, body) = get(state, "/readyz").await;

    assert_eq!(status, StatusCode::OK, "cuerpo: {body}");
    assert_eq!(body["checks"]["modules"]["expected"], json!(1), "cuerpo: {body}");
    assert_eq!(body["checks"]["modules"]["registered"], json!(1), "cuerpo: {body}");
    let _ = std::fs::remove_dir_all(&dir);
}

/// hub#1376 — un switchover del que el hub se recuperó **solo** no puede quedar invisible.
///
/// `/readyz` sigue verde (la BD atiende, y bajarlo dispararía el rollback de Swarm por algo que ya
/// está resuelto), pero dice cuántas escrituras llegó a rechazar la réplica. Es el dato que se mira
/// cuando alguien pregunta por qué el TPV se quedó un momento sin cobrar: sin él, el hub responde
/// 200 en todo y no queda rastro de que la base de datos cambió de líder debajo.
#[tokio::test]
async fn a_switchover_the_hub_recovered_from_shows_up_in_readyz_hub1376() {
    let tdb = erplora_db::testutil::TestDb::new().await;
    // Una sola conexión: así la escritura de abajo usa forzosamente la que se degrada a réplica,
    // en vez de que el pool le dé otra limpia y el test pase sin probar nada.
    let db = tdb.adapter_with_max_connections(1).await;
    erplora_runtime::migrations::ensure_table(&db).await.unwrap();
    erplora_runtime::installer::ensure_hub_module_table(&db).await.unwrap();
    erplora_runtime::identity::ensure_tables(&db).await.unwrap();
    erplora_runtime::system_migrations::apply(&db, DEV_HUB_ID).await.unwrap();

    // La BD hace switchover: la conexión del pool se queda hablando con el ex-líder.
    erplora_db::testutil::demote_pooled_connections_to_replica(&db, 1).await;
    // Una escritura cualquiera — se recupera sola, y por eso justamente nadie se enteraría.
    db.execute_batch("CREATE TABLE switchover_probe (id BIGINT PRIMARY KEY);")
        .await
        .expect("la escritura se recupera sola tras el switchover");

    let state = AppState::with_config(
        Runtime::new(Box::new(db)),
        HubConfig::from_env_with_auth(AuthMode::Dev),
    );
    let (status, body) = get(state, "/readyz").await;

    assert_eq!(status, StatusCode::OK, "la BD atiende: el hub sigue listo. cuerpo: {body}");
    assert_eq!(body["checks"]["database"]["status"], json!("UP"), "cuerpo: {body}");
    assert_eq!(
        body["checks"]["database"]["read_only_rejections"],
        json!(1),
        "el switchover que el hub sobrevivió tiene que verse desde fuera. cuerpo: {body}"
    );
}
