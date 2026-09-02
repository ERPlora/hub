//! TDD (hub#571): **un reinicio sin red no puede dejar al hub sin sus módulos.**
//!
//! El contrato stateless de Hub Cloud (`HUB_MODULE_CACHE=/tmp/module-cache`, sin volumen) borra la
//! caché de descargas en cada crash, redeploy o reschedule de Swarm. Hasta hoy la ÚNICA forma de
//! recuperarla era volver al marketplace, así que un SaaS caído —o un DNS torcido— dejaba al hub
//! arrancando **sin un solo módulo**: `/readyz` en DOWN y el bar sin TPV.
//!
//! Lo que se fija aquí es que el hub guarda el zip **ya verificado** en su propia base de datos
//! (la única cosa duradera que NO es el SaaS y NO ata el contenedor a un nodo) y que al arrancar
//! sabe reponer desde ahí **por la misma puerta verificada** que una descarga: SHA256 obligatorio
//! (ADR-0015) + firma ed25519 según la política (ADR-0193/0194). Una caché que se salte la
//! verificación no es una red de seguridad, es una superficie de ataque nueva.

use std::collections::HashMap;
use std::io::Write;
use std::sync::{Arc, Mutex};

use axum::extract::{Path, State};
use axum::routing::{get, post};
use axum::{Json, Router};
use cloud_client::Auth;
use erplora_db::testutil::TestDb;
use erplora_runtime::Runtime;
use erplora_server::install::{install_from_cloud, restore_from_local_packages};
use serde_json::{json, Value};

// ── utilidades de fixture ────────────────────────────────────────────────────────────────────

fn build_zip(entries: &[(&str, &[u8])]) -> Vec<u8> {
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        for (name, bytes) in entries {
            w.start_file(*name, opts).unwrap();
            w.write_all(bytes).unwrap();
        }
        w.finish().unwrap();
    }
    buf
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// `module.zip` mínimo instalable.
fn module_zip(id: &str) -> Vec<u8> {
    module_zip_with_deps(id, &[])
}

/// Igual, declarando `depends_on`.
fn module_zip_with_deps(id: &str, deps: &[&str]) -> Vec<u8> {
    let manifest = json!({ "id": id, "name": id, "version": "1.0.0", "depends_on": deps });
    build_zip(&[(
        "module.json",
        serde_json::to_string(&manifest).unwrap().as_bytes(),
    )])
}

struct MockCloud {
    catalog: HashMap<String, (Vec<u8>, String)>,
    calls: Mutex<Vec<String>>,
}

type Shared = Arc<MockCloud>;

/// Mini-marketplace en un puerto efímero. Devuelve `(base_url, handle)`; abortar el handle es
/// «el SaaS se cayó».
async fn spawn_mock_cloud(mock: Shared) -> (String, tokio::task::JoinHandle<()>) {
    async fn versions(State(m): State<Shared>, Path(id): Path<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("versions:{id}"));
        let sha = m
            .catalog
            .get(&id)
            .map(|(_, s)| s.clone())
            .unwrap_or_default();
        Json(json!([{ "version": "1.0.0", "is_active": true, "sha256": sha }]))
    }
    async fn download(State(m): State<Shared>, Path(id): Path<String>) -> Vec<u8> {
        m.calls.lock().unwrap().push(format!("download:{id}"));
        m.catalog
            .get(&id)
            .map(|(z, _)| z.clone())
            .unwrap_or_default()
    }
    async fn mark_installed(State(m): State<Shared>, Path(id): Path<String>) -> Json<Value> {
        m.calls.lock().unwrap().push(format!("mark:{id}"));
        Json(json!({ "ok": true }))
    }
    // Cloud sin ADR-0060 desplegado: el hub degrada a la resolución por manifest.
    async fn no_plan() -> axum::response::Response {
        use axum::response::IntoResponse;
        (
            axum::http::StatusCode::NOT_FOUND,
            Json(json!({"detail": "Not found."})),
        )
            .into_response()
    }
    let app = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .route("/api/v1/marketplace/install-plan/", post(no_plan))
        .with_state(mock);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let handle = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (format!("http://{addr}"), handle)
}

/// Una URL de Cloud a la que **no contesta nadie**: el puerto se reserva y se suelta, así que
/// cualquier llamada da «connection refused». Es el SaaS caído, sin depender de un `abort()`.
async fn cloud_that_is_down() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{addr}")
}

fn cache_dir(tag: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-571-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// `hub_id` del despliegue de este test (el mismo en las dos vidas del contenedor).
const HUB: &str = "hub-571";

fn auth() -> Auth {
    Auth::HubToken {
        hub_id: HUB.into(),
        token: "machine-secret".into(),
    }
}

// ── el contrato ──────────────────────────────────────────────────────────────────────────────

/// **El caso del issue.** Un hub con `notes` instalado se recrea (caché `/tmp` vacía) mientras el
/// Cloud está caído: tiene que arrancar CON su módulo, desde su propia copia.
#[tokio::test]
async fn a_hub_recreated_with_the_cloud_down_still_boots_with_its_modules() {
    let db = TestDb::new().await;
    let zip = module_zip("notes");
    let sha = sha256_hex(&zip);
    let mock = Arc::new(MockCloud {
        catalog: HashMap::from([("notes".to_string(), (zip, sha))]),
        calls: Mutex::new(Vec::new()),
    });
    let (cloud, handle) = spawn_mock_cloud(mock).await;
    let http = reqwest::Client::new();
    let policy = erplora_server::install::dev_signature_policy();

    // ── vida 1: el hub instala `notes` del marketplace, con red ──────────────────────────────
    let cache_1 = cache_dir("live1");
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    install_from_cloud(
        &http,
        &cloud,
        &cache_1,
        &auth(),
        &mut rt,
        "notes",
        "1.0.0",
        &|_, _| {},
        &policy,
    )
    .await
    .expect("la instalación con red funciona");
    assert!(rt.registry().is_installed("notes"));
    drop(rt);

    // ── el contenedor se recrea: caché `/tmp` vacía y el SaaS no contesta ────────────────────
    handle.abort();
    let _ = std::fs::remove_dir_all(&cache_1);
    let down = cloud_that_is_down().await;
    let cache_2 = cache_dir("live2");

    let mut rt2 = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt2.ensure_system_tables().await.unwrap();
    rt2.rehydrate_installed(&cache_2).await.unwrap();
    let missing = rt2.installed_but_unregistered().await.unwrap();
    assert_eq!(
        missing,
        vec![("notes".to_string(), "1.0.0".to_string())],
        "sin caché, `notes` está instalado según hub_module pero no registrado"
    );

    // La vía del marketplace está muerta: si el hub dependiera de ella, aquí se quedaría sin módulo.
    assert!(
        install_from_cloud(
            &http,
            &down,
            &cache_2,
            &auth(),
            &mut rt2,
            "notes",
            "1.0.0",
            &|_, _| {},
            &policy,
        )
        .await
        .is_err(),
        "el Cloud tiene que estar CAÍDO para que este test pruebe algo"
    );

    // ── la copia propia del hub ─────────────────────────────────────────────────────────────
    let restored = restore_from_local_packages(&cache_2, &mut rt2, &missing, &policy).await;

    assert_eq!(restored, vec!["notes".to_string()]);
    assert!(
        rt2.registry().is_installed("notes"),
        "un reinicio sin red tiene que dejar el hub CON sus módulos"
    );
    assert!(
        rt2.installed_but_unregistered().await.unwrap().is_empty(),
        "ya no queda nada instalado-sin-registrar"
    );

    let _ = std::fs::remove_dir_all(&cache_2);
}

/// `hub_module` no guarda orden topológico, así que la reposición se encuentra al dependiente
/// ANTES que su dependencia. Tiene que reponer los dos igual: el runtime exige que las `depends_on`
/// estén registradas, y rendirse en la primera pasada dejaría al hub a medias sin motivo.
#[tokio::test]
async fn a_module_is_restored_even_when_its_dependency_comes_later_in_the_list() {
    let db = TestDb::new().await;
    let base = module_zip("ledger");
    let dependent = module_zip_with_deps("invoicing", &["ledger"]);
    let mock = Arc::new(MockCloud {
        catalog: HashMap::from([
            ("ledger".to_string(), (base.clone(), sha256_hex(&base))),
            (
                "invoicing".to_string(),
                (dependent.clone(), sha256_hex(&dependent)),
            ),
        ]),
        calls: Mutex::new(Vec::new()),
    });
    let (cloud, handle) = spawn_mock_cloud(mock).await;
    let http = reqwest::Client::new();
    let policy = erplora_server::install::dev_signature_policy();

    let cache_1 = cache_dir("deps1");
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    // Instalar `invoicing` arrastra `ledger` (instalación anidada): quedan los dos, con sus copias.
    install_from_cloud(
        &http,
        &cloud,
        &cache_1,
        &auth(),
        &mut rt,
        "invoicing",
        "1.0.0",
        &|_, _| {},
        &policy,
    )
    .await
    .unwrap();
    drop(rt);
    handle.abort();
    let _ = std::fs::remove_dir_all(&cache_1);

    let cache_2 = cache_dir("deps2");
    let mut rt2 = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt2.ensure_system_tables().await.unwrap();
    rt2.rehydrate_installed(&cache_2).await.unwrap();

    // El dependiente PRIMERO, a propósito: es el orden que rompe una reposición de una sola pasada.
    let missing = vec![
        ("invoicing".to_string(), "1.0.0".to_string()),
        ("ledger".to_string(), "1.0.0".to_string()),
    ];
    let restored = restore_from_local_packages(&cache_2, &mut rt2, &missing, &policy).await;

    assert_eq!(restored.len(), 2, "los dos módulos, no solo el que tocaba");
    assert!(rt2.registry().is_installed("ledger"));
    assert!(rt2.registry().is_installed("invoicing"));

    let _ = std::fs::remove_dir_all(&cache_2);
}

/// La copia local entra **por la misma puerta verificada**: unos bytes que no casan con el SHA256
/// guardado se rechazan igual que una descarga manipulada. Una caché que confía en sí misma sería
/// una vía de carga de código sin verificar.
#[tokio::test]
async fn a_tampered_local_copy_is_refused_exactly_like_a_tampered_download() {
    let db = TestDb::new().await;
    let zip = module_zip("notes");
    let sha = sha256_hex(&zip);
    let mock = Arc::new(MockCloud {
        catalog: HashMap::from([("notes".to_string(), (zip, sha.clone()))]),
        calls: Mutex::new(Vec::new()),
    });
    let (cloud, handle) = spawn_mock_cloud(mock).await;
    let http = reqwest::Client::new();
    let policy = erplora_server::install::dev_signature_policy();

    let cache_1 = cache_dir("tamper1");
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    install_from_cloud(
        &http,
        &cloud,
        &cache_1,
        &auth(),
        &mut rt,
        "notes",
        "1.0.0",
        &|_, _| {},
        &policy,
    )
    .await
    .unwrap();
    drop(rt);
    handle.abort();
    let _ = std::fs::remove_dir_all(&cache_1);

    // Alguien reescribe el zip guardado (BD comprometida): el SHA256 de la fila deja de casar.
    let evil = build_zip(&[(
        "module.json",
        br#"{"id":"notes","name":"notes","version":"1.0.0","evil":true}"# as &[u8],
    )]);
    erplora_runtime::module_package::save(
        db_adapter_of(&db).await.as_ref(),
        HUB,
        "notes",
        "1.0.0",
        &sha, // el sha ORIGINAL: los bytes ya no son esos
        None,
        &evil,
    )
    .await
    .unwrap();

    let cache_2 = cache_dir("tamper2");
    let mut rt2 = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt2.ensure_system_tables().await.unwrap();
    rt2.rehydrate_installed(&cache_2).await.unwrap();
    let missing = rt2.installed_but_unregistered().await.unwrap();

    let restored = restore_from_local_packages(&cache_2, &mut rt2, &missing, &policy).await;
    assert!(
        restored.is_empty(),
        "un paquete local manipulado NO se instala"
    );
    assert!(!rt2.registry().is_installed("notes"));

    let _ = std::fs::remove_dir_all(&cache_2);
}

/// Desinstalar borra también la copia: si no, el módulo que el dueño quitó volvería en el
/// siguiente reinicio sin red.
#[tokio::test]
async fn uninstalling_forgets_the_local_copy_so_it_cannot_come_back() {
    let db = TestDb::new().await;
    let zip = module_zip("notes");
    let sha = sha256_hex(&zip);
    let mock = Arc::new(MockCloud {
        catalog: HashMap::from([("notes".to_string(), (zip, sha))]),
        calls: Mutex::new(Vec::new()),
    });
    let (cloud, handle) = spawn_mock_cloud(mock).await;
    let http = reqwest::Client::new();
    let policy = erplora_server::install::dev_signature_policy();

    let cache_1 = cache_dir("uninst1");
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    install_from_cloud(
        &http,
        &cloud,
        &cache_1,
        &auth(),
        &mut rt,
        "notes",
        "1.0.0",
        &|_, _| {},
        &policy,
    )
    .await
    .unwrap();
    assert!(
        erplora_runtime::module_package::load(rt.db(), rt.hub_id(), "notes")
            .await
            .unwrap()
            .is_some(),
        "instalar guarda la copia"
    );

    rt.uninstall("notes").await.unwrap();
    assert!(
        erplora_runtime::module_package::load(rt.db(), rt.hub_id(), "notes")
            .await
            .unwrap()
            .is_none(),
        "desinstalar la borra"
    );

    handle.abort();
    let _ = std::fs::remove_dir_all(&cache_1);
}

/// Adaptador extra sobre el MISMO esquema (el test manipula la fila por fuera del runtime).
async fn db_adapter_of(db: &TestDb) -> Box<dyn erplora_db::DatabaseAdapter> {
    Box::new(db.adapter().await)
}
