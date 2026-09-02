//! Superficie HTTP de instalación LOCAL (`POST /api/modules/install {dir}`) — ERPlora/hub#239.
//!
//! Contrato que fijan estos tests (todos con sesión admin concedida: el agujero NO era de auth):
//!  - en **producción** (sin modo desarrollo explícito) la vía entera está apagada → error
//!    estable `dev_mode_required`, y el módulo NO queda instalado;
//!  - en modo desarrollo, un `dir` **fuera del staging** (`/etc`, travesía `..`) se rechaza con
//!    `install_dir_outside_staging` sin tocar el runtime;
//!  - en modo desarrollo, un `dir` **dentro del staging** (la caché de descargas del hub)
//!    instala como siempre.
//!
//! Patrón: router en memoria + `tower::ServiceExt::oneshot` (como `tests/http.rs`).

use std::path::{Path, PathBuf};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// Módulo de prueba real (manifest + migración Postgres) que ya usan los tests del runtime.
fn fixture_module() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_notes")
}

/// Copia recursiva (el fixture es minúsculo: manifest + sql + wasm).
fn copy_tree(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap().flatten() {
        let src = entry.path();
        let dst = to.join(entry.file_name());
        if src.is_dir() {
            copy_tree(&src, &dst);
        } else {
            std::fs::copy(&src, &dst).unwrap();
        }
    }
}

/// Árbol del test: `<tmp>/<tag>/{module_cache/notes/1.0.0, fuera/notes}` (el segundo es un clon
/// del módulo FUERA del staging: legítimo como paquete, prohibido como origen).
fn tree(tag: &str) -> PathBuf {
    let base = std::env::temp_dir().join(format!(
        "erplora-install-surface-{}-{tag}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&base);
    copy_tree(&fixture_module(), &base.join("module_cache/notes/1.0.0"));
    copy_tree(&fixture_module(), &base.join("fuera/notes"));
    base
}

fn config(base: &Path, dev_mode: bool) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: "hub-install".into(),
        cloud_base_url: "http://127.0.0.1:1".into(),
        module_cache: base.join("module_cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        // La máquina cuenta como registrada para atravesar la barrera global de arranque.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: base.join("media"),
        sector: None,
        dev_mode,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn make_app(base: &Path, dev_mode: bool) -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-install");
    rt.ensure_system_tables().await.unwrap();
    app(AppState::with_config(rt, config(base, dev_mode)))
}

fn post_install(dir: &Path) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/modules/install")
        .header("content-type", "application/json")
        .header("x-permissions", "*")
        .body(Body::from(json!({ "dir": dir }).to_string()))
        .unwrap()
}

fn get_modules() -> Request<Body> {
    Request::builder()
        .method("GET")
        .uri("/api/modules")
        .header("x-permissions", "*")
        .body(Body::empty())
        .unwrap()
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn installed_ids(router: &axum::Router) -> Vec<String> {
    let resp = router.clone().oneshot(get_modules()).await.unwrap();
    let body = body_json(resp).await;
    body["data"]
        .as_array()
        .map(|rows| {
            rows.iter()
                .filter_map(|r| r["id"].as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

/// (b) En producción la vía «instalar desde carpeta» no instala: error estable, sin efectos.
#[tokio::test]
async fn instalar_desde_carpeta_esta_apagado_en_produccion() {
    let base = tree("prod");
    let router = make_app(&base, false).await;

    let resp = router
        .clone()
        .oneshot(post_install(&base.join("module_cache/notes/1.0.0")))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(false));
    assert_eq!(body["error"]["code"], json!("dev_mode_required"));

    assert!(
        !installed_ids(&router).await.contains(&"notes".to_string()),
        "en producción el módulo NO debe quedar instalado"
    );
    let _ = std::fs::remove_dir_all(&base);
}

/// (a) Con modo desarrollo, un `dir` fuera del staging se rechaza (absoluto y por travesía).
#[tokio::test]
async fn instalar_desde_carpeta_fuera_del_staging_se_rechaza() {
    let base = tree("fuera");
    let router = make_app(&base, true).await;

    for dir in [
        PathBuf::from("/etc"),
        base.join("fuera/notes"),
        base.join("module_cache/../fuera/notes"),
    ] {
        let resp = router.clone().oneshot(post_install(&dir)).await.unwrap();
        assert_eq!(resp.status(), StatusCode::FORBIDDEN, "{}", dir.display());
        let body = body_json(resp).await;
        assert_eq!(
            body["error"]["code"],
            json!("install_dir_outside_staging"),
            "{}",
            dir.display()
        );
    }

    assert!(
        !installed_ids(&router).await.contains(&"notes".to_string()),
        "ningún rechazo debe dejar el módulo instalado"
    );
    let _ = std::fs::remove_dir_all(&base);
}

/// El camino REAL de producción (marketplace) NO pasa por el guardarraíl de `install {dir}`:
/// descarga del SaaS, **verifica firma ed25519 + SHA256** (hub#239, ADR-0015) y extrae en la
/// caché antes de instalar. Este test lo fija: con `dev_mode = false` (producción) una
/// instalación desde el marketplace de un módulo **correctamente firmado por una clave de
/// confianza** funciona — el cierre de `install {dir}` y la exigencia de firma no pueden llevarse
/// por delante la vía por la que un hub real instala módulos.
#[tokio::test]
async fn instalar_del_marketplace_firmado_funciona_en_produccion() {
    let base = std::env::temp_dir().join(format!(
        "erplora-install-surface-market-{tag}",
        tag = std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&base);
    // Cache LIMPIO: el marketplace debe descargar, verificar firma Y sha, y descomprimir. Si
    // pre-poblamos el cache (como `tree()`), el short-circuit de cache-hit saltaría la verifica.
    std::fs::create_dir_all(base.join("module_cache")).unwrap();

    let zip = module_zip("notes");
    // Firmante del marketplace + su clave pública (hex) para el anillo de confianza del hub.
    let rng = ring::rand::SystemRandom::new();
    let (signer, _) = cloud_client::Signer::generate(&rng);
    let sig = signer.sign("marketplace", &zip);
    let trusted_pk_hex = hex::encode(signer.public_key());
    let cloud = spawn_mock_cloud(zip, Some(sig)).await;

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-install");
    rt.ensure_system_tables().await.unwrap();
    let mut cfg = config(&base, false); // producción: sin HUB_DEV_MODE
    cfg.cloud_base_url = cloud;
    cfg.module_trusted_keys = vec![format!("marketplace={trusted_pk_hex}")];
    let router = app(AppState::with_config(rt, cfg));

    let req = Request::builder()
        .method("POST")
        .uri("/api/modules/request-install")
        .header("content-type", "application/json")
        .header("x-permissions", "*")
        .body(Body::from(json!({ "module_id": "notes" }).to_string()))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "el marketplace debe instalar un módulo firmado"
    );
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true), "{body}");
    // hub#1130: the wire response must always carry `also_installed` — empty here (`notes` has no
    // dependencies), but PRESENT, so a caller never has to special-case an absent field.
    assert_eq!(
        body["also_installed"],
        json!([]),
        "request-install must always report also_installed, even when nothing was dragged in: {body}"
    );

    assert!(
        installed_ids(&router).await.contains(&"notes".to_string()),
        "el módulo firmado del marketplace queda instalado"
    );
    let _ = std::fs::remove_dir_all(&base);
}

/// ⭐ **ADR-0194 (corrige el default de hub#239).** En producción **SIN anillo de claves
/// desplegado**, un módulo sin firma **SÍ se instala**: la integridad la garantiza el SHA256
/// obligatorio del grant (ADR-0015).
///
/// Este test afirmaba lo contrario (403) porque fijaba el default de hub#239. Ese default **tumbó
/// producción**: el provisioning nunca inyecta `HUB_MODULE_TRUSTED_KEYS`, así que TODA imagen
/// quedaba en `Enforce(<anillo vacío>)` = deny-all mientras **nadie firma** (`signing-key/` da 404
/// y `versions/` no expone `signature`). Resultado: `request-install` devolvía 403 y el import de
/// blueprint fallaba en 13 de 13 módulos — un hub nuevo no se podía poblar por ninguna vía.
///
/// Y no es una licencia nueva: ADR-0193 ya lo exigía en sus consecuencias — «hasta entonces el Hub
/// debe estar en `warn`, no `enforce`». El rechazo real vive en el test hermano de abajo, que es
/// donde el `enforce` tiene con qué verificar.
#[tokio::test]
async fn sin_anillo_desplegado_un_modulo_sin_firma_si_se_instala() {
    let base = std::env::temp_dir().join(format!(
        "erplora-install-surface-unsigned-{tag}",
        tag = std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&base);
    std::fs::create_dir_all(base.join("module_cache")).unwrap();

    let zip = module_zip("notes");
    // El mock cloud NO firma (como el serializer del Cloud actual, que aún no expone signature).
    let cloud = spawn_mock_cloud(zip, None).await;

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-install");
    rt.ensure_system_tables().await.unwrap();
    let mut cfg = config(&base, false); // producción, anillo de confianza VACÍO
    cfg.cloud_base_url = cloud;
    // `module_trusted_keys` vacío = no hay infraestructura de firma desplegada ⇒ `Sha256Only`
    // (el modo `warn` de ADR-0193), NO deny-all.
    let router = app(AppState::with_config(rt, cfg));

    let req = Request::builder()
        .method("POST")
        .uri("/api/modules/request-install")
        .header("content-type", "application/json")
        .header("x-permissions", "*")
        .body(Body::from(json!({ "module_id": "notes" }).to_string()))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "sin claves desplegadas NO hay firma que exigir: el hub debe poder instalar del \
         marketplace (integridad = SHA256, ADR-0015). Si esto es 403, el producto no arranca."
    );
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true), "{body}");

    assert!(
        installed_ids(&router).await.contains(&"notes".to_string()),
        "el módulo debe quedar instalado"
    );
    let _ = std::fs::remove_dir_all(&base);
}

/// El envés de ADR-0194 y el que conserva el valor de seguridad de hub#239: **con una clave
/// desplegada**, un módulo sin firma se rechaza con **403**. Desplegar la clave es el interruptor
/// que enciende el `enforce`, sin tocar código ni imagen.
#[tokio::test]
async fn con_anillo_desplegado_un_modulo_sin_firma_se_rechaza() {
    let base = std::env::temp_dir().join(format!(
        "erplora-install-surface-unsigned-enforce-{tag}",
        tag = std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&base);
    std::fs::create_dir_all(base.join("module_cache")).unwrap();

    // El mock cloud NO firma (como el serializer del Cloud de hoy).
    let cloud = spawn_mock_cloud(module_zip("notes"), None).await;

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-install");
    rt.ensure_system_tables().await.unwrap();
    let mut cfg = config(&base, false);
    cfg.cloud_base_url = cloud;
    // Clave del marketplace desplegada ⇒ el hub pasa SOLO a `Enforce`.
    let rng = ring::rand::SystemRandom::new();
    let (signer, _) = cloud_client::Signer::generate(&rng);
    cfg.module_trusted_keys = vec![hex::encode(signer.public_key())];
    let router = app(AppState::with_config(rt, cfg));

    let req = Request::builder()
        .method("POST")
        .uri("/api/modules/request-install")
        .header("content-type", "application/json")
        .header("x-permissions", "*")
        .body(Body::from(json!({ "module_id": "notes" }).to_string()))
        .unwrap();
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "con clave desplegada, un módulo sin firma se rechaza (403, rechazo de seguridad)"
    );
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(false), "{body}");

    assert!(
        !installed_ids(&router).await.contains(&"notes".to_string()),
        "el módulo sin firma NO debe quedar instalado"
    );
    let _ = std::fs::remove_dir_all(&base);
}

/// `module.zip` mínimo publicable (mismo patrón que `tests/install_progress.rs`).
fn module_zip(id: &str) -> Vec<u8> {
    let manifest = json!({ "id": id, "name": id, "version": "1.0.0" });
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        w.start_file("module.json", opts).unwrap();
        std::io::Write::write_all(&mut w, manifest.to_string().as_bytes()).unwrap();
        w.finish().unwrap();
    }
    buf
}

/// Mini-SaaS con las tres rutas que consume `CloudClient` (versions/download/mark_installed),
/// sirviendo el zip con su SHA256 REAL y, opcionalmente, su **firma ed25519** (hub#239). La
/// verificación de integridad Y autenticidad se ejercita de verdad.
async fn spawn_mock_cloud(
    zip_bytes: Vec<u8>,
    signature: Option<cloud_client::ModuleSignature>,
) -> String {
    use axum::extract::State;
    use axum::routing::{get, post};
    use axum::{Json, Router};
    use sha2::{Digest, Sha256};

    let sha: String = Sha256::digest(&zip_bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    type Pkg = std::sync::Arc<(Vec<u8>, String, Option<cloud_client::ModuleSignature>)>;
    let pkg: Pkg = std::sync::Arc::new((zip_bytes, sha, signature));

    async fn versions(State(pkg): State<Pkg>) -> Json<Value> {
        // Expone sha256 (integridad) y, si la hay, signature (autenticidad). El serializer del
        // Cloud real aún no expone `signature` (TODO); el mock sí para ejercitar la verificación.
        let mut entry = json!({ "version": "1.0.0", "is_active": true, "sha256": pkg.1 });
        if let Some(sig) = &pkg.2 {
            entry["signature"] = serde_json::to_value(sig).unwrap();
        }
        json!([entry]).into()
    }
    async fn download(State(pkg): State<Pkg>) -> Vec<u8> {
        pkg.0.clone()
    }
    async fn mark_installed() -> Json<Value> {
        json!({ "ok": true }).into()
    }

    let app = Router::new()
        .route("/api/v1/marketplace/modules/:id/versions/", get(versions))
        .route("/api/v1/marketplace/modules/:id/download/", get(download))
        .route(
            "/api/v1/marketplace/modules/:id/mark_installed/",
            post(mark_installed),
        )
        .with_state(pkg);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("http://{addr}")
}

/// (c) Modo desarrollo + `dir` dentro del staging (la caché de descargas) = flujo de siempre.
#[tokio::test]
async fn instalar_desde_carpeta_dentro_del_staging_en_dev_funciona() {
    let base = tree("dev");
    let router = make_app(&base, true).await;

    let resp = router
        .clone()
        .oneshot(post_install(&base.join("module_cache/notes/1.0.0")))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true));
    assert_eq!(body["data"]["module_id"], json!("notes"));

    assert!(
        installed_ids(&router).await.contains(&"notes".to_string()),
        "el módulo queda instalado y listado"
    );
    let _ = std::fs::remove_dir_all(&base);
}
