//! `GET/POST/DELETE /api/media*` — gestor de la carpeta `media/` del hub (pantalla /files).
//!
//! `media/` es el path por defecto de TODOS los ficheros del hub (se crea en el despliegue):
//! adjuntos de módulos, registros de sistema (`_logs/`), monitor de actividad (`_system/`)…
//! La navega el componente `ok-file-manager` (OutfitKit) desde `hub/apps/web/src/views/FilesPage.vue`
//! vía el cliente `hub/apps/web/src/lib/media.ts`.
//!
//! Esta implementación es **axis-aware** igual que `system.rs`, pero hoy cubre el camino LOCAL
//! (disco bajo `config.media_dir`), que es el que corre en `single` (SQLite/Tauri/dev). El listado
//! S3 del combo `cloud` queda como follow-up del humano (necesita IAM/SDK), igual que los
//! documentos en `system.rs`; mientras tanto, en cloud sin disco de media el listado sale vacío.
//!
//! Seguridad: TODA ruta que llega del cliente (`folder`/`path`/`name`) se une al root con
//! [`safe_join`], que descarta cualquier componente `..`/absoluto/prefijo (anti path-traversal /
//! zip-slip). El gate de auth lo hereda del router como el resto (mismo patrón que `system.rs`);
//! endurecerlo es columna del humano.
//!
//! Endpoints (contrato consumido por `lib/media.ts`):
//!   GET    /api/media?folder=<rel>      → { ok, data: { folders[], files[], path[] } }
//!   GET    /api/media/raw?path=<rel>    → bytes del fichero (inline)
//!   POST   /api/media/upload            → multipart `folder` + `files`
//!   DELETE /api/media?path=<rel>        → borra un fichero
//!   POST   /api/media/folder            → json { parent, name } crea sub-carpeta

use axum::body::Body;
use axum::extract::{Multipart, Query, State};
use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use sysinfo::Disks;

use crate::AppState;

/// Profundidad máxima del árbol de carpetas que se devuelve al panel lateral (defensivo).
const MAX_TREE_DEPTH: usize = 8;

// ─────────────────────────── Eje A: local (disco) vs cloud (S3 vía Cloud) ───────────────────────────
//
// `single` (SQLite) → disco local (este módulo). `cloud` (Postgres/ECS) → la carpeta media vive en
// S3 y el Hub **no** habla con S3: delega en el Cloud (ADR-0047), igual que el módulo backup. El
// contrato hacia el frontend es el MISMO; solo cambia de dónde salen los datos.

/// `true` si el backend de datos es cloud (Postgres) → la media vive en S3 (proxy al Cloud).
async fn is_cloud_backend(st: &AppState) -> bool {
    let rt = st.runtime.lock().await;
    matches!(rt.db().dialect(), erplora_db::Dialect::Postgres)
}

/// Cabeceras de autenticación de máquina (`X-Hub-Token` + `X-Hub-Id`) para hablar con el Cloud.
/// `None` si el hub no está enrolado (sin token de máquina) → no se puede proxyar.
fn cloud_headers(st: &AppState) -> Option<Vec<(&'static str, String)>> {
    let token = st.machine_token()?;
    Some(cloud_client::Auth::HubToken { hub_id: st.config.hub_id.clone(), token }.headers())
}

/// Base del Cloud sin barra final.
fn cloud_base(st: &AppState) -> String {
    st.config.cloud_base_url.trim_end_matches('/').to_string()
}

/// ISO 8601 → "YYYY-MM-DD HH:MM" (el front muestra la cadena tal cual, igual que la rama local).
fn fmt_iso(s: &str) -> String {
    if s.len() >= 16 {
        s[..16].replace('T', " ")
    } else {
        s.to_string()
    }
}

// ─────────────────────────── Rama cloud: proxy al Cloud ───────────────────────────

/// `GET /api/v1/hub/device/media/?folder=` → mapea el shape RAW del Cloud al del frontend
/// (formatea bytes/fecha, quota "sin límite").
async fn cloud_list(st: &AppState, folder: &str) -> Response {
    let Some(headers) = cloud_headers(st) else {
        return err(StatusCode::BAD_GATEWAY, "hub sin token de máquina");
    };
    let url = format!("{}/api/v1/hub/device/media/?folder={}", cloud_base(st), pct_encode(folder));
    let mut r = st.http.get(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    let resp = match r.send().await {
        Ok(x) => x,
        Err(e) => return err(StatusCode::BAD_GATEWAY, &e.to_string()),
    };
    if !resp.status().is_success() {
        return err(StatusCode::BAD_GATEWAY, "el Cloud rechazó el listado de media");
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
                    let modified = f.get("modified").and_then(Value::as_str).map(fmt_iso).unwrap_or_default();
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

    let used = raw.pointer("/usage/used_bytes").and_then(Value::as_u64).unwrap_or(0);
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
                let fname = field.file_name().map(|s| s.to_string()).unwrap_or_else(|| "file".to_string());
                let Ok(data) = field.bytes().await else { continue };
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
    let url = format!("{}/api/v1/hub/device/media/?path={}", cloud_base(st), pct_encode(path));
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
    let mut r = st.http.post(&url).json(&json!({ "parent": parent, "name": name }));
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(_) => err(StatusCode::BAD_GATEWAY, "el Cloud no pudo crear la carpeta"),
        Err(e) => err(StatusCode::BAD_GATEWAY, &e.to_string()),
    }
}

// ─────────────────────────── GET /api/media ───────────────────────────

#[derive(Deserialize)]
pub struct FolderQuery {
    #[serde(default)]
    folder: String,
}

/// Lista el árbol de carpetas + los ficheros de la carpeta pedida (raíz si `folder` vacío).
pub async fn media_list(State(st): State<AppState>, Query(q): Query<FolderQuery>) -> Response {
    if is_cloud_backend(&st).await {
        return cloud_list(&st, &q.folder).await;
    }
    let root = st.config.media_dir.clone();
    let folder = q.folder;
    match tokio::task::spawn_blocking(move || build_listing(&root, &folder)).await {
        Ok(Ok(data)) => Json(json!({ "ok": true, "data": data })).into_response(),
        Ok(Err(msg)) => err(StatusCode::BAD_REQUEST, &msg),
        Err(_) => err(StatusCode::INTERNAL_SERVER_ERROR, "fallo interno"),
    }
}

/// Construye el `MediaListing` (síncrono; corre en `spawn_blocking`).
fn build_listing(root: &Path, folder: &str) -> Result<Value, String> {
    // La carpeta media se crea de forma perezosa: el primer acceso la materializa.
    std::fs::create_dir_all(root).map_err(|e| format!("no se pudo crear media/: {e}"))?;
    let target = safe_join(root, folder).ok_or_else(|| "ruta no válida".to_string())?;
    if !target.is_dir() && !folder.is_empty() {
        return Err("la carpeta no existe".to_string());
    }

    // Árbol lateral: un nodo raíz "media" (id "") que contiene el árbol recursivo de sub-carpetas.
    let children = build_tree(root, root, 1);
    let root_count = count_entries(root);
    let mut root_node = json!({
        "id": "",
        "label": "media",
        "icon": "folder-open-outline",
        "count": root_count,
    });
    if !children.is_empty() {
        root_node["children"] = Value::Array(children);
    }

    let mut out = json!({
        "folders": [root_node],
        "files": list_files(root, &target),
        "path": breadcrumb(folder),
    });
    // Medidor de espacio: en LOCAL (single/disco) reportamos la capacidad del disco que aloja
    // `media/`. En cloud (S3) no aplica (follow-up). `null`/ausente ⇒ el componente oculta el meter.
    if let Some(quota) = disk_quota(root) {
        out["quota"] = quota;
    }
    Ok(out)
}

/// Capacidad del disco que aloja `media/` (usado/total + fracción), vía `sysinfo`. Elige el disco
/// cuyo punto de montaje es el prefijo más largo de la ruta de media. `None` si no se resuelve.
fn disk_quota(media: &Path) -> Option<Value> {
    let abs = std::fs::canonicalize(media).ok()?;
    let disks = Disks::new_with_refreshed_list();
    let mut best_total = 0u64;
    let mut best_avail = 0u64;
    let mut best_len = 0usize;
    let mut found = false;
    for d in disks.list() {
        let mp = d.mount_point();
        if abs.starts_with(mp) {
            let len = mp.components().count();
            if !found || len >= best_len {
                best_len = len;
                best_total = d.total_space();
                best_avail = d.available_space();
                found = true;
            }
        }
    }
    if !found || best_total == 0 {
        return None;
    }
    let used = best_total.saturating_sub(best_avail);
    Some(json!({
        "usedLabel": human_bytes(used),
        "totalLabel": human_bytes(best_total),
        "fraction": (used as f64 / best_total as f64).clamp(0.0, 1.0),
    }))
}

/// Árbol recursivo de SUB-carpetas de `dir` (solo directorios). `depth` empieza en 1 para el
/// primer nivel bajo la raíz; se corta en [`MAX_TREE_DEPTH`].
fn build_tree(root: &Path, dir: &Path, depth: usize) -> Vec<Value> {
    if depth > MAX_TREE_DEPTH {
        return vec![];
    }
    let mut dirs: Vec<PathBuf> = match std::fs::read_dir(dir) {
        Ok(rd) => rd
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.is_dir())
            .collect(),
        Err(_) => return vec![],
    };
    dirs.sort();

    let mut out = Vec::with_capacity(dirs.len());
    for path in dirs {
        let name = file_name_str(&path);
        let rel = rel_id(root, &path);
        let children = build_tree(root, &path, depth + 1);
        let mut node = json!({
            "id": rel,
            "label": name.clone(),
            "count": count_entries(&path),
        });
        if let Some(icon) = icon_for(&name) {
            node["icon"] = json!(icon);
        }
        if !children.is_empty() {
            node["children"] = Value::Array(children);
        }
        out.push(node);
    }
    out
}

/// Ficheros (no directorios) directamente dentro de `dir`, ordenados por nombre.
fn list_files(root: &Path, dir: &Path) -> Vec<Value> {
    let mut files: Vec<PathBuf> = match std::fs::read_dir(dir) {
        Ok(rd) => rd
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.is_file())
            .collect(),
        Err(_) => return vec![],
    };
    files.sort();

    files
        .iter()
        .map(|path| {
            let name = file_name_str(path);
            let rel = rel_id(root, path);
            let meta = std::fs::metadata(path).ok();
            let size = meta.as_ref().map(|m| m.len()).unwrap_or(0);
            let modified = meta
                .as_ref()
                .and_then(|m| m.modified().ok())
                .map(fmt_mtime)
                .unwrap_or_default();
            json!({
                "id": rel,
                "name": name,
                "ext": ext_of(&name),
                "sizeLabel": human_bytes(size),
                "modified": modified,
                "url": format!("/api/media/raw?path={}", pct_encode(&rel)),
            })
        })
        .collect()
}

/// Breadcrumb de raíz ("media") a la carpeta `folder`.
fn breadcrumb(folder: &str) -> Vec<Value> {
    let mut crumbs = vec![json!({ "id": "", "label": "media" })];
    let mut acc = String::new();
    for part in folder.split('/').filter(|s| !s.is_empty()) {
        if !acc.is_empty() {
            acc.push('/');
        }
        acc.push_str(part);
        crumbs.push(json!({ "id": acc.clone(), "label": part }));
    }
    crumbs
}

// ─────────────────────────── GET /api/media/raw ───────────────────────────

#[derive(Deserialize)]
pub struct PathQuery {
    path: String,
}

/// Sirve el contenido de un fichero de `media/` (inline). Lee a memoria (los ficheros de media son
/// modestos: logs, PDFs, imágenes); el streaming por trozos para ficheros grandes es follow-up.
pub async fn media_raw(State(st): State<AppState>, Query(q): Query<PathQuery>) -> Response {
    let root = st.config.media_dir.clone();
    let Some(target) = safe_join(&root, &q.path) else {
        return err(StatusCode::BAD_REQUEST, "ruta no válida");
    };
    let read = tokio::task::spawn_blocking(move || {
        let meta = std::fs::metadata(&target).ok()?;
        if !meta.is_file() {
            return None;
        }
        let bytes = std::fs::read(&target).ok()?;
        Some((bytes, file_name_str(&target)))
    })
    .await;

    match read {
        Ok(Some((bytes, name))) => Response::builder()
            .header(header::CONTENT_TYPE, content_type(&name))
            .header(
                header::CONTENT_DISPOSITION,
                format!("inline; filename=\"{}\"", name.replace('"', "")),
            )
            .body(Body::from(bytes))
            .unwrap_or_else(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "respuesta inválida")),
        _ => err(StatusCode::NOT_FOUND, "fichero no encontrado"),
    }
}

// ─────────────────────────── POST /api/media/upload ───────────────────────────

/// Sube uno o varios ficheros a la carpeta `folder` (campo de texto del multipart). Los nombres se
/// reducen a su componente final (sin ruta) para que un cliente no escriba fuera de la carpeta.
pub async fn media_upload(State(st): State<AppState>, mut mp: Multipart) -> Response {
    if is_cloud_backend(&st).await {
        return cloud_upload(&st, mp).await;
    }
    let root = st.config.media_dir.clone();
    let mut folder = String::new();
    let mut saved = 0u32;

    while let Ok(Some(field)) = mp.next_field().await {
        match field.name() {
            Some("folder") => {
                folder = field.text().await.unwrap_or_default();
            }
            Some("files") => {
                // Nombre seguro = solo el componente final del nombre declarado por el cliente.
                let safe_name = field
                    .file_name()
                    .and_then(|f| Path::new(f).file_name().map(|s| s.to_string_lossy().into_owned()));
                let Some(safe_name) = safe_name.filter(|s| !s.is_empty()) else {
                    continue;
                };
                let Ok(data) = field.bytes().await else { continue };
                let Some(dir) = safe_join(&root, &folder) else {
                    return err(StatusCode::BAD_REQUEST, "carpeta no válida");
                };
                if std::fs::create_dir_all(&dir).is_err() {
                    return err(StatusCode::INTERNAL_SERVER_ERROR, "no se pudo crear la carpeta");
                }
                if std::fs::write(dir.join(&safe_name), &data).is_ok() {
                    saved += 1;
                }
            }
            _ => {}
        }
    }

    Json(json!({ "ok": true, "data": { "saved": saved } })).into_response()
}

// ─────────────────────────── DELETE /api/media ───────────────────────────

/// Borra un fichero de `media/`. Solo ficheros (no directorios) para evitar borrados masivos por
/// accidente; borrar carpetas es follow-up explícito.
pub async fn media_delete(State(st): State<AppState>, Query(q): Query<PathQuery>) -> Response {
    if is_cloud_backend(&st).await {
        return cloud_delete(&st, &q.path).await;
    }
    let root = st.config.media_dir.clone();
    let Some(target) = safe_join(&root, &q.path) else {
        return err(StatusCode::BAD_REQUEST, "ruta no válida");
    };
    if target == root {
        return err(StatusCode::BAD_REQUEST, "ruta no válida");
    }
    let ok = tokio::task::spawn_blocking(move || {
        matches!(std::fs::metadata(&target), Ok(m) if m.is_file())
            && std::fs::remove_file(&target).is_ok()
    })
    .await
    .unwrap_or(false);

    if ok {
        Json(json!({ "ok": true })).into_response()
    } else {
        err(StatusCode::NOT_FOUND, "no se pudo borrar")
    }
}

// ─────────────────────────── POST /api/media/folder ───────────────────────────

#[derive(Deserialize)]
pub struct CreateFolderReq {
    #[serde(default)]
    parent: String,
    name: String,
}

/// Crea una sub-carpeta `name` dentro de `parent`. `name` se valida como UN solo componente.
pub async fn media_create_folder(
    State(st): State<AppState>,
    Json(req): Json<CreateFolderReq>,
) -> Response {
    if is_cloud_backend(&st).await {
        return cloud_create_folder(&st, &req.parent, &req.name).await;
    }
    let root = st.config.media_dir.clone();
    let name = req.name.trim().to_string();
    // Nombre = un único componente normal (sin separadores ni `..`).
    if name.is_empty() || !is_simple_name(&name) {
        return err(StatusCode::BAD_REQUEST, "nombre no válido");
    }
    let Some(parent) = safe_join(&root, &req.parent) else {
        return err(StatusCode::BAD_REQUEST, "ruta no válida");
    };
    let ok = tokio::task::spawn_blocking(move || std::fs::create_dir_all(parent.join(&name)).is_ok())
        .await
        .unwrap_or(false);

    if ok {
        Json(json!({ "ok": true })).into_response()
    } else {
        err(StatusCode::INTERNAL_SERVER_ERROR, "no se pudo crear")
    }
}

// ─────────────────────────── Helpers ───────────────────────────

/// Une `rel` (ruta relativa del cliente) bajo `root` descartando cualquier intento de salir del
/// root: solo se aceptan componentes normales; `..`, raíz absoluta y prefijos (p.ej. `C:\`) se
/// rechazan devolviendo `None`. Es la única puerta por la que pasa el input de ruta del cliente.
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

/// `true` si `name` es un único componente de ruta normal (sin `/`, `\`, `..`, ni vacío).
fn is_simple_name(name: &str) -> bool {
    let mut comps = Path::new(name).components();
    matches!(
        (comps.next(), comps.next()),
        (Some(Component::Normal(_)), None)
    )
}

/// Ruta relativa de `path` respecto a `root`, con separador `/` (id estable cross-plataforma).
fn rel_id(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .components()
        .filter_map(|c| match c {
            Component::Normal(s) => Some(s.to_string_lossy().into_owned()),
            _ => None,
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn file_name_str(path: &Path) -> String {
    path.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default()
}

/// Nº de entradas directas de un directorio (para el contador de la fila del árbol).
fn count_entries(dir: &Path) -> usize {
    std::fs::read_dir(dir).map(|rd| rd.flatten().count()).unwrap_or(0)
}

/// Icono (ionicon) para carpetas especiales conocidas de `media/`; `None` = icono por defecto.
fn icon_for(name: &str) -> Option<&'static str> {
    match name {
        "_logs" => Some("terminal-outline"),
        "_system" => Some("pulse-outline"),
        "modules" => Some("cube-outline"),
        "backups" => Some("save-outline"),
        _ => None,
    }
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

/// `SystemTime` → "YYYY-MM-DD HH:MM" en UTC, sin dependencias de fechas (algoritmo civil de
/// Howard Hinnant). TZ = UTC (el front solo muestra la cadena).
fn fmt_mtime(t: SystemTime) -> String {
    let secs = t.duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) as i64;
    let days = secs.div_euclid(86_400);
    let rem = secs.rem_euclid(86_400);
    let (hh, mm) = ((rem / 3600), (rem % 3600) / 60);

    // days since 1970-01-01 → (year, month, day) civil.
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097; // [0, 146096]
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365; // [0, 399]
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); // [0, 365]
    let mp = (5 * doy + 2) / 153; // [0, 11]
    let d = doy - (153 * mp + 2) / 5 + 1; // [1, 31]
    let m = if mp < 10 { mp + 3 } else { mp - 9 }; // [1, 12]
    let year = if m <= 2 { y + 1 } else { y };

    format!("{year:04}-{m:02}-{d:02} {hh:02}:{mm:02}")
}

/// Respuesta de error en el envelope estándar (`{ ok:false, error:{ message } }`).
fn err(code: StatusCode, msg: &str) -> Response {
    (code, Json(json!({ "ok": false, "error": { "message": msg } }))).into_response()
}
