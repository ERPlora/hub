//! `GET/POST/DELETE /api/media*` — gestor de la carpeta `media/` del hub (pantalla /files).
//!
//! `media/` es el path por defecto de TODOS los ficheros del hub: adjuntos de módulos, registros
//! de sistema (`_logs/`), monitor de actividad (`_system/`)… La navega el componente
//! `ok-file-manager` (OutfitKit) desde `hub/apps/web/src/views/FilesPage.vue` vía el cliente
//! `hub/apps/web/src/lib/media.ts`.
//!
//! Hub Cloud (Postgres-only, ADR-0154): la carpeta media vive en Object Storage y el Hub **no**
//! habla con S3. Cada endpoint es un **proxy autenticado Hub→Cloud→Object Storage** (ADR-0047):
//! reenvía la petición al Cloud con las cabeceras de máquina (`X-Hub-Token` + `X-Hub-Id`) y mapea
//! la respuesta al contrato del frontend. Sin token de máquina no se puede proxyar (502).
//!
//! Seguridad: listar/abrir exige sesión de usuario; subir, crear carpetas y borrar exige sesión
//! owner/admin. Una API key nunca accede al gestor de archivos. La validación de rutas
//! (anti path-traversal) la hace el Cloud, dueño del almacenamiento.
//!
//! Endpoints (contrato consumido por `lib/media.ts`):
//!   GET    /api/media?folder=<rel>      → { ok, data: { folders[], files[], path[], quota, policy } }
//!   GET    /api/media/raw?path=<rel>    → bytes del fichero (inline). El Cloud devuelve una URL
//!                                         firmada y la descarga la hace ESTE runtime: los buckets
//!                                         no tienen CORS, así que el navegador no puede leerla, y
//!                                         es lo que necesita el visor (ADR-0171).
//!   POST   /api/media/upload            → multipart `folder` + `files`
//!   DELETE /api/media?path=<rel>        → borra un fichero o una carpeta (con su contenido)
//!   POST   /api/media/folder            → json { parent, name } crea sub-carpeta
//!   POST   /api/media/rename            → json { path, name } renombra fichero o carpeta
//!
//! Qué puede hacer el USUARIO con cada ruta lo decide el módulo dueño de la carpeta
//! (`static_files.user_actions`, ADR-0172): por defecto solo ver y descargar. Ver `policy_for`.

use axum::body::Body;
use axum::extract::{Multipart, Path as AxumPath, Query, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;

use erplora_runtime::manifest::{StaticFilesDef, UserFileAction};
use erplora_runtime::Runtime;
use tokio::sync::Mutex;

use crate::{auth, AppState};

fn unauthorized(error: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": error.message() })),
    )
        .into_response()
}

type AuthenticatedTenant = (String, Arc<Mutex<Runtime>>);

async fn require_user(
    st: &AppState,
    headers: &HeaderMap,
) -> Result<AuthenticatedTenant, Response> {
    let hub_id = auth::hub_id(headers, &st.hub_id());
    let runtime = st
        .runtime_for(&hub_id)
        .await
        .map_err(crate::tenant_rejected)?;
    {
        let rt = runtime.lock().await;
        auth::require_user_session(headers, &st.config, &rt)
            .await
            .map_err(unauthorized)?;
    }
    Ok((hub_id, runtime))
}

async fn require_admin(
    st: &AppState,
    headers: &HeaderMap,
) -> Result<AuthenticatedTenant, Response> {
    let hub_id = auth::hub_id(headers, &st.hub_id());
    let runtime = st
        .runtime_for(&hub_id)
        .await
        .map_err(crate::tenant_rejected)?;
    {
        let rt = runtime.lock().await;
        auth::require_admin_session(headers, &st.config, &rt)
            .await
            .map_err(unauthorized)?;
    }
    Ok((hub_id, runtime))
}

// ─────────────────────────── Proxy Hub→Cloud (Object Storage) ───────────────────────────
//
// La carpeta media vive en Object Storage y el Hub **no** habla con S3: delega en el Cloud
// (ADR-0047), igual que el módulo backup. El contrato hacia el frontend es el MISMO; el Hub solo
// firma la petición con las cabeceras de máquina y mapea la respuesta.

/// Cabeceras de autenticación de máquina (`X-Hub-Token` + `X-Hub-Id`) para hablar con el Cloud.
/// `None` si el hub no está enrolado (sin token de máquina) → no se puede proxyar.
fn cloud_headers(st: &AppState, hub_id: &str) -> Option<Vec<(&'static str, String)>> {
    Some(auth::machine_auth_for(st, hub_id)?.headers())
}

/// Base del Cloud sin barra final.
fn cloud_base(st: &AppState) -> String {
    st.config.cloud_base_url.trim_end_matches('/').to_string()
}

/// ISO 8601 → "YYYY-MM-DD HH:MM" (el front muestra la cadena tal cual).
fn fmt_iso(s: &str) -> String {
    if s.len() >= 16 {
        s[..16].replace('T', " ")
    } else {
        s.to_string()
    }
}

// ─────────────────────────── Handlers de proxy al Cloud ───────────────────────────

/// `GET /api/v1/hub/device/media/?folder=` → mapea el shape RAW del Cloud al del frontend
/// (formatea bytes/fecha, quota "sin límite").
async fn cloud_list(
    st: &AppState,
    hub_id: &str,
    runtime: &Arc<Mutex<Runtime>>,
    folder: &str,
) -> Response {
    let Some(headers) = cloud_headers(st, hub_id) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let url = format!(
        "{}/api/v1/hub/device/media/?folder={}",
        cloud_base(st),
        pct_encode(folder)
    );
    let mut r = st.http.get(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    let resp = match r.send().await {
        Ok(x) => x,
        Err(e) => return err(StatusCode::BAD_GATEWAY, &e.to_string()),
    };
    if !resp.status().is_success() {
        return err(
            StatusCode::BAD_GATEWAY,
            "el Cloud rechazó el listado de media",
        );
    }
    let raw: Value = match resp.json().await {
        Ok(v) => v,
        Err(e) => return err(StatusCode::BAD_GATEWAY, &e.to_string()),
    };

    let files: Vec<Value> = raw
        .get("files")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .map(|f| {
                    let bytes = f.get("bytes").and_then(Value::as_u64).unwrap_or(0);
                    let modified = f
                        .get("modified")
                        .and_then(Value::as_str)
                        .map(fmt_iso)
                        .unwrap_or_default();
                    // La URL que ve el navegador es SIEMPRE la del runtime, nunca la firmada de
                    // Object Storage: los buckets no tienen CORS (el visor no podría leerla) y
                    // la firma caduca. El runtime es la autoridad del almacenamiento (ADR-0047).
                    let path = f.get("path").and_then(Value::as_str).unwrap_or_default();
                    json!({
                        "id": path,
                        "name": f.get("name").cloned().unwrap_or(Value::Null),
                        "ext": f.get("ext").cloned().unwrap_or(Value::Null),
                        "sizeLabel": human_bytes(bytes),
                        "modified": modified,
                        "url": format!("/api/media/raw?path={}", pct_encode(path)),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    let used = raw
        .pointer("/usage/used_bytes")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    // Política de la carpeta pedida: la UI pinta solo las acciones posibles (ADR-0172). No es la
    // autoridad — cada endpoint la revalida —, pero evita ofrecer un botón que va a dar 403.
    let policy = resolve_policy(runtime, folder).await;
    let data = json!({
        "folders": raw.get("folders").cloned().unwrap_or_else(|| json!([])),
        "files": files,
        "path": raw.get("path").cloned().unwrap_or_else(|| json!([])),
        // Bucket por hub sin cuota dura (ADR-0047): solo lo usado, sin barra.
        "quota": { "usedLabel": human_bytes(used), "unlimited": true },
        "policy": { "upload": policy.upload, "rename": policy.rename, "delete": policy.delete },
    });
    Json(json!({ "ok": true, "data": data })).into_response()
}

/// Reenvía un multipart de subida al Cloud (`POST …/media/`).
async fn cloud_upload(
    st: &AppState,
    hub_id: &str,
    runtime: &Arc<Mutex<Runtime>>,
    mut mp: Multipart,
) -> Response {
    let Some(headers) = cloud_headers(st, hub_id) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    // El multipart se recoge ENTERO antes de decidir: el orden de los campos no está garantizado
    // y la política depende de `folder`, así que no se puede empezar a reenviar y comprobar luego.
    let mut folder = String::new();
    let mut files: Vec<(String, Vec<u8>)> = Vec::new();
    while let Ok(Some(field)) = mp.next_field().await {
        match field.name() {
            Some("folder") => folder = field.text().await.unwrap_or_default(),
            Some("files") => {
                let fname = field
                    .file_name()
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| "file".to_string());
                let Ok(data) = field.bytes().await else {
                    continue;
                };
                files.push((fname, data.to_vec()));
            }
            _ => {}
        }
    }
    if let Err(response) = require_action(runtime, &folder, UserFileAction::Upload).await {
        return response;
    }
    if files.is_empty() {
        return err(StatusCode::BAD_REQUEST, "no se enviaron ficheros");
    }
    let normalized_folder = folder.trim_matches('/');
    let public_page_folder = is_public_page_folder(normalized_folder);
    if public_page_folder
        && files
            .iter()
            .any(|(name, _)| !is_safe_public_image_name(name))
    {
        return err(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "las páginas públicas solo admiten imágenes png, jpg, jpeg, gif o webp",
        );
    }
    let public_url = files.first().and_then(|(name, _)| {
        (public_page_folder && is_safe_public_image_name(name)).then(|| {
            let rel = format!("{normalized_folder}/{name}");
            format!("/files/{}", pct_encode(&rel))
        })
    });
    let mut form = reqwest::multipart::Form::new().text("folder", folder);
    for (fname, data) in files {
        form = form.part(
            "files",
            reqwest::multipart::Part::bytes(data).file_name(fname),
        );
    }
    let url = format!("{}/api/v1/hub/device/media/", cloud_base(st));
    let mut r = st.http.post(&url).multipart(form);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(match public_url {
            Some(url) => json!({
                "ok": true,
                "data": { "url": url, "file": { "url": url } },
            }),
            None => json!({ "ok": true }),
        })
        .into_response(),
        Ok(_) => err(StatusCode::BAD_GATEWAY, "el Cloud rechazó la subida"),
        Err(e) => err(StatusCode::BAD_GATEWAY, &e.to_string()),
    }
}

/// `DELETE …/media/?path=` en el Cloud.
async fn cloud_delete(st: &AppState, hub_id: &str, path: &str) -> Response {
    let Some(headers) = cloud_headers(st, hub_id) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let url = format!(
        "{}/api/v1/hub/device/media/?path={}",
        cloud_base(st),
        pct_encode(path)
    );
    let mut r = st.http.delete(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(resp) => err(
            StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY),
            "el Cloud no pudo borrar",
        ),
        Err(e) => err(StatusCode::BAD_GATEWAY, &e.to_string()),
    }
}

/// `POST …/media/rename/` en el Cloud (que hace el copy+delete sobre Object Storage).
async fn cloud_rename(st: &AppState, hub_id: &str, path: &str, name: &str) -> Response {
    let Some(headers) = cloud_headers(st, hub_id) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let url = format!("{}/api/v1/hub/device/media/rename/", cloud_base(st));
    let mut r = st.http.post(&url).json(&json!({ "path": path, "name": name }));
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(resp) => err(
            StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY),
            "el Cloud no pudo renombrar",
        ),
        Err(e) => err(StatusCode::BAD_GATEWAY, &e.to_string()),
    }
}

/// `POST …/media/folder/` en el Cloud.
async fn cloud_create_folder(st: &AppState, hub_id: &str, parent: &str, name: &str) -> Response {
    let Some(headers) = cloud_headers(st, hub_id) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let url = format!("{}/api/v1/hub/device/media/folder/", cloud_base(st));
    let mut r = st
        .http
        .post(&url)
        .json(&json!({ "parent": parent, "name": name }));
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(_) => err(StatusCode::BAD_GATEWAY, "el Cloud no pudo crear la carpeta"),
        Err(e) => err(StatusCode::BAD_GATEWAY, &e.to_string()),
    }
}

/// `GET …/media/raw?path=` en el Cloud → reenvía los bytes del fichero (inline) al cliente. Lee a
/// memoria (los ficheros de media son modestos: logs, PDFs, imágenes) y fija `Content-Type` por
/// extensión, igual que hacía la rama local.
async fn cloud_raw(st: &AppState, hub_id: &str, path: &str) -> Response {
    let Some(headers) = cloud_headers(st, hub_id) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let url = format!(
        "{}/api/v1/hub/device/media/raw?path={}",
        cloud_base(st),
        pct_encode(path)
    );
    let mut r = st.http.get(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    let resp = match r.send().await {
        Ok(x) => x,
        Err(e) => return err(StatusCode::BAD_GATEWAY, &e.to_string()),
    };
    if !resp.status().is_success() {
        return err(StatusCode::NOT_FOUND, "fichero no encontrado");
    }
    // El Cloud responde `{ url }` con una firma temporal de Object Storage. La descarga la hace
    // el runtime, no el navegador: los buckets no tienen CORS (un `fetch` desde el visor se cae) y
    // la firma caduca. Se pide con un cliente LIMPIO —sin las cabeceras de máquina del hub—:
    // `X-Hub-Token` es un secreto del hub y no puede viajar a un tercero (ADR-0003).
    let signed = match resp.json::<Value>().await {
        Ok(v) => v.get("url").and_then(Value::as_str).unwrap_or_default().to_string(),
        Err(e) => return err(StatusCode::BAD_GATEWAY, &e.to_string()),
    };
    if signed.is_empty() {
        return err(StatusCode::BAD_GATEWAY, "el Cloud no devolvió la URL del fichero");
    }
    let object = match st.http.get(&signed).send().await {
        Ok(o) if o.status().is_success() => o,
        Ok(_) => return err(StatusCode::NOT_FOUND, "fichero no encontrado"),
        Err(e) => return err(StatusCode::BAD_GATEWAY, &e.to_string()),
    };
    let bytes = match object.bytes().await {
        Ok(b) => b,
        Err(e) => return err(StatusCode::BAD_GATEWAY, &e.to_string()),
    };
    let name = file_name_str(Path::new(path));
    Response::builder()
        .header(header::CONTENT_TYPE, content_type(&name))
        .header(
            header::CONTENT_DISPOSITION,
            format!("inline; filename=\"{}\"", name.replace('"', "")),
        )
        .body(Body::from(bytes.to_vec()))
        .unwrap_or_else(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "respuesta inválida"))
}

/// GET /files/pages/*path — media EXCLUSIVA de las páginas públicas. No acepta `..`, prefijos
/// alternativos ni rutas absolutas; jamás abre `_logs`, adjuntos de módulos u otros ficheros del hub.
/// El runtime descarga la URL firmada con su credencial de máquina y devuelve solo los bytes.
pub async fn public_page_media(
    State(st): State<AppState>,
    headers: HeaderMap,
    AxumPath(path): AxumPath<String>,
) -> Response {
    let (hub_id, _, _) = match crate::public::resolve_public_tenant(&st, &headers).await {
        Ok(resolved) => resolved,
        Err(response) => return response,
    };
    let relative = Path::new(&path);
    let valid = !path.is_empty()
        && !relative.is_absolute()
        && relative
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
        && is_safe_public_image_name(file_name_str(relative).as_str());
    if !valid {
        return err(StatusCode::NOT_FOUND, "fichero no encontrado");
    }
    let mut response = cloud_raw(&st, &hub_id, &format!("pages/{path}")).await;
    response.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        "nosniff".parse().expect("static header"),
    );
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        "public, max-age=3600".parse().expect("static header"),
    );
    response
}

// ─────────────────────────── GET /api/media ───────────────────────────

#[derive(Deserialize)]
pub struct FolderQuery {
    #[serde(default)]
    folder: String,
}

/// Lista el árbol de carpetas + los ficheros de la carpeta pedida (raíz si `folder` vacío).
pub async fn media_list(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<FolderQuery>,
) -> Response {
    let (hub_id, runtime) = match require_user(&st, &headers).await {
        Ok(tenant) => tenant,
        Err(response) => return response,
    };
    cloud_list(&st, &hub_id, &runtime, &q.folder).await
}

// ─────────────────────────── GET /api/media/raw ───────────────────────────

#[derive(Deserialize)]
pub struct PathQuery {
    path: String,
}

/// Sirve el contenido de un fichero de `media/` (inline), proxyando al Cloud.
pub async fn media_raw(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<PathQuery>,
) -> Response {
    let (hub_id, _) = match require_user(&st, &headers).await {
        Ok(tenant) => tenant,
        Err(response) => return response,
    };
    cloud_raw(&st, &hub_id, &q.path).await
}

// ─────────────────────────── POST /api/media/upload ───────────────────────────

/// Sube uno o varios ficheros a la carpeta `folder` (campo de texto del multipart), proxyando el
/// multipart al Cloud.
pub async fn media_upload(
    State(st): State<AppState>,
    headers: HeaderMap,
    mp: Multipart,
) -> Response {
    let (hub_id, runtime) = match require_admin(&st, &headers).await {
        Ok(tenant) => tenant,
        Err(response) => return response,
    };
    cloud_upload(&st, &hub_id, &runtime, mp).await
}

// ─────────────────────────── DELETE /api/media ───────────────────────────

/// Borra un fichero de `media/`, proxyando al Cloud.
pub async fn media_delete(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<PathQuery>,
) -> Response {
    let (hub_id, runtime) = match require_admin(&st, &headers).await {
        Ok(tenant) => tenant,
        Err(response) => return response,
    };
    if let Err(response) = require_action(&runtime, &q.path, UserFileAction::Delete).await {
        return response;
    }
    cloud_delete(&st, &hub_id, &q.path).await
}

// ─────────────────────────── POST /api/media/folder ───────────────────────────

#[derive(Deserialize)]
pub struct CreateFolderReq {
    #[serde(default)]
    parent: String,
    name: String,
}

/// Crea una sub-carpeta `name` dentro de `parent`, proxyando al Cloud (que valida el nombre).
pub async fn media_create_folder(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CreateFolderReq>,
) -> Response {
    let (hub_id, runtime) = match require_admin(&st, &headers).await {
        Ok(tenant) => tenant,
        Err(response) => return response,
    };
    // Crear una subcarpeta es escribir dentro del padre → misma acción que subir.
    if let Err(response) = require_action(&runtime, &req.parent, UserFileAction::Upload).await {
        return response;
    }
    cloud_create_folder(&st, &hub_id, &req.parent, &req.name).await
}

// ─────────────────────────── POST /api/media/rename ───────────────────────────

#[derive(Deserialize)]
pub struct RenameReq {
    /// Ruta relativa (a `media/`) del fichero o carpeta a renombrar.
    path: String,
    /// **Nombre** nuevo, no una ruta: renombrar no mueve nada de sitio.
    name: String,
}

/// `true` si `name` es un nombre de un solo segmento utilizable en disco y en Object Storage.
///
/// Deliberadamente NO acepta rutas: si `name` pudiera contener `/` o `..`, se podría sacar un
/// fichero de una carpeta bloqueada (VeriFactu) a una libre y borrarlo allí, saltándose la
/// política entera. Renombrar cambia el nombre, nunca el sitio.
fn valid_file_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 255
        && name != "."
        && name != ".."
        && !name.contains('/')
        && !name.contains('\\')
        && !name.chars().any(char::is_control)
}

/// Renombra un fichero o una carpeta dentro de `media/` (ADR-0172), proxyando al Cloud.
pub async fn media_rename(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<RenameReq>,
) -> Response {
    let (hub_id, runtime) = match require_admin(&st, &headers).await {
        Ok(tenant) => tenant,
        Err(response) => return response,
    };
    if !valid_file_name(&req.name) {
        return err(
            StatusCode::BAD_REQUEST,
            "el nombre nuevo no es válido (debe ser un nombre, no una ruta)",
        );
    }
    if req.path.trim_matches('/').is_empty() {
        return err(StatusCode::BAD_REQUEST, "falta la ruta a renombrar");
    }
    if let Err(response) = require_action(&runtime, &req.path, UserFileAction::Rename).await {
        return response;
    }
    cloud_rename(&st, &hub_id, &req.path, &req.name).await
}

// ─────────────────────────── Helpers ───────────────────────────

/// Une `rel` (ruta relativa) bajo `root` descartando cualquier intento de salir del root: solo se
/// aceptan componentes normales; `..`, raíz absoluta y prefijos (p.ej. `C:\`) se rechazan
/// devolviendo `None`.
/// `pub(crate)`: lo reutiliza el import de blueprints (`export_import.rs`) al copiar `media/*`.
pub(crate) fn safe_join(root: &Path, rel: &str) -> Option<PathBuf> {
    let mut out = root.to_path_buf();
    for comp in Path::new(rel).components() {
        match comp {
            Component::Normal(c) => out.push(c),
            Component::CurDir => {}
            _ => return None,
        }
    }
    Some(out)
}

/// Componente final del path (nombre de fichero); cadena vacía si no tiene.
fn file_name_str(path: &Path) -> String {
    path.file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default()
}

/// Extensión en minúsculas (sin punto); cadena vacía si no tiene.
fn ext_of(name: &str) -> String {
    Path::new(name)
        .extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .unwrap_or_default()
}

fn is_public_page_folder(folder: &str) -> bool {
    let path = Path::new(folder);
    !folder.is_empty()
        && !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
        && path
            .components()
            .next()
            .is_some_and(|component| component.as_os_str() == "pages")
}

fn is_safe_public_image_name(name: &str) -> bool {
    let path = Path::new(name);
    path.components().count() == 1
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
        && matches!(ext_of(name).as_str(), "png" | "jpg" | "jpeg" | "gif" | "webp")
}

/// `Content-Type` por extensión (mapa mínimo; el resto cae a octet-stream).
fn content_type(name: &str) -> &'static str {
    match ext_of(name).as_str() {
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "svg" => "image/svg+xml",
        "txt" | "log" => "text/plain; charset=utf-8",
        "csv" => "text/csv; charset=utf-8",
        "json" => "application/json",
        "html" | "htm" => "text/html; charset=utf-8",
        "zip" => "application/zip",
        _ => "application/octet-stream",
    }
}

/// Percent-encoding de un valor de query: deja sin tocar los no-reservados y `/`; codifica el resto
/// (en particular espacio→`%20` y `+`→`%2B`, para que `serde_urlencoded` lo decodifique bien).
fn pct_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// Bytes legibles con coma decimal (es-ES): 642 MB, 1,2 GB, 8,6 MB. (Copia local del de `system.rs`.)
fn human_bytes(bytes: u64) -> String {
    const KIB: f64 = 1024.0;
    const MIB: f64 = KIB * 1024.0;
    const GIB: f64 = MIB * 1024.0;
    let b = bytes as f64;
    if b >= GIB {
        format!("{} GB", fmt_decimal(b / GIB, 1))
    } else if b >= MIB {
        let mb = b / MIB;
        format!("{} MB", fmt_decimal(mb, if mb >= 100.0 { 0 } else { 1 }))
    } else if b >= KIB {
        format!("{} KB", fmt_decimal(b / KIB, 0))
    } else {
        format!("{bytes} B")
    }
}

fn fmt_decimal(value: f64, decimals: usize) -> String {
    let s = format!("{value:.decimals$}");
    let s = if decimals > 0 {
        s.trim_end_matches('0').trim_end_matches('.').to_string()
    } else {
        s
    };
    s.replace('.', ",")
}

/// Respuesta de error en el envelope estándar (`{ ok:false, error:{ message } }`).
fn err(code: StatusCode, msg: &str) -> Response {
    (
        code,
        Json(json!({ "ok": false, "error": { "message": msg } })),
    )
        .into_response()
}

// ─────────────────────────── Política de acciones del usuario (ADR-0172) ───────────────────────────
//
// Ver y descargar es siempre posible con sesión. Lo que MODIFICA (subir, renombrar, borrar) depende
// de quién sea el dueño de la carpeta:
//
//   `_logs/`, `_system/`      → solo lectura. Son el rastro del propio Hub y tienen retención
//                               automática; borrarlos a mano solo serviría para taparlo.
//   `modules/<folder>/…`      → lo que declare ESE módulo en `static_files.user_actions`.
//                               Ausente = solo lectura (el default deliberado: los XML de
//                               VeriFactu son inalterables por ley). No hay override de admin.
//   `modules/` (la raíz)      → solo lectura: borrarla se llevaría los ficheros de todos.
//   cualquier otra            → gestión completa (es la carpeta de una persona).
//
// El módulo NO queda limitado por esto: sigue escribiendo por `ModuleStorage`. La política habla
// de lo que puede hacer una PERSONA desde `/files`.

/// Raíz común de las carpetas privadas de módulo dentro de `media/` (ADR-0151).
const MODULES_ROOT: &str = "modules";

/// Carpetas del propio Hub: se ven y se descargan, no se tocan.
const RESERVED_ROOTS: [&str; 2] = ["_logs", "_system"];

/// Qué puede hacer el usuario sobre una ruta de `media/`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MediaPolicy {
    pub upload: bool,
    pub rename: bool,
    pub delete: bool,
}

impl MediaPolicy {
    pub const FULL: Self = Self { upload: true, rename: true, delete: true };
    pub const READ_ONLY: Self = Self { upload: false, rename: false, delete: false };

    fn allows(&self, action: UserFileAction) -> bool {
        match action {
            UserFileAction::Upload => self.upload,
            UserFileAction::Rename => self.rename,
            UserFileAction::Delete => self.delete,
        }
    }
}

impl From<&StaticFilesDef> for MediaPolicy {
    fn from(def: &StaticFilesDef) -> Self {
        Self {
            upload: def.allows(UserFileAction::Upload),
            rename: def.allows(UserFileAction::Rename),
            delete: def.allows(UserFileAction::Delete),
        }
    }
}

/// Primer segmento de la ruta relativa (`""` si está vacía).
fn first_segment(rel: &str) -> &str {
    rel.trim_matches('/').split('/').next().unwrap_or("")
}

/// Nombre de la carpeta de módulo dueña de la ruta, si vive bajo `modules/<folder>/…`.
/// `modules` a secas no pertenece a ningún módulo.
pub fn module_folder_of(rel: &str) -> Option<&str> {
    let trimmed = rel.trim_matches('/');
    let rest = trimmed.strip_prefix(MODULES_ROOT)?.strip_prefix('/')?;
    let folder = rest.split('/').next().unwrap_or("");
    (!folder.is_empty()).then_some(folder)
}

/// Política de la ruta. `owner` es el `static_files` del módulo dueño (lo resuelve el llamante
/// contra el registro de módulos instalados); `None` cuando no hay módulo dueño instalado.
pub fn policy_for(rel: &str, owner: Option<&StaticFilesDef>) -> MediaPolicy {
    if RESERVED_ROOTS.contains(&first_segment(rel)) {
        return MediaPolicy::READ_ONLY;
    }
    if first_segment(rel) == MODULES_ROOT {
        // Dentro del árbol de módulos manda el manifest; sin manifest (raíz o módulo
        // desinstalado) nadie ha autorizado nada.
        return owner.map(MediaPolicy::from).unwrap_or(MediaPolicy::READ_ONLY);
    }
    MediaPolicy::FULL
}

/// Resuelve la política de una ruta consultando el registro de módulos instalados.
async fn resolve_policy(runtime: &Arc<Mutex<Runtime>>, rel: &str) -> MediaPolicy {
    let Some(folder) = module_folder_of(rel) else {
        return policy_for(rel, None);
    };
    let rt = runtime.lock().await;
    let owner = rt
        .registry()
        .installed
        .iter()
        .find_map(|m| m.static_files.as_ref().filter(|s| s.folder == folder))
        .cloned();
    policy_for(rel, owner.as_ref())
}

/// Corta la petición con 403 si la política de `rel` no concede `action`.
async fn require_action(
    runtime: &Arc<Mutex<Runtime>>,
    rel: &str,
    action: UserFileAction,
) -> Result<(), Response> {
    if resolve_policy(runtime, rel).await.allows(action) {
        return Ok(());
    }
    Err(err(
        StatusCode::FORBIDDEN,
        "esta carpeta es de solo lectura: su módulo no permite esa acción",
    ))
}

#[cfg(test)]
mod policy_tests {
    use super::*;
    use erplora_runtime::manifest::StaticFilesDef;

    fn declaring(actions: &[&str]) -> StaticFilesDef {
        StaticFilesDef {
            folder: "verifactu".into(),
            user_actions: actions.iter().map(|s| (*s).to_string()).collect(),
        }
    }

    #[test]
    fn a_folder_of_the_user_stays_fully_manageable() {
        // Lo que sube una persona a su carpeta es suyo: sin módulo dueño no hay candado.
        assert_eq!(policy_for("", None), MediaPolicy::FULL);
        assert_eq!(policy_for("facturas", None), MediaPolicy::FULL);
        assert_eq!(policy_for("facturas/2026/a.pdf", None), MediaPolicy::FULL);
    }

    #[test]
    fn the_hubs_own_folders_are_read_only_even_for_an_admin() {
        // `_logs` ya tiene retención automática; borrarlos a mano solo sirve para tapar el rastro.
        for path in ["_logs", "_logs/hub.2026-07-31", "_system", "_system/activity.json"] {
            assert_eq!(policy_for(path, None), MediaPolicy::READ_ONLY, "{path}");
        }
    }

    #[test]
    fn a_module_folder_is_read_only_unless_the_module_says_otherwise() {
        let def = declaring(&[]);
        assert_eq!(
            policy_for("modules/verifactu/xml/rec-1.xml", Some(&def)),
            MediaPolicy::READ_ONLY,
        );
    }

    #[test]
    fn a_module_grants_exactly_what_it_declared() {
        let def = declaring(&["upload", "delete"]);
        let policy = policy_for("modules/verifactu/xml/rec-1.xml", Some(&def));
        assert!(policy.upload);
        assert!(policy.delete);
        assert!(!policy.rename, "rename no se declaró → no se concede");
    }

    #[test]
    fn an_orphan_module_folder_is_read_only() {
        // Desinstalar un módulo NO borra sus ficheros (ADR-0151). Sin manifest que hable por
        // ellos, nadie ha autorizado tocarlos.
        assert_eq!(
            policy_for("modules/desaparecido/x.pdf", None),
            MediaPolicy::READ_ONLY,
        );
    }

    #[test]
    fn the_modules_root_itself_cannot_be_renamed_or_deleted() {
        // Borrar `modules/` se llevaría por delante los ficheros de TODOS los módulos.
        assert_eq!(policy_for("modules", None), MediaPolicy::READ_ONLY);
    }

    #[test]
    fn identifies_the_owning_module_folder() {
        assert_eq!(module_folder_of("modules/verifactu/xml/a.xml"), Some("verifactu"));
        assert_eq!(module_folder_of("modules/verifactu"), Some("verifactu"));
        assert_eq!(module_folder_of("modules"), None);
        assert_eq!(module_folder_of("facturas/modules/x"), None);
        assert_eq!(module_folder_of(""), None);
    }

    #[test]
    fn public_pages_only_accept_safe_raster_images() {
        assert!(is_public_page_folder("pages/menu"));
        assert!(!is_public_page_folder("pages/../private"));
        assert!(!is_public_page_folder("other/pages"));
        assert!(is_safe_public_image_name("plato.WEBP"));
        assert!(is_safe_public_image_name("foto.jpeg"));
        for unsafe_name in ["x.svg", "x.html", "x.pdf", "../x.png", "folder/x.png"] {
            assert!(!is_safe_public_image_name(unsafe_name), "{unsafe_name}");
        }
    }
}
