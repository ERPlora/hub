//! Capa SERVER del motor export/import de blueprints (ADR-0113).
//!
//! El MOTOR de datos vive en el runtime (`erplora_runtime::export::export_hub` +
//! `erplora_runtime::import::import_sections`, Fase 1-2, columna del humano); esta capa solo
//! añade lo que es del server: auth (sesión admin owner/admin, mismo gate que `/api/settings`),
//! validación de payload, los bytes de `media/` (gestor media, ADR-0047), el `.p12` del negocio
//! (tabla `_hub_certificate`, ADR-0079 — la CONTRASEÑA NO viaja, decisión (d)), el empaquetado
//! ZIP en memoria y el ciclo inspect→import con temporal.
//!
//! Endpoints (montados en `crate::app`):
//!   POST /api/hub/export          → `application/zip` (`<name>_<locale>.blueprint.zip`)
//!   POST /api/hub/import/inspect  → body binario del zip → `{ ok, upload_id, manifest }`
//!   POST /api/hub/import          → `{ upload_id, selection }` → `{ ok, report }`
//!
//! Seguridad: anti zip-slip en TODA entrada del zip (rutas `..`/absolutas/`\` → 422, patrón de
//! `erplora-source`); el `upload_id` se valida como UN componente simple antes de tocar el FS;
//! la integridad sha256 del manifest es dura (mismatch → 422 SIN efectos, ADR-0015).

use std::collections::BTreeMap;
use std::io::{Cursor, Read as _, Write as _};
use std::path::{Component, Path};

use axum::body::{Body, Bytes};
use axum::extract::State;
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use erplora_runtime::export::{self, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{self, ImportSelection};
use erplora_runtime::Runtime;

use crate::state::AppState;
use crate::{auth, install, media};

/// Techo del zip de import (defensivo; el default de axum son 2 MiB, corto para un blueprint
/// con media). Se aplica como `DefaultBodyLimit` de la ruta `/api/hub/import/inspect`.
pub const MAX_BLUEPRINT_BYTES: usize = 256 * 1024 * 1024;

/// Subdir del `module_cache` donde viven los temporales del inspect (`_import_tmp/<upload_id>/`).
/// El `module_cache` ya es la carpeta de trabajo efímera del server (stateless en Hub Cloud) y la
/// re-hidratación de módulos lee de la BD (no escanea el dir), así que un subdir extra no molesta.
const IMPORT_TMP_DIR: &str = "_import_tmp";

/// `401` para fallo de auth (sin sesión / sesión inválida / rol insuficiente). Mismo envelope
/// que `settings.rs`.
fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// Error en el envelope estándar `{ ok:false, error:{ message } }` (patrón `media.rs`).
fn err(code: StatusCode, msg: &str) -> Response {
    (
        code,
        Json(json!({ "ok": false, "error": { "message": msg } })),
    )
        .into_response()
}

fn sha256_hex(bytes: &[u8]) -> String {
    let d = Sha256::digest(bytes);
    d.iter().map(|b| format!("{b:02x}")).collect()
}

// ─────────────────────────── POST /api/hub/export ───────────────────────────

/// Body del export: nombre lógico + idioma + selección de secciones (checkboxes del formulario).
#[derive(Deserialize)]
pub struct ExportReq {
    name: String,
    #[serde(default = "default_locale")]
    locale: String,
    #[serde(default)]
    selection: ExportSelectionReq,
}

fn default_locale() -> String {
    "es".to_string()
}

/// Espejo serde de `erplora_runtime::export::ExportSelection` (que no deriva Deserialize).
#[derive(Deserialize, Default)]
pub struct ExportSelectionReq {
    #[serde(default)]
    users: bool,
    #[serde(default)]
    settings: bool,
    #[serde(default)]
    settings_items: Option<Vec<String>>,
    #[serde(default)]
    fiscal: bool,
    #[serde(default)]
    media: bool,
    #[serde(default)]
    modules: Vec<ModuleSelReq>,
}

#[derive(Deserialize)]
pub struct ModuleSelReq {
    module_id: String,
    #[serde(default)]
    with_data: bool,
}

impl ExportSelectionReq {
    fn into_selection(self) -> ExportSelection {
        ExportSelection {
            users: self.users,
            settings: self.settings,
            settings_items: self.settings_items,
            fiscal: self.fiscal,
            media: self.media,
            modules: self
                .modules
                .into_iter()
                .map(|m| ModuleDataSelection {
                    module_id: m.module_id,
                    with_data: m.with_data,
                })
                .collect(),
        }
    }
}

/// `true` si `s` sirve como componente de nombre de fichero: ni vacío, ni separadores, ni `..`,
/// ni punto inicial; solo `[A-Za-z0-9._-]`, máx. 64. El nombre acaba en el `Content-Disposition`
/// y el usuario puede teclearlo libremente → se valida duro (422 si no cumple).
fn is_safe_name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && !s.starts_with('.')
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
}

/// `true` si `s` parece un locale BCP-47 corto (`es`, `en`, `pt-BR`).
fn is_safe_locale(s: &str) -> bool {
    (2..=10).contains(&s.len()) && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
}

/// POST /api/hub/export — exporta el hub a un `.blueprint.zip` según la selección.
/// Auth = sesión admin (owner/admin), el MISMO gate que `PUT /api/settings`/certificate.
pub async fn export_blueprint(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<ExportReq>>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    // hub del PLANO DE DATOS: el mismo contexto que usan /api/command|query. En Session es
    // `config.hub_id` (despliegue, no spoofable); en Dev es el de cabecera/`local` — así el
    // export ve EXACTAMENTE las filas que escribió el resto de la app (review 2026-07-12:
    // en Dev el export salía vacío por volcar `config.hub_id` mientras los datos iban a `local`).
    let data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx.hub_id,
        Err(e) => return unauthorized(e),
    };
    // Payload: el body es obligatorio; nombre/locale se validan duro (van a un filename).
    let Some(Json(req)) = body else {
        return err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "falta el body JSON { name, locale, selection }",
        );
    };
    let name = req.name.trim().to_string();
    if !is_safe_name(&name) {
        return err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "name inválido: solo letras/números/guiones (sin separadores de ruta)",
        );
    }
    let locale = req.locale.trim().to_string();
    if !is_safe_locale(&locale) {
        return err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "locale inválido (esperado p.ej. \"es\")",
        );
    }
    let selection = req.selection.into_selection();

    // Motor del runtime (Fase 1): manifest + data/*.sql. `created_at` lo aporta esta capa
    // (el runtime no lee el reloj) en ISO-8601 UTC.
    let created_at = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true);
    let bundle = match export::export_hub(
        &rt,
        &data_hub_id,
        &selection,
        &name,
        &locale,
        &created_at,
    )
    .await
    {
        Ok(b) => b,
        Err(e) => return crate::err_response(e),
    };
    let mut manifest = bundle.manifest;
    let mut files = bundle.files;

    // Certificado fiscal (decisión (d)): si se pidió `fiscal` y el hub tiene `.p12`, viaja el
    // binario TAL CUAL (ya protegido por su propia contraseña, que NO viaja) como
    // `data/fiscal/certificate.p12`. Se lee de `_hub_certificate` (ADR-0079) vía el db handle.
    if selection.fiscal {
        if let Some(p12) = read_certificate_p12(&rt, &data_hub_id).await {
            let path = "data/fiscal/certificate.p12".to_string();
            manifest.sha256.insert(path.clone(), sha256_hex(&p12));
            files.insert(path, p12);
            ensure_section(&mut manifest.sections, "fiscal");
        }
    }
    drop(rt); // la carpeta media no necesita el runtime: suelta el lock antes del I/O de disco.

    // Media (ADR-0047): los bytes los añade el server (el runtime solo marca la sección). Se
    // recorre `media_dir` en un hilo blocking; carpetas de sistema `_*` de primer nivel
    // (`_logs`, `_system`, `_import_tmp`) NO son datos del negocio y se excluyen.
    if selection.media {
        let root = st.config.media_dir.clone();
        let media_files = tokio::task::spawn_blocking(move || collect_media(&root))
            .await
            .unwrap_or_default();
        if !media_files.is_empty() {
            ensure_section(&mut manifest.sections, "media");
        }
        for (rel, bytes) in media_files {
            manifest.sha256.insert(rel.clone(), sha256_hex(&bytes));
            files.insert(rel, bytes);
        }
    }

    // Empaquetado: manifest.json (fuente de verdad, actualizado con los sha añadidos) + files.
    let manifest_bytes = match serde_json::to_vec_pretty(&manifest) {
        Ok(b) => b,
        Err(e) => return err(StatusCode::INTERNAL_SERVER_ERROR, &format!("manifest: {e}")),
    };
    let zip_bytes = match build_zip(&manifest_bytes, &files) {
        Ok(b) => b,
        Err(e) => return err(StatusCode::INTERNAL_SERVER_ERROR, &format!("zip: {e}")),
    };

    Response::builder()
        .header(header::CONTENT_TYPE, "application/zip")
        .header(
            header::CONTENT_DISPOSITION,
            format!("attachment; filename=\"{name}_{locale}.blueprint.zip\""),
        )
        .body(Body::from(zip_bytes))
        .unwrap_or_else(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "respuesta inválida"))
}

/// Añade `section` a la lista si no está (el runtime puede haberla registrado ya).
fn ensure_section(sections: &mut Vec<String>, section: &str) {
    if !sections.iter().any(|s| s == section) {
        sections.push(section.to_string());
    }
}

/// Bytes DEScifrados del PKCS#12 del negocio (`_hub_certificate.pkcs12_b64`, ADR-0079/ADR-0016)
/// del hub, o `None` si no hay certificado (o falla el descifrado/no hay master key). La
/// contraseña NO se lee: no viaja (decisión d). Desde ERPlora/hub#114 la columna va cifrada
/// at-rest — pasa por `erplora_runtime::certificate::der_bytes` en vez de leer/decodificar el
/// base64 crudo de la fila.
async fn read_certificate_p12(rt: &Runtime, hub_id: &str) -> Option<Vec<u8>> {
    erplora_runtime::certificate::der_bytes(rt.db(), hub_id).await.ok().flatten()
}

/// Recorre `media/` y devuelve `(ruta "media/<rel>", bytes)` por fichero. No sigue symlinks
/// (podrían salir del root); excluye las carpetas de sistema `_*` de PRIMER nivel; profundidad
/// acotada (defensivo, como `MAX_TREE_DEPTH` del gestor media).
fn collect_media(root: &Path) -> Vec<(String, Vec<u8>)> {
    let mut out = Vec::new();
    walk_media(root, root, 0, &mut out);
    out
}

fn walk_media(root: &Path, dir: &Path, depth: usize, out: &mut Vec<(String, Vec<u8>)>) {
    const MAX_DEPTH: usize = 16;
    if depth > MAX_DEPTH {
        return;
    }
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for e in rd.flatten() {
        let Ok(ft) = e.file_type() else { continue };
        if ft.is_symlink() {
            continue;
        }
        let path = e.path();
        let name = e.file_name().to_string_lossy().into_owned();
        if ft.is_dir() {
            if depth == 0 && name.starts_with('_') {
                continue; // _logs/_system/…: sistema, no datos del negocio.
            }
            walk_media(root, &path, depth + 1, out);
        } else if ft.is_file() {
            if let Ok(bytes) = std::fs::read(&path) {
                let rel = path
                    .strip_prefix(root)
                    .unwrap_or(&path)
                    .components()
                    .filter_map(|c| match c {
                        Component::Normal(s) => Some(s.to_string_lossy().into_owned()),
                        _ => None,
                    })
                    .collect::<Vec<_>>()
                    .join("/");
                out.push((format!("media/{rel}"), bytes));
            }
        }
    }
}

/// Construye el `.blueprint.zip` en memoria: `manifest.json` + cada fichero del bundle.
fn build_zip(manifest_bytes: &[u8], files: &BTreeMap<String, Vec<u8>>) -> Result<Vec<u8>, String> {
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
        w.start_file("manifest.json", opts)
            .map_err(|e| e.to_string())?;
        w.write_all(manifest_bytes).map_err(|e| e.to_string())?;
        for (path, bytes) in files {
            w.start_file(path, opts).map_err(|e| e.to_string())?;
            w.write_all(bytes).map_err(|e| e.to_string())?;
        }
        w.finish().map_err(|e| e.to_string())?;
    }
    Ok(buf)
}

// ─────────────────────── POST /api/hub/import/inspect ───────────────────────

/// POST /api/hub/import/inspect — body binario del zip (`application/octet-stream`). Valida en
/// memoria (zip bien formado, rutas seguras, `manifest.json` conforme al struct y
/// `schema_version` conocida), persiste el zip en un temporal y devuelve
/// `{ ok, upload_id, manifest }` para que la UI pinte la selección del import.
pub async fn import_inspect(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    {
        let arc = match st.runtime_for(&st.hub_id()).await {
            Ok(rt) => rt,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    if body.is_empty() {
        return err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "cuerpo vacío: se espera el zip del blueprint",
        );
    }

    // Validación en memoria (anti zip-slip incluido) — SOLO se lee el manifest.
    let manifest = match read_manifest(&body) {
        Ok(m) => m,
        Err(msg) => return err(StatusCode::UNPROCESSABLE_ENTITY, &msg),
    };

    // Persistir el zip TAL CUAL en el temporal del server (`module_cache/_import_tmp/<id>/`).
    let upload_id = new_upload_id(&body);
    let dir = st.config.module_cache.join(IMPORT_TMP_DIR).join(&upload_id);
    let write = tokio::fs::create_dir_all(&dir).await;
    let write = match write {
        Ok(()) => tokio::fs::write(dir.join("blueprint.zip"), &body).await,
        Err(e) => Err(e),
    };
    if let Err(e) = write {
        return err(
            StatusCode::INTERNAL_SERVER_ERROR,
            &format!("no se pudo guardar el temporal: {e}"),
        );
    }

    let manifest_v = serde_json::to_value(&manifest).unwrap_or(Value::Null);
    Json(json!({ "ok": true, "upload_id": upload_id, "manifest": manifest_v })).into_response()
}

/// `true` si la ruta de una entrada del zip es segura: relativa, sin `..`, sin `\`, solo
/// componentes normales (patrón anti zip-slip de `erplora-source`, aplicado a bytes en memoria).
fn is_safe_entry(name: &str) -> bool {
    if name.contains('\\') || name.starts_with('/') {
        return false;
    }
    Path::new(name)
        .components()
        .all(|c| matches!(c, Component::Normal(_)))
}

/// Abre el zip en memoria, valida TODAS las rutas (anti zip-slip) y devuelve el
/// `BlueprintManifest` de `manifest.json` (con `schema_version` conocida). `Err(mensaje)` → 422.
fn read_manifest(bytes: &[u8]) -> Result<export::BlueprintManifest, String> {
    let mut archive =
        zip::ZipArchive::new(Cursor::new(bytes)).map_err(|e| format!("zip inválido: {e}"))?;
    // Anti zip-slip: se validan TODAS las entradas ANTES de leer nada.
    for i in 0..archive.len() {
        let entry = archive
            .by_index(i)
            .map_err(|e| format!("zip inválido: {e}"))?;
        let raw = entry.name().to_string();
        if !is_safe_entry(&raw) {
            return Err(format!("zip inseguro: ruta no permitida ({raw})"));
        }
    }
    let mut mf = archive
        .by_name("manifest.json")
        .map_err(|_| "el zip no contiene manifest.json".to_string())?;
    let mut s = String::new();
    mf.read_to_string(&mut s)
        .map_err(|e| format!("manifest.json ilegible: {e}"))?;
    let manifest: export::BlueprintManifest =
        serde_json::from_str(&s).map_err(|e| format!("manifest.json inválido: {e}"))?;
    if manifest.schema_version != export::SCHEMA_VERSION {
        return Err(format!(
            "schema_version {} desconocida (este hub soporta {})",
            manifest.schema_version,
            export::SCHEMA_VERSION
        ));
    }
    Ok(manifest)
}

/// Id opaco del upload: sha256(zip + reloj + pid) truncado a 32 hex. Único en la práctica y,
/// por construcción, un único componente de ruta seguro (solo `[0-9a-f]`).
fn new_upload_id(bytes: &[u8]) -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let mut h = Sha256::new();
    h.update(bytes);
    h.update(nanos.to_le_bytes());
    h.update(std::process::id().to_le_bytes());
    let d = h.finalize();
    d[..16].iter().map(|b| format!("{b:02x}")).collect()
}

// ─────────────────────────── POST /api/hub/import ───────────────────────────

/// Body del import: el `upload_id` del inspect + la selección de secciones a aplicar.
#[derive(Deserialize)]
pub struct ImportReq {
    upload_id: String,
    #[serde(default)]
    selection: ImportSelectionReq,
}

/// Espejo serde de `erplora_runtime::import::ImportSelection`.
#[derive(Deserialize, Default)]
pub struct ImportSelectionReq {
    #[serde(default)]
    users: bool,
    #[serde(default)]
    settings: bool,
    #[serde(default)]
    fiscal: bool,
    #[serde(default)]
    media: bool,
    #[serde(default)]
    modules: Vec<String>,
}

impl ImportSelectionReq {
    fn into_selection(self) -> ImportSelection {
        ImportSelection {
            users: self.users,
            settings: self.settings,
            fiscal: self.fiscal,
            media: self.media,
            modules: self.modules,
        }
    }
}

/// `true` si el upload_id es un id emitido por [`new_upload_id`] (hex, un componente simple).
fn is_valid_upload_id(s: &str) -> bool {
    s.len() == 32 && s.chars().all(|c| c.is_ascii_hexdigit())
}

/// POST /api/hub/import — aplica el blueprint del `upload_id` según la selección, estilo
/// «migrate»: verificación sha256 dura (422 sin efectos) → módulos que falten (best-effort,
/// `install_from_cloud`) → `import_sections` del runtime → media (best-effort) → fiscal como
/// `pending` (la contraseña del `.p12` no viaja). El temporal se borra SIEMPRE, también en error.
pub async fn import_blueprint(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<ImportReq>>,
) -> Response {
    // hub del PLANO DE DATOS (mismo criterio que el export): en Session = config.hub_id; en Dev
    // = el del contexto de cabecera — el import restaura donde el resto de la app lee/escribe.
    let data_hub_id;
    {
        let arc = match st.runtime_for(&st.hub_id()).await {
            Ok(rt) => rt,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
        data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
            Ok(ctx) => ctx.hub_id,
            Err(e) => return unauthorized(e),
        };
    }
    let Some(Json(req)) = body else {
        return err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "falta el body JSON { upload_id, selection }",
        );
    };
    // El upload_id se usa como componente de ruta: formato estricto o 404 (ni se toca el FS).
    if !is_valid_upload_id(&req.upload_id) {
        return err(
            StatusCode::NOT_FOUND,
            "upload no encontrado o caducado (repite el inspect)",
        );
    }
    let tmp_dir = st
        .config
        .module_cache
        .join(IMPORT_TMP_DIR)
        .join(&req.upload_id);
    let bytes = match tokio::fs::read(tmp_dir.join("blueprint.zip")).await {
        Ok(b) => b,
        Err(_) => {
            return err(
                StatusCode::NOT_FOUND,
                "upload no encontrado o caducado (repite el inspect)",
            )
        }
    };

    // A partir de aquí el temporal se borra SIEMPRE (también en error): el trabajo va en una
    // función aparte y el borrado ocurre antes de devolver la respuesta.
    let result = run_import(
        &st,
        &headers,
        &bytes,
        req.selection.into_selection(),
        &data_hub_id,
    )
    .await;
    let _ = tokio::fs::remove_dir_all(&tmp_dir).await;
    match result {
        Ok(report) => Json(json!({ "ok": true, "report": report })).into_response(),
        Err(resp) => resp,
    }
}

/// El trabajo del import (sin el borrado del temporal, que garantiza el llamador).
/// `Err(Response)` = respuesta de error ya formada.
async fn run_import(
    st: &AppState,
    headers: &HeaderMap,
    zip_bytes: &[u8],
    selection: ImportSelection,
    data_hub_id: &str,
) -> Result<Value, Response> {
    // (1) Re-extraer TODO en memoria (re-valida zip + rutas: el temporal pudo manipularse).
    let (manifest, files) =
        extract_bundle(zip_bytes).map_err(|msg| err(StatusCode::UNPROCESSABLE_ENTITY, &msg))?;

    // (2) Integridad dura (ADR-0015): sha256 de TODOS los ficheros contra el manifest, en las
    //     dos direcciones. Cualquier discrepancia → 422 SIN efectos.
    for (path, expected) in &manifest.sha256 {
        let Some(bytes) = files.get(path) else {
            return Err(err(
                StatusCode::UNPROCESSABLE_ENTITY,
                &format!("integridad: el manifest lista {path} pero no está en el zip"),
            ));
        };
        if sha256_hex(bytes) != expected.to_lowercase() {
            return Err(err(
                StatusCode::UNPROCESSABLE_ENTITY,
                &format!("integridad: sha256 de {path} no coincide con el manifest"),
            ));
        }
    }
    for path in files.keys() {
        if !manifest.sha256.contains_key(path) {
            return Err(err(
                StatusCode::UNPROCESSABLE_ENTITY,
                &format!("integridad: {path} no está listado en el manifest"),
            ));
        }
    }

    // (3) Módulos del manifest que falten → flujo EXISTENTE `install_from_cloud` (versiones del
    //     manifest). Best-effort: un fallo se registra y se sigue (estilo «migrate»).
    let mut installed_modules: Vec<Value> = Vec::new();
    if !manifest.modules.is_empty() {
        let cred = auth::hub_scoped_auth(headers, st);
        let arc = st
            .runtime_for(&st.hub_id())
            .await
            .map_err(crate::tenant_rejected)?;
        let mut rt = arc.lock().await;
        for m in &manifest.modules {
            if rt.registry().is_installed(&m.id) {
                installed_modules.push(
                    json!({ "id": m.id, "version": m.version, "status": "already_installed" }),
                );
                continue;
            }
            let entry = match &cred {
                None => json!({
                    "id": m.id, "version": m.version, "status": "failed",
                    "error": "hub sin credencial para el marketplace (ni token de máquina ni Bearer)",
                }),
                Some(auth_cred) => {
                    // Mismo contrato de progreso que request-install: WS `module.install.progress`
                    // con `root_id` = módulo del manifest (las deps anidadas apuntan a su root).
                    let progress_state = st.clone();
                    let root_id = m.id.clone();
                    let on_progress = move |module_id: &str, phase: &str| {
                        progress_state.broadcast(json!({
                            "type": "module.install.progress",
                            "module_id": module_id,
                            "root_id": root_id,
                            "phase": phase,
                        }));
                    };
                    match install::install_from_cloud(
                        &st.http,
                        &st.config.cloud_base_url,
                        &st.config.module_cache,
                        auth_cred,
                        &mut rt,
                        &m.id,
                        &m.version,
                        &on_progress,
                    )
                    .await
                    {
                        Ok(inst) => {
                            st.broadcast(
                                json!({ "type": "module.installed", "module_id": inst.module_id }),
                            );
                            json!({ "id": inst.module_id, "version": inst.version, "status": "installed" })
                        }
                        Err(e) => {
                            tracing::warn!(module_id = %m.id, error = %e, "import: instalación de módulo del blueprint falló (best-effort, se sigue)");
                            json!({ "id": m.id, "version": m.version, "status": "failed", "error": e.to_string() })
                        }
                    }
                }
            };
            installed_modules.push(entry);
        }
    }

    // (4) Motor del runtime (Fase 2): aplica las secciones de datos con el hub_id DEL DESPLIEGUE.
    //     Un Err del motor = rechazo duro (integridad/versión) → 422 sin efectos.
    let report = {
        let arc = st
            .runtime_for(&st.hub_id())
            .await
            .map_err(crate::tenant_rejected)?;
        let mut rt = arc.lock().await;
        import::import_sections(&mut rt, &manifest, &files, &selection, data_hub_id)
            .await
            .map_err(|e| {
                err(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    &format!("import rechazado: {e}"),
                )
            })?
    };

    // (5) Media: copia `media/*` del bundle al gestor media (ADR-0047). Best-effort por fichero
    //     (un fichero que no se pueda escribir se ignora y se sigue).
    let mut media_copied = 0u32;
    let mut media_failed = 0u32;
    if selection.media {
        for (path, bytes) in &files {
            let Some(rel) = path.strip_prefix("media/") else {
                continue;
            };
            let Some(target) = media::safe_join(&st.config.media_dir, rel) else {
                media_failed += 1;
                continue;
            };
            let ok = target
                .parent()
                .map(std::fs::create_dir_all)
                .map(|r| r.is_ok())
                .unwrap_or(false)
                && std::fs::write(&target, bytes).is_ok();
            if ok {
                media_copied += 1;
            } else {
                media_failed += 1;
            }
        }
    }

    // (6) Fiscal (decisión (d)): el `.p12` NO se aplica automáticamente — la contraseña no viaja.
    //     Se devuelve como `pending` y el usuario lo sube por `PUT /api/business/certificate`.
    let fiscal_status = if !selection.fiscal {
        "skipped"
    } else if files.contains_key("data/fiscal/certificate.p12") {
        "pending"
    } else {
        "absent"
    };

    // (7) Informe del runtime EXTENDIDO con lo que gestionó esta capa.
    let mut report_v = serde_json::to_value(&report).unwrap_or_else(|_| json!({ "sections": [] }));
    report_v["installed_modules"] = Value::Array(installed_modules);
    report_v["media"] =
        json!({ "selected": selection.media, "copied": media_copied, "failed": media_failed });
    report_v["fiscal"] = json!({
        "certificate": fiscal_status,
        "note": "el certificado no se aplica automáticamente (la contraseña no viaja en el bundle): súbelo en Ajustes → Negocio (PUT /api/business/certificate)",
    });
    Ok(report_v)
}

/// Extrae TODO el bundle en memoria: valida rutas (anti zip-slip), parsea `manifest.json`
/// (versión conocida) y devuelve el resto de ficheros como mapa ruta→bytes.
fn extract_bundle(
    bytes: &[u8],
) -> Result<(export::BlueprintManifest, BTreeMap<String, Vec<u8>>), String> {
    let manifest = read_manifest(bytes)?; // valida zip + rutas + manifest
    let mut archive =
        zip::ZipArchive::new(Cursor::new(bytes)).map_err(|e| format!("zip inválido: {e}"))?;
    let mut files = BTreeMap::new();
    for i in 0..archive.len() {
        let mut entry = archive
            .by_index(i)
            .map_err(|e| format!("zip inválido: {e}"))?;
        if entry.is_dir() {
            continue;
        }
        let name = entry.name().to_string();
        if name == "manifest.json" {
            continue; // el manifest va aparte (fuente de verdad, no un "fichero de datos").
        }
        let mut buf = Vec::with_capacity(entry.size() as usize);
        entry
            .read_to_end(&mut buf)
            .map_err(|e| format!("zip ilegible ({name}): {e}"))?;
        files.insert(name, buf);
    }
    Ok((manifest, files))
}
