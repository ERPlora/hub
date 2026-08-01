//! Flujo real de instalación de un módulo desde el Cloud Portal (ARQUITECTURA.md §2.2, §4).
//!
//! Reemplaza el endpoint ficticio `…/install/` del antiguo `erplora-cloud-client` por el
//! flujo verificado contra el Cloud:
//!
//!   1. `POST install-plan/`      → Cloud resuelve cierre + topo-sort + entitlement.
//!   2. `GET download/?version=` → descarga cada ZIP en el orden del plan.
//!   3. verify SHA256 + unzip    → reusa `erplora-source::ModuleStore` (anti zip-slip + cache).
//!   4. `Runtime::install_from_dir` → migra y activa cada nodo (deps primero).
//!   5. `POST mark_installed/`   → registra cada instalación en Cloud (best-effort).
//!
//! Auth = JWT del usuario activo (`Authorization: Bearer`) + `X-Hub-Id` (cabeceras de la
//! petición entrante). La verificación SHA256 es **obligatoria y no-saltable** (ADR-0015):
//! si el Cloud no expone `sha256` en el plan, la instalación se **aborta** con
//! [`InstallError::MissingSha256`] antes de descargar nada (el fix server-side para que el
//! serializer lo exponga siempre va en el issue pareja de Cloud).

use std::cell::RefCell;
use std::path::PathBuf;

use cloud_client::{Auth, CloudClient, InstallGrant, InstallPlan, InstallPlanNode, ModuleVersion};
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
    /// El plan entero se valida antes de descargar el primer byte: un nodo premium bloqueado no
    /// deja una instalación parcial y la UI conserva precio + URL para pedir compra/consentimiento.
    #[error("plan bloqueado por entitlement: {blocked_on:?}")]
    Blocked {
        blocked_on: Vec<String>,
        plan: Box<InstallPlan>,
    },
    #[error("install-plan inválido: {0}")]
    InvalidPlan(String),
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

/// Callback de progreso del pipeline: `(module_id_en_curso, fase)`. Fases, en orden por módulo:
/// `resolving` → `downloading` → `verifying` → `installing`. Con deps anidadas el callback se
/// dispara también por cada dependencia (la dep completa sus fases ANTES del `installing` del
/// módulo que la declara). El server lo retransmite por WS como `module.install.progress` para
/// que el Hub pinte en la card del catálogo en qué punto está la instalación.
pub type OnProgress<'a> = &'a (dyn Fn(&str, &str) + Send + Sync);

/// Resultado de una instalación correcta (forma del JSON de `/api/modules/request-install`).
#[derive(Debug, Clone)]
pub struct Installed {
    pub module_id: String,
    pub version: String,
    /// Carpeta extraída en el cache local (para la ingestión de embeddings, §9).
    pub dir: PathBuf,
}

/// Política de firma para **tests**: admite módulos sin firmar (los mocks del Cloud de los tests
/// no firman). Equivale al escape hatch de dev — nunca debe usarse en código de producción.
pub fn dev_signature_policy() -> cloud_client::SignaturePolicy {
    cloud_client::SignaturePolicy::DevTrust
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
        versions
            .into_iter()
            .next()
            .ok_or_else(|| InstallError::VersionNotFound("latest".into()))
    }
}

/// Ejecuta una `PreparedRequest` GET y devuelve el cuerpo como texto.
async fn send_text(
    http: &reqwest::Client,
    req: &cloud_client::PreparedRequest,
) -> Result<String, InstallError> {
    let mut r = http.request(method(req), &req.url);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| InstallError::Cloud(e.to_string()))?;
    let resp = resp
        .error_for_status()
        .map_err(|e| InstallError::Cloud(e.to_string()))?;
    resp.text()
        .await
        .map_err(|e| InstallError::Cloud(e.to_string()))
}

/// Resuelve el plan canónico en Cloud. Es público para que el endpoint de previsualización y el
/// ejecutor compartan exactamente el mismo contrato (la UI nunca infiere dependencias).
pub async fn resolve_install_plan(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    runtime: &erplora_runtime::Runtime,
    module_id: &str,
    requested_version: &str,
) -> Result<InstallPlan, InstallError> {
    let cloud = CloudClient::new(cloud_base_url);
    let installed: Vec<String> = runtime.modules().into_iter().map(|m| m.id).collect();
    let prepared = cloud.install_plan(auth, module_id, Some(requested_version), &installed);
    let mut req = http
        .request(method(&prepared.request), &prepared.request.url)
        .json(&prepared.body);
    for (k, v) in &prepared.request.headers {
        req = req.header(*k, v);
    }
    let resp = req
        .send()
        .await
        .map_err(|e| InstallError::Cloud(e.to_string()))?;
    let status = resp.status();
    let text = resp
        .text()
        .await
        .map_err(|e| InstallError::Cloud(e.to_string()))?;
    if !status.is_success() {
        return Err(if status == reqwest::StatusCode::NOT_FOUND {
            InstallError::VersionNotFound(module_id.to_string())
        } else {
            InstallError::Cloud(format!("install-plan {status}: {text}"))
        });
    }
    let plan =
        InstallPlan::parse(&text).map_err(|e| InstallError::InvalidPlan(format!("JSON: {e}")))?;
    validate_plan(&plan, module_id)?;
    Ok(plan)
}

fn validate_plan(plan: &InstallPlan, requested: &str) -> Result<(), InstallError> {
    if plan.requested != requested {
        return Err(InstallError::InvalidPlan(format!(
            "requested={} pero se pidió {requested}",
            plan.requested
        )));
    }
    let mut seen = std::collections::HashSet::new();
    for node in &plan.plan {
        if node.module_id.trim().is_empty() || node.version.trim().is_empty() {
            return Err(InstallError::InvalidPlan(
                "cada nodo necesita module_id y version".into(),
            ));
        }
        if node.sha256.trim().is_empty() {
            return Err(InstallError::MissingSha256 {
                module_id: node.module_id.clone(),
                version: node.version.clone(),
            });
        }
        if !seen.insert(node.module_id.as_str()) {
            return Err(InstallError::InvalidPlan(format!(
                "módulo duplicado: {}",
                node.module_id
            )));
        }
    }
    if !plan.blocked
        && !plan.already_satisfied.iter().any(|m| m == requested)
        && !plan.plan.iter().any(|n| n.module_id == requested)
    {
        return Err(InstallError::InvalidPlan(
            "el plan ejecutable no contiene el módulo pedido".into(),
        ));
    }
    Ok(())
}

/// Ejecuta una `PreparedRequest` GET y devuelve el cuerpo binario (descarga del ZIP).
async fn send_bytes(
    http: &reqwest::Client,
    req: &cloud_client::PreparedRequest,
) -> Result<Vec<u8>, InstallError> {
    let mut r = http.request(method(req), &req.url);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| InstallError::Cloud(e.to_string()))?;
    let resp = resp
        .error_for_status()
        .map_err(|e| InstallError::Cloud(e.to_string()))?;
    Ok(resp
        .bytes()
        .await
        .map_err(|e| InstallError::Cloud(e.to_string()))?
        .to_vec())
}

fn method(req: &cloud_client::PreparedRequest) -> reqwest::Method {
    req.method.parse().unwrap_or(reqwest::Method::GET)
}

/// Descarga + verifica + descomprime el módulo en el cache local, devolviendo su carpeta.
///
/// `sha` es el SHA256 esperado del zip (ya validado como presente por el llamador, ADR-0015);
/// `ModuleStore::install` verifica integridad (SHA256) y autenticidad (firma ed25519, hub#239)
/// y aborta sin tocar nada si no casa. La firma se exige según `policy` (DEFAULT deny: en
/// producción el llamador pasa `Enforce(keyring)`).
fn acquire(
    store: &ModuleStore,
    module_id: &str,
    version: &ModuleVersion,
    sha: &str,
    signature: Option<cloud_client::ModuleSignature>,
    zip_bytes: Vec<u8>,
    policy: &cloud_client::SignaturePolicy,
) -> Result<PathBuf, InstallError> {
    let grant = InstallGrant {
        module_id: module_id.to_string(),
        version: version.version.clone(),
        download_url: format!("mem://{module_id}/{}", version.version),
        sha256: sha.to_string(),
        signature,
    };

    let fetcher = InMemoryFetcher {
        bytes: RefCell::new(Some(zip_bytes)),
    };
    let dir = store.install(&fetcher, &grant, policy)?;
    Ok(dir)
}

/// Ejecuta el plan canónico del Cloud en orden. El plan completo se resuelve y valida antes de
/// descargar: `blocked=true` corta sin instalar nada y nunca inicia una compra automática.
pub async fn install_from_cloud(
    http: &reqwest::Client,
    cloud_base_url: &str,
    cache_root: &std::path::Path,
    auth: &Auth,
    runtime: &mut erplora_runtime::Runtime,
    module_id: &str,
    requested_version: &str,
    on_progress: OnProgress<'_>,
    signature_policy: &cloud_client::SignaturePolicy,
) -> Result<Installed, InstallError> {
    on_progress(module_id, "resolving");
    let plan = resolve_install_plan(
        http,
        cloud_base_url,
        auth,
        runtime,
        module_id,
        requested_version,
    )
    .await?;
    if plan.blocked {
        return Err(InstallError::Blocked {
            blocked_on: plan.blocked_on.clone(),
            plan: Box::new(plan),
        });
    }
    if plan.already_satisfied.iter().any(|m| m == module_id) && plan.plan.is_empty() {
        let installed = runtime
            .modules()
            .into_iter()
            .find(|m| m.id == module_id)
            .ok_or_else(|| {
                InstallError::InvalidPlan("Cloud marcó satisfecho un módulo ausente".into())
            })?;
        return Ok(Installed {
            module_id: installed.id,
            version: installed.version,
            dir: cache_root.join(module_id),
        });
    }

    let cloud = CloudClient::new(cloud_base_url);
    let store = ModuleStore::new(cache_root);
    let mut headline: Option<Installed> = None;
    for node in &plan.plan {
        let InstallPlanNode {
            module_id: id,
            version,
            sha256,
            signature,
            ..
        } = node;
        on_progress(id, "resolving");

        // ADR-0060 antecede a hub#239. Mientras el plan de Cloud no lleve `signature`, pedimos
        // SOLO esa metadata a versions/ bajo política Enforce. Dev usa cero round-trips extra.
        let signature = if signature.is_none() && signature_policy.requires_signature() {
            resolve_version(http, &cloud, auth, id, version)
                .await?
                .signature
        } else {
            signature.clone()
        };

        on_progress(id, "downloading");
        let zip_bytes = send_bytes(http, &cloud.download(auth, id, version)).await?;
        on_progress(id, "verifying");
        let metadata = ModuleVersion {
            version: version.clone(),
            changelog: String::new(),
            is_active: true,
            file_size_bytes: 0,
            sha256: Some(sha256.clone()),
            signature: signature.clone(),
        };
        let dir = acquire(
            &store,
            id,
            &metadata,
            sha256,
            signature,
            zip_bytes,
            signature_policy,
        )?;

        on_progress(id, "installing");
        let installed_id = runtime
            .install_from_dir(&dir)
            .await
            .map_err(|e| InstallError::Runtime(e.to_string()))?;

        let mark = cloud.mark_installed(auth, id);
        let mark_body = serde_json::json!({ "version": version });
        let mut r = http.request(method(&mark), &mark.url).json(&mark_body);
        for (k, v) in &mark.headers {
            r = r.header(*k, v);
        }
        if let Err(e) = r.send().await {
            tracing::warn!(module_id = %id, error = %e, "mark_installed/ falló (no crítico)");
        }
        if id == module_id {
            headline = Some(Installed {
                module_id: installed_id,
                version: version.clone(),
                dir,
            });
        }
    }
    headline.ok_or_else(|| InstallError::InvalidPlan("el plan no instaló el módulo pedido".into()))
}
