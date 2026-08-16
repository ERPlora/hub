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
//!   POST   /api/media/move              → json { from, to } mueve fichero o carpeta
//!
//! Qué puede hacer el USUARIO con cada ruta lo decide el módulo dueño de la carpeta
//! (`static_files.user_actions`, ADR-0172): por defecto solo ver y descargar. Ver `policy_for`.

use axum::body::Body;
use axum::extract::{Multipart, Query, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::{json, Value};
use std::future::Future;
use std::path::{Component, Path};

use erplora_runtime::manifest::{StaticFilesDef, UserFileAction};

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
    let policy = resolve_policy(st, folder).await;
    // Árbol de carpetas decorado con `readOnly` por nodo: una carpeta es readOnly cuando su módulo
    // dueño no concede ninguna acción de modificación (carpetas reservadas del hub `_logs/_system`,
    // `modules/` raíz o un módulo que no opte en `static_files.user_actions`). La UI lo usa para
    // marcarlas como no arrastrables y no receptoras de drops (ADR-0172, arrastrar-y-soltar).
    let folders = decorate_folders(
        raw.get("folders").cloned().unwrap_or_else(|| json!([])),
        st,
    )
    .await;
    let data = json!({
        "folders": folders,
        "files": files,
        "path": raw.get("path").cloned().unwrap_or_else(|| json!([])),
        // Bucket por hub sin cuota dura (ADR-0047): solo lo usado, sin barra.
        "quota": { "usedLabel": human_bytes(used), "unlimited": true },
        "policy": { "upload": policy.upload, "rename": policy.rename, "delete": policy.delete },
    });
    Json(json!({ "ok": true, "data": data })).into_response()
}

/// Reenvía un multipart de subida al Cloud (`POST …/media/`).
async fn cloud_upload(st: &AppState, mut mp: Multipart) -> Response {
    let Some(headers) = cloud_headers(st) else {
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
    if let Err(response) = require_action(st, &folder, UserFileAction::Upload).await {
        return response;
    }
    if files.is_empty() {
        return err(StatusCode::BAD_REQUEST, "no se enviaron ficheros");
    }
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

/// `POST …/media/rename/` en el Cloud (que hace el copy+delete sobre Object Storage).
async fn cloud_rename(st: &AppState, path: &str, name: &str) -> Response {
    let Some(headers) = cloud_headers(st) else {
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

/// Cap on simultaneous media object downloads (hub#759). A catalog page mounts ~300 image URLs
/// at once; each in-flight download holds network buffers in a 96 MiB container, so the burst
/// queues here in groups instead of stacking up. The value is deliberately small: media files are
/// modest (logs, PDFs, images) and each download completes fast, so queued requests drain quickly.
pub const MAX_CONCURRENT_MEDIA_FETCHES: usize = 8;

/// Hard cap on the size of a single media object served through the raw proxy (hub#759). Media
/// files are modest (logs, PDFs, catalog images); anything bigger than this cannot be safely
/// relayed by a 96 MiB container and is refused (413) — upfront when the size is declared, or by
/// aborting the stream when it is not.
pub const MAX_MEDIA_OBJECT_BYTES: u64 = 25 * 1024 * 1024;

/// `GET …/media/raw?path=` en el Cloud → **streams** the file bytes (inline) to the client and
/// sets `Content-Type` by extension.
///
/// Memory discipline (hub#759): this proxy used to buffer each object fully in RAM with no
/// concurrency bound — a catalog burst of ~300 images was enough to OOM the 96 MiB container
/// (exit 137). Three mechanisms bound it now: a semaphore on simultaneous downloads (acquired
/// before any network I/O and held until the response body is fully drained), chunked streaming
/// instead of `bytes()`, and a per-object size cap ([`MAX_MEDIA_OBJECT_BYTES`]).
async fn cloud_raw(st: &AppState, path: &str) -> Response {
    // The permit gates the WHOLE pipeline (Cloud signing call + object download + body relay).
    // `acquire_owned` queues excess requests instead of shedding them; the semaphore is never
    // closed, so an `Err` can only mean shutdown.
    let Ok(permit) = st.media_fetch_limiter.clone().acquire_owned().await else {
        return err(StatusCode::SERVICE_UNAVAILABLE, "media limiter closed");
    };
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
    // When the size is declared, refuse an oversized object BEFORE downloading a single byte.
    if object
        .content_length()
        .is_some_and(|len| len > MAX_MEDIA_OBJECT_BYTES)
    {
        return err(
            StatusCode::PAYLOAD_TOO_LARGE,
            "media object exceeds the size cap",
        );
    }
    let name = file_name_str(Path::new(path));
    // Relay the object chunk by chunk instead of materializing it: memory per request is one
    // chunk, not one file. The closure owns `permit` so it is released only when the response
    // body is dropped (fully drained or the client went away), keeping the concurrency bound
    // true for the whole download, not just this function call. `total` re-enforces the size
    // cap mid-stream for objects that did not declare a length: exceeding it aborts the body.
    let mut total: u64 = 0;
    let stream = object.bytes_stream().map(move |chunk| {
        let _held_until_drained = &permit;
        let chunk = chunk.map_err(axum::BoxError::from)?;
        total += chunk.len() as u64;
        if total > MAX_MEDIA_OBJECT_BYTES {
            return Err(axum::BoxError::from(std::io::Error::other(
                "media object exceeds the size cap",
            )));
        }
        Ok::<_, axum::BoxError>(chunk)
    });
    Response::builder()
        .header(header::CONTENT_TYPE, content_type(&name))
        .header(
            header::CONTENT_DISPOSITION,
            format!("inline; filename=\"{}\"", name.replace('"', "")),
        )
        .body(Body::from_stream(stream))
        .unwrap_or_else(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "respuesta inválida"))
}

/// `POST …/media/move/` en el Cloud (que hace el copy+delete sobre Object Storage). Mueve un
/// fichero o carpeta de `from` al destino `to` (ambos relativos a `media/`).
async fn cloud_move(st: &AppState, from: &str, to: &str) -> Response {
    let Some(headers) = cloud_headers(st) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let url = format!("{}/api/v1/hub/device/media/move/", cloud_base(st));
    let mut r = st.http.post(&url).json(&json!({ "from": from, "to": to }));
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(resp) => err(
            StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY),
            "el Cloud no pudo mover",
        ),
        Err(e) => err(StatusCode::BAD_GATEWAY, &e.to_string()),
    }
}

/// Recorre el árbol de carpetas y añade `readOnly: true` a cada nodo cuya política no conceda
/// ninguna acción de modificación. El `id` de cada carpeta es su ruta relativa; la política se
/// resuelve contra el registro de módulos instalados.
fn decorate_folders(folders: Value, st: &AppState) -> std::pin::Pin<Box<dyn Future<Output = Value> + Send + '_>> {
    Box::pin(async move {
        let Some(arr) = folders.as_array().cloned() else {
            return folders;
        };
        let mut out = Vec::with_capacity(arr.len());
        for mut node in arr {
            if let Some(obj) = node.as_object_mut() {
                if let Some(id) = obj.get("id").and_then(Value::as_str) {
                    let policy = resolve_policy(st, id).await;
                    let read_only = !policy.upload && !policy.rename && !policy.delete;
                    obj.insert("readOnly".into(), json!(read_only));
                }
                if let Some(children) = obj.get("children").cloned() {
                    let decorated = decorate_folders(children, st).await;
                    obj.insert("children".into(), decorated);
                }
            }
            out.push(node);
        }
        Value::Array(out)
    })
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
    if let Err(response) = require_action(&st, &q.path, UserFileAction::Delete).await {
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
    // Crear una subcarpeta es escribir dentro del padre → misma acción que subir.
    if let Err(response) = require_action(&st, &req.parent, UserFileAction::Upload).await {
        return response;
    }
    cloud_create_folder(&st, &req.parent, &req.name).await
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
    if let Err(response) = require_admin(&st, &headers).await {
        return response;
    }
    if !valid_file_name(&req.name) {
        return err(
            StatusCode::BAD_REQUEST,
            "el nombre nuevo no es válido (debe ser un nombre, no una ruta)",
        );
    }
    if req.path.trim_matches('/').is_empty() {
        return err(StatusCode::BAD_REQUEST, "falta la ruta a renombrar");
    }
    if let Err(response) = require_action(&st, &req.path, UserFileAction::Rename).await {
        return response;
    }
    cloud_rename(&st, &req.path, &req.name).await
}

// ─────────────────────────── POST /api/media/move ───────────────────────────

#[derive(Deserialize)]
pub struct MoveReq {
    /// Ruta relativa (a `media/`) del fichero o carpeta a mover.
    from: String,
    /// Carpeta destino (relativa a `media/`; `""` = raíz) donde reubicarlo.
    to: String,
}

/// Mueve un fichero o carpeta dentro de `media/`, proxyando al Cloud.
///
/// Para que el movimiento sea válido, el usuario debe poder MODIFICAR tanto el origen (sacarlo de
/// ahí es un delete) como el destino (meterlo es un upload). Así una carpeta de módulo (readOnly)
/// no recibe drops ni se deja sacar de su sitio.
pub async fn media_move(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<MoveReq>,
) -> Response {
    if let Err(response) = require_admin(&st, &headers).await {
        return response;
    }
    if req.from.trim_matches('/').is_empty() {
        return err(StatusCode::BAD_REQUEST, "falta la ruta de origen");
    }
    if req.from == req.to {
        return err(StatusCode::BAD_REQUEST, "origen y destino coinciden");
    }
    // No se puede mover algo al interior de sí mismo (carpeta dentro de su subcarpeta).
    if is_within(&req.from, &req.to) {
        return err(
            StatusCode::BAD_REQUEST,
            "no se puede mover una carpeta dentro de sí misma",
        );
    }
    // Sacar el elemento del origen cuenta como borrado; meterlo, como subida.
    if let Err(response) = require_action(&st, &req.from, UserFileAction::Delete).await {
        return response;
    }
    if let Err(response) = require_action(&st, &req.to, UserFileAction::Upload).await {
        return response;
    }
    cloud_move(&st, &req.from, &req.to).await
}

// ───────────────── Puerta del export/import de blueprints (ADR-0113 + ADR-0047) ─────────────────
//
// El bundle lleva las imágenes DENTRO del zip, y su fuente y destino es el gestor media — es decir,
// Object Storage vía el Cloud. Estas dos funciones son esa puerta.
//
// 🔴 No las sustituyas por `std::fs` sobre `config.media_dir`: eso es lo que hacía el export y por
// eso los blueprints salían sin una sola imagen. En Hub Cloud (ADR-0154) `media_dir` es scratch
// local y los ficheros del hub NO están ahí; este módulo no tiene ni una llamada al sistema de
// ficheros, y esa es justamente la propiedad que hay que conservar.

/// Carpetas de PRIMER nivel que no son datos del negocio (`_logs`, `_system`, `_import_tmp`…) y
/// por tanto no entran en un bundle.
fn is_system_folder(path: &str) -> bool {
    path.split('/').next().is_some_and(|top| top.starts_with('_'))
}

/// Aplana el árbol de carpetas del listado (`[{id, children:[…]}]`) en rutas.
fn flatten_folder_ids(folders: &Value, out: &mut Vec<String>) {
    let Some(arr) = folders.as_array() else { return };
    for node in arr {
        if let Some(id) = node.get("id").and_then(Value::as_str) {
            if !id.is_empty() {
                out.push(id.to_string());
            }
        }
        if let Some(children) = node.get("children") {
            flatten_folder_ids(children, out);
        }
    }
}

/// Listado CRUDO de una carpeta tal cual lo da el Cloud (sin el mapeo cosmético que necesita la
/// UI): aquí solo interesan `folders` y `files[].path`.
async fn cloud_list_raw(st: &AppState, folder: &str) -> Option<Value> {
    let headers = cloud_headers(st)?;
    let url = format!(
        "{}/api/v1/hub/device/media/?folder={}",
        cloud_base(st),
        pct_encode(folder)
    );
    let mut r = st.http.get(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    let resp = r.send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    resp.json::<Value>().await.ok()
}

/// Bytes de un objeto del gestor media. Repite el doble salto de [`cloud_raw`] —el Cloud firma una
/// URL de Object Storage y la descarga la hace el runtime— con su mismo límite de concurrencia y
/// su tope por objeto, porque un export de catálogo pide ~300 ficheros seguidos (hub#759).
///
/// La URL firmada se pide con el cliente LIMPIO: `X-Hub-Token` es un secreto del hub y no viaja a
/// un tercero (ADR-0003).
async fn fetch_object_bytes(st: &AppState, path: &str) -> Option<Vec<u8>> {
    let _permit = st.media_fetch_limiter.clone().acquire_owned().await.ok()?;
    let headers = cloud_headers(st)?;
    let url = format!(
        "{}/api/v1/hub/device/media/raw?path={}",
        cloud_base(st),
        pct_encode(path)
    );
    let mut r = st.http.get(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    let resp = r.send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let signed = resp
        .json::<Value>()
        .await
        .ok()?
        .get("url")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    if signed.is_empty() {
        return None;
    }
    let object = st.http.get(&signed).send().await.ok()?;
    if !object.status().is_success() {
        return None;
    }
    if object
        .content_length()
        .is_some_and(|len| len > MAX_MEDIA_OBJECT_BYTES)
    {
        tracing::warn!(path, "export: objeto de media por encima del tope, se omite");
        return None;
    }
    let bytes = object.bytes().await.ok()?;
    if bytes.len() as u64 > MAX_MEDIA_OBJECT_BYTES {
        tracing::warn!(path, "export: objeto de media por encima del tope, se omite");
        return None;
    }
    Some(bytes.to_vec())
}

/// Recorre el gestor media entero y devuelve `(ruta "media/<rel>", bytes)` por fichero, listo para
/// entrar en el zip. Excluye las carpetas de sistema de primer nivel. Profundidad acotada y con
/// conjunto de visitadas: el listado del Cloud puede venir como árbol completo o nivel a nivel, y
/// ninguna de las dos formas debe hacer que un fichero se recoja dos veces.
pub(crate) async fn collect_for_bundle(st: &AppState) -> Vec<(String, Vec<u8>)> {
    const MAX_FOLDERS: usize = 4096;
    let mut pending = vec![String::new()];
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut out: Vec<(String, Vec<u8>)> = Vec::new();

    while let Some(folder) = pending.pop() {
        if !seen.insert(folder.clone()) || seen.len() > MAX_FOLDERS {
            continue;
        }
        let Some(raw) = cloud_list_raw(st, &folder).await else {
            tracing::warn!(folder, "export: el Cloud no listó la carpeta de media");
            continue;
        };
        let mut children = Vec::new();
        flatten_folder_ids(raw.get("folders").unwrap_or(&Value::Null), &mut children);
        for child in children {
            if !is_system_folder(&child) && !seen.contains(&child) {
                pending.push(child);
            }
        }
        let Some(files) = raw.get("files").and_then(Value::as_array) else {
            continue;
        };
        for f in files {
            let path = f.get("path").and_then(Value::as_str).unwrap_or_default();
            if path.is_empty() || is_system_folder(path) {
                continue;
            }
            match fetch_object_bytes(st, path).await {
                Some(bytes) => out.push((format!("media/{path}"), bytes)),
                None => tracing::warn!(path, "export: no se pudo descargar el fichero de media"),
            }
        }
    }
    out
}

/// Destino `(carpeta, nombre)` de un `media/<rel>` del bundle, o `None` si la ruta no debe
/// escribirse. Es la guarda anti-traversal del import, en función pura para poder probarla sin red:
/// solo se aceptan componentes normales (`..`, rutas absolutas y prefijos como `C:\` se rechazan) y
/// la entrada tiene que nombrar un fichero (`media/` o `media/sub/` no producen destino).
///
/// Antes esta guarda vivía en `prepare_media_target`, que además esquivaba symlinks porque escribía
/// en disco. Ya no hay disco: el destino es Object Storage y el Cloud es el dueño de la validación
/// de rutas — pero rechazar aquí lo que ni siquiera debería salir del hub sigue siendo barato.
pub(crate) fn bundle_media_destination(rel: &str) -> Option<(String, String)> {
    // `\` no es separador en el zip: una entrada que lo trae está intentando algo (hub#239).
    if rel.contains('\\') {
        return None;
    }
    let mut parts: Vec<String> = Vec::new();
    for comp in Path::new(rel).components() {
        match comp {
            Component::Normal(c) => parts.push(c.to_string_lossy().into_owned()),
            Component::CurDir => {}
            _ => return None,
        }
    }
    let name = parts.pop()?;
    if name.is_empty() {
        return None;
    }
    Some((parts.join("/"), name))
}

/// Sube un `media/<rel>` del bundle al gestor media, conservando su carpeta. `false` si la ruta se
/// rechaza o el Cloud lo rechazó — el import lo cuenta como fallido y sigue (best-effort por
/// fichero, ADR-0113).
pub(crate) async fn upload_from_bundle(st: &AppState, rel: &str, bytes: Vec<u8>) -> bool {
    let Some((folder, name)) = bundle_media_destination(rel) else {
        return false;
    };
    let Some(headers) = cloud_headers(st) else {
        return false;
    };
    let form = reqwest::multipart::Form::new()
        .text("folder", folder)
        .part(
            "files",
            reqwest::multipart::Part::bytes(bytes).file_name(name),
        );
    let url = format!("{}/api/v1/hub/device/media/", cloud_base(st));
    let mut r = st.http.post(&url).multipart(form);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    matches!(r.send().await, Ok(resp) if resp.status().is_success())
}

// ─────────────────────────── Helpers ───────────────────────────

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

/// `true` si `to` es el mismo o un descendiente de `from` (ambas rutas relativas a `media/`).
/// Usado por `media_move` para rechazar meter una carpeta dentro de sí misma o de su subárbol.
fn is_within(from: &str, to: &str) -> bool {
    let f = from.trim_matches('/');
    let t = to.trim_matches('/');
    if f.is_empty() {
        return false;
    }
    t == f || t.starts_with(&format!("{f}/"))
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
async fn resolve_policy(st: &AppState, rel: &str) -> MediaPolicy {
    let Some(folder) = module_folder_of(rel) else {
        return policy_for(rel, None);
    };
    let rt = st.runtime.lock().await;
    let owner = rt
        .registry()
        .installed
        .iter()
        .find_map(|m| m.static_files.as_ref().filter(|s| s.folder == folder))
        .cloned();
    policy_for(rel, owner.as_ref())
}

/// Corta la petición con 403 si la política de `rel` no concede `action`.
async fn require_action(st: &AppState, rel: &str, action: UserFileAction) -> Result<(), Response> {
    if resolve_policy(st, rel).await.allows(action) {
        return Ok(());
    }
    Err(err(
        StatusCode::FORBIDDEN,
        "esta carpeta es de solo lectura: su módulo no permite esa acción",
    ))
}

#[cfg(test)]
mod bundle_tests {
    use super::*;

    /// Una ruta legítima conserva su carpeta y su nombre: es lo que hace que un catálogo importado
    /// encuentre sus fotos donde el `image` del producto dice que están.
    #[test]
    fn una_ruta_legitima_conserva_carpeta_y_nombre() {
        assert_eq!(
            bundle_media_destination("modules/inventory/logo.png"),
            Some(("modules/inventory".into(), "logo.png".into()))
        );
        // En la raíz de media/ la carpeta es la cadena vacía, que es lo que espera el Cloud.
        assert_eq!(
            bundle_media_destination("logo.png"),
            Some((String::new(), "logo.png".into()))
        );
    }

    /// La guarda que heredamos de `prepare_media_target` (hub#239): ninguna entrada del bundle
    /// puede nombrar algo fuera de `media/`. Sin disco de por medio la consecuencia ya no es
    /// escribir fuera del hub, pero una ruta así no tiene por qué llegar siquiera al Cloud.
    #[test]
    fn ninguna_ruta_con_traversal_produce_destino() {
        for evil in [
            "../evil.png",
            "../../etc/passwd",
            "/etc/passwd",
            "sub/../../evil.png",
            "modules\\..\\evil.png",
        ] {
            assert_eq!(bundle_media_destination(evil), None, "{evil} debía rechazarse");
        }
    }

    /// Entradas que no nombran un fichero (`media/`, `media/sub/`) no producen destino.
    #[test]
    fn una_entrada_sin_nombre_de_fichero_no_produce_destino() {
        assert_eq!(bundle_media_destination(""), None);
        assert_eq!(bundle_media_destination("."), None);
        assert_eq!(bundle_media_destination("sub/"), Some(("".into(), "sub".into())));
    }

    /// Las carpetas de sistema de primer nivel no son datos del negocio y no entran en un bundle.
    #[test]
    fn las_carpetas_de_sistema_se_reconocen_por_su_primer_nivel() {
        assert!(is_system_folder("_logs"));
        assert!(is_system_folder("_logs/boot.log"));
        assert!(is_system_folder("_system/activity.json"));
        assert!(!is_system_folder("catalogo/cafe.webp"));
        // Solo el PRIMER nivel: una subcarpeta con guion bajo sí es del negocio.
        assert!(!is_system_folder("catalogo/_borradores/x.webp"));
    }

    /// El árbol de carpetas del listado se aplana a rutas, hijos incluidos.
    #[test]
    fn el_arbol_de_carpetas_se_aplana_a_rutas() {
        let tree = serde_json::json!([
            { "id": "catalogo", "children": [{ "id": "catalogo/bebidas", "children": [] }] },
            { "id": "_logs", "children": [] }
        ]);
        let mut out = Vec::new();
        flatten_folder_ids(&tree, &mut out);
        assert_eq!(out, vec!["catalogo", "catalogo/bebidas", "_logs"]);
    }
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
}
