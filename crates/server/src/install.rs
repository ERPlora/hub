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

/// Módulo del plan que exige compra: lo que la UI necesita para ofrecer el consentimiento.
/// Es el nodo del plan del Cloud + su `module_id` (que el serializer deja en el nodo, no en
/// `purchase`). **Nunca se auto-cobra** (ADR-0060).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BlockedPurchase {
    pub module_id: String,
    pub module_type: String,
    pub price: String,
    pub currency: String,
    pub purchase_url: String,
}

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
    /// El plan (ADR-0060) trae dependencias que el hub NO ha comprado. **No se instala nada**:
    /// el consentimiento/compra es del usuario, nunca un auto-cobro. `purchase` lleva a dónde ir.
    #[error("el módulo `{requested}` necesita módulos que este hub no tiene contratados: {}", blocked_on.join(", "))]
    Blocked {
        requested: String,
        blocked_on: Vec<String>,
        purchase: Vec<BlockedPurchase>,
    },
    #[error("runtime: {0}")]
    Runtime(String),
}

impl InstallError {
    /// Código de error **estable** (canal de errores de dominio, hub#139): la UI programa y
    /// traduce contra él, nunca contra el mensaje. Un fallo de instalación deja de ser mudo.
    pub fn code(&self) -> &'static str {
        match self {
            InstallError::Cloud(_) => "install_cloud_unavailable",
            InstallError::VersionNotFound(_) => "install_version_not_found",
            InstallError::Source(SourceError::BadSignature(_)) => "install_bad_signature",
            InstallError::Source(_) => "install_download_failed",
            InstallError::MissingSha256 { .. } => "install_missing_sha256",
            InstallError::Blocked { .. } => "install_blocked",
            InstallError::Runtime(_) => "install_runtime_failed",
        }
    }
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

/// Pipeline completo de instalación **con resolución de dependencias anidadas** (nested install).
/// Descarga el módulo pedido y, ANTES de instalarlo, descarga+instala recursivamente cada
/// dependencia declarada en su manifest que aún no esté instalada (topo-orden por profundidad).
/// Devuelve la `Installed` del módulo pedido (el "headline"); las deps quedan instaladas como
/// efecto lateral, igual que al instalar un lote horneado con `install_all_from_dir`.
///
/// El grafo de deps se lee del **manifest del ZIP publicado** (la fuente autoritativa que valida
/// el runtime al registrar), no del catálogo del Cloud: ADR-0060 (`resolve_install_plan`) sigue
/// sin cablear y el M2M `Module.dependencies` del Cloud está vacío en prod, así que un plan
/// Cloud-side no ordenaría nada. El entitlement se sigue aplicando por módulo en cada `download/`.
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
    on_progress: OnProgress<'_>,
    signature_policy: &cloud_client::SignaturePolicy,
) -> Result<Installed, InstallError> {
    // (0) ADR-0060: el Cloud resuelve el cierre transitivo (tiene el grafo fresco y la verdad del
    //     entitlement); el Hub lo EJECUTA. Si el plan llega, manda: trae `version`+`sha256` por
    //     nodo, así que nos ahorramos el round-trip a `versions/` de cada uno.
    //
    //     El progreso NO se emite aquí: las fases son POR MÓDULO (`resolving → downloading →
    //     verifying → installing`) y las emite quien acaba instalando —`execute_plan` por nodo o
    //     `install_recursive` en el fallback—. Emitir un `resolving` extra antes de saber cuál de
    //     los dos caminos se toma duplicaría la fase del módulo pedido.
    match fetch_install_plan(http, cloud_base_url, auth, runtime, module_id, requested_version)
        .await
    {
        Ok(plan) => {
            return execute_plan(
                http,
                cloud_base_url,
                cache_root,
                auth,
                runtime,
                module_id,
                plan,
                on_progress,
                signature_policy,
            )
            .await;
        }
        Err(PlanUnavailable::Blocked(e)) => return Err(e),
        Err(PlanUnavailable::Degraded(reason)) => {
            // Cloud sin el endpoint desplegado, caído o respuesta ilegible: la resolución
            // anidada por manifest sigue siendo la red de seguridad. Se degrada, no se rompe.
            tracing::warn!(
                module_id = %module_id,
                reason = %reason,
                "install-plan no disponible (ADR-0060): resolviendo dependencias por manifest"
            );
        }
    }

    let mut installing: std::collections::HashSet<String> = std::collections::HashSet::new();
    install_recursive(
        http,
        cloud_base_url,
        cache_root,
        auth,
        runtime,
        module_id.to_string(),
        requested_version.to_string(),
        &mut installing,
        on_progress,
        signature_policy,
    )
    .await
}

/// Por qué no hay plan ejecutable.
enum PlanUnavailable {
    /// El plan SÍ llegó y dice `blocked`: es un error de dominio, no un fallback.
    Blocked(InstallError),
    /// El plan no se pudo obtener/parsear → usar la resolución anidada por manifest.
    Degraded(String),
}

/// Pide el plan al Cloud pasando el set instalado REAL del registry (el runtime es la autoridad).
/// `blocked` se traduce a [`InstallError::Blocked`] con los punteros de compra.
async fn fetch_install_plan(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    runtime: &erplora_runtime::Runtime,
    module_id: &str,
    requested_version: &str,
) -> Result<cloud_client::InstallPlan, PlanUnavailable> {
    let installed: Vec<String> = runtime
        .registry()
        .installed
        .iter()
        .map(|m| m.id.clone())
        .collect();
    let cloud = CloudClient::new(cloud_base_url);
    let prepared = cloud.install_plan(auth, module_id, requested_version, &installed);

    let mut r = http
        .request(reqwest::Method::POST, &prepared.request.url)
        .json(&prepared.body);
    for (k, v) in &prepared.request.headers {
        r = r.header(*k, v);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| PlanUnavailable::Degraded(e.to_string()))?;
    let status = resp.status();
    let body = resp
        .text()
        .await
        .map_err(|e| PlanUnavailable::Degraded(e.to_string()))?;
    if !status.is_success() {
        // 404/405 = Cloud sin ADR-0060 desplegado; 5xx = caído. En ambos casos: degradar.
        return Err(PlanUnavailable::Degraded(format!("HTTP {status}")));
    }
    let plan = cloud_client::InstallPlan::parse(&body)
        .map_err(|e| PlanUnavailable::Degraded(format!("plan ilegible: {e}")))?;

    if plan.blocked {
        let purchase = plan
            .plan
            .iter()
            .filter(|n| n.requires_purchase)
            .map(|n| {
                let p = n.purchase.clone().unwrap_or(cloud_client::InstallPlanPurchase {
                    module_type: n.tier.clone(),
                    price: String::new(),
                    currency: String::new(),
                    purchase_url: String::new(),
                });
                BlockedPurchase {
                    module_id: n.module_id.clone(),
                    module_type: p.module_type,
                    price: p.price,
                    currency: p.currency,
                    purchase_url: p.purchase_url,
                }
            })
            .collect();
        return Err(PlanUnavailable::Blocked(InstallError::Blocked {
            requested: if plan.requested.is_empty() {
                module_id.to_string()
            } else {
                plan.requested.clone()
            },
            blocked_on: plan.blocked_on.clone(),
            purchase,
        }));
    }
    Ok(plan)
}

/// Ejecuta el plan **en orden** (dependencias primero). Por nodo: `download/?version=` → verificar
/// el `sha256` DEL PLAN → `install_from_dir` → `mark_installed`. Sin round-trip a `versions/`.
///
/// El `MissingDependency` del runtime (paso 6) e `install_order` siguen ahí como red de seguridad
/// ante drift entre el set que reportamos y el real: si el plan viniera incompleto, el runtime lo
/// rechaza en vez de instalar algo roto.
#[allow(clippy::too_many_arguments)]
async fn execute_plan(
    http: &reqwest::Client,
    cloud_base_url: &str,
    cache_root: &std::path::Path,
    auth: &Auth,
    runtime: &mut erplora_runtime::Runtime,
    module_id: &str,
    plan: cloud_client::InstallPlan,
    on_progress: OnProgress<'_>,
    signature_policy: &cloud_client::SignaturePolicy,
) -> Result<Installed, InstallError> {
    let cloud = CloudClient::new(cloud_base_url);
    let mut headline: Option<Installed> = None;

    for node in &plan.plan {
        // Idempotencia / drift: el plan excluye lo ya instalado, pero si el registry lo tiene
        // igualmente (instalación concurrente, set desfasado) no se reinstala.
        if runtime.registry().is_installed(&node.module_id) {
            continue;
        }

        // Mismas fases que el camino anidado, una tanda por nodo del plan.
        on_progress(&node.module_id, "resolving");

        // ADR-0015: sin sha256 esperado no hay verificación posible → abortar antes de descargar.
        let sha = node.sha256.trim();
        if sha.is_empty() {
            return Err(InstallError::MissingSha256 {
                module_id: node.module_id.clone(),
                version: node.version.clone(),
            });
        }

        // El plan no expone `signature` todavía (ADR-0194). Bajo `Enforce` NO se degrada en
        // silencio: se resuelve la versión por `versions/` para recuperar la firma.
        let signature = match (&node.signature, signature_policy) {
            (Some(s), _) => Some(s.clone()),
            (None, cloud_client::SignaturePolicy::Enforce(_)) => {
                resolve_version(http, &cloud, auth, &node.module_id, &node.version)
                    .await?
                    .signature
            }
            (None, _) => None,
        };

        on_progress(&node.module_id, "downloading");
        let dl_req = cloud.download(auth, &node.module_id, &node.version);
        let zip_bytes = send_bytes(http, &dl_req).await?;

        on_progress(&node.module_id, "verifying");
        let store = ModuleStore::new(cache_root);
        let version = ModuleVersion {
            version: node.version.clone(),
            changelog: String::new(),
            is_active: true,
            file_size_bytes: 0,
            sha256: Some(sha.to_string()),
            signature: signature.clone(),
        };
        let dir = acquire(
            &store,
            &node.module_id,
            &version,
            sha,
            signature,
            zip_bytes,
            signature_policy,
        )?;

        on_progress(&node.module_id, "installing");
        let installed_id = runtime
            .install_from_dir(&dir)
            .await
            .map_err(|e| InstallError::Runtime(e.to_string()))?;

        mark_installed(http, &cloud, auth, &node.module_id, &node.version).await;

        let installed = Installed {
            module_id: installed_id,
            version: node.version.clone(),
            dir,
        };
        if node.module_id == module_id {
            headline = Some(installed);
        }
    }

    // El módulo pedido puede no estar en el plan porque YA estaba instalado (`already_satisfied`):
    // reinstalarlo no aporta nada, así que se reporta lo que hay.
    match headline {
        Some(i) => Ok(i),
        None if runtime.registry().is_installed(module_id) => Ok(Installed {
            module_id: module_id.to_string(),
            version: runtime.registry().module_version(module_id),
            dir: cache_root.to_path_buf(),
        }),
        // Plan vacío y el módulo no está: el Cloud no lo considera instalable aquí.
        None => Err(InstallError::VersionNotFound(module_id.to_string())),
    }
}

/// `POST mark_installed/` — best-effort: un fallo aquí NO aborta (el módulo ya está operativo).
async fn mark_installed(
    http: &reqwest::Client,
    cloud: &CloudClient,
    auth: &Auth,
    module_id: &str,
    version: &str,
) {
    let mark = cloud.mark_installed(auth, module_id);
    let body = serde_json::json!({ "version": version });
    let mut r = http.request(method(&mark), &mark.url).json(&body);
    for (k, v) in &mark.headers {
        r = r.header(*k, v);
    }
    if let Err(e) = r.send().await {
        tracing::warn!(module_id = %module_id, error = %e, "mark_installed/ falló (no crítico)");
    }
}

/// Instala `module_id`@`requested_version` resolviendo sus deps primero (recursivo). `installing`
/// guarda la cadena en curso para cortar ciclos (`a→b→a`): una dep ya presente en la pila no se
/// re-expande — el runtime la rechazará luego con `MissingDependency` si el ciclo es real, que es
/// lo correcto (un ciclo es un error de autoría del módulo, no algo a resolver aquí).
#[allow(clippy::too_many_arguments)]
fn install_recursive<'a>(
    http: &'a reqwest::Client,
    cloud_base_url: &'a str,
    cache_root: &'a std::path::Path,
    auth: &'a Auth,
    runtime: &'a mut erplora_runtime::Runtime,
    module_id: String,
    requested_version: String,
    installing: &'a mut std::collections::HashSet<String>,
    on_progress: OnProgress<'a>,
    signature_policy: &'a cloud_client::SignaturePolicy,
) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<Installed, InstallError>> + Send + 'a>>
{
    Box::pin(async move {
        let cloud = CloudClient::new(cloud_base_url);

        // (1) Resolver versión contra el Cloud. SHA256 obligatorio (ADR-0015): sin hash esperado
        //     no hay verificación de integridad posible → abortar ANTES de descargar nada.
        on_progress(&module_id, "resolving");
        let version = resolve_version(http, &cloud, auth, &module_id, &requested_version).await?;
        let sha = version
            .sha256
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .ok_or_else(|| InstallError::MissingSha256 {
                module_id: module_id.clone(),
                version: version.version.clone(),
            })?
            .to_string();

        // (2) Descargar el ZIP binario.
        on_progress(&module_id, "downloading");
        let dl_req = cloud.download(auth, &module_id, &version.version);
        let zip_bytes = send_bytes(http, &dl_req).await?;

        // (3) Verificar firma ed25519 (hub#239, DEFAULT deny según policy) + SHA256 + descomprimir
        //     de forma segura + cachear.
        on_progress(&module_id, "verifying");
        let store = ModuleStore::new(cache_root);
        let dir = acquire(
            &store,
            &module_id,
            &version,
            &sha,
            version.signature.clone(),
            zip_bytes,
            signature_policy,
        )?;

        // (4) INSTALACIÓN ANIDADA: instala las dependencias declaradas que falten ANTES del módulo.
        //     El runtime exige que las deps estén registradas al instalar (installer.rs::install);
        //     aquí se satisface ese contrato descargándolas del Cloud en orden de profundidad.
        let missing = runtime
            .missing_dependencies(&dir)
            .map_err(|e| InstallError::Runtime(e.to_string()))?;
        installing.insert(module_id.clone());
        for dep in missing {
            // Ya en la cadena en curso (ciclo) o ya instalada por otra rama (dep en diamante): saltar.
            if installing.contains(&dep) || runtime.registry().is_installed(&dep) {
                continue;
            }
            install_recursive(
                http,
                cloud_base_url,
                cache_root,
                auth,
                &mut *runtime,
                dep,
                "latest".to_string(),
                &mut *installing,
                on_progress,
                signature_policy,
            )
            .await?;
        }

        // (5) Instalar el módulo (migra, registra, activa) — ya con sus deps presentes.
        on_progress(&module_id, "installing");
        let installed_id = runtime
            .install_from_dir(&dir)
            .await
            .map_err(|e| InstallError::Runtime(e.to_string()))?;

        // (6) Registrar la instalación en el Cloud (best-effort: no aborta si falla).
        mark_installed(http, &cloud, auth, &module_id, &version.version).await;

        Ok(Installed {
            module_id: installed_id,
            version: version.version,
            dir,
        })
    })
}
