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
//! Security: listing/opening asks for a user session, and the hub's own folders (`_*`) and the
//! apps' tree (`modules/…`) for an owner/admin, who are also the only ones whose folder tree names
//! them (hub#2495, `read_requires_admin`); uploading, creating folders and deleting asks for an
//! owner/admin session. Una API key nunca accede al gestor de archivos. La validación de rutas
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
use std::collections::BTreeMap;
use std::future::Future;
use std::path::{Component, Path};

use erplora_runtime::manifest::{StaticFilesDef, UserFileAction};

use crate::cloud_proxy::cloud_unreachable;
use crate::{auth, cloud_proxy, AppState};

/// The gate's refusal with its code (hub#1776, the recipe of hub#1700): `401 unauthorized` with no
/// usable session, `403 forbidden` when the session is fine and the role is not.
fn unauthorized(error: auth::AuthError) -> Response {
    crate::auth_rejected(error)
}

async fn require_user(st: &AppState, headers: &HeaderMap) -> Result<(), Response> {
    let rt = st.runtime.read().await;
    auth::require_user_session(headers, &st.config, &rt)
        .await
        .map(|_| ())
        .map_err(unauthorized)
}

/// The reading gate (hub#2495): a session of the hub, and the hub's own folders and the apps' tree
/// only for whoever administers the hub ([`read_requires_admin`]). Answers whether the session
/// reads EVERY folder, so the listing can leave out of the tree what it may not open.
///
/// Administering is asked as the `hub.administer` permission, not as a role, so the same predicate
/// that refuses here is the one that filters the tree, and Dev mode (`*`) reads everything as it
/// already did.
async fn require_reader(st: &AppState, headers: &HeaderMap, rel: &str) -> Result<bool, Response> {
    let rt = st.runtime.read().await;
    let ctx = auth::require_user_session(headers, &st.config, &rt)
        .await
        .map_err(unauthorized)?;
    let reads_everything =
        erplora_runtime::permissions::has(&ctx, erplora_runtime::hub_users::ADMINISTER_PERMISSION);
    if !reads_everything && read_requires_admin(rel) {
        return Err(unauthorized(auth::AuthError::Forbidden(
            "only an owner or an administrator can open this folder".into(),
        )));
    }
    Ok(reads_everything)
}

async fn require_admin(st: &AppState, headers: &HeaderMap) -> Result<(), Response> {
    let rt = st.runtime.read().await;
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
fn cloud_headers(st: &AppState, url: &str) -> Option<Vec<(&'static str, String)>> {
    let token = st.machine_token()?;
    let auth = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token,
    };
    // hub#1464: por LA puerta, que es la única que comprueba el destino. Aquí todas las URLs son
    // de nuestra nube, y precisamente por eso el día que una deje de serlo nadie lo notaría sin
    // esto — que es como estaban `system.rs` y `usage_series.rs` cuando se abrió la issue.
    Some(cloud_client::CloudClient::new(&st.config.cloud_base_url).headers_for(url, &auth))
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
async fn cloud_list(st: &AppState, folder: &str, reads_everything: bool) -> Response {
    let url = format!(
        "{}/api/v1/hub/device/media/?folder={}",
        cloud_base(st),
        pct_encode(folder)
    );
    let Some(headers) = cloud_headers(st, &url) else {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::HUB_NOT_ENROLLED,
            "this hub has no machine credential",
        );
    };
    let mut r = st.http.get(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    let resp = match r.send().await {
        Ok(x) => x,
        Err(e) => {
            return err(
                cloud_proxy::CLOUD_FAILED,
                cloud_unreachable(&e.to_string()),
                "erplora.com did not answer",
            )
        }
    };
    if !resp.status().is_success() {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::CLOUD_REJECTED,
            "erplora.com refused the media listing",
        );
    }
    let raw: Value = match resp.json().await {
        Ok(v) => v,
        Err(e) => {
            return err(
                cloud_proxy::CLOUD_FAILED,
                cloud_unreachable(&e.to_string()),
                "erplora.com did not answer",
            )
        }
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
    // Quien no administra no recibe ni el nombre de lo que no puede abrir (hub#2495).
    let mut folders = raw.get("folders").cloned().unwrap_or_else(|| json!([]));
    if !reads_everything {
        folders = without_restricted_folders(folders);
    }
    let folders = decorate_folders(folders, st).await;
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
    let url = format!("{}/api/v1/hub/device/media/", cloud_base(st));
    let Some(headers) = cloud_headers(st, &url) else {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::HUB_NOT_ENROLLED,
            "this hub has no machine credential",
        );
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
        return err(
            StatusCode::BAD_REQUEST,
            "media.no_files",
            "no files were sent",
        );
    }
    let mut form = reqwest::multipart::Form::new().text("folder", folder);
    for (fname, data) in files {
        form = form.part(
            "files",
            reqwest::multipart::Part::bytes(data).file_name(fname),
        );
    }
    let mut r = st
        .http
        .post(&url)
        .multipart(form)
        .timeout(crate::state::CLOUD_TRANSFER_TIMEOUT);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(_) => err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::CLOUD_REJECTED,
            "erplora.com refused the upload",
        ),
        Err(e) => err(
            cloud_proxy::CLOUD_FAILED,
            cloud_unreachable(&e.to_string()),
            "erplora.com did not answer",
        ),
    }
}

/// `DELETE …/media/?path=` en el Cloud.
async fn cloud_delete(st: &AppState, path: &str) -> Response {
    let url = format!(
        "{}/api/v1/hub/device/media/?path={}",
        cloud_base(st),
        pct_encode(path)
    );
    let Some(headers) = cloud_headers(st, &url) else {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::HUB_NOT_ENROLLED,
            "this hub has no machine credential",
        );
    };
    let mut r = st.http.delete(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(resp) => relayed(resp.status().as_u16(), "erplora.com could not delete"),
        Err(e) => err(
            cloud_proxy::CLOUD_FAILED,
            cloud_unreachable(&e.to_string()),
            "erplora.com did not answer",
        ),
    }
}

/// `POST …/media/rename/` en el Cloud (que hace el copy+delete sobre Object Storage).
async fn cloud_rename(st: &AppState, path: &str, name: &str) -> Response {
    let url = format!("{}/api/v1/hub/device/media/rename/", cloud_base(st));
    let Some(headers) = cloud_headers(st, &url) else {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::HUB_NOT_ENROLLED,
            "this hub has no machine credential",
        );
    };
    let mut r = st
        .http
        .post(&url)
        .json(&json!({ "path": path, "name": name }));
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(resp) => relayed(resp.status().as_u16(), "erplora.com could not rename"),
        Err(e) => err(
            cloud_proxy::CLOUD_FAILED,
            cloud_unreachable(&e.to_string()),
            "erplora.com did not answer",
        ),
    }
}

/// `POST …/media/folder/` en el Cloud.
async fn cloud_create_folder(st: &AppState, parent: &str, name: &str) -> Response {
    let url = format!("{}/api/v1/hub/device/media/folder/", cloud_base(st));
    let Some(headers) = cloud_headers(st, &url) else {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::HUB_NOT_ENROLLED,
            "this hub has no machine credential",
        );
    };
    let mut r = st
        .http
        .post(&url)
        .json(&json!({ "parent": parent, "name": name }));
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(_) => err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::CLOUD_REJECTED,
            "erplora.com could not create the folder",
        ),
        Err(e) => err(
            cloud_proxy::CLOUD_FAILED,
            cloud_unreachable(&e.to_string()),
            "erplora.com did not answer",
        ),
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
        return err(
            StatusCode::SERVICE_UNAVAILABLE,
            "media.busy",
            "media limiter closed",
        );
    };
    let url = format!(
        "{}/api/v1/hub/device/media/raw?path={}",
        cloud_base(st),
        pct_encode(path)
    );
    let Some(headers) = cloud_headers(st, &url) else {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::HUB_NOT_ENROLLED,
            "this hub has no machine credential",
        );
    };
    let mut r = st.http.get(&url);
    for (k, v) in headers {
        r = r.header(k, v);
    }
    let resp = match r.send().await {
        Ok(x) => x,
        Err(e) => {
            return err(
                cloud_proxy::CLOUD_FAILED,
                cloud_unreachable(&e.to_string()),
                "erplora.com did not answer",
            )
        }
    };
    // `404` sigue siendo `404` —el fichero no está—, pero cualquier OTRA negativa del Cloud no lo
    // es (hub#1763): contar un `500` de erplora.com como «fichero no encontrado» manda a quien
    // mira la foto a subirla otra vez cuando la foto SÍ está, y esconde la avería.
    if !resp.status().is_success() {
        return if resp.status() == reqwest::StatusCode::NOT_FOUND {
            err(StatusCode::NOT_FOUND, "not_found", "file not found")
        } else {
            relayed(resp.status().as_u16(), cloud_proxy::CLOUD_REJECTED)
        };
    }
    // El Cloud responde `{ url }` con una firma temporal de Object Storage. La descarga la hace
    // el runtime, no el navegador: los buckets no tienen CORS (un `fetch` desde el visor se cae) y
    // la firma caduca. Se pide con un cliente LIMPIO —sin las cabeceras de máquina del hub—:
    // `X-Hub-Token` es un secreto del hub y no puede viajar a un tercero (ADR-0003).
    let signed = match resp.json::<Value>().await {
        Ok(v) => v
            .get("url")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        Err(e) => {
            return err(
                cloud_proxy::CLOUD_FAILED,
                cloud_unreachable(&e.to_string()),
                "erplora.com did not answer",
            )
        }
    };
    if signed.is_empty() {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::CLOUD_UNREADABLE,
            "erplora.com returned no URL for the file",
        );
    }
    let object = match st
        .http
        .get(&signed)
        .timeout(crate::state::CLOUD_TRANSFER_TIMEOUT)
        .send()
        .await
    {
        Ok(o) if o.status().is_success() => o,
        // Igual que arriba: el objeto que no está es un `404`; el almacén que falla es una avería
        // del que guarda la foto, y decir «no encontrado» la daría por perdida (hub#1763).
        Ok(o) if o.status() == reqwest::StatusCode::NOT_FOUND => {
            return err(StatusCode::NOT_FOUND, "not_found", "file not found")
        }
        Ok(o) => return relayed(o.status().as_u16(), cloud_proxy::CLOUD_REJECTED),
        Err(e) => {
            return err(
                cloud_proxy::CLOUD_FAILED,
                cloud_unreachable(&e.to_string()),
                "erplora.com did not answer",
            )
        }
    };
    // When the size is declared, refuse an oversized object BEFORE downloading a single byte.
    if object
        .content_length()
        .is_some_and(|len| len > MAX_MEDIA_OBJECT_BYTES)
    {
        return err(
            StatusCode::PAYLOAD_TOO_LARGE,
            "media.too_large",
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
        .unwrap_or_else(|_| {
            err(
                StatusCode::INTERNAL_SERVER_ERROR,
                cloud_proxy::CLOUD_UNREADABLE,
                "unreadable answer",
            )
        })
}

/// `POST …/media/move/` en el Cloud (que hace el copy+delete sobre Object Storage). Mueve un
/// fichero o carpeta de `from` al destino `to` (ambos relativos a `media/`).
async fn cloud_move(st: &AppState, from: &str, to: &str) -> Response {
    let url = format!("{}/api/v1/hub/device/media/move/", cloud_base(st));
    let Some(headers) = cloud_headers(st, &url) else {
        return err(
            cloud_proxy::CLOUD_FAILED,
            cloud_proxy::HUB_NOT_ENROLLED,
            "this hub has no machine credential",
        );
    };
    let mut r = st.http.post(&url).json(&json!({ "from": from, "to": to }));
    for (k, v) in headers {
        r = r.header(k, v);
    }
    match r.send().await {
        Ok(resp) if resp.status().is_success() => Json(json!({ "ok": true })).into_response(),
        Ok(resp) => relayed(resp.status().as_u16(), "erplora.com could not move"),
        Err(e) => err(
            cloud_proxy::CLOUD_FAILED,
            cloud_unreachable(&e.to_string()),
            "erplora.com did not answer",
        ),
    }
}

/// Recorre el árbol de carpetas y añade `readOnly: true` a cada nodo cuya política no conceda
/// ninguna acción de modificación. El `id` de cada carpeta es su ruta relativa; la política se
/// resuelve contra el registro de módulos instalados.
fn decorate_folders(
    folders: Value,
    st: &AppState,
) -> std::pin::Pin<Box<dyn Future<Output = Value> + Send + '_>> {
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

/// El árbol de carpetas sin los nodos (ni su subárbol) que [`read_requires_admin`] reserva.
fn without_restricted_folders(folders: Value) -> Value {
    let Value::Array(nodes) = folders else {
        return folders;
    };
    Value::Array(
        nodes
            .into_iter()
            .filter(|node| {
                !node
                    .get("id")
                    .and_then(Value::as_str)
                    .is_some_and(read_requires_admin)
            })
            .map(|mut node| {
                if let Some(obj) = node.as_object_mut() {
                    if let Some(children) = obj.remove("children") {
                        obj.insert("children".into(), without_restricted_folders(children));
                    }
                }
                node
            })
            .collect(),
    )
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
    match require_reader(&st, &headers, &q.folder).await {
        Ok(reads_everything) => cloud_list(&st, &q.folder, reads_everything).await,
        Err(response) => response,
    }
}

// ─────────────────────────── GET /api/media/raw ───────────────────────────

#[derive(Deserialize)]
pub struct PathQuery {
    path: String,
}

/// Sirve el contenido de un fichero de `media/` (inline), proxyando al Cloud.
///
/// **La única puerta del hub que acepta cookie** (hub#791, ADR-0366). Todo lo demás se autentica con
/// la cabecera `X-Hub-Session` que el frontend pone a mano (ADR-0003), y eso cubre todo lo que la
/// app *llama*. No cubre lo que el navegador *pide solo*: un `<img src>` lo emite el motor de render
/// y no hay dónde ponerle una cabecera. Es el mismo problema que `EventSource` en el canal de
/// eventos, que se resolvió con un ticket en la query (`event_stream`); aquí no vale, porque la URL
/// que se pinta sale del dato (`product.image`) y el TPV pinta 50 fotos de golpe.
///
/// La cookie es de LECTURA: subir, borrar, renombrar y mover siguen exigiendo la cabecera. Por eso
/// el CSRF no es un riesgo a mitigar sino uno que no existe — una petición forjada desde otro sitio
/// no alcanza ninguna puerta que cambie algo. Ver [`mint_media_session`].
pub async fn media_raw(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<PathQuery>,
) -> Response {
    if let Err(response) = require_reader(&st, &with_cookie_session(headers), &q.path).await {
        return response;
    }
    cloud_raw(&st, &q.path).await
}

// ─────────────────────────── POST /api/media/session ───────────────────────────

/// Nombre de la cookie de lectura de media.
pub const MEDIA_COOKIE: &str = "erplora_media";

/// Ruta a la que el navegador manda la cookie: **solo** la puerta de lectura.
const MEDIA_COOKIE_PATH: &str = "/api/media/raw";

/// Copia de las cabeceras con `X-Hub-Session` rellenado desde la cookie cuando la petición no la
/// trae. Así la cookie entra por el MISMO camino de validación que la cabecera (`resolve_session`)
/// en vez de abrir un segundo criterio de «quién eres» que pudiera divergir. Si vienen las dos,
/// manda la cabecera: la pone la app, y la cookie es el apaño para quien no puede ponerla.
fn with_cookie_session(mut headers: HeaderMap) -> HeaderMap {
    if auth::session_token(&headers).is_some() {
        return headers;
    }
    if let Some(token) = auth::cookie(&headers, MEDIA_COOKIE) {
        if let Ok(value) = axum::http::HeaderValue::from_str(&token) {
            headers.insert("x-hub-session", value);
        }
    }
    headers
}

/// `POST /api/media/session` — **la app pidiéndole al hub la credencial que el navegador sí sabe
/// adjuntar.** Exige la sesión por cabecera (así que un anónimo no obtiene ninguna) y devuelve la
/// cookie de lectura de media.
///
/// La cookie lleva **el propio token de sesión**, no una credencial nueva: caduca exactamente cuando
/// caduca la sesión, y cerrar sesión la invalida sin que haya una segunda vida que revocar aparte.
/// Los atributos son el mínimo que funciona: `Path` a la puerta de lectura y a nada más, `HttpOnly`
/// (un XSS no la levanta), `Secure` y `SameSite=Strict`.
pub async fn mint_media_session(State(st): State<AppState>, headers: HeaderMap) -> Response {
    if let Err(response) = require_user(&st, &headers).await {
        return response;
    }
    // Sin token que meter en la cookie no hay nada que emitir: pasa en `AuthMode::Dev`, donde la
    // puerta concede sin sesión y el frontend no necesita cookie porque tampoco la necesita nadie.
    let Some(token) = auth::session_token(&headers) else {
        return Json(json!({ "ok": true, "data": { "cookie": false } })).into_response();
    };
    let cookie = format!(
        "{MEDIA_COOKIE}={token}; Path={MEDIA_COOKIE_PATH}; HttpOnly; Secure; SameSite=Strict"
    );
    (
        [(header::SET_COOKIE, cookie)],
        Json(json!({ "ok": true, "data": { "cookie": true } })),
    )
        .into_response()
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
            "media.invalid_name",
            "the new name is not valid (a name, not a path)",
        );
    }
    if req.path.trim_matches('/').is_empty() {
        return err(
            StatusCode::BAD_REQUEST,
            "media.missing_path",
            "missing path to rename",
        );
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
        return err(
            StatusCode::BAD_REQUEST,
            "media.missing_path",
            "missing source path",
        );
    }
    if req.from == req.to {
        return err(
            StatusCode::BAD_REQUEST,
            "media.same_path",
            "source and destination are the same",
        );
    }
    // No se puede mover algo al interior de sí mismo (carpeta dentro de su subcarpeta).
    if is_within(&req.from, &req.to) {
        return err(
            StatusCode::BAD_REQUEST,
            "media.move_into_itself",
            "a folder cannot be moved into itself",
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
    path.split('/')
        .next()
        .is_some_and(|top| top.starts_with('_'))
}

/// Aplana el árbol de carpetas del listado (`[{id, children:[…]}]`) en rutas.
fn flatten_folder_ids(folders: &Value, out: &mut Vec<String>) {
    let Some(arr) = folders.as_array() else {
        return;
    };
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
    let url = format!(
        "{}/api/v1/hub/device/media/?folder={}",
        cloud_base(st),
        pct_encode(folder)
    );
    let headers = cloud_headers(st, &url)?;
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
    let url = format!(
        "{}/api/v1/hub/device/media/raw?path={}",
        cloud_base(st),
        pct_encode(path)
    );
    let headers = cloud_headers(st, &url)?;
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
    let object = st
        .http
        .get(&signed)
        .timeout(crate::state::CLOUD_TRANSFER_TIMEOUT)
        .send()
        .await
        .ok()?;
    if !object.status().is_success() {
        return None;
    }
    if object
        .content_length()
        .is_some_and(|len| len > MAX_MEDIA_OBJECT_BYTES)
    {
        tracing::warn!(
            path,
            "export: objeto de media por encima del tope, se omite"
        );
        return None;
    }
    let bytes = object.bytes().await.ok()?;
    if bytes.len() as u64 > MAX_MEDIA_OBJECT_BYTES {
        tracing::warn!(
            path,
            "export: objeto de media por encima del tope, se omite"
        );
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

/// Maximum number of files in one Cloud media request.
///
/// The Cloud endpoint already accepts repeated multipart fields named `files`. Keeping the batch
/// deliberately small avoids the per-request/file guard at the edge and bounds the amount of work
/// the synchronous Cloud view hands to Object Storage at once. A restaurant blueprint with ~300
/// images used to make ~300 HTTP requests here and consistently lost everything after the first
/// ~100; grouping by folder turns that into a handful of requests.
const MAX_BUNDLE_MEDIA_BATCH_FILES: usize = 40;

/// A batch is also bounded by bytes, not only by file count. `Part::bytes` owns its payload, so a
/// 40 × 25 MiB multipart would otherwise briefly duplicate far more than the Hub container can
/// hold. The per-object limit remains [`MAX_MEDIA_OBJECT_BYTES`].
const MAX_BUNDLE_MEDIA_BATCH_BYTES: u64 = MAX_MEDIA_OBJECT_BYTES;

/// Total attempts for an idempotent multipart. A media upload overwrites by `(folder, name)`, so
/// replaying the whole batch after an edge timeout cannot create duplicates. Bounded retries cover
/// the Cloud/edge throttling that motivated batching without making an import hang indefinitely.
const BUNDLE_MEDIA_UPLOAD_MAX_ATTEMPTS: usize = 3;
const BUNDLE_MEDIA_UPLOAD_RETRY_BASE_MS: u64 = 200;

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub(crate) struct BundleMediaUploadReport {
    pub copied: u32,
    pub failed: u32,
}

impl BundleMediaUploadReport {
    fn add(&mut self, other: Self) {
        self.copied += other.copied;
        self.failed += other.failed;
    }
}

struct BundleMediaUpload<'a> {
    name: String,
    bytes: &'a [u8],
}

/// Counts returned by the Cloud for one terminal multipart response. The contract reports `saved`
/// and `failed` on a partial rejection; older Clouds only signalled success through the status.
/// Trust explicit counts only when they account for the whole batch. Retryable statuses bypass
/// this function: an exhausted 408/429/5xx fails the complete batch conservatively.
fn bundle_upload_response_counts(
    status_success: bool,
    payload: Option<&Value>,
    expected: usize,
) -> BundleMediaUploadReport {
    if let Some(body) = payload {
        let has_counts = body.get("saved").is_some() || body.get("failed").is_some();
        if has_counts {
            let saved = body.get("saved").and_then(Value::as_u64);
            let failed = match body.get("failed") {
                Some(value) => value.as_u64(),
                None => Some(0),
            };
            let explicit = saved
                .zip(failed)
                .filter(|(saved, failed)| saved + failed == expected as u64)
                .map(|(saved, failed)| BundleMediaUploadReport {
                    copied: saved as u32,
                    failed: failed as u32,
                });
            return explicit.unwrap_or(BundleMediaUploadReport {
                copied: 0,
                failed: expected as u32,
            });
        }
    }

    // Backward compatibility with the original endpoint (`2xx {success:true}` without counts),
    // while remaining fail-closed for transport/5xx responses whose outcome is unknown.
    if status_success {
        BundleMediaUploadReport {
            copied: expected as u32,
            failed: 0,
        }
    } else {
        BundleMediaUploadReport {
            copied: 0,
            failed: expected as u32,
        }
    }
}

fn bundle_upload_status_retryable(status: StatusCode) -> bool {
    status == StatusCode::REQUEST_TIMEOUT
        || status == StatusCode::TOO_MANY_REQUESTS
        || status.is_server_error()
}

async fn upload_bundle_batch(
    st: &AppState,
    headers: &[(&'static str, String)],
    folder: &str,
    batch: &[BundleMediaUpload<'_>],
) -> BundleMediaUploadReport {
    let url = format!("{}/api/v1/hub/device/media/", cloud_base(st));
    for attempt in 1..=BUNDLE_MEDIA_UPLOAD_MAX_ATTEMPTS {
        // Multipart bodies are streams and cannot be replayed. Rebuild the bounded form for each
        // attempt; the byte cap above keeps this owned copy within the Hub's memory budget.
        let mut form = reqwest::multipart::Form::new().text("folder", folder.to_string());
        for file in batch {
            let part =
                reqwest::multipart::Part::bytes(file.bytes.to_vec()).file_name(file.name.clone());
            let part = match part.mime_str(content_type(&file.name)) {
                Ok(part) => part,
                Err(error) => {
                    tracing::warn!(file = %file.name, %error, "import: MIME inválido para fichero media");
                    return BundleMediaUploadReport {
                        copied: 0,
                        failed: batch.len() as u32,
                    };
                }
            };
            form = form.part("files", part);
        }

        let mut request = st
            .http
            .post(&url)
            .multipart(form)
            .timeout(crate::state::CLOUD_TRANSFER_TIMEOUT);
        for (key, value) in headers {
            request = request.header(*key, value);
        }
        match request.send().await {
            Ok(response) => {
                let status = response.status();
                let retryable = bundle_upload_status_retryable(status);
                if retryable {
                    if attempt < BUNDLE_MEDIA_UPLOAD_MAX_ATTEMPTS {
                        tracing::warn!(folder, %status, attempt, files = batch.len(), "import: reintentando lote media idempotente");
                        tokio::time::sleep(std::time::Duration::from_millis(
                            BUNDLE_MEDIA_UPLOAD_RETRY_BASE_MS * attempt as u64,
                        ))
                        .await;
                        continue;
                    }
                    // A timeout/429/5xx is an unknown final outcome. Even if its JSON claims some
                    // writes, retry attempts may overlap; count the complete batch as failed so the
                    // report can never present an unverified file as copied.
                    tracing::warn!(folder, %status, attempts = attempt, files = batch.len(), "import: lote media agotó sus reintentos");
                    return BundleMediaUploadReport {
                        copied: 0,
                        failed: batch.len() as u32,
                    };
                }

                let payload = response.json::<Value>().await.ok();
                let report = bundle_upload_response_counts(
                    status.is_success(),
                    payload.as_ref(),
                    batch.len(),
                );
                if report.failed > 0 {
                    tracing::warn!(folder, status = %status, copied = report.copied, failed = report.failed, "import: el Cloud rechazó parte o todo el lote de media");
                }
                return report;
            }
            Err(error) if attempt < BUNDLE_MEDIA_UPLOAD_MAX_ATTEMPTS => {
                tracing::warn!(folder, %error, attempt, files = batch.len(), "import: reintentando lote media tras error de red");
                tokio::time::sleep(std::time::Duration::from_millis(
                    BUNDLE_MEDIA_UPLOAD_RETRY_BASE_MS * attempt as u64,
                ))
                .await;
            }
            Err(error) => {
                tracing::warn!(folder, %error, attempts = attempt, files = batch.len(), "import: lote media agotó sus reintentos de red");
                return BundleMediaUploadReport {
                    copied: 0,
                    failed: batch.len() as u32,
                };
            }
        }
    }
    unreachable!("el rango de intentos nunca está vacío")
}

/// Sube las entradas `media/<rel>` de un bundle al gestor media.
///
/// Las rutas se validan antes de cualquier petición, los ficheros se agrupan por carpeta (el
/// contrato multipart tiene un único campo `folder`) y se mandan en lotes de hasta 40 y 25 MiB.
/// El resultado sigue siendo best-effort por fichero: un lote parcial usa los contadores
/// `saved`/`failed` del Cloud y los lotes posteriores continúan.
pub(crate) async fn upload_bundle_media(
    st: &AppState,
    entries: &[(&str, &[u8])],
) -> BundleMediaUploadReport {
    let mut report = BundleMediaUploadReport::default();
    let mut by_folder: BTreeMap<String, Vec<BundleMediaUpload<'_>>> = BTreeMap::new();

    for &(rel, bytes) in entries {
        let Some((folder, name)) = bundle_media_destination(rel) else {
            tracing::warn!(entry = rel, "import: ruta media rechazada");
            report.failed += 1;
            continue;
        };
        if bytes.len() as u64 > MAX_MEDIA_OBJECT_BYTES {
            tracing::warn!(
                entry = rel,
                bytes = bytes.len(),
                "import: fichero media por encima del tope"
            );
            report.failed += 1;
            continue;
        }
        by_folder
            .entry(folder)
            .or_default()
            .push(BundleMediaUpload { name, bytes });
    }

    let upload_url = format!("{}/api/v1/hub/device/media/", cloud_base(st));
    let Some(headers) = cloud_headers(st, &upload_url) else {
        report.failed += by_folder.values().map(Vec::len).sum::<usize>() as u32;
        return report;
    };

    for (folder, files) in by_folder {
        let mut start = 0;
        while start < files.len() {
            let mut end = start;
            let mut bytes = 0u64;
            while end < files.len() && end - start < MAX_BUNDLE_MEDIA_BATCH_FILES {
                let next = files[end].bytes.len() as u64;
                if end > start && bytes + next > MAX_BUNDLE_MEDIA_BATCH_BYTES {
                    break;
                }
                bytes += next;
                end += 1;
            }
            report.add(upload_bundle_batch(st, &headers, &folder, &files[start..end]).await);
            start = end;
        }
    }
    report
}

/// Stores ONE file the runtime itself vetted and named (hub#2335/hub#2347: the photo, video or PDF
/// of a WhatsApp header, uploaded from a flow step) in `media/<folder>/<name>`. `true` only when
/// erplora.com says it stored it; a hub with no machine credential, a file that cannot be read, a
/// store that failed and an answer that never came are all `false` — the caller must not hand out
/// a reference to a file that is not there.
///
/// **Streamed from `path`, never held whole**: a header PDF weighs up to 100 MB and the hub runs in
/// 96 MiB. The part declares its `size`, so the store gets a `Content-Length` and not a chunked
/// body. Same road and retry ladder as a blueprint's media ([`upload_bundle_batch`]): the file is
/// reopened for each attempt, and the name is the caller's, so a retry overwrites the same file
/// instead of leaving a second copy.
pub(crate) async fn store_vetted_file(
    st: &AppState,
    folder: &str,
    name: &str,
    path: &Path,
    size: u64,
    mime: &str,
) -> bool {
    let url = format!("{}/api/v1/hub/device/media/", cloud_base(st));
    let Some(headers) = cloud_headers(st, &url) else {
        return false;
    };
    for attempt in 1..=BUNDLE_MEDIA_UPLOAD_MAX_ATTEMPTS {
        let file = match std::fs::File::open(path) {
            Ok(file) => file,
            Err(error) => {
                tracing::warn!(file = name, %error, "media: the vetted file could not be reopened");
                return false;
            }
        };
        let part = reqwest::multipart::Part::stream_with_length(
            reqwest::Body::wrap_stream(file_chunks(file)),
            size,
        )
        .file_name(name.to_string());
        let part = match part.mime_str(mime) {
            Ok(part) => part,
            Err(error) => {
                tracing::warn!(file = name, %error, "media: invalid MIME for a vetted file");
                return false;
            }
        };
        let form = reqwest::multipart::Form::new()
            .text("folder", folder.to_string())
            .part("files", part);
        let mut request = st
            .http
            .post(&url)
            .multipart(form)
            .timeout(crate::state::CLOUD_TRANSFER_TIMEOUT);
        for (key, value) in &headers {
            request = request.header(*key, value);
        }
        let retry = match request.send().await {
            Ok(response) => {
                let status = response.status();
                if !bundle_upload_status_retryable(status) {
                    let payload = response.json::<Value>().await.ok();
                    let report =
                        bundle_upload_response_counts(status.is_success(), payload.as_ref(), 1);
                    if report.copied != 1 {
                        tracing::warn!(folder, file = name, %status, "media: erplora.com did not store the vetted file");
                    }
                    return report.copied == 1;
                }
                format!("{status}")
            }
            Err(error) => error.to_string(),
        };
        if attempt == BUNDLE_MEDIA_UPLOAD_MAX_ATTEMPTS {
            tracing::warn!(folder, file = name, attempts = attempt, error = %retry, "media: the vetted file ran out of retries");
            return false;
        }
        tracing::warn!(folder, file = name, attempt, error = %retry, "media: retrying the vetted file");
        tokio::time::sleep(std::time::Duration::from_millis(
            BUNDLE_MEDIA_UPLOAD_RETRY_BASE_MS * attempt as u64,
        ))
        .await;
    }
    false
}

/// A local file as a stream of 64 KiB chunks, read as the body is sent: at most one chunk of it is
/// in memory at a time. A read error ends the body with that error (the request fails, never
/// sends a truncated file as whole).
fn file_chunks(
    file: std::fs::File,
) -> impl futures_util::Stream<Item = std::io::Result<Vec<u8>>> + Send + 'static {
    futures_util::stream::unfold(Some(file), |file| async move {
        use std::io::Read;
        let mut file = file?;
        let mut chunk = vec![0u8; 64 * 1024];
        match file.read(&mut chunk) {
            Ok(0) => None,
            Ok(read) => {
                chunk.truncate(read);
                Some((Ok(chunk), Some(file)))
            }
            Err(error) => Some((Err(error), None)),
        }
    })
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

/// A refusal in the envelope every door of this hub answers: `{ ok:false, error:{ code, message } }`.
///
/// hub#1776: the `code` is required. Before it this helper emitted only a Spanish `message`, so Files
/// could only say «check the connection» whatever had failed — erplora.com down, a hub with no
/// machine credential, a folder that no longer exists, a read-only module folder. The screen
/// translates the code (`files.errors.*`, `runtimeErrors.*`); the message is for the log.
fn err(status: StatusCode, code: &str, message: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// The code of an answer of erplora.com the hub RELAYS: «that does not exist» keeps meaning that
/// from either end; anything else it refused is `cloud_rejected`.
fn relayed_code(status: StatusCode) -> &'static str {
    if status == StatusCode::NOT_FOUND {
        "not_found"
    } else {
        cloud_proxy::CLOUD_REJECTED
    }
}

/// A refusal of erplora.com the hub relays, with the status [`cloud_proxy::relayed_status`] gives it
/// and the code that status means.
fn relayed(raw_status: u16, message: &str) -> Response {
    let status = cloud_proxy::relayed_status(cloud_proxy::cloud_status(raw_status));
    err(status, relayed_code(status), message)
}

// ─────────────────────────── Política de acciones del usuario (ADR-0172) ───────────────────────────
//
// Reading (list, open, download) asks for a session, and the hub's own folders (`_*`) and the apps'
// tree (`modules/…`) for an owner or an administrator: they hold the hub's request log and the
// records sent to the tax agency with the customers' data (hub#2495, `read_requires_admin`). Every
// other folder is read by any session — the till paints its product photos for the cashier.
//
// Lo que MODIFICA (subir, renombrar, borrar) depende de quién sea el dueño de la carpeta:
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
    pub const FULL: Self = Self {
        upload: true,
        rename: true,
        delete: true,
    };
    pub const READ_ONLY: Self = Self {
        upload: false,
        rename: false,
        delete: false,
    };

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

/// `true` when only an owner or an administrator may READ `rel` (hub#2495): a folder of the hub
/// (first segment starting with `_`: `_logs`, `_system`, `_import_tmp`…) or anything under the apps'
/// tree (`modules`, `modules/<folder>/…`). No app declares today who else may read its files, and the
/// only one that keeps files there (VeriFactu) keeps fiscal evidence with customers' data.
///
/// The question is asked of the path as erplora.com will resolve it, not of the first characters:
/// `\` counts as a separator and a `.` or `..` segment answers `true`, so `hospitality/../_logs/x`
/// cannot read as a folder of the business. An administrator still passes those to erplora.com,
/// which validates the route as it always did.
pub fn read_requires_admin(rel: &str) -> bool {
    let normalized = rel.replace('\\', "/");
    let mut segments = normalized.split('/').filter(|s| !s.is_empty());
    let Some(top) = segments.next() else {
        return false;
    };
    if top == "." || top == ".." || segments.any(|s| s == "." || s == "..") {
        return true;
    }
    top.starts_with('_') || top == MODULES_ROOT
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
        return owner
            .map(MediaPolicy::from)
            .unwrap_or(MediaPolicy::READ_ONLY);
    }
    MediaPolicy::FULL
}

/// Resuelve la política de una ruta consultando el registro de módulos instalados.
async fn resolve_policy(st: &AppState, rel: &str) -> MediaPolicy {
    let Some(folder) = module_folder_of(rel) else {
        return policy_for(rel, None);
    };
    let rt = st.runtime.read().await;
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
        "media.read_only_folder",
        "this folder is read-only: its module does not allow that action",
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
            assert_eq!(
                bundle_media_destination(evil),
                None,
                "{evil} debía rechazarse"
            );
        }
    }

    /// Entradas que no nombran un fichero (`media/`, `media/sub/`) no producen destino.
    #[test]
    fn una_entrada_sin_nombre_de_fichero_no_produce_destino() {
        assert_eq!(bundle_media_destination(""), None);
        assert_eq!(bundle_media_destination("."), None);
        assert_eq!(
            bundle_media_destination("sub/"),
            Some(("".into(), "sub".into()))
        );
    }

    #[test]
    fn solo_timeouts_throttling_y_errores_del_servidor_reintentan() {
        for retryable in [
            StatusCode::REQUEST_TIMEOUT,
            StatusCode::TOO_MANY_REQUESTS,
            StatusCode::INTERNAL_SERVER_ERROR,
            StatusCode::BAD_GATEWAY,
            StatusCode::SERVICE_UNAVAILABLE,
        ] {
            assert!(bundle_upload_status_retryable(retryable), "{retryable}");
        }
        for terminal in [
            StatusCode::BAD_REQUEST,
            StatusCode::UNAUTHORIZED,
            StatusCode::FORBIDDEN,
            StatusCode::UNPROCESSABLE_ENTITY,
        ] {
            assert!(!bundle_upload_status_retryable(terminal), "{terminal}");
        }
    }

    #[test]
    fn un_rechazo_parcial_no_inventa_contadores() {
        let payload = json!({ "saved": 39, "failed": 1 });
        assert_eq!(
            bundle_upload_response_counts(false, Some(&payload), 40),
            BundleMediaUploadReport {
                copied: 39,
                failed: 1
            }
        );
        // Una respuesta que no cubre el lote completo es desconocida y por tanto falla cerrada.
        let inconsistent = json!({ "saved": 38, "failed": 1 });
        assert_eq!(
            bundle_upload_response_counts(true, Some(&inconsistent), 40),
            BundleMediaUploadReport {
                copied: 0,
                failed: 40
            }
        );
        let missing_failed = json!({ "saved": 39 });
        assert_eq!(
            bundle_upload_response_counts(true, Some(&missing_failed), 40),
            BundleMediaUploadReport {
                copied: 0,
                failed: 40
            },
            "un 201 con un contador incompleto nunca cae al fallback legacy"
        );
        assert_eq!(
            bundle_upload_response_counts(true, Some(&json!({ "success": true })), 40),
            BundleMediaUploadReport {
                copied: 40,
                failed: 0
            },
            "el Cloud antiguo no tenía contadores; su 2xx sigue siendo compatible"
        );
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
        for path in [
            "_logs",
            "_logs/hub.2026-07-31",
            "_system",
            "_system/activity.json",
        ] {
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
        assert_eq!(
            module_folder_of("modules/verifactu/xml/a.xml"),
            Some("verifactu")
        );
        assert_eq!(module_folder_of("modules/verifactu"), Some("verifactu"));
        assert_eq!(module_folder_of("modules"), None);
        assert_eq!(module_folder_of("facturas/modules/x"), None);
        assert_eq!(module_folder_of(""), None);
    }
}
