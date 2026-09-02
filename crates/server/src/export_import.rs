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

use erplora_runtime::export::{self, BundlePurpose, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{self, ImportSelection};
use erplora_runtime::reset;
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
    /// Subselección de claves de `hub_settings`. `None` = todas las **exportables**, no todas a
    /// secas (ADR-0195 §4, hub#405): con `purpose: template` el motor filtra a las claves de
    /// configuración y el NIF/razón social no entran. El llamador ACOTA, nunca amplía.
    #[serde(default)]
    settings_items: Option<Vec<String>>,
    #[serde(default)]
    fiscal: bool,
    #[serde(default)]
    media: bool,
    #[serde(default)]
    modules: Vec<ModuleSelReq>,
    /// Para qué es el bundle (ADR-0195). Ausente ⇒ `backup` (lo que ha sido siempre). Con
    /// `"template"` el motor EXCLUYE del zip identidades, fiscal y la identidad de negocio de
    /// `hub_settings` (§4, hub#405), marque lo que marque el formulario: una plantilla se publica
    /// y no puede llevar cuentas, certificados ni el NIF de nadie.
    #[serde(default)]
    purpose: BundlePurpose,
}

#[derive(Deserialize)]
pub struct ModuleSelReq {
    module_id: String,
    #[serde(default)]
    with_data: bool,
    /// Subselección de TABLAS del módulo (hub#534). Ausente ⇒ todas las suyas, que es lo que
    /// significaba `with_data` antes de existir este campo — así que un shell que no lo mande sigue
    /// exportando igual. El llamador **acota, nunca amplía**: lo que la regla del `purpose` deja
    /// fuera (`export::TEMPLATE_EXCLUDED_TABLES`) sigue fuera aunque se marque aquí.
    #[serde(default)]
    tables: Option<Vec<String>>,
}

impl ExportSelectionReq {
    fn into_selection(self) -> ExportSelection {
        ExportSelection {
            users: self.users,
            settings: self.settings,
            settings_items: self.settings_items,
            fiscal: self.fiscal,
            media: self.media,
            purpose: self.purpose,
            modules: self
                .modules
                .into_iter()
                .map(|m| ModuleDataSelection {
                    module_id: m.module_id,
                    with_data: m.with_data,
                    tables: m.tables,
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
/// `GET /api/hub/export/tables` — qué tablas tiene cada módulo instalado y **cuántas filas**
/// volcaría el export de cada una (hub#534).
///
/// Es lo que hace que las casillas por tabla sean una decisión y no una fila de nombres: «Citas:
/// 28» es lo que hace que quien monta la plantilla las desmarque. Mismo argumento que el resumen
/// del publicador (saas#1257) — sin el número, mirar no sirve de nada.
///
/// Misma puerta que el export (`require_admin_session`): la respuesta dice cuántas filas tiene cada
/// tabla del negocio, así que no puede ser más abierta que el volcado que la usa.
/// El `purpose` que este hub tiene IMPUESTO, o `None` si quien exporta puede elegirlo.
///
/// Un hub que no es un negocio real nunca exporta más que una plantilla (hub#377, ADR-0195): el
/// hub de desarrollo sin enrolar (`is_dev_hub`) y la demo efímera (ADR-0197). La regla es la
/// misma de siempre; lo que cambia es que ahora tiene UN solo sitio y las dos puertas del export
/// la leen de aquí — la que empaqueta el zip y la que el formulario consulta antes de pintarse.
///
/// 🔴 hub#1249: vivía SOLO dentro de `export_blueprint`, así que el formulario seguía ofreciendo
/// «copia de seguridad» con la casilla de usuarios marcada y el zip volvía sin ellos, sin un solo
/// aviso. Es exactamente la casilla que `ExportPanel.vue` tiene prohibido pintar («una casilla que
/// el motor va a ignorar es una mentira»), solo que la mentira la escribía el servidor.
pub(crate) fn locked_purpose(st: &AppState) -> Option<BundlePurpose> {
    (st.is_dev_hub() || st.config.demo).then_some(BundlePurpose::Template)
}

pub async fn export_tables(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    // Mismo `hub_id` del plano de DATOS que el export, por la misma razón: contar sobre otro hub
    // daría números que no casan con lo que sale del zip.
    let data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx.hub_id,
        Err(e) => return unauthorized(e),
    };
    let ids: Vec<String> = rt
        .registry()
        .installed
        .iter()
        .map(|m| m.id.clone())
        .collect();
    // `locked_purpose`: el formulario no puede ofrecer lo que el motor va a ignorar (hub#1249).
    let locked = locked_purpose(&st);
    match export::module_table_counts(&rt, &data_hub_id, &ids).await {
        Ok(modules) => Json(json!({ "ok": true, "modules": modules, "locked_purpose": locked }))
            .into_response(),
        Err(e) => err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()),
    }
}

pub async fn export_blueprint(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<ExportReq>>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
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
    let mut selection = req.selection.into_selection();

    // Un hub que no es un negocio real nunca puede exportar más que una plantilla (hub#377,
    // ADR-0195). Son dos los estados que cumplen eso, y los dos se tratan igual aquí:
    //   · `is_dev_hub()` — el hub de desarrollo sin enrolar (`AuthMode::Dev` + `DEV_HUB_ID`), cuyo
    //     `hub_user` lleva el `pin_hash` de pruebas;
    //   · `config.demo` — la demo efímera (ADR-0197).
    // Forzar `purpose: template` antes de que el motor vea la selección hace que el runtime excluya
    // identidades (`hub_user`), fiscal (`verifactu_config`, certificado) y la identidad de negocio
    // de `hub_settings`, marque lo que marque el formulario. El runtime ya honra `purpose` por
    // encima de las casillas (export.rs), así que esto basta: no hace falta tocar `users`/`fiscal`
    // uno a uno. (La issue hablaba de `is_demo`; ese nombre se retiró en ADR-0212 porque era ambiguo
    // — `is_dev_hub` es lo que significaba.)
    if let Some(forced) = locked_purpose(&st) {
        selection.purpose = forced;
    }

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
    drop(rt); // la media no necesita el runtime: suelta el lock antes de hablar con el Cloud.

    // Media (ADR-0047): los bytes los añade el server (el runtime solo marca la sección). Se leen
    // del GESTOR MEDIA —Object Storage vía el Cloud—, que es donde viven los ficheros del hub; las
    // carpetas de sistema `_*` de primer nivel (`_logs`, `_system`, `_import_tmp`) NO son datos
    // del negocio y las excluye el propio recorrido.
    //
    // 🔴 Esto recorría `config.media_dir` con `std::fs`. En Hub Cloud (ADR-0154) ese directorio es
    // scratch local y no contiene NADA del hub, así que el recorrido salía vacío, la sección
    // `media` ni se declaraba y todo blueprint se publicaba sin una sola imagen.
    if selection.media {
        let media_files = media::collect_for_bundle(&st).await;
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

/// Bytes DEScifrados del PKCS#12 que el bundle PUEDE llevar, o `None` si el hub no tiene ninguno
/// exportable (o falla el descifrado/no hay master key). La contraseña NO se lee: no viaja
/// (decisión d). Desde ERPlora/hub#114 la columna va cifrada at-rest, así que pasa por el core en
/// vez de leer/decodificar el base64 crudo de la fila.
///
/// **Qué slot sale lo decide el core, no esta capa** (ADR-0202 §2.1, hub#316): un hub tiene hasta
/// dos certificados y el DELEGADO —la clave privada con la que ERPlora se identifica ante la AEAT
/// por apoderamiento— nunca entra en un bundle. `exportable_der_bytes` es la única puerta por la
/// que salen bytes de `.p12` en crudo, y la regla vive dentro de ella: aquí no hay filtro que
/// alguien pueda olvidarse de repetir la próxima vez que se toque el export.
async fn read_certificate_p12(rt: &Runtime, hub_id: &str) -> Option<Vec<u8>> {
    erplora_runtime::certificate::exportable_der_bytes(rt.db(), hub_id)
        .await
        .ok()
        .flatten()
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
        let rt = arc.read().await;
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
pub(crate) fn read_manifest(bytes: &[u8]) -> Result<export::BlueprintManifest, String> {
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
    /// Where the bundle came from, when the client downloaded it from the catalogue (hub#845):
    /// the card's `slug` + the `version` it announced. Persisted with the report so a partial
    /// import can be retried against the SAME bundle. Absent for a hand-uploaded file — which is
    /// exactly what makes that import non-retryable, and the report says so.
    #[serde(default)]
    origin: Option<ImportOriginReq>,
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
        let rt = arc.read().await;
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
        auth::hub_scoped_auth(&headers, &st),
        &bytes,
        req.selection.into_selection(),
        &data_hub_id,
        req.origin.as_ref(),
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
///
/// Toma la **credencial ya resuelta**, no las cabeceras: el import de arranque (ADR-0212, hub#406)
/// entra por aquí **sin petición HTTP** —lo dispara `serve()` con el token de máquina— y sacar
/// `hub_scoped_auth` fuera es lo que permite reusar este camino en vez de duplicarlo. `None` = hub
/// sin credencial: los módulos del manifest no se pueden bajar y el informe lo dice.
pub(crate) async fn run_import(
    st: &AppState,
    cred: Option<cloud_client::Auth>,
    zip_bytes: &[u8],
    selection: ImportSelection,
    data_hub_id: &str,
    origin: Option<&ImportOriginReq>,
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
        let arc = st
            .runtime_for(&st.hub_id())
            .await
            .map_err(crate::tenant_rejected)?;
        let mut rt = arc.write().await;
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
                    // ADR-0060 (hub#68): `install_bundle_module` pide el PLAN al Cloud y lo
                    // ejecuta, así que un módulo del blueprint arrastra sus dependencias
                    // transitivas (p. ej. `invoice` → `taxes`, `sales`) aunque el manifest no las
                    // liste. Y **no** exige la versión exacta del manifest (hub#751/#752): es la
                    // foto del hub que exportó, y el marketplace poda las versiones viejas — el
                    // pin caduca solo y con él la plantilla entera.
                    let outcome = install::install_bundle_module(
                        &st.http,
                        &st.config.cloud_base_url,
                        &st.config.module_cache,
                        auth_cred,
                        &mut rt,
                        &m.id,
                        &m.version,
                        &on_progress,
                        &st.config.signature_policy(),
                    )
                    .await;
                    match &outcome {
                        Ok(inst) => st.broadcast(
                            json!({ "type": "module.installed", "module_id": inst.module_id }),
                        ),
                        Err(e) => {
                            tracing::warn!(module_id = %m.id, code = %e.code(), error = %e, "import: instalación de módulo del blueprint falló (best-effort, se sigue)")
                        }
                    }
                    module_install_entry(&m.id, &m.version, outcome)
                }
            };
            installed_modules.push(entry);
        }
    }

    // (4) Motor del runtime (Fase 2): aplica las secciones de datos con el hub_id DEL DESPLIEGUE.
    //     Un Err del motor = rechazo duro (integridad/versión) → 422 sin efectos.
    let (report, batch_id) = {
        let arc = st
            .runtime_for(&st.hub_id())
            .await
            .map_err(crate::tenant_rejected)?;
        let mut rt = arc.write().await;
        let r = import::import_sections(&mut rt, &manifest, &files, &selection, data_hub_id)
            .await
            .map_err(|e| {
                err(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    &format!("import rechazado: {e}"),
                )
            })?;
        // The runtime persisted its OWN report under `batch_id` (hub#763). The server UPSERTs the
        // EXTENDED one (below) over the same id, so a reload reads the full picture. Captured here
        // so the extend step can reuse the same `batch_id` the engine opened.
        let batch_id = r.batch_id.clone();
        (r, batch_id)
    };

    // (5) Media: sube `media/*` del bundle al GESTOR MEDIA (ADR-0047) — Object Storage vía el
    //     Cloud, que es de donde el hub las sirve. Best-effort por fichero: se agrupan por carpeta
    //     en multipart acotados, y los contadores `saved`/`failed` del Cloud conservan el resultado
    //     exacto cuando un lote se acepta solo en parte.
    //
    // 🔴 Esto escribía con `std::fs` en `config.media_dir`. Era el espejo del fallo del export:
    // aun con un bundle que trajese imágenes, quedaban en un scratch local que nadie consulta, así
    // que el catálogo importado seguía sin fotos. La guarda anti-traversal no se pierde: vive
    // ahora dentro de `upload_bundle_media`.
    let media_report = if selection.media {
        let entries: Vec<(&str, &[u8])> = files
            .iter()
            .filter_map(|(path, bytes)| {
                path.strip_prefix("media/")
                    .map(|rel| (rel, bytes.as_slice()))
            })
            .collect();
        media::upload_bundle_media(st, &entries).await
    } else {
        media::BundleMediaUploadReport::default()
    };

    // (6) Fiscal (decisión (d)): el `.p12` NO se aplica automáticamente — la contraseña no viaja.
    //     Se devuelve como `pending` y el usuario lo sube por `PUT /api/business/certificate`.
    //
    //     …salvo en una PLANTILLA (ADR-0195, hub#305). Esta sección es la única que el motor no
    //     puede cerrar —la materializa esta capa, no él—, así que el guard se repite aquí. Con un
    //     bundle `template`, `pending` no es un estado neutro: es una invitación a instalarse la
    //     identidad fiscal de OTRO negocio (NIF, entorno VeriFactu, certificado de firma). Se
    //     descarta y se dice, igual que hace el motor con las identidades.
    let fiscal_status = if !manifest.purpose.allows_identity_sections() {
        "ignored"
    } else if !selection.fiscal {
        "skipped"
    } else if files.contains_key("data/fiscal/certificate.p12") {
        "pending"
    } else {
        "absent"
    };

    // (7) Informe del runtime EXTENDIDO con lo que gestionó esta capa.
    let mut report_v = serde_json::to_value(&report).unwrap_or_else(|_| json!({ "sections": [] }));
    report_v["installed_modules"] = Value::Array(installed_modules);
    report_v["media"] = json!({
        "selected": selection.media,
        "copied": media_report.copied,
        "failed": media_report.failed,
    });
    // La nota acompaña al estado: con `ignored`, «súbelo en Ajustes → Negocio» diría justo lo
    // contrario de lo que acaba de decidirse, y el usuario acabaría instalándose a mano el
    // certificado ajeno que el import se negó a ofrecerle.
    report_v["fiscal"] = json!({
        "certificate": fiscal_status,
        "note": if fiscal_status == "ignored" {
            "una plantilla no aplica datos fiscales: el NIF, la configuración VeriFactu y el certificado son de cada negocio. Configura los tuyos en Ajustes → Negocio."
        } else {
            "el certificado no se aplica automáticamente (la contraseña no viaja en el bundle): súbelo en Ajustes → Negocio (PUT /api/business/certificate)"
        },
    });
    // The EXACT origin travels with the report (hub#845): catalogue slug + version when the bundle
    // came from the cloud, or an explicit «local» — which is what tells the retry endpoint (and the
    // shell's retry button) whether re-downloading the SAME bundle is even possible. Inside the
    // report JSON on purpose: the `_hub_import_report.report` column is opaque, so no migration.
    report_v["origin"] = origin_json(origin, &manifest.locale);

    // (8) Persist the EXTENDED report under its batch (hub#763). The runtime stored its sections
    //     already; this UPSERTs the full document (sections + installed_modules + media + fiscal)
    //     so navigating to Settings › Data (or reloading, or a new session) recovers EXACTLY what
    //     the hero card was pointing at. A failure here MUST NOT fail the import (best-effort, like
    //     every step that is not integrity): the data is in; what would be lost is this view of it.
    if let Some(ref batch) = batch_id {
        if let Ok(report_json) = serde_json::to_string(&report_v) {
            let arc = st
                .runtime_for(&st.hub_id())
                .await
                .map_err(crate::tenant_rejected)?;
            let rt = arc.read().await;
            let _ =
                reset::store_import_report(&rt, data_hub_id, batch, &manifest.name, &report_json)
                    .await;
        }
    }
    Ok(report_v)
}

// ─────────────────── POST /api/hub/import/retry (hub#845) ────────────────────

/// Exact origin of an import as the CLIENT knows it: the catalogue card it clicked (`slug`) and
/// the version that card announced. Both are required — without the version a retry cannot
/// guarantee it re-runs the SAME bundle, and retrying with another one is another bug waiting.
#[derive(Deserialize, Clone)]
pub struct ImportOriginReq {
    #[serde(default)]
    slug: String,
    #[serde(default)]
    version: String,
}

/// What [`origin_json`] wrote, read back from a persisted report. `locale` narrows the catalogue
/// download when the same slug is published in more than one language.
struct StoredOrigin {
    slug: String,
    version: String,
    locale: Option<String>,
}

/// The `origin` entry persisted INSIDE the extended report (no schema change: the
/// `_hub_import_report.report` column is opaque JSON). `source: "catalog"` carries
/// slug + version + locale; anything else — a hand-uploaded file, or a half-empty origin that
/// cannot guarantee a version — is `source: "local"`: an import the hub cannot re-download, and
/// the report SAYS so instead of hiding it (hub#845).
fn origin_json(origin: Option<&ImportOriginReq>, manifest_locale: &str) -> Value {
    match origin {
        Some(o) if !o.slug.trim().is_empty() && !o.version.trim().is_empty() => json!({
            "source": "catalog",
            "slug": o.slug.trim(),
            "version": o.version.trim(),
            "locale": manifest_locale,
        }),
        _ => json!({ "source": "local" }),
    }
}

/// Reads the origin back. `None` = not retryable: local upload, a report older than the field, or
/// an origin that cannot pin a version.
fn stored_origin(report: &Value) -> Option<StoredOrigin> {
    let origin = report.get("origin")?;
    if origin["source"].as_str()? != "catalog" {
        return None;
    }
    let slug = origin["slug"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_string();
    let version = origin["version"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_string();
    if slug.is_empty() || version.is_empty() {
        return None;
    }
    let locale = origin["locale"]
        .as_str()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .map(str::to_string);
    Some(StoredOrigin {
        slug,
        version,
        locale,
    })
}

/// `true` if a section's status is `Failed` (serde wire shape: `{"Failed": "reason"}`).
fn section_failed(status: &Value) -> bool {
    status.get("Failed").is_some()
}

/// Derives «retry ONLY what did not make it in» from a persisted report (hub#845).
///
/// - `Failed` sections come back, mapped to their selection flag / module id.
/// - `Applied` is never re-applied blindly; `Skipped` was never asked for; `Ignored` and
///   `PartiallyApplied` are the engine's own discards — retrying them repeats the same decision.
/// - `installed_modules[]` entries in `failed` or `blocked` join the module list: `blocked` is a
///   purchase decision (ADR-0060) and after subscribing the SAME button re-runs it.
/// - Media uses the server's extended entry (`media.failed`): files that could not be copied are
///   retried too.
fn retry_selection_from_report(report: &Value) -> ImportSelection {
    let mut sel = ImportSelection::default();
    let empty = Vec::new();
    for s in report["sections"].as_array().unwrap_or(&empty) {
        if !section_failed(&s["status"]) {
            continue;
        }
        match s["section"].as_str().unwrap_or_default() {
            "hub_users" | "users" => sel.users = true,
            "hub_settings" | "settings" => sel.settings = true,
            "fiscal" => sel.fiscal = true,
            "media" => sel.media = true,
            other => {
                if let Some(id) = other.strip_prefix("modules/") {
                    if !id.is_empty() && !sel.modules.iter().any(|m| m == id) {
                        sel.modules.push(id.to_string());
                    }
                }
            }
        }
    }
    for m in report["installed_modules"].as_array().unwrap_or(&empty) {
        let status = m["status"].as_str().unwrap_or_default();
        if status != "failed" && status != "blocked" {
            continue;
        }
        if let Some(id) = m["id"].as_str() {
            if !id.is_empty() && !sel.modules.iter().any(|x| x == id) {
                sel.modules.push(id.to_string());
            }
        }
    }
    if report["media"]["selected"].as_bool().unwrap_or(false)
        && report["media"]["failed"].as_u64().unwrap_or(0) > 0
    {
        sel.media = true;
    }
    sel
}

/// `true` when the derived selection asks for nothing — a fully applied import: the retry is an
/// explicit «nothing to retry», never a blind full re-run.
fn selection_is_empty(sel: &ImportSelection) -> bool {
    !sel.users && !sel.settings && !sel.fiscal && !sel.media && sel.modules.is_empty()
}

/// Error with a STABLE code next to the honest message (same lesson as the domain-error channel,
/// ADR-0205): the shell translates the code; the message is the fallback.
fn coded_err(status: StatusCode, code: &str, msg: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "code": code, "error": { "message": msg } })),
    )
        .into_response()
}

/// Body of `POST /api/hub/import/retry`.
#[derive(Deserialize)]
pub struct RetryReq {
    batch_id: String,
}

/// POST /api/hub/import/retry — re-runs a partially applied import, retrying ONLY what its
/// persisted report says failed (or stayed blocked), against the SAME catalogue bundle (hub#845).
///
/// Not duplicating what is already present is the ENGINE's property, not this endpoint's promise:
/// the technical-key guard (hub#260) skips the bundle's own rows and the natural-key guards
/// (ADR-0304) skip rows the hub created by itself — `import_retry_test.rs` pins both. This layer
/// derives the narrowed selection from the report and refuses to run when it cannot guarantee the
/// same bundle: a local upload has no origin to re-download, and a catalogue that no longer serves
/// the imported version would silently retry with a DIFFERENT bundle.
pub async fn retry_import(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<RetryReq>>,
) -> Response {
    let data_hub_id;
    {
        let arc = match st.runtime_for(&st.hub_id()).await {
            Ok(rt) => rt,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.read().await;
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
            "missing JSON body { batch_id }",
        );
    };
    let batch_id = req.batch_id.trim().to_string();
    if batch_id.is_empty() {
        return err(StatusCode::UNPROCESSABLE_ENTITY, "empty batch_id");
    }

    // The persisted report of THAT import, scoped to this hub (a guessed batch_id is a 404).
    let stored = {
        let arc = match st.runtime_for(&st.hub_id()).await {
            Ok(rt) => rt,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.read().await;
        match reset::last_import_report(&rt, &data_hub_id, &batch_id).await {
            Ok(Some(s)) => s,
            Ok(None) => {
                return coded_err(
                    StatusCode::NOT_FOUND,
                    "import_retry_batch_not_found",
                    "no import report for that batch (it may have been undone)",
                )
            }
            Err(e) => {
                return err(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    &format!("could not read the import report: {e}"),
                )
            }
        }
    };
    let report: Value = serde_json::from_str(&stored.report).unwrap_or_else(|_| json!({}));

    // A retry needs an origin it can re-download. A local upload is refused WITH its reason — the
    // shell disables the button for the same case, but the server is the authority.
    let Some(origin) = stored_origin(&report) else {
        return coded_err(
            StatusCode::CONFLICT,
            "import_origin_not_retryable",
            "this import did not come from the catalogue (uploaded file): upload the file again and select only what failed",
        );
    };

    let selection = retry_selection_from_report(&report);
    if selection_is_empty(&selection) {
        // Explicit no-op: everything already applied. 200 on purpose (like a double undo) — the
        // user pressing again after a slow network must not see an error.
        return (
            StatusCode::OK,
            Json(json!({ "ok": true, "retried": false, "code": "import_nothing_to_retry" })),
        )
            .into_response();
    }

    // Same-version guarantee: the catalogue download has no version pin, so this fetches what the
    // SaaS serves TODAY and refuses if it is not the version the report imported.
    let Some(cred) = auth::hub_scoped_auth(&headers, &st) else {
        return err(
            StatusCode::BAD_GATEWAY,
            "hub has no cloud credential (neither machine token nor Bearer)",
        );
    };
    let fetched =
        match crate::fetch_blueprint(&st, &cred, &origin.slug, origin.locale.as_deref()).await {
            Ok(f) => f,
            Err(crate::BlueprintFetchError::Cloud { status, body }) => {
                return (status, [(header::CONTENT_TYPE, "application/json")], body).into_response()
            }
            Err(e) => return err(StatusCode::BAD_GATEWAY, &e.message()),
        };
    if fetched.version != origin.version {
        return coded_err(
            StatusCode::CONFLICT,
            "import_retry_version_unavailable",
            &format!(
                "the import used version {} of \u{ab}{}\u{bb}, but the catalogue now serves {} — retrying with a different bundle is refused",
                origin.version, origin.slug, fetched.version
            ),
        );
    }

    let origin_req = ImportOriginReq {
        slug: origin.slug,
        version: origin.version,
    };
    match run_import(
        &st,
        Some(cred),
        &fetched.zip,
        selection,
        &data_hub_id,
        Some(&origin_req),
    )
    .await
    {
        Ok(report) => {
            Json(json!({ "ok": true, "retried": true, "report": report })).into_response()
        }
        Err(resp) => resp,
    }
}

/// Entrada de `report.installed_modules[]` para UN módulo del blueprint.
///
/// El import es best-effort («migrate»): si un módulo no se puede instalar, el resto sigue. Pero
/// **no puede ser mudo** — la pantalla de import PROMETE dejar el hub funcionando, así que cada
/// entrada dice qué pasó con un `code` estable (hub#139) contra el que la UI programa y traduce.
///
/// `blocked` (ADR-0060) es un estado propio, NO un `failed`: el módulo no se instaló porque el
/// plan exige comprar una dependencia — es una decisión del usuario, no una avería. Se nombran
/// `blocked_on` + `purchase` para que la UI ofrezca la compra en vez de un error opaco.
///
/// `requested_version` solo aparece cuando la versión instalada **no** es la que fijaba el manifest
/// (hub#751/#752): el marketplace ya no publicaba el pin y se cayó a la más nueva compatible. Una
/// plantilla que instala en silencio algo distinto de lo que anuncia sería justo la sorpresa que la
/// sustitución trata de evitar, así que el informe lo nombra en vez de esconderlo.
fn module_install_entry(
    module_id: &str,
    manifest_version: &str,
    result: Result<install::Installed, install::InstallError>,
) -> Value {
    match result {
        Ok(inst) => {
            let mut entry = json!({
                "id": inst.module_id,
                "version": inst.version,
                "status": "installed",
            });
            if inst.version != manifest_version {
                entry["requested_version"] = json!(manifest_version);
            }
            entry
        }
        Err(install::InstallError::Blocked {
            blocked_on,
            purchase,
            ..
        }) => json!({
            "id": module_id,
            "version": manifest_version,
            "status": "blocked",
            "code": "install_blocked",
            "blocked_on": blocked_on,
            "purchase": purchase
                .iter()
                .map(|p| json!({
                    "module_id": p.module_id,
                    "module_type": p.module_type,
                    "price": p.price,
                    "currency": p.currency,
                    "purchase_url": p.purchase_url,
                }))
                .collect::<Vec<_>>(),
        }),
        Err(e) => json!({
            "id": module_id,
            "version": manifest_version,
            "status": "failed",
            "code": e.code(),
            "error": e.to_string(),
        }),
    }
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    /// Toda ruta del bundle con `..`, absoluta o con `\` queda fuera del zip ANTES de extraer.
    #[test]
    fn las_rutas_del_zip_con_traversal_se_rechazan() {
        assert!(is_safe_entry("media/logo.png"));
        assert!(is_safe_entry("data/hub_settings.sql"));
        for evil in [
            "media/../../evil",
            "../evil",
            "/etc/evil",
            "media/../../../etc/passwd",
            "media\\..\\evil",
        ] {
            assert!(!is_safe_entry(evil), "{evil} debería rechazarse");
        }
    }

    // ── ADR-0060 (hub#68): el informe del import no puede ser mudo ─────────────

    /// Un módulo del blueprint que se instala sale en el informe como `installed`.
    #[test]
    fn el_informe_marca_installed_el_modulo_que_se_instalo() {
        let entry = module_install_entry(
            "inventory",
            "1.0.0",
            Ok(install::Installed {
                module_id: "inventory".into(),
                version: "1.2.0".into(),
                dir: PathBuf::from("/tmp/x"),
                also_installed: Vec::new(),
            }),
        );
        assert_eq!(entry["status"], "installed");
        assert_eq!(entry["id"], "inventory");
        assert_eq!(
            entry["version"], "1.2.0",
            "gana la versión realmente instalada"
        );
    }

    /// Un fallo genérico viaja con su CÓDIGO estable (hub#139), no solo con el texto: la UI
    /// programa contra el código y el usuario ve por qué el blueprint no pudo cumplirse.
    #[test]
    fn el_informe_lleva_el_codigo_estable_del_fallo() {
        let entry = module_install_entry(
            "inventory",
            "1.0.0",
            Err(install::InstallError::Cloud("boom".into())),
        );
        assert_eq!(entry["status"], "failed");
        assert_eq!(entry["code"], "install_cloud_unavailable");
        assert!(entry["error"].as_str().unwrap().contains("boom"));
    }

    /// El caso de ADR-0060: el plan exige comprar una dependencia. El informe lo distingue de un
    /// fallo (`blocked`, no `failed`) y NOMBRA qué falta comprar — la promesa del blueprint no se
    /// rompe en silencio, se explica.
    #[test]
    fn el_informe_distingue_bloqueado_por_compra_y_nombra_la_dependencia() {
        let entry = module_install_entry(
            "verifactu",
            "1.0.0",
            Err(install::InstallError::Blocked {
                requested: "verifactu".into(),
                blocked_on: vec!["invoice".into()],
                purchase: vec![install::BlockedPurchase {
                    module_id: "invoice".into(),
                    module_type: "premium".into(),
                    price: "9.00".into(),
                    currency: "EUR".into(),
                    purchase_url: "/marketplace/invoice/".into(),
                }],
            }),
        );
        assert_eq!(entry["status"], "blocked");
        assert_eq!(entry["code"], "install_blocked");
        assert_eq!(entry["blocked_on"][0], "invoice");
        assert_eq!(entry["purchase"][0]["module_id"], "invoice");
        assert_eq!(entry["purchase"][0]["price"], "9.00");
    }

    // ── hub#845 — retry ONLY what did not make it in ───────────────────────────

    /// The retry selection is DERIVED from the persisted report: only `Failed` sections come back.
    /// `Applied` must not be re-applied blindly, and `Ignored`/`PartiallyApplied` are the engine's
    /// own decisions — retrying them would just repeat the same discard.
    #[test]
    fn retry_selection_takes_only_failed_sections() {
        let report = json!({
            "sections": [
                { "section": "hub_users", "status": { "Failed": "db down" } },
                { "section": "hub_settings", "status": "Applied" },
                { "section": "fiscal", "status": "Skipped" },
                { "section": "media", "status": { "Ignored": "identity_not_portable" } },
                { "section": "modules/inventory", "status": { "Failed": "module not installed" } },
                { "section": "modules/taxes", "status": "Applied" },
                { "section": "modules/sales", "status": { "PartiallyApplied": "numbering_not_portable" } },
            ]
        });
        let sel = retry_selection_from_report(&report);
        assert!(sel.users, "a failed section is retried");
        assert!(
            !sel.settings,
            "an applied section is NOT re-applied blindly"
        );
        assert!(!sel.fiscal, "a skipped section stays out");
        assert!(
            !sel.media,
            "an ignored section was a decision, not a breakage"
        );
        assert_eq!(
            sel.modules,
            vec!["inventory".to_string()],
            "only the failed module's data comes back"
        );
    }

    /// A module the import could not install (`failed`) or left as a purchase decision (`blocked`,
    /// ADR-0060) is part of the retry: after fixing the cause (or subscribing) the same button
    /// re-runs it. Modules that installed are not listed twice.
    #[test]
    fn retry_selection_includes_failed_and_blocked_modules_deduplicated() {
        let report = json!({
            "sections": [
                { "section": "modules/inventory", "status": { "Failed": "module not installed" } },
            ],
            "installed_modules": [
                { "id": "inventory", "version": "1.0.0", "status": "failed", "code": "install_cloud_unavailable" },
                { "id": "verifactu", "version": "1.4.1", "status": "blocked", "code": "install_blocked" },
                { "id": "taxes", "version": "2.0.0", "status": "installed" },
                { "id": "sales", "version": "2.13.0", "status": "already_installed" },
            ]
        });
        let sel = retry_selection_from_report(&report);
        assert_eq!(
            sel.modules,
            vec!["inventory".to_string(), "verifactu".to_string()],
            "failed + blocked, without duplicating the id the section already brought back"
        );
    }

    /// The media outcome lives in the server's extended entry (`media.failed`), not only in the
    /// engine's section row: files that could not be copied are retried too.
    #[test]
    fn retry_selection_reads_the_extended_media_entry() {
        let report = json!({
            "sections": [ { "section": "media", "status": "Skipped" } ],
            "media": { "selected": true, "copied": 3, "failed": 2 }
        });
        let sel = retry_selection_from_report(&report);
        assert!(sel.media, "media with failed copies is retried");

        let clean = json!({
            "sections": [],
            "media": { "selected": true, "copied": 5, "failed": 0 }
        });
        assert!(!retry_selection_from_report(&clean).media);
    }

    /// A fully applied import derives an EMPTY selection: the retry endpoint answers «nothing to
    /// retry» instead of re-running the whole bundle (the no-op is explicit, not accidental).
    #[test]
    fn a_fully_applied_report_derives_an_empty_selection() {
        let report = json!({
            "sections": [
                { "section": "hub_settings", "status": "Applied" },
                { "section": "modules/inventory", "status": "Applied" },
            ],
            "installed_modules": [
                { "id": "inventory", "version": "1.0.0", "status": "installed" },
            ],
            "media": { "selected": true, "copied": 4, "failed": 0 }
        });
        let sel = retry_selection_from_report(&report);
        assert!(
            selection_is_empty(&sel),
            "nothing failed ⇒ nothing to retry"
        );
    }

    /// The report persists the EXACT origin of the import (hub#845): catalogue slug + version (the
    /// only thing that lets a retry guarantee the same bundle) — or it says it has none.
    #[test]
    fn the_report_origin_says_catalog_or_local_explicitly() {
        let catalog = origin_json(
            Some(&ImportOriginReq {
                slug: "peluqueria".into(),
                version: "1.0.4".into(),
            }),
            "es",
        );
        assert_eq!(catalog["source"], "catalog");
        assert_eq!(catalog["slug"], "peluqueria");
        assert_eq!(catalog["version"], "1.0.4");
        assert_eq!(catalog["locale"], "es");

        let local = origin_json(None, "es");
        assert_eq!(
            local["source"], "local",
            "a hand-uploaded file SAYS it has no origin"
        );

        // A half-empty origin cannot guarantee the same version ⇒ it is NOT a catalogue origin.
        let empty_version = origin_json(
            Some(&ImportOriginReq {
                slug: "peluqueria".into(),
                version: "".into(),
            }),
            "es",
        );
        assert_eq!(empty_version["source"], "local");
    }

    /// Reading the origin back: only a complete catalogue origin is retryable.
    #[test]
    fn stored_origin_is_only_returned_for_a_complete_catalog_origin() {
        let report = json!({
            "origin": { "source": "catalog", "slug": "peluqueria", "version": "1.0.4", "locale": "es" }
        });
        let origin = stored_origin(&report).expect("catalog origin is retryable");
        assert_eq!(origin.slug, "peluqueria");
        assert_eq!(origin.version, "1.0.4");
        assert_eq!(origin.locale.as_deref(), Some("es"));

        assert!(stored_origin(&json!({ "origin": { "source": "local" } })).is_none());
        assert!(
            stored_origin(&json!({ "sections": [] })).is_none(),
            "a report older than the field has no origin — and says so by not being retryable"
        );
        assert!(
            stored_origin(&json!({ "origin": { "source": "catalog", "slug": "x" } })).is_none(),
            "an origin without a version cannot guarantee the same bundle"
        );
    }
}
