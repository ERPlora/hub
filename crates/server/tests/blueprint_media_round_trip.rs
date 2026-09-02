//! **Las imágenes viajan DENTRO del `.blueprint.zip`** — el ciclo completo contra el gestor media.
//!
//! Lo que manda [`architecture/hub/export-import.md`] es explícito: «Imágenes dentro del ZIP
//! (leídas del **gestor media** al exportar — disco o S3 — y copiadas a media al importar). Sin
//! dependencia del S3 del SaaS. El `image` de productos son rutas de media que el import resuelve
//! al copiar `media/`.»
//!
//! El código hacía otra cosa: export e import leían y escribían con `std::fs` sobre
//! `config.media_dir`, que en Hub Cloud (ADR-0154) es **scratch local** — el propio `state.rs` lo
//! dice. Los ficheros del hub viven en Object Storage detrás del proxy del Cloud (ADR-0047):
//! `media.rs` no tiene ni una llamada al sistema de ficheros. Resultado: `collect_media` recorría
//! una carpeta vacía, la sección `media` ni se añadía, y el zip salía SIN imágenes; el import, en
//! espejo, las dejaba en un directorio que nadie consulta.
//!
//! Sobrevivió porque ningún test la ejercitaba: en `export_import_test.rs` **todas** las
//! selecciones son `"media": false`, y lo único que toca rutas `media/` es un caso de zip-slip.
//! Por eso este banco habla con un Cloud de mentira que sí guarda ficheros: la aserción es sobre
//! los bytes que cruzan la frontera, no sobre una carpeta local que en producción no existe.

use std::io::Write as _;
use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Multipart, Query, State};
use axum::http::{Request, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

/// Bytes de la imagen del catálogo y del log de sistema. No comparten subcadena a propósito: un
/// test que afirme que el log NO viajó no puede acertar por casualidad sobre la imagen.
const IMAGE_BYTES: &[u8] = b"WEBP-cafe-con-leche";
const LOG_BYTES: &[u8] = b"BOOT-LOG-linea";

// ─────────────────────────── Cloud de mentira (Object Storage del hub) ───────────────────────────

/// Lo que el Cloud tiene guardado y lo que le han subido. `uploads` es la evidencia del import:
/// `(carpeta, nombre, bytes)` por cada fichero que el hub mandó a Object Storage.
#[derive(Default)]
struct CloudState {
    uploads: Mutex<Vec<(String, String, Vec<u8>)>>,
    /// Número de ficheros recibidos por petición, para fijar el límite del batch en el test.
    upload_batches: Mutex<Vec<(String, usize)>>,
    /// Nombres que el Object Storage de mentira rechaza; el resto del multipart sí se guarda.
    rejected_names: Mutex<std::collections::HashSet<String>>,
    /// Próximas peticiones que fallan enteras con 502 antes de escribir nada.
    transient_failures: Mutex<usize>,
    /// MIME observado por nombre, separado de `uploads` para no romper la evidencia histórica.
    upload_mimes: Mutex<Vec<(String, String)>>,
    /// Su propia dirección, para poder firmar URLs hacia sí mismo.
    base: Mutex<String>,
}

#[derive(serde::Deserialize)]
struct FolderQ {
    #[serde(default)]
    folder: String,
}

#[derive(serde::Deserialize)]
struct PathQ {
    #[serde(default)]
    path: String,
}

/// `GET /api/v1/hub/device/media/?folder=` — el listado que el gestor media proxya (ADR-0047).
/// El hub tiene una carpeta de negocio (`catalogo/`) y una de sistema (`_logs/`).
async fn cloud_list(Query(q): Query<FolderQ>) -> Json<Value> {
    let data = match q.folder.as_str() {
        "" => json!({
            "folders": [
                { "id": "catalogo", "name": "catalogo", "children": [] },
                { "id": "_logs", "name": "_logs", "children": [] }
            ],
            "files": [],
            "path": [],
            "usage": { "used_bytes": 0 }
        }),
        "catalogo" => json!({
            "folders": [],
            "files": [{
                "path": "catalogo/cafe.webp", "name": "cafe.webp", "ext": "webp",
                "bytes": IMAGE_BYTES.len(), "modified": "2026-08-16T00:00:00Z"
            }],
            "path": [], "usage": { "used_bytes": 0 }
        }),
        "_logs" => json!({
            "folders": [],
            "files": [{
                "path": "_logs/boot.log", "name": "boot.log", "ext": "log",
                "bytes": LOG_BYTES.len(), "modified": "2026-08-16T00:00:00Z"
            }],
            "path": [], "usage": { "used_bytes": 0 }
        }),
        _ => json!({ "folders": [], "files": [], "path": [], "usage": { "used_bytes": 0 } }),
    };
    Json(data)
}

/// `GET …/media/raw?path=` — el Cloud NO devuelve bytes, devuelve una URL firmada de Object
/// Storage que descarga el runtime (los buckets no tienen CORS). El export tiene que seguir ese
/// segundo salto, igual que hace el visor.
async fn cloud_raw(State(st): State<Arc<CloudState>>, Query(q): Query<PathQ>) -> Json<Value> {
    let base = st.base.lock().unwrap().clone();
    Json(json!({ "url": format!("{base}/object?path={}", q.path) }))
}

/// El objeto firmado. Se sirve desde el mismo proceso por comodidad; lo que importa es que sea un
/// **segundo** GET, sin las cabeceras de máquina.
async fn cloud_object(Query(q): Query<PathQ>) -> Vec<u8> {
    match q.path.as_str() {
        "catalogo/cafe.webp" => IMAGE_BYTES.to_vec(),
        "_logs/boot.log" => LOG_BYTES.to_vec(),
        _ => Vec::new(),
    }
}

/// `POST …/media/` — la subida multipart (`folder` + `files`). Guarda lo recibido como evidencia.
async fn cloud_upload(State(st): State<Arc<CloudState>>, mut mp: Multipart) -> Response {
    let mut folder = String::new();
    let mut files: Vec<(String, String, Vec<u8>)> = Vec::new();
    while let Ok(Some(field)) = mp.next_field().await {
        match field.name() {
            Some("folder") => folder = field.text().await.unwrap_or_default(),
            Some("files") => {
                let name = field.file_name().map(str::to_string).unwrap_or_default();
                let mime = field.content_type().map(str::to_string).unwrap_or_default();
                if let Ok(b) = field.bytes().await {
                    files.push((name, mime, b.to_vec()));
                }
            }
            _ => {}
        }
    }
    st.upload_batches
        .lock()
        .unwrap()
        .push((folder.clone(), files.len()));
    {
        let mut remaining = st.transient_failures.lock().unwrap();
        if *remaining > 0 {
            *remaining -= 1;
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "error": "temporary edge failure" })),
            )
                .into_response();
        }
    }
    let rejected = st.rejected_names.lock().unwrap().clone();
    let mut saved = 0usize;
    let mut failed = 0usize;
    for (name, mime, bytes) in files {
        if rejected.contains(&name) {
            failed += 1;
            continue;
        }
        st.uploads
            .lock()
            .unwrap()
            .push((folder.clone(), name.clone(), bytes));
        st.upload_mimes.lock().unwrap().push((name, mime));
        saved += 1;
    }
    if failed > 0 {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({ "error": "partial storage failure", "saved": saved, "failed": failed })),
        )
            .into_response();
    }
    (
        StatusCode::CREATED,
        Json(json!({ "success": true, "saved": saved })),
    )
        .into_response()
}

/// Levanta el Cloud de mentira y devuelve `(base_url, estado)`.
async fn spawn_cloud() -> (String, Arc<CloudState>) {
    let state = Arc::new(CloudState::default());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    *state.base.lock().unwrap() = format!("http://{addr}");
    let router = Router::new()
        .route(
            "/api/v1/hub/device/media/",
            get(cloud_list).post(cloud_upload),
        )
        .route("/api/v1/hub/device/media/raw", get(cloud_raw))
        .route("/object", get(cloud_object))
        .with_state(state.clone());
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{addr}"), state)
}

// ─────────────────────────── El hub bajo prueba ───────────────────────────

fn config(cloud_base_url: String, tag: &str) -> HubConfig {
    let base = std::env::temp_dir().join(format!("erplora_bpmedia_{}_{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-test".into(),
        cloud_base_url,
        module_cache: base.join("module_cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        // Scratch local. En Hub Cloud NUNCA contiene los ficheros del hub — que es justo el punto:
        // si el export mirase aquí, este banco saldría vacío.
        media_dir: base.join("media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn make_app(cloud_base_url: String, tag: &str) -> Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-test");
    rt.ensure_system_tables().await.unwrap();
    app(AppState::with_config(rt, config(cloud_base_url, tag)))
}

fn post_json(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", "hub-test")
        .body(Body::from(body.to_string()))
        .unwrap()
}

fn zip_entries(bytes: &[u8]) -> Vec<(String, Vec<u8>)> {
    use std::io::Read as _;
    let mut ar = zip::ZipArchive::new(std::io::Cursor::new(bytes.to_vec())).unwrap();
    let mut out = Vec::new();
    for i in 0..ar.len() {
        let mut f = ar.by_index(i).unwrap();
        let name = f.name().to_string();
        let mut buf = Vec::new();
        f.read_to_end(&mut buf).unwrap();
        out.push((name, buf));
    }
    out
}

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

fn build_media_zip(files: &[(String, Vec<u8>)]) -> Vec<u8> {
    let sha256: serde_json::Map<String, Value> = files
        .iter()
        .map(|(path, bytes)| (path.clone(), json!(sha256_hex(bytes))))
        .collect();
    let manifest = json!({
        "schema_version": 1, "name": "restaurante", "locale": "es",
        "hub": { "name": "Demo", "country": "ES", "currency": "EUR" },
        "created_at": "2026-08-16T00:00:00Z",
        "modules": [], "sections": ["media"], "sha256": sha256,
    })
    .to_string();
    let mut sources = Vec::with_capacity(files.len() + 1);
    sources.push(("manifest.json".to_string(), manifest.into_bytes()));
    sources.extend(files.iter().cloned());
    let refs: Vec<(&str, &[u8])> = sources
        .iter()
        .map(|(path, bytes)| (path.as_str(), bytes.as_slice()))
        .collect();
    build_zip(&refs)
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn import_zip(app: Router, zip: Vec<u8>) -> (StatusCode, Value) {
    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/import/inspect")
                .header("content-type", "application/octet-stream")
                .header("x-hub-id", "hub-test")
                .body(Body::from(zip))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let upload_id = body_json(resp).await["upload_id"]
        .as_str()
        .unwrap()
        .to_string();

    let resp = app
        .oneshot(post_json(
            "/api/hub/import",
            json!({ "upload_id": upload_id, "selection": { "media": true } }),
        ))
        .await
        .unwrap();
    let status = resp.status();
    (status, body_json(resp).await)
}

// ─────────────────────────── EXPORT: las imágenes entran en el zip ───────────────────────────

/// **El fallo que reportó Ioan.** Un hub con una imagen de catálogo en su gestor media exporta un
/// blueprint: la imagen tiene que ir DENTRO del zip, con su sha256 en el manifest y la sección
/// `media` declarada. Antes del arreglo el zip salía sin una sola entrada `media/`.
#[tokio::test]
async fn el_export_mete_las_imagenes_del_gestor_media_en_el_zip() {
    let (cloud, _state) = spawn_cloud().await;
    let app = make_app(cloud, "export").await;

    let resp = app
        .oneshot(post_json(
            "/api/hub/export",
            json!({
                "name": "restaurante", "locale": "es",
                "selection": {
                    "users": false, "settings": false, "settings_items": null,
                    "fiscal": false, "media": true, "modules": []
                }
            }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let entries = zip_entries(&bytes);

    let imagen = entries
        .iter()
        .find(|(n, _)| n == "media/catalogo/cafe.webp");
    assert!(
        imagen.is_some(),
        "la imagen del catálogo tiene que viajar dentro del zip; entradas = {:?}",
        entries.iter().map(|(n, _)| n).collect::<Vec<_>>()
    );
    assert_eq!(
        imagen.unwrap().1,
        IMAGE_BYTES,
        "los bytes del zip tienen que ser los del gestor media, no un placeholder"
    );

    // El manifest es la fuente de verdad del bundle: sin su sha256 el import rechaza el fichero.
    let manifest: Value = entries
        .iter()
        .find(|(n, _)| n == "manifest.json")
        .map(|(_, b)| serde_json::from_slice(b).unwrap())
        .expect("manifest.json");
    assert_eq!(
        manifest["sha256"]["media/catalogo/cafe.webp"],
        json!(sha256_hex(IMAGE_BYTES)),
        "la imagen tiene que ir firmada en el manifest: {}",
        manifest["sha256"]
    );
    assert!(
        manifest["sections"]
            .as_array()
            .unwrap()
            .iter()
            .any(|s| s == "media"),
        "la sección `media` tiene que declararse: {}",
        manifest["sections"]
    );
}

/// Las carpetas de sistema de primer nivel (`_logs`, `_system`, …) NO son datos del negocio y no
/// entran en el bundle. Es la regla que ya tenía el recorrido de disco y que el arreglo conserva.
#[tokio::test]
async fn el_export_deja_fuera_las_carpetas_de_sistema() {
    let (cloud, _state) = spawn_cloud().await;
    let app = make_app(cloud, "export_sys").await;

    let resp = app
        .oneshot(post_json(
            "/api/hub/export",
            json!({
                "name": "restaurante", "locale": "es",
                "selection": {
                    "users": false, "settings": false, "settings_items": null,
                    "fiscal": false, "media": true, "modules": []
                }
            }),
        ))
        .await
        .unwrap();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let entries = zip_entries(&bytes);

    assert!(
        !entries.iter().any(|(n, _)| n.starts_with("media/_logs/")),
        "los registros de sistema no son datos del negocio: {:?}",
        entries.iter().map(|(n, _)| n).collect::<Vec<_>>()
    );
    // Control positivo del mismo recorrido: si esto falla, el test de arriba no probaría nada.
    assert!(
        entries.iter().any(|(n, _)| n == "media/catalogo/cafe.webp"),
        "el recorrido tiene que traer la carpeta de negocio"
    );
}

// ─────────────────────────── IMPORT: las imágenes llegan al gestor media ───────────────────────

/// La otra mitad: un blueprint que trae `media/**` tiene que dejar esos bytes donde el hub los
/// sirve — Object Storage vía el Cloud —, no en el scratch local que nadie consulta.
#[tokio::test]
async fn el_import_sube_las_imagenes_del_zip_al_gestor_media() {
    let (cloud, state) = spawn_cloud().await;
    let app = make_app(cloud, "import").await;

    let manifest = json!({
        "schema_version": 1, "name": "restaurante", "locale": "es",
        "hub": { "name": "Demo", "country": "ES", "currency": "EUR" },
        "created_at": "2026-08-16T00:00:00Z",
        "modules": [], "sections": ["media"],
        "sha256": { "media/catalogo/cafe.webp": sha256_hex(IMAGE_BYTES) },
    })
    .to_string();
    let zip = build_zip(&[
        ("manifest.json", manifest.as_bytes()),
        ("media/catalogo/cafe.webp", IMAGE_BYTES),
    ]);

    let resp = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/hub/import/inspect")
                .header("content-type", "application/octet-stream")
                .header("x-hub-id", "hub-test")
                .body(Body::from(zip))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let upload_id = body_json(resp).await["upload_id"]
        .as_str()
        .unwrap()
        .to_string();

    let resp = app
        .oneshot(post_json(
            "/api/hub/import",
            json!({ "upload_id": upload_id, "selection": { "media": true } }),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let report = body_json(resp).await;

    let subidas = state.uploads.lock().unwrap().clone();
    assert_eq!(
        subidas.len(),
        1,
        "la imagen tenía que subirse al gestor media; subidas = {subidas:?}"
    );
    assert_eq!(subidas[0].0, "catalogo", "conservando su carpeta");
    assert_eq!(subidas[0].1, "cafe.webp", "y su nombre");
    assert_eq!(subidas[0].2, IMAGE_BYTES, "con los bytes del bundle");
    assert_eq!(
        state.upload_mimes.lock().unwrap().as_slice(),
        &[("cafe.webp".to_string(), "image/webp".to_string())],
        "cada parte conserva el MIME derivado de su nombre"
    );

    // El informe cuenta lo que pasó de verdad: una copiada, ninguna fallida.
    assert_eq!(
        report["report"]["media"]["copied"],
        json!(1),
        "{}",
        report["report"]["media"]
    );
    assert_eq!(
        report["report"]["media"]["failed"],
        json!(0),
        "{}",
        report["report"]["media"]
    );
}

/// Regresión del restaurante real: con una petición por imagen, el edge dejó pasar ~100 y las
/// siguientes 182 nunca llegaron. El contrato del Cloud acepta varios `files`, así que 123 objetos
/// de una carpeta deben cruzar en 4 peticiones (40 + 40 + 40 + 3), con bytes y MIME intactos.
#[tokio::test]
async fn el_import_agrupa_mas_de_cien_imagenes_en_lotes_de_hasta_cuarenta() {
    let (cloud, state) = spawn_cloud().await;
    let app = make_app(cloud, "import_123").await;
    let files: Vec<(String, Vec<u8>)> = (0..123)
        .map(|i| {
            (
                format!("media/catalogo/plato-{i:03}.webp"),
                format!("WEBP-plato-{i:03}").into_bytes(),
            )
        })
        .collect();

    let (status, body) = import_zip(app, build_media_zip(&files)).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["report"]["media"]["copied"], json!(123), "{body}");
    assert_eq!(body["report"]["media"]["failed"], json!(0), "{body}");

    let batches = state.upload_batches.lock().unwrap().clone();
    assert_eq!(
        batches,
        vec![
            ("catalogo".to_string(), 40),
            ("catalogo".to_string(), 40),
            ("catalogo".to_string(), 40),
            ("catalogo".to_string(), 3),
        ],
        "el import no debe volver a una llamada HTTP por fichero"
    );
    let uploads = state.uploads.lock().unwrap().clone();
    assert_eq!(uploads.len(), 123);
    for (i, (_, name, bytes)) in uploads.iter().enumerate() {
        assert_eq!(name, &format!("plato-{i:03}.webp"));
        assert_eq!(bytes, &format!("WEBP-plato-{i:03}").into_bytes());
    }
    assert!(state
        .upload_mimes
        .lock()
        .unwrap()
        .iter()
        .all(|(_, mime)| mime == "image/webp"));
}

/// El Cloud procesa todos los ficheros de un multipart y en un rechazo no transitorio devuelve cuántos
/// quedaron guardados. El Hub debe usar esos contadores —no marcar todo el lote como copiado ni
/// como fallido— y continuar con los lotes posteriores.
#[tokio::test]
async fn el_import_cuenta_un_rechazo_parcial_y_continua_el_siguiente_lote() {
    let (cloud, state) = spawn_cloud().await;
    state
        .rejected_names
        .lock()
        .unwrap()
        .insert("plato-010.webp".to_string());
    let app = make_app(cloud, "import_partial").await;
    let files: Vec<(String, Vec<u8>)> = (0..45)
        .map(|i| {
            (
                format!("media/catalogo/plato-{i:03}.webp"),
                format!("WEBP-plato-{i:03}").into_bytes(),
            )
        })
        .collect();

    let (status, body) = import_zip(app, build_media_zip(&files)).await;
    assert_eq!(status, StatusCode::OK, "el import es best-effort: {body}");
    assert_eq!(body["report"]["media"]["copied"], json!(44), "{body}");
    assert_eq!(body["report"]["media"]["failed"], json!(1), "{body}");
    assert_eq!(
        state.upload_batches.lock().unwrap().as_slice(),
        &[("catalogo".to_string(), 40), ("catalogo".to_string(), 5)],
        "un rechazo parcial no debe abortar los lotes siguientes"
    );
    let uploads = state.uploads.lock().unwrap();
    assert_eq!(uploads.len(), 44);
    assert!(!uploads.iter().any(|(_, name, _)| name == "plato-010.webp"));
    assert!(uploads.iter().any(|(_, name, _)| name == "plato-044.webp"));
}

/// 408/429/5xx se pueden repetir porque cada fichero reemplaza la misma ruta. El multipart se
/// reconstruye y el tercer intento verde es el único que se contabiliza.
#[tokio::test]
async fn el_import_reintenta_un_lote_transitorio_de_forma_acotada() {
    let (cloud, state) = spawn_cloud().await;
    *state.transient_failures.lock().unwrap() = 2;
    let app = make_app(cloud, "import_retry").await;
    let files: Vec<(String, Vec<u8>)> = (0..5)
        .map(|i| {
            (
                format!("media/catalogo/plato-{i:03}.webp"),
                format!("WEBP-plato-{i:03}").into_bytes(),
            )
        })
        .collect();

    let (status, body) = import_zip(app, build_media_zip(&files)).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["report"]["media"]["copied"], json!(5), "{body}");
    assert_eq!(body["report"]["media"]["failed"], json!(0), "{body}");
    assert_eq!(
        state.upload_batches.lock().unwrap().as_slice(),
        &[
            ("catalogo".to_string(), 5),
            ("catalogo".to_string(), 5),
            ("catalogo".to_string(), 5),
        ],
        "dos fallos + un éxito, nunca reintentos sin límite"
    );
    assert_eq!(state.uploads.lock().unwrap().len(), 5);
}

/// Si los tres intentos del primer lote fallan, su resultado es desconocido y el informe marca
/// los 40 como fallidos. El lote siguiente continúa y puede quedar verde: nunca hay falso éxito.
#[tokio::test]
async fn el_import_marca_el_lote_completo_tras_agotar_reintentos() {
    let (cloud, state) = spawn_cloud().await;
    *state.transient_failures.lock().unwrap() = 3;
    let app = make_app(cloud, "import_retry_exhausted").await;
    let files: Vec<(String, Vec<u8>)> = (0..45)
        .map(|i| {
            (
                format!("media/catalogo/plato-{i:03}.webp"),
                format!("WEBP-plato-{i:03}").into_bytes(),
            )
        })
        .collect();

    let (status, body) = import_zip(app, build_media_zip(&files)).await;
    assert_eq!(
        status,
        StatusCode::OK,
        "el import global sigue siendo best-effort: {body}"
    );
    assert_eq!(body["report"]["media"]["copied"], json!(5), "{body}");
    assert_eq!(body["report"]["media"]["failed"], json!(40), "{body}");
    assert_eq!(state.upload_batches.lock().unwrap().len(), 4);
    let uploads = state.uploads.lock().unwrap();
    assert_eq!(uploads.len(), 5);
    assert!(uploads.iter().any(|(_, name, _)| name == "plato-044.webp"));
}
