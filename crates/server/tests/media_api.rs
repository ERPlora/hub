//! Gestor de media (`/api/media*`) en Hub Cloud (Postgres-only, ADR-0154): cada endpoint es un
//! **proxy autenticado Hub→Cloud→Object Storage**. El fixture arranca un **mini-Cloud** que captura
//! las peticiones (mismo patrón que `module_storage`) y apunta `cloud_base_url` a él, para poder
//! afirmar tanto el 2xx del endpoint como que el Cloud recibió la petición esperada.
//!
//! Las afirmaciones de autorización (anónimo → 401, empleado no-admin → 401) corren ANTES del
//! dispatch al backend, así que no tocan el Cloud.

use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Request, State};
use axum::http::StatusCode;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

/// Petición capturada por el mini-Cloud: (método, path).
type Captured = Arc<Mutex<Vec<(String, String)>>>;

/// Mini-Cloud: captura cada petición y responde `200 {}` (JSON parseable → el proxy del listado no
/// falla al deserializar, y el `{}` vacío degrada con los defaults del contrato del frontend).
async fn capture(State(captured): State<Captured>, request: Request) -> Json<Value> {
    let method = request.method().to_string();
    let path = request.uri().path().to_string();
    captured.lock().unwrap().push((method, path));
    Json(json!({}))
}

/// Levanta el mini-Cloud en un puerto efímero; devuelve (base_url, captura).
async fn spawn_mock_cloud() -> (String, Captured) {
    let captured: Captured = Arc::new(Mutex::new(Vec::new()));
    let appx = Router::new().fallback(capture).with_state(captured.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, appx).await.unwrap() });
    (format!("http://{addr}"), captured)
}

/// Fixture: BD Postgres efímera (esquema propio) + Cloud simulado. Devuelve el router, las sesiones
/// de admin y empleado, y la captura de peticiones del Cloud.
async fn fixture() -> (axum::Router, String, String, Captured) {
    let (cloud_base_url, captured) = spawn_mock_cloud().await;

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-media");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let employee_id = rt
        .create_user("Employee", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();

    let cfg = HubConfig {
        hub_id: "hub-media".into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join("erplora-media-api-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        // El fixture prueba autorización humana de media + el proxy al Cloud, no el alta de máquina.
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-media-api-scratch"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
    };
    (app(AppState::with_config(rt, cfg)), admin, employee, captured)
}

#[tokio::test]
async fn media_requires_a_human_session_even_for_reads() {
    let (router, _admin, employee, captured) = fixture().await;

    // Anónimo → 401 ANTES de tocar el Cloud.
    let anonymous = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/media")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    // Sesión de usuario → 200; el listado se proxya al Cloud.
    let authenticated = router
        .oneshot(
            Request::builder()
                .uri("/api/media")
                .header("x-hub-session", employee)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(authenticated.status(), StatusCode::OK);

    // El Cloud recibió el listado (GET a …/media/).
    let calls = captured.lock().unwrap();
    assert!(
        calls
            .iter()
            .any(|(method, path)| method == "GET" && path.ends_with("/media/")),
        "el proxy debe pedir el listado al Cloud, got {calls:?}",
    );
}

#[tokio::test]
async fn only_admin_can_modify_media() {
    let (router, admin, employee, captured) = fixture().await;
    let body = json!({ "parent": "", "name": "facturas" }).to_string();

    // Empleado no-admin → 401 ANTES de tocar el Cloud.
    let denied = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/media/folder")
                .header("content-type", "application/json")
                .header("x-hub-session", employee)
                .body(Body::from(body.clone()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);
    assert!(
        captured.lock().unwrap().is_empty(),
        "un 401 no debe llegar a proxyar al Cloud",
    );

    // Admin → 200; la creación de carpeta se proxya al Cloud.
    let allowed = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/media/folder")
                .header("content-type", "application/json")
                .header("x-hub-session", admin)
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(allowed.status(), StatusCode::OK);

    // El Cloud recibió la creación de carpeta (POST a …/media/folder/).
    let calls = captured.lock().unwrap();
    assert!(
        calls
            .iter()
            .any(|(method, path)| method == "POST" && path.ends_with("/media/folder/")),
        "el proxy debe crear la carpeta en el Cloud, got {calls:?}",
    );
}

// ─────────────── Permisos por módulo sobre sus ficheros (ADR-0172) ───────────────

/// Storage de módulo no-op: el fixture solo necesita que instalar un manifest con `static_files`
/// no falle; lo que se prueba aquí es la política, no la materialización de la carpeta.
#[derive(Debug, Default)]
struct NoopStorage;

#[async_trait::async_trait]
impl erplora_runtime::module_storage::ModuleStorage for NoopStorage {
    async fn ensure_module_folder(&self, _hub: &str, _folder: &str) -> erplora_runtime::Result<()> {
        Ok(())
    }
    async fn write_module_file(
        &self,
        _hub: &str,
        _folder: &str,
        path: &str,
        _bytes: &[u8],
        _content_type: &str,
    ) -> erplora_runtime::Result<String> {
        Ok(path.to_string())
    }
}

/// Sufijo único por test (sin `uuid`, que no es dependencia del server).
fn unique() -> String {
    use std::sync::atomic::{AtomicUsize, Ordering};
    static N: AtomicUsize = AtomicUsize::new(0);
    format!("{}-{}", std::process::id(), N.fetch_add(1, Ordering::Relaxed))
}

/// Fixture con un módulo instalado que declara `static_files` con las acciones indicadas.
async fn fixture_with_module(user_actions: &str) -> (axum::Router, String, Captured) {
    let (cloud_base_url, captured) = spawn_mock_cloud().await;
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-media");
    rt.ensure_system_tables().await.unwrap();
    rt.set_module_storage(std::sync::Arc::new(NoopStorage));

    let dir = std::env::temp_dir().join(format!("erplora-media-policy-{}", unique()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        format!(
            r#"{{"id":"verifactu","name":"VeriFactu","version":"1.0.0",
                 "static_files":{{"folder":"verifactu"{user_actions}}}}}"#
        ),
    )
    .unwrap();
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let admin_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let cfg = HubConfig {
        hub_id: "hub-media".into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join("erplora-media-policy-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-media-policy-scratch"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
    };
    (app(AppState::with_config(rt, cfg)), admin, captured)
}

async fn send(router: &axum::Router, request: Request) -> axum::response::Response<Body> {
    router.clone().oneshot(request).await.unwrap()
}

fn delete_request(path: &str, session: &str) -> Request {
    Request::builder()
        .method("DELETE")
        .uri(format!("/api/media?path={path}"))
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

#[tokio::test]
async fn a_module_folder_is_read_only_for_the_user_by_default() {
    // VeriFactu no declara `user_actions` → sus XML son evidencia fiscal: se ven y se descargan,
    // no se borran desde el gestor de archivos. Ni siquiera un admin.
    let (router, admin, captured) = fixture_with_module("").await;

    let response = send(
        &router,
        delete_request("modules/verifactu/xml/rec-1.xml", &admin),
    )
    .await;

    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    // Y el rechazo ocurre ANTES de tocar el Cloud: no hay borrado a medias.
    assert!(
        !captured.lock().unwrap().iter().any(|(m, _)| m == "DELETE"),
        "el Cloud no debe recibir el borrado"
    );
}

#[tokio::test]
async fn a_module_can_open_up_deletion_of_its_own_files() {
    let (router, admin, captured) = fixture_with_module(r#","user_actions":["delete"]"#).await;

    let response = send(
        &router,
        delete_request("modules/verifactu/xml/rec-1.xml", &admin),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    assert!(captured.lock().unwrap().iter().any(|(m, _)| m == "DELETE"));
}

#[tokio::test]
async fn the_hub_own_log_folder_cannot_be_deleted_from_the_file_manager() {
    let (router, admin, _captured) = fixture_with_module("").await;
    let response = send(&router, delete_request("_logs/hub.2026-07-31", &admin)).await;
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn a_folder_without_an_owning_module_stays_manageable() {
    // Lo que sube una persona a su propia carpeta sigue siendo suyo.
    let (router, admin, captured) = fixture_with_module("").await;
    let response = send(&router, delete_request("facturas/a.pdf", &admin)).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(captured.lock().unwrap().iter().any(|(m, _)| m == "DELETE"));
}

#[tokio::test]
async fn uploading_into_a_read_only_module_folder_is_rejected() {
    let (router, admin, _captured) = fixture_with_module("").await;
    let body = "--x\r\nContent-Disposition: form-data; name=\"folder\"\r\n\r\nmodules/verifactu\r\n--x--\r\n";
    let response = send(
        &router,
        Request::builder()
            .method("POST")
            .uri("/api/media/upload")
            .header("x-hub-session", &admin)
            .header("content-type", "multipart/form-data; boundary=x")
            .body(Body::from(body))
            .unwrap(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn creating_a_subfolder_in_a_read_only_module_folder_is_rejected() {
    let (router, admin, _captured) = fixture_with_module("").await;
    let response = send(
        &router,
        Request::builder()
            .method("POST")
            .uri("/api/media/folder")
            .header("x-hub-session", &admin)
            .header("content-type", "application/json")
            .body(Body::from(
                json!({ "parent": "modules/verifactu", "name": "copia" }).to_string(),
            ))
            .unwrap(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
}

// ─────────────── Renombrar (ficheros y carpetas) ───────────────

fn rename_request(path: &str, name: &str, session: &str) -> Request {
    Request::builder()
        .method("POST")
        .uri("/api/media/rename")
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from(json!({ "path": path, "name": name }).to_string()))
        .unwrap()
}

#[tokio::test]
async fn renames_a_folder_of_the_user() {
    let (router, admin, captured) = fixture_with_module("").await;
    let response = send(&router, rename_request("facturas", "facturas-2026", &admin)).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(captured
        .lock()
        .unwrap()
        .iter()
        .any(|(_, p)| p.contains("rename")));
}

#[tokio::test]
async fn renaming_inside_a_read_only_module_folder_is_rejected() {
    let (router, admin, _captured) = fixture_with_module("").await;
    let response = send(
        &router,
        rename_request("modules/verifactu/xml/rec-1.xml", "otro.xml", &admin),
    )
    .await;
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn renaming_cannot_move_a_file_out_of_its_folder() {
    // `name` es un NOMBRE, no una ruta: si aceptase `../` se podría sacar un fichero de una
    // carpeta bloqueada a una libre y borrarlo allí, saltándose la política entera.
    let (router, admin, _captured) = fixture_with_module("").await;
    for bad in ["../fuera.xml", "sub/otro.xml", "", "."] {
        let response = send(&router, rename_request("facturas/a.pdf", bad, &admin)).await;
        assert_eq!(
            response.status(),
            StatusCode::BAD_REQUEST,
            "nombre rechazado: {bad:?}"
        );
    }
}

#[tokio::test]
async fn renaming_requires_an_admin_session() {
    let (router, _admin, _captured) = fixture_with_module("").await;
    let response = send(
        &router,
        Request::builder()
            .method("POST")
            .uri("/api/media/rename")
            .header("content-type", "application/json")
            .body(Body::from(json!({ "path": "a", "name": "b" }).to_string()))
            .unwrap(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

// ─────────────── El listado entrega URLs del propio runtime ───────────────

/// Mini-Cloud que responde un listado con una URL FIRMADA de Object Storage, como hace el SaaS.
async fn spawn_cloud_listing() -> String {
    let listing = json!({
        "folders": [{ "id": "", "label": "media" }],
        "files": [{
            "path": "facturas/a.pdf", "name": "a.pdf", "ext": "pdf", "bytes": 1024,
            "modified": "2026-07-31T09:00:00Z",
            "url": "https://fsn1.your-objectstorage.com/erplora-hubs/hubs/h1/facturas/a.pdf?X-Amz-Signature=abc"
        }],
        "path": [],
        "usage": { "used_bytes": 1024 }
    });
    let appx = Router::new().fallback(move || {
        let listing = listing.clone();
        async move { Json(listing) }
    });
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, appx).await.unwrap() });
    format!("http://{addr}")
}

#[tokio::test]
async fn the_listing_serves_files_through_the_runtime_not_a_signed_object_storage_url() {
    // El navegador NO puede leer la URL firmada: los buckets no tienen CORS, así que un `fetch`
    // desde el visor se cae. Y aunque lo tuvieran, la URL caduca. El runtime es la vía (ADR-0047).
    let cloud_base_url = spawn_cloud_listing().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-media");
    rt.ensure_system_tables().await.unwrap();
    let user_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&user_id, 3600, None).await.unwrap();
    let cfg = HubConfig {
        hub_id: "hub-media".into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join("erplora-media-url-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-media-url-scratch"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
    };
    let router = app(AppState::with_config(rt, cfg));

    let response = send(
        &router,
        Request::builder()
            .uri("/api/media")
            .header("x-hub-session", &session)
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();
    let url = json["data"]["files"][0]["url"].as_str().unwrap();

    assert_eq!(url, "/api/media/raw?path=facturas/a.pdf");
    assert!(url.starts_with('/'), "mismo origen: el navegador la pide con su sesión");
    assert!(!url.contains("your-objectstorage"), "la URL firmada no sale al navegador");
}

#[tokio::test]
async fn the_listing_tells_the_ui_what_can_be_done_in_the_current_folder() {
    // El botón que no se puede pulsar no se pinta: la UI necesita la política, no adivinarla
    // (y el servidor la revalida igual en cada endpoint).
    let (router, admin, _captured) = fixture_with_module("").await;
    let response = send(
        &router,
        Request::builder()
            .uri("/api/media?folder=modules%2Fverifactu")
            .header("x-hub-session", &admin)
            .body(Body::empty())
            .unwrap(),
    )
    .await;
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["data"]["policy"]["upload"], json!(false));
    assert_eq!(json["data"]["policy"]["rename"], json!(false));
    assert_eq!(json["data"]["policy"]["delete"], json!(false));
}

// ─────────────── El runtime sirve los bytes: el navegador nunca toca Object Storage ───────────────

#[tokio::test]
async fn raw_downloads_the_file_server_side_and_never_leaks_the_hub_token_to_storage() {
    // El Cloud devuelve una URL FIRMADA; el runtime la descarga él (server-side) y entrega los
    // bytes por su propio origen. Dos motivos: los buckets no tienen CORS (el navegador no puede
    // leerla) y la cabecera de máquina del hub es un secreto que no puede viajar a un tercero.
    use std::sync::atomic::{AtomicBool, Ordering};
    static TOKEN_LEAKED: AtomicBool = AtomicBool::new(false);

    // "Object Storage": sirve los bytes y delata si le llega la cabecera de máquina.
    let storage = Router::new().fallback(|req: Request| async move {
        if req.headers().contains_key("x-hub-token") {
            TOKEN_LEAKED.store(true, Ordering::SeqCst);
        }
        ([("content-type", "application/pdf")], Body::from(&b"%PDF-1.7 bytes"[..]))
    });
    let storage_listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let storage_addr = storage_listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(storage_listener, storage).await.unwrap() });

    // Mini-Cloud: responde con la URL firmada del almacenamiento simulado.
    let signed = format!("http://{storage_addr}/erplora-hubs/hubs/h1/a.pdf?X-Amz-Signature=abc");
    let cloud = Router::new().fallback(move || {
        let signed = signed.clone();
        async move { Json(json!({ "url": signed })) }
    });
    let cloud_listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let cloud_addr = cloud_listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(cloud_listener, cloud).await.unwrap() });

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-media");
    rt.ensure_system_tables().await.unwrap();
    let user_id = rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&user_id, 3600, None).await.unwrap();
    let cfg = HubConfig {
        hub_id: "hub-media".into(),
        cloud_base_url: format!("http://{cloud_addr}"),
        module_cache: std::env::temp_dir().join("erplora-media-raw-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-media-raw-scratch"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
    };
    let router = app(AppState::with_config(rt, cfg));

    let response = send(
        &router,
        Request::builder()
            .uri("/api/media/raw?path=a.pdf")
            .header("x-hub-session", &session)
            .body(Body::empty())
            .unwrap(),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    assert_eq!(&body[..], b"%PDF-1.7 bytes");
    assert!(
        !TOKEN_LEAKED.load(Ordering::SeqCst),
        "el token de máquina del hub no puede llegar al almacenamiento"
    );
}
