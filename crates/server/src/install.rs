//! Flujo real de instalación de un módulo desde el Cloud Portal (ARQUITECTURA.md §2.2, §4).
//!
//! Reemplaza el endpoint ficticio `…/install/` del antiguo `erplora-cloud-client` por el
//! flujo verificado contra el Cloud:
//!
//!   1. `GET versions/`          → lista de versiones; elige la pedida (o la última activa).
//!   2. `GET download/?version=` → descarga el ZIP binario (async reqwest).
//!   3. verify SHA256 + unzip    → reusa `erplora-source::ModuleStore` (anti zip-slip + cache).
//!   4. `Runtime::install_from_dir` → migra, registra capacidades, deja el módulo activo.
//!   5. `POST mark_installed/`   → registra la instalación en el Cloud (best-effort).
//!
//! Auth = JWT del usuario activo (`Authorization: Bearer`) + `X-Hub-Id` (cabeceras de la
//! petición entrante). La verificación SHA256 es **obligatoria y no-saltable** (ADR-0015):
//! si el Cloud no expone `sha256` en `versions/`, la instalación se **aborta** con
//! [`InstallError::MissingSha256`] antes de descargar nada (el fix server-side para que el
//! serializer lo exponga siempre va en el issue pareja de Cloud).

use std::cell::RefCell;
use std::path::PathBuf;

use cloud_client::{Auth, CloudClient, InstallGrant, ModuleVersion};
use source::{Fetcher, ModuleStore, SourceError};

/// Error del flujo de instalación server-side.
#[derive(Debug, thiserror::Error)]
pub enum InstallError {
    #[error("cloud: {0}")]
    Cloud(String),
    #[error("versión no encontrada: {0}")]
    VersionNotFound(String),
    #[error("descarga/integridad: {0}")]
    Source(#[from] SourceError),
    /// El Cloud no expuso `sha256` para la versión a instalar. ADR-0015: la verificación de
    /// integridad es obligatoria y no-saltable → se aborta **antes** de descargar el zip.
    #[error("integridad: el Cloud no expuso sha256 para {module_id}@{version} — instalación abortada (ADR-0015)")]
    MissingSha256 { module_id: String, version: String },
    #[error("runtime: {0}")]
    Runtime(String),
}

/// `Fetcher` de un solo uso: sirve unos bytes ya descargados (async, fuera de banda) a la
/// lógica síncrona de `ModuleStore` (verify SHA256 + unzip seguro). Evita duplicar la
/// verificación/descompresión que ya vive —y está testeada— en `erplora-source`.
struct InMemoryFetcher {
    bytes: RefCell<Option<Vec<u8>>>,
}

impl Fetcher for InMemoryFetcher {
    fn fetch(&self, _url: &str) -> source::Result<Vec<u8>> {
        self.bytes
            .borrow_mut()
            .take()
            .ok_or_else(|| SourceError::Fetch("bytes ya consumidos".into()))
    }
}

/// Resultado de una instalación correcta (forma del JSON de `/api/modules/request-install`).
#[derive(Debug, Clone)]
pub struct Installed {
    pub module_id: String,
    pub version: String,
    /// Carpeta extraída en el cache local (para la ingestión de embeddings, §9).
    pub dir: PathBuf,
}

/// Resuelve la versión a instalar contra `versions/`: la pedida si se indica, o la última
/// activa. Devuelve la entrada completa (incluye `sha256` si el Cloud lo expone).
async fn resolve_version(
    http: &reqwest::Client,
    cloud: &CloudClient,
    auth: &Auth,
    module_id: &str,
    requested: &str,
) -> Result<ModuleVersion, InstallError> {
    let req = cloud.versions(auth, module_id);
    let body = send_text(http, &req).await?;
    let mut versions = ModuleVersion::parse_list(&body)
        .map_err(|e| InstallError::Cloud(format!("versions/ inválido: {e}")))?;
    versions.retain(|v| v.is_active);

    if !requested.is_empty() && requested != "latest" {
        versions
            .into_iter()
            .find(|v| v.version == requested)
            .ok_or_else(|| InstallError::VersionNotFound(requested.to_string()))
    } else {
        // "última activa": el endpoint las devuelve por `-created_at` (más reciente primero).
        versions.into_iter().next().ok_or_else(|| InstallError::VersionNotFound("latest".into()))
    }
}

/// Ejecuta una `PreparedRequest` GET y devuelve el cuerpo como texto.
async fn send_text(http: &reqwest::Client, req: &cloud_client::PreparedRequest) -> Result<String, InstallError> {
    let mut r = http.request(method(req), &req.url);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }
    let resp = r.send().await.map_err(|e| InstallError::Cloud(e.to_string()))?;
    let resp = resp.error_for_status().map_err(|e| InstallError::Cloud(e.to_string()))?;
    resp.text().await.map_err(|e| InstallError::Cloud(e.to_string()))
}

/// Ejecuta una `PreparedRequest` GET y devuelve el cuerpo binario (descarga del ZIP).
async fn send_bytes(http: &reqwest::Client, req: &cloud_client::PreparedRequest) -> Result<Vec<u8>, InstallError> {
    let mut r = http.request(method(req), &req.url);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }
    let resp = r.send().await.map_err(|e| InstallError::Cloud(e.to_string()))?;
    let resp = resp.error_for_status().map_err(|e| InstallError::Cloud(e.to_string()))?;
    Ok(resp.bytes().await.map_err(|e| InstallError::Cloud(e.to_string()))?.to_vec())
}

fn method(req: &cloud_client::PreparedRequest) -> reqwest::Method {
    req.method.parse().unwrap_or(reqwest::Method::GET)
}

/// Descarga + verifica + descomprime el módulo en el cache local, devolviendo su carpeta.
///
/// `sha` es el SHA256 esperado del zip (ya validado como presente por el llamador, ADR-0015);
/// `ModuleStore::install` verifica integridad y aborta sin tocar nada si no casa.
fn acquire(
    store: &ModuleStore,
    module_id: &str,
    version: &ModuleVersion,
    sha: &str,
    zip_bytes: Vec<u8>,
) -> Result<PathBuf, InstallError> {
    let grant = InstallGrant {
        module_id: module_id.to_string(),
        version: version.version.clone(),
        download_url: format!("mem://{module_id}/{}", version.version),
        sha256: sha.to_string(),
    };

    let fetcher = InMemoryFetcher { bytes: RefCell::new(Some(zip_bytes)) };
    let dir = store.install(&fetcher, &grant)?;
    Ok(dir)
}

/// Pipeline completo de instalación. Devuelve la versión y carpeta instaladas.
///
/// `runtime` se bloquea por el llamador (server) y se pasa por `&mut`; el resto del I/O
/// (red, FS) es async/blocking sin tocar el lock más de lo necesario.
pub async fn install_from_cloud(
    http: &reqwest::Client,
    cloud_base_url: &str,
    cache_root: &std::path::Path,
    auth: &Auth,
    runtime: &mut erplora_runtime::Runtime,
    module_id: &str,
    requested_version: &str,
) -> Result<Installed, InstallError> {
    let cloud = CloudClient::new(cloud_base_url);

    // (1) Resolver versión contra el Cloud. SHA256 obligatorio (ADR-0015): sin hash esperado
    //     no hay verificación de integridad posible → abortar ANTES de descargar nada.
    let version = resolve_version(http, &cloud, auth, module_id, requested_version).await?;
    let sha = version
        .sha256
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .ok_or_else(|| InstallError::MissingSha256 {
            module_id: module_id.to_string(),
            version: version.version.clone(),
        })?
        .to_string();

    // (2) Descargar el ZIP binario.
    let dl_req = cloud.download(auth, module_id, &version.version);
    let zip_bytes = send_bytes(http, &dl_req).await?;

    // (3) Verificar SHA256 (obligatorio) + descomprimir de forma segura + cachear.
    let store = ModuleStore::new(cache_root);
    let dir = acquire(&store, module_id, &version, &sha, zip_bytes)?;

    // (4) Instalar en el runtime (migra, registra, activa).
    let installed_id = runtime
        .install_from_dir(&dir)
        .await
        .map_err(|e| InstallError::Runtime(e.to_string()))?;

    // (5) Registrar la instalación en el Cloud (best-effort: no aborta si falla).
    let mark = cloud.mark_installed(auth, module_id);
    let mark_body = serde_json::json!({ "version": version.version });
    let mut r = http.request(method(&mark), &mark.url).json(&mark_body);
    for (k, v) in &mark.headers {
        r = r.header(*k, v);
    }
    if let Err(e) = r.send().await {
        tracing::warn!(module_id, error = %e, "mark_installed/ falló (no crítico)");
    }

    Ok(Installed { module_id: installed_id, version: version.version, dir })
}
