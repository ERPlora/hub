//! **Un hub RECIÉN NACIDO nace VACÍO** — cero módulos instalados (decisión de Ioan, 2026-08-10).
//!
//! ERPlora es un **ERP genérico, no un POS**: el vertical no viene de fábrica. Un hub nuevo arranca
//! con su configuración y nada más, y es **el usuario** quien entra, ve los blueprints e importa el
//! que le sirve. Sembrarle un vertical al nacer decide por él justo lo que el producto le deja
//! elegir.
//!
//! ## Contra qué se defiende esto exactamente
//!
//! Los módulos de un hub recién provisionado no los ponía el SaaS ni las migraciones de sistema:
//! los instalaba **el propio arranque**, importando el blueprint que el despliegue le DECLARABA en
//! `HUB_BOOTSTRAP_BLUEPRINT` (ADR-0212 / hub#406). Ese import entraba por `run_import` con
//! `ImportSelection.modules = <todos los módulos del manifest>`, así que un hub nacía con tantos
//! módulos como trajera la plantilla — 13 en la demo del blueprint `restaurante`.
//!
//! Por eso el test se hace **por la puerta del env**, no llamando a una función: lo que el
//! despliegue pone es la variable, y lo que hay que garantizar es que ponerla ya no instala nada.
//! Un test que llamara al lector sería un test del lector; este es un test del **arranque**.
//!
//! ## Y por qué arranca de verdad (`serve()`) en vez de montar un `AppState` a mano
//!
//! Porque lo que se prueba es una **ausencia**, y una ausencia solo se puede comprobar recorriendo
//! el camino entero: cualquier paso del boot que en el futuro vuelva a pedirle un blueprint al
//! Cloud —o a instalar módulos por su cuenta— cae aquí. Un fixture que arme el estado a mano se
//! saltaría precisamente el paso que se quiere vigilar.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::extract::{Path as AxumPath, RawQuery, State};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::{test_database_url, TestDb};
use erplora_db::{DatabaseAdapter, Params};
use erplora_server::{AuthMode, HubConfig, ServeConfig};
use serde_json::{json, Value};

/// El slug que el SaaS declara hoy para las demos (`DEMO_BLUEPRINT_SLUG`, ADR-0212).
const DECLARED_SLUG: &str = "restaurante";
const DECLARED_LOCALE: &str = "es";

// ───────────────────────────── el Cloud, que apunta quién le llama ────────────────────────────

/// Un Cloud de mentira cuyo único trabajo es **dejar constancia**: si el arranque le pide un
/// blueprint, la llamada queda registrada y el test lo ve. No sirve ningún bundle a propósito —
/// que el import fracasara por un 500 lo haría pasar por las razones equivocadas.
#[derive(Default)]
struct SpyCloud {
    calls: Mutex<Vec<String>>,
}

type Shared = Arc<SpyCloud>;

impl SpyCloud {
    fn calls(&self) -> Vec<String> {
        self.calls.lock().unwrap().clone()
    }

    /// Llamadas que solo puede haber hecho el import de blueprint del arranque. El resto del boot
    /// (latido, entitlement, reporte de errores) también toca el Cloud, y confundirlas haría fallar
    /// al test por algo que no es lo suyo.
    fn blueprint_calls(&self) -> Vec<String> {
        self.calls()
            .into_iter()
            .filter(|c| c.contains("blueprint"))
            .collect()
    }
}

async fn spawn_spy_cloud() -> (String, Shared) {
    async fn blueprint(
        State(spy): State<Shared>,
        AxumPath(slug): AxumPath<String>,
        RawQuery(query): RawQuery,
    ) -> Json<Value> {
        spy.calls
            .lock()
            .unwrap()
            .push(format!("blueprints/{slug}?{}", query.unwrap_or_default()));
        Json(json!({ "error": "no blueprint here" }))
    }

    async fn anything_else(State(spy): State<Shared>, uri: axum::http::Uri) -> Json<Value> {
        spy.calls.lock().unwrap().push(uri.path().to_string());
        Json(json!({}))
    }

    let spy: Shared = Arc::new(SpyCloud::default());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let app = Router::new()
        .route("/api/v1/catalog/blueprints/:slug/download/", get(blueprint))
        .fallback(anything_else)
        .with_state(spy.clone());
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (base, spy)
}

// ───────────────────────────────── el hub, arrancado de verdad ────────────────────────────────

/// DSN de un esquema efímero: el mismo Postgres de los tests, aislado por `search_path`, para poder
/// dárselo a `serve()` como se lo da el despliegue (`HUB_DATABASE_URL`).
fn dsn_for(schema: &str) -> String {
    let base = test_database_url();
    let sep = if base.contains('?') { '&' } else { '?' };
    format!("{base}{sep}options=-c%20search_path%3D{schema}")
}

/// Un puerto libre. Se pide y se suelta: `serve()` bindea `cfg.bind` y no devuelve el puerto real,
/// así que hay que elegirlo antes.
fn free_port() -> u16 {
    let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = l.local_addr().unwrap().port();
    drop(l);
    port
}

/// Arranca el hub por su punto de entrada REAL y espera a que conteste. Devuelve la base HTTP.
async fn boot_hub(hub_id: &str, schema: &str, cloud: &str, tag: &str) -> String {
    let base_dir = std::env::temp_dir().join(format!("erplora_newborn_{}_{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base_dir);
    let cfg = ServeConfig {
        database_url: dsn_for(schema),
        bind: format!("127.0.0.1:{}", free_port()),
        modules_dir: None,
        hub: HubConfig {
            hub_id: hub_id.to_string(),
            cloud_base_url: cloud.to_string(),
            // Con credencial de máquina: sin ella el import ni lo intentaría y el test pasaría por
            // la razón equivocada («no había token»), no por la que se quiere garantizar.
            cloud_api_token: Some("machine-token".into()),
            module_cache: base_dir.join("module_cache"),
            media_dir: base_dir.join("media"),
            dev_mode: false,
            dev_modules_dir: None,
            ..HubConfig::from_env_with_auth(AuthMode::Dev)
        },
        machine_token_cell: None,
        hub_id_cell: None,
        web_dir: None,
        csp: None,
    };
    let url = format!("http://{}", cfg.bind);
    // En su propio hilo con su propio runtime: el futuro de `serve()` no es `Send` (su error es un
    // `Box<dyn Error>`), así que no se puede `tokio::spawn`. Arrancarlo aparte, además, es más fiel:
    // es lo que hace el binario.
    std::thread::spawn(move || {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .unwrap();
        if let Err(e) = rt.block_on(erplora_server::serve(cfg)) {
            eprintln!("serve() terminó: {e}");
        }
    });
    wait_until_answering(&url).await;
    url
}

/// El arranque real hace red y migraciones; se espera a que `/healthz` conteste antes de mirar nada.
async fn wait_until_answering(base: &str) {
    let client = reqwest::Client::new();
    for _ in 0..200 {
        if let Ok(r) = client.get(format!("{base}/healthz")).send().await {
            if r.status().is_success() {
                return;
            }
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    panic!("el hub no llegó a contestar en {base}");
}

async fn readyz(base: &str) -> Value {
    reqwest::get(format!("{base}/readyz"))
        .await
        .expect("readyz")
        .json()
        .await
        .expect("readyz devuelve JSON")
}

/// Las filas de `hub_module` de este hub — la lista de lo que el hub cree tener instalado.
async fn installed_module_ids(schema: &str, hub_id: &str) -> Vec<String> {
    let db = erplora_db::PgAdapter::connect(&dsn_for(schema))
        .await
        .expect("conectar al esquema del test");
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    let result = db
        .query(
            "SELECT module_id FROM hub_module WHERE hub_id = :hub_id ORDER BY module_id",
            &params,
        )
        .await
        .expect("leer hub_module");
    result
        .rows
        .iter()
        .filter_map(|r| r["module_id"].as_str().map(str::to_owned))
        .collect()
}

/// Pone las dos claves que el despliegue de una demo lleva hoy. El env es global al proceso: este
/// fichero corre en su propio binario de test y las deja puestas para todos sus casos, que es
/// justamente el escenario que se quiere.
fn declare_blueprint_in_the_deploy_env() {
    std::env::set_var("HUB_BOOTSTRAP_BLUEPRINT", DECLARED_SLUG);
    std::env::set_var("HUB_BOOTSTRAP_BLUEPRINT_LOCALE", DECLARED_LOCALE);
}

// ───────────────────────────────────────── los casos ──────────────────────────────────────────

/// **Un hub recién nacido no instala nada, aunque el despliegue le declare un blueprint.**
///
/// Es el corazón de la decisión: al entrar, el usuario tiene que encontrarse el hub vacío y elegir
/// él su vertical. Y de paso cierra el otro extremo — `/readyz` con cero módulos tiene que decir
/// **UP**: si dijera `DOWN`, el healthcheck de Swarm mataría cada despliegue de hub nuevo.
#[tokio::test(flavor = "multi_thread")]
async fn a_newborn_hub_installs_nothing_even_if_the_deploy_declares_a_blueprint() {
    declare_blueprint_in_the_deploy_env();
    let db = TestDb::new().await;
    let (cloud, spy) = spawn_spy_cloud().await;
    let hub_id = "hub-newborn";

    let hub = boot_hub(hub_id, db.schema(), &cloud, "newborn").await;
    // El import de arranque iba en su propia task: hay que darle margen para que se note.
    tokio::time::sleep(Duration::from_secs(2)).await;

    assert_eq!(
        installed_module_ids(db.schema(), hub_id).await,
        Vec::<String>::new(),
        "un hub nuevo nace VACÍO: nadie le instala módulos al arrancar"
    );
    assert_eq!(
        spy.blueprint_calls(),
        Vec::<String>::new(),
        "el arranque no le pide blueprints al Cloud"
    );

    let ready = readyz(&hub).await;
    assert_eq!(ready["status"], "UP", "cuerpo: {ready}");
    assert_eq!(ready["checks"]["modules"]["expected"], json!(0));
    assert_eq!(ready["checks"]["modules"]["registered"], json!(0));
    assert_eq!(ready["checks"]["modules"]["status"], "UP");
}

/// **Esto cambia el NACIMIENTO, no la vida:** un hub que ya tenía módulos no los pierde al arrancar.
///
/// La fila de `hub_module` es el estado anterior del hub y sobrevive al contenedor. Un arranque que
/// la borrara —o que la ignorase— sería el mismo fallo que `/readyz` vigila, servido por la puerta
/// de al lado: el hub saldría con menos de lo que entró.
#[tokio::test(flavor = "multi_thread")]
async fn a_hub_that_already_had_modules_keeps_them() {
    declare_blueprint_in_the_deploy_env();
    let db = TestDb::new().await;
    let (cloud, _spy) = spawn_spy_cloud().await;
    let hub_id = "hub-with-history";

    // El hub de ayer: sus tablas de sistema y una app instalada.
    {
        let adapter = db.adapter().await;
        erplora_runtime::installer::ensure_hub_module_table(&adapter)
            .await
            .unwrap();
        erplora_runtime::identity::ensure_tables(&adapter).await.unwrap();
        erplora_runtime::system_migrations::apply(&adapter, hub_id)
            .await
            .unwrap();
        let mut params = Params::new();
        params.insert("hub_id".into(), json!(hub_id));
        adapter
            .execute(
                "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
                 VALUES (:hub_id, 'sales', '1.0.0', 'active', '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z')",
                &params,
            )
            .await
            .unwrap();
    }

    boot_hub(hub_id, db.schema(), &cloud, "history").await;
    tokio::time::sleep(Duration::from_secs(2)).await;

    assert_eq!(
        installed_module_ids(db.schema(), hub_id).await,
        vec!["sales".to_string()],
        "arrancar no puede quitarle a un hub lo que ya tenía instalado"
    );
}
