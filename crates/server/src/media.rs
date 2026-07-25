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
//!   GET    /api/media?folder=<rel>      → { ok, data: { folders[], files[], path[] } }
//!   GET    /api/media/raw?path=<rel>    → bytes del fichero (inline)
//!   POST   /api/media/upload            → multipart `folder` + `files`
//!   DELETE /api/media?path=<rel>        → borra un fichero
//!   POST   /api/media/folder            → json { parent, name } crea sub-carpeta

use axum::body::Body;
use axum::extract::{Multipart, Query, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::{Component, Path, PathBuf};

use crate::{auth, AppState};

fn unauthorized(error: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": error.message() })),
    )
        .into_response()
}

async fn require_user(st: &AppState, headers: &HeaderMap) -> Result<(), Response> {
    let rt = st.runtime.lock().await;
    auth::require_user_session(headers, &st.config, &rt)
        .await
        .map(|_| ())
        .map_err(unauthorized)
}

async fn require_admin(st: &AppState, headers: &HeaderMap) -> Result<(), Response> {
    let rt = st.runtime.lock().await;
    auth::require_admin_session(headers, &st.config, &rt)
        .await
        .map(|_| ())
        .map_err(unauthorized)
}

// ─────────────────────────── Proxy Hub→Cloud (Object Storage) ───────────────────────────
//
// La carpeta media vive en Object Storage y el Hub **no** habla con S3: delega en el Cloud
// (ADR-0047), igual que el módulo backup. El contrato hacia el frontend es el MISMO; el Hub solo
// firma la petición con las cabeceras de máquina y mapea la respuesta.

/// Cabeceras de autenticación de máquina (`X-Hub-Token` + `X-Hub-Id`) para hablar con el Cloud.
/// `None` si el hub no está enrolado (sin token de máquina) → no se puede proxyar.
fn cloud_headers(st: &AppState) -> Option<Vec<(&'static str, String)>> {
    let token = st.machine_token()?;
    Some(
        cloud_client::Auth::HubToken {
            hub_id: st.hub_id(),
            token,
        }
        .headers(),
    )
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
async fn cloud_list(st: &AppState, folder: &str) -> Response {
    let Some(headers) = cloud_headers(st) else {
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
                    json!({
                        "id": f.get("path").cloned().unwrap_or(Value::Null),
                        "name": f.get("name").cloned().unwrap_or(Value::Null),
                        "ext": f.get("ext").cloned().unwrap_or(Value::Null),
                        "sizeLabel": human_bytes(bytes),
                        "modified": modified,
                        "url": f.get("url").cloned().unwrap_or(Value::Null),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    let used = raw
        .pointer("/usage/used_bytes")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let data = json!({
        "folders": raw.get("folders").cloned().unwrap_or_else(|| json!([])),
        "files": files,
        "path": raw.get("path").cloned().unwrap_or_else(|| json!([])),
        // Bucket por hub sin cuota dura (ADR-0047): solo lo usado, sin barra.
        "quota": { "usedLabel": human_bytes(used), "unlimited": true },
    });
    Json(json!({ "ok": true, "data": data })).into_response()
}

/// Reenvía un multipart de subida al Cloud (`POST …/media/`).
async fn cloud_upload(st: &AppState, mut mp: Multipart) -> Response {
    let Some(headers) = cloud_headers(st) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let mut form = reqwest::multipart::Form::new();
    let mut has_file = false;
    while let Ok(Some(field)) = mp.next_field().await {
        match field.name() {
            Some("folder") => {
                form = form.text("folder", field.text().await.unwrap_or_default());
            }
            Some("files") => {
                let fname = field
                    .file_name()
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| "file".to_string());
                let Ok(data) = field.bytes().await else {
                    continue;
                };
                let part = reqwest::multipart::Part::bytes(data.to_vec()).file_name(fname);
                form = form.part("files", part);
                has_file = true;
            }
            _ => {}
        }
    }
    if !has_file {
        return err(StatusCode::BAD_REQUEST, "no se enviaron ficheros");
    }
    let url = format!("{}/api/v1/hub/device/media/", cloud_base(st));
    let mut r = st.http.post(&url).multipart(form);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(_) => err(StatusCode::BAD_GATEWAY, "el Cloud rechazó la subida"),
        Err(e) => err(StatusCode::BAD_GATEWAY, &e.to_string()),
    }
}

/// `DELETE …/media/?path=` en el Cloud.
async fn cloud_delete(st: &AppState, path: &str) -> Response {
    let Some(headers) = cloud_headers(st) else {
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

/// `POST …/media/folder/` en el Cloud.
async fn cloud_create_folder(st: &AppState, parent: &str, name: &str) -> Response {
    let Some(headers) = cloud_headers(st) else {
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
async fn cloud_raw(st: &AppState, path: &str) -> Response {
    let Some(headers) = cloud_headers(st) else {
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
    let bytes = match resp.bytes().await {
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
    if let Err(response) = require_user(&st, &headers).await {
        return response;
    }
    cloud_list(&st, &q.folder).await
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
    if let Err(response) = require_user(&st, &headers).await {
        return response;
    }
    cloud_raw(&st, &q.path).await
}

// ─────────────────────────── POST /api/media/upload ───────────────────────────

/// Sube uno o varios ficheros a la carpeta `folder` (campo de texto del multipart), proxyando el
/// multipart al Cloud.
pub async fn media_upload(
    State(st): State<AppState>,
    headers: HeaderMap,
    mp: Multipart,
) -> Response {
    if let Err(response) = require_admin(&st, &headers).await {
        return response;
    }
    cloud_upload(&st, mp).await
}

// ─────────────────────────── DELETE /api/media ───────────────────────────

/// Borra un fichero de `media/`, proxyando al Cloud.
pub async fn media_delete(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<PathQuery>,
) -> Response {
    if let Err(response) = require_admin(&st, &headers).await {
        return response;
    }
    cloud_delete(&st, &q.path).await
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
    if let Err(response) = require_admin(&st, &headers).await {
        return response;
    }
    cloud_create_folder(&st, &req.parent, &req.name).await
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
