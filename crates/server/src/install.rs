//! Flujo real de instalación de un módulo desde el Cloud Portal (ARQUITECTURA.md §2.2, §4).
//!
//! Reemplaza el endpoint ficticio `…/install/` del antiguo `erplora-cloud-client` por el
//! flujo verificado contra el Cloud:
//!
//!   1. `GET versions/`          → lista de versiones; elige la pedida (o la última activa).
//!   2. `GET download/?version=` → descarga el ZIP **en streaming a un temp file** de la caché
//!      de módulos, con el SHA256 calculado sobre la marcha (hub#981: el zip no vive en RAM).
//!   3. verify SHA256 + unzip    → reusa `erplora-source::ModuleStore` (anti zip-slip + cache),
//!      leyendo del fichero (`install_from_file`).
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
    /// The module declares it needs a newer core than this hub runs (hub#1620). Its own variant,
    /// not a [`InstallError::Runtime`] string: the shell translates it with both numbers instead
    /// of painting the engine's English sentence.
    #[error("the module `{module}` requires ERPlora {required} and this hub runs {core}")]
    CoreVersionTooOld {
        module: String,
        required: String,
        core: String,
    },
    /// Se pidió **actualizar** un módulo que este hub no tiene instalado (hub#516). Actualizar no
    /// es una puerta trasera para instalar: un id mal escrito debe decirlo, no instalar algo nuevo.
    #[error("el módulo `{0}` no está instalado en este hub: no hay nada que actualizar")]
    NotInstalled(String),
    /// El Cloud **contestó**, y rechazó la credencial de máquina de este hub (`401`/`403`)
    /// — hub#1720. No es lo mismo que no contestar: aquí no hay nada que reintentar, hay una
    /// credencial que arreglar, y decirle a la tienda «inténtalo en unos minutos» la deja en
    /// bucle. La causa que destapó la issue: un hub con llave nueva cruzaba a una cabecera que el
    /// SaaS no reconocía.
    #[error("el Cloud no aceptó la credencial de este hub")]
    CloudDenied,
    /// El Cloud **contestó** `404`: ese módulo no está en el catálogo que este hub puede ver
    /// (hub#1720). Es un id que no existe o que este hub no tiene contratado — no una caída.
    #[error("el módulo `{module_id}` no está en el catálogo de este hub")]
    NotInCatalog { module_id: String },
    /// El Cloud **contestó** con otro error (`5xx`, `429`, …) — hub#1720. Contestó, así que no es
    /// «no llegué»; y no dijo cuál de los dos casos de arriba es, así que solo cabe reintentar.
    #[error("el Cloud contestó con un error ({status})")]
    CloudRejected { status: u16 },
    /// The marketplace took the call and then went silent past the stall limit (hub#2251):
    /// no headers, or the zip stopped arriving. Retrying later is all there is to do.
    #[error("the marketplace did not answer in time")]
    CloudTimeout,
}

impl InstallError {
    /// The one door every runtime refusal of the install pipeline takes (hub#1620).
    ///
    /// «This app needs a newer hub» is lifted out with its numbers because it is the one refusal
    /// the owner can act on — update the hub — and the shell has to be able to say so in their
    /// language. Everything else keeps travelling as `install_runtime_failed`.
    pub fn from_runtime(e: erplora_runtime::RuntimeError) -> Self {
        match e {
            erplora_runtime::RuntimeError::CoreVersionTooOld {
                module,
                required,
                core,
            } => InstallError::CoreVersionTooOld {
                module,
                required,
                core,
            },
            other => InstallError::Runtime(other.to_string()),
        }
    }

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
            InstallError::CoreVersionTooOld { .. } => "core_version_too_old",
            InstallError::NotInstalled(_) => "update_not_installed",
            InstallError::CloudDenied => "install_cloud_denied",
            InstallError::NotInCatalog { .. } => "install_not_in_catalog",
            InstallError::CloudRejected { .. } => "install_cloud_rejected",
            InstallError::CloudTimeout => "install_cloud_timeout",
        }
    }
}

/// `Fetcher` de un solo uso: sirve unos bytes ya en memoria (hoy, la copia local de hub#571
/// leída de la BD) a la lógica síncrona de `ModuleStore` (verify SHA256 + unzip seguro). El
/// camino de DESCARGA ya no pasa por aquí: va en streaming a disco (hub#981) y entra por
/// `ModuleStore::install_from_file`. Evita duplicar la verificación/descompresión que ya
/// vive —y está testeada— en `erplora-source`.
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
    /// hub#1130: ids que la resolución de dependencias (plan del Cloud, ADR-0060, o el fallback
    /// anidado por manifest) instaló como efecto lateral de `module_id`, y que **no** estaban
    /// instalados antes de esta llamada. `module_id` nunca aparece en su propia lista. Vacío —
    /// nunca ausente— cuando no arrastró nada, para que quien la lea no distinga dos formas.
    pub also_installed: Vec<String>,
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
    let body = send_text(http, &req, module_id).await?;
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
/// The `Display` of a `reqwest` error names the address this hub calls erplora.com on. It goes
/// to the hub's log; the person on the marketplace gets the stable code (hub#1689).
fn cloud_unreachable(e: reqwest::Error) -> InstallError {
    if e.is_timeout() {
        tracing::warn!(error = %e, "the marketplace went silent past the stall limit (hub#2251)");
        return InstallError::CloudTimeout;
    }
    InstallError::Cloud(crate::cloud_proxy::cloud_unreachable(&e.to_string()).to_string())
}

/// Lo contrario: el Cloud **sí** contestó, y contestó un error (hub#1720).
///
/// Contestar no es caerse, y para quien está delante del marketplace no significan lo mismo: una
/// credencial rechazada no se arregla esperando, y un módulo que no está en su catálogo no se
/// arregla nunca. Hasta hub#1720 las tres cruzaban por `cloud_unreachable` y salían con el mismo
/// código —«tu hub no ha podido llegar a erplora.com, inténtalo de nuevo»—, así que un hub con la
/// credencial rechazada reintentaba en bucle leyendo una frase falsa. El status va al log del hub;
/// la persona recibe el código estable, nunca la dirección que se marcó (hub#1689).
fn cloud_refused(status: reqwest::StatusCode, module_id: &str) -> InstallError {
    tracing::warn!(
        module_id = %module_id,
        status = %status,
        "erplora.com answered the install pipeline with an error"
    );
    match status {
        reqwest::StatusCode::UNAUTHORIZED | reqwest::StatusCode::FORBIDDEN => {
            InstallError::CloudDenied
        }
        reqwest::StatusCode::NOT_FOUND => InstallError::NotInCatalog {
            module_id: module_id.to_string(),
        },
        other => InstallError::CloudRejected {
            status: other.as_u16(),
        },
    }
}

/// El status de una respuesta del Cloud, o el fallo que le toca. Misma condición que
/// `error_for_status()` —4xx y 5xx—, para que un `3xx` que `reqwest` ya siguió no cambie de
/// significado al pasar por aquí.
fn ok_or_refused(
    resp: reqwest::Response,
    module_id: &str,
) -> Result<reqwest::Response, InstallError> {
    let status = resp.status();
    if status.is_client_error() || status.is_server_error() {
        return Err(cloud_refused(status, module_id));
    }
    Ok(resp)
}

async fn send_text(
    http: &reqwest::Client,
    req: &cloud_client::PreparedRequest,
    module_id: &str,
) -> Result<String, InstallError> {
    let mut r = http.request(method(req), &req.url);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }
    let resp = r.send().await.map_err(cloud_unreachable)?;
    let resp = ok_or_refused(resp, module_id)?;
    resp.text().await.map_err(cloud_unreachable)
}

/// Descarga el ZIP del módulo **en streaming a un temp file** en la caché de módulos (mismo
/// volumen que la extracción final), calculando el SHA256 **sobre la marcha** mientras escribe
/// (hub#981): el archivo nunca se bufferiza entero en RAM. Devuelve el temp file y el hex del
/// SHA256 de lo realmente escrito. El `NamedTempFile` se borra solo al soltarse, así que TODOS
/// los caminos de fallo (y el de éxito, tras usarlo) limpian la descarga.
async fn download_to_temp_file(
    http: &reqwest::Client,
    req: &cloud_client::PreparedRequest,
    cache_root: &std::path::Path,
    module_id: &str,
) -> Result<(tempfile::NamedTempFile, String), InstallError> {
    use futures_util::StreamExt;
    use sha2::{Digest, Sha256};
    use std::io::Write;

    let mut r = http.request(method(req), &req.url);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }
    let resp = r.send().await.map_err(cloud_unreachable)?;
    let resp = ok_or_refused(resp, module_id)?;

    std::fs::create_dir_all(cache_root).map_err(|e| InstallError::Source(e.into()))?;
    let mut tmp =
        tempfile::NamedTempFile::new_in(cache_root).map_err(|e| InstallError::Source(e.into()))?;
    let mut hasher = Sha256::new();
    let mut stream = resp.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(cloud_unreachable)?;
        hasher.update(&chunk);
        tmp.write_all(&chunk)
            .map_err(|e| InstallError::Source(e.into()))?;
    }
    tmp.flush().map_err(|e| InstallError::Source(e.into()))?;

    let sha: String = hasher
        .finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    Ok((tmp, sha))
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

/// Como [`acquire`], pero para un zip que ya está **en disco** (hub#981): la verificación
/// (SHA256 + firma) y la descompresión leen del fichero, sin bufferizar el archivo en RAM.
/// La usa el camino de descarga (streaming); [`acquire`] queda para la reposición local
/// (hub#571), cuyos bytes salen de la base de datos.
fn acquire_from_file(
    store: &ModuleStore,
    module_id: &str,
    version: &ModuleVersion,
    sha: &str,
    signature: Option<cloud_client::ModuleSignature>,
    zip_path: &std::path::Path,
    policy: &cloud_client::SignaturePolicy,
) -> Result<PathBuf, InstallError> {
    let grant = InstallGrant {
        module_id: module_id.to_string(),
        version: version.version.clone(),
        download_url: format!("file://{}", zip_path.display()),
        sha256: sha.to_string(),
        signature,
    };
    Ok(store.install_from_file(zip_path, &grant, policy)?)
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
    acquire_and_install(
        http,
        cloud_base_url,
        cache_root,
        auth,
        runtime,
        module_id,
        requested_version,
        on_progress,
        signature_policy,
        None,
    )
    .await
}

/// Instala un módulo que pidió un BUNDLE (blueprint), tolerando que su versión ya no se publique.
///
/// Es [`install_from_cloud`] con **una** diferencia, y es toda la issue hub#751/#752: la versión
/// que trae `manifest.modules[].version` es una **foto del hub de origen**, no una exigencia del
/// negocio que importa. El marketplace poda las versiones viejas al publicar (se queda con las
/// últimas N), así que un pin de hace unos meses simplemente **ya no existe** — y exigirlo dejaba
/// a la peluquería sin `sales` y sin `verifactu`: sin cobro, sin ticket, sin registro fiscal.
///
/// El pin se intenta **primero y tal cual**: la sustitución es una vía de recuperación, no la
/// norma, así que un pin vivo se instala exacto y no se paga ningún round-trip de más. Solo cuando
/// el marketplace responde «esa versión no existe» se pregunta qué publica hoy y decide
/// [`module_update::resolve_bundle_version`] — la más nueva compatible, nunca hacia atrás, nunca
/// cruzando un major, nunca una en cuarentena.
///
/// Ese `requested != installed` **no puede ser mudo**: se devuelve para que el informe del import
/// lo diga (una plantilla que instala otra versión de la que anuncia sería justo la sorpresa que
/// esto trata de evitar). `None` = se instaló exactamente lo pineado.
///
/// That pin-first rule is the **backup** rule: restoring your own hub reinstalls what it ran. A
/// published **template** (`purpose: template`, hub#1904) starts a new business, so it asks what
/// the store publishes first and installs the newest version compatible with the recorded one
/// ([`module_update::resolve_template_version`]) — otherwise a salon opened today runs on the day
/// the template was exported until its next boot moves it forward.
pub async fn install_bundle_module(
    http: &reqwest::Client,
    cloud_base_url: &str,
    cache_root: &std::path::Path,
    auth: &Auth,
    runtime: &mut erplora_runtime::Runtime,
    module_id: &str,
    manifest_version: &str,
    purpose: erplora_runtime::export::BundlePurpose,
    on_progress: OnProgress<'_>,
    signature_policy: &cloud_client::SignaturePolicy,
) -> Result<Installed, InstallError> {
    if purpose.is_template() {
        if let Some(current) =
            template_target(http, cloud_base_url, auth, module_id, manifest_version).await
        {
            if current != manifest_version {
                tracing::info!(
                    module_id = %module_id,
                    recorded = %manifest_version,
                    installing = %current,
                    "template: installing the newest version compatible with the recorded one (hub#1904)"
                );
            }
            return install_from_cloud(
                http,
                cloud_base_url,
                cache_root,
                auth,
                runtime,
                module_id,
                &current,
                on_progress,
                signature_policy,
            )
            .await;
        }
        // Nothing to resolve in the recorded line (or the store did not answer): the pin path
        // below tries it as is and reports the real reason if it cannot be installed either.
    }

    let pinned = install_from_cloud(
        http,
        cloud_base_url,
        cache_root,
        auth,
        runtime,
        module_id,
        manifest_version,
        on_progress,
        signature_policy,
    )
    .await;

    // Cualquier otro desenlace se respeta: un `blocked` es una compra pendiente, un fallo de firma
    // o de red es una avería. Solo «esa versión ya no está» abre la puerta a sustituir.
    let Err(InstallError::VersionNotFound(_)) = &pinned else {
        return pinned;
    };
    if manifest_version.is_empty() || manifest_version == "latest" {
        // No había pin: el módulo no publica nada instalable y no hay nada que sustituir.
        return pinned;
    }

    let available = published_versions(http, cloud_base_url, auth, module_id).await?;
    let Some(substitute) =
        erplora_runtime::module_update::resolve_bundle_version(manifest_version, &available)
    else {
        return pinned;
    };

    tracing::warn!(
        module_id = %module_id,
        pinned = %manifest_version,
        installing = %substitute,
        "el marketplace ya no publica la versión que fija el bundle: se instala la más nueva compatible (hub#751)"
    );
    install_from_cloud(
        http,
        cloud_base_url,
        cache_root,
        auth,
        runtime,
        module_id,
        &substitute,
        on_progress,
        signature_policy,
    )
    .await
}

/// The version a template installs for the one it recorded, or `None` to fall back to the pin.
///
/// No pin (`""`/`latest`) already means «the newest» to [`install_from_cloud`], so there is nothing
/// to resolve. A store that does not answer is not a reason to fail the module here: the pin path
/// asks again and, if it cannot install either, reports the real error.
async fn template_target(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    module_id: &str,
    manifest_version: &str,
) -> Option<String> {
    if manifest_version.is_empty() || manifest_version == "latest" {
        return None;
    }
    match published_versions(http, cloud_base_url, auth, module_id).await {
        Ok(available) => {
            erplora_runtime::module_update::resolve_template_version(manifest_version, &available)
        }
        Err(error) => {
            tracing::warn!(
                module_id = %module_id,
                code = %error.code(),
                error = %error,
                "template: could not read versions/; falling back to the recorded version"
            );
            None
        }
    }
}

/// Lo que el marketplace publica hoy de un módulo, en la forma que entiende el resolutor del
/// runtime (`is_active` = la cuarentena, que decide igual aquí que en el auto-update).
async fn published_versions(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    module_id: &str,
) -> Result<Vec<erplora_runtime::module_update::Available>, InstallError> {
    let cloud = CloudClient::new(cloud_base_url);
    let body = send_text(http, &cloud.versions(auth, module_id), module_id).await?;
    let versions = ModuleVersion::parse_list(&body)
        .map_err(|e| InstallError::Cloud(format!("versions/ inválido: {e}")))?;
    Ok(versions
        .into_iter()
        .map(|v| erplora_runtime::module_update::Available {
            version: v.version,
            is_active: v.is_active,
        })
        .collect())
}

/// El pipeline compartido por `install` y `update`. `updating` = el módulo que se está
/// **actualizando** (hub#516): el único al que hay que volver a instalar aunque ya esté instalado.
#[allow(clippy::too_many_arguments)]
async fn acquire_and_install(
    http: &reqwest::Client,
    cloud_base_url: &str,
    cache_root: &std::path::Path,
    auth: &Auth,
    runtime: &mut erplora_runtime::Runtime,
    module_id: &str,
    requested_version: &str,
    on_progress: OnProgress<'_>,
    signature_policy: &cloud_client::SignaturePolicy,
    updating: Option<&str>,
) -> Result<Installed, InstallError> {
    // (0) ADR-0060: el Cloud resuelve el cierre transitivo (tiene el grafo fresco y la verdad del
    //     entitlement); el Hub lo EJECUTA. Si el plan llega, manda: trae `version`+`sha256` por
    //     nodo, así que nos ahorramos el round-trip a `versions/` de cada uno.
    //
    //     El progreso NO se emite aquí: las fases son POR MÓDULO (`resolving → downloading →
    //     verifying → installing`) y las emite quien acaba instalando —`execute_plan` por nodo o
    //     `install_recursive` en el fallback—. Emitir un `resolving` extra antes de saber cuál de
    //     los dos caminos se toma duplicaría la fase del módulo pedido.
    //
    //     En un **update** el set instalado que viaja al Cloud excluye al propio módulo: de lo
    //     contrario el plan lo daría por `already_satisfied` y no traería ni su versión nueva ni
    //     las dependencias que esa versión añade — que es justo lo que hay que resolver.
    match fetch_install_plan(
        http,
        cloud_base_url,
        auth,
        runtime,
        module_id,
        requested_version,
        updating,
    )
    .await
    {
        Ok(plan) => {
            match execute_plan(
                http,
                cloud_base_url,
                cache_root,
                auth,
                runtime,
                module_id,
                plan,
                on_progress,
                signature_policy,
                updating,
            )
            .await?
            {
                PlanOutcome::Installed(installed) => return Ok(installed),
                // hub#672: the plan arrived 200 but omits dependencies the downloaded manifest
                // declares (the saas#1352 empty-graph outage shape). Executing it as-is would die
                // in the runtime's `MissingDependency` net; degrade to the manifest fallback below
                // instead — the safety net must RECOVER, not just kill.
                PlanOutcome::Incomplete {
                    module_id: drifted_node,
                    missing,
                } => {
                    tracing::warn!(
                        module_id = %module_id,
                        drifted_node = %drifted_node,
                        missing = ?missing,
                        "install-plan omits dependencies the manifest declares (hub#672): resolving by manifest"
                    );
                }
            }
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
    // hub#1130: shared across the whole recursion, so a dependency's own nested dependencies land
    // here too — depth-first, so every dependency is pushed only after ITS dependencies already
    // are (the topological order the response promises).
    let mut dragged_in: Vec<String> = Vec::new();
    let mut installed = install_recursive(
        http,
        cloud_base_url,
        cache_root,
        auth,
        runtime,
        module_id.to_string(),
        requested_version.to_string(),
        &mut installing,
        &mut dragged_in,
        on_progress,
        signature_policy,
        updating.map(str::to_string),
    )
    .await?;
    installed.also_installed = dragged_in;
    Ok(installed)
}

/// Guarda en la base del PROPIO hub el paquete que se acaba de verificar e instalar (hub#571).
///
/// Es lo que convierte «el hub sabe qué módulos tiene» en «el hub puede volver a montarlos sin
/// preguntarle a nadie». Se llama SIEMPRE después de `register`, nunca antes: guardar un zip que
/// no llegó a instalarse sería ofrecer en el próximo arranque algo que ya se sabe que no monta.
///
/// **Best-effort a propósito.** Si el guardado falla, el módulo YA está instalado y sirviendo:
/// tumbar la instalación porque no se pudo escribir la red de seguridad cambiaría un TPV que
/// funciona por una copia de respaldo. Queda el WARN, y la consecuencia —si algún día hace falta y
/// no está— la canta `/readyz` (hub#538) en el arranque que la necesite.
async fn remember_package(
    runtime: &erplora_runtime::Runtime,
    module_id: &str,
    version: &str,
    sha256: &str,
    signature: Option<&cloud_client::ModuleSignature>,
    zip: &[u8],
) {
    let signature_json = signature.and_then(|s| serde_json::to_string(s).ok());
    if let Err(e) = erplora_runtime::module_package::save(
        runtime.db(),
        runtime.hub_id(),
        module_id,
        version,
        sha256,
        signature_json.as_deref(),
        zip,
    )
    .await
    {
        tracing::warn!(
            module_id = %module_id,
            error = %e,
            "no se pudo guardar la copia local del módulo (hub#571): este hub no sobrevive a un reinicio sin red"
        );
    }
}

/// [`remember_package`] leyendo el zip **desde el temp file de la descarga** (hub#981): una
/// asignación transitoria DESPUÉS de instalar, en vez de sostener el archivo en RAM durante
/// todo el pipeline. Mismo contrato best-effort: si la lectura falla, queda el WARN y el módulo
/// —ya instalado y sirviendo— no se toca.
async fn remember_package_from_file(
    runtime: &erplora_runtime::Runtime,
    module_id: &str,
    version: &str,
    sha256: &str,
    signature: Option<&cloud_client::ModuleSignature>,
    zip_path: &std::path::Path,
) {
    match std::fs::read(zip_path) {
        Ok(zip) => remember_package(runtime, module_id, version, sha256, signature, &zip).await,
        Err(e) => tracing::warn!(
            module_id = %module_id,
            error = %e,
            "no se pudo releer el zip verificado para la copia local (hub#571): este hub no sobrevive a un reinicio sin red"
        ),
    }
}

/// Repone los módulos que faltan **desde la copia propia del hub**, sin tocar la red (hub#571).
///
/// Es la red de seguridad del arranque: cuando el marketplace no contesta —SaaS caído, DNS torcido,
/// el router del cliente apagado— esto es lo único que separa «se reinició el TPV» de «el negocio
/// no puede cobrar». Devuelve los ids repuestos.
///
/// **Entra por la MISMA puerta que una descarga** (`ModuleStore::install`): SHA256 obligatorio
/// (ADR-0015) y firma ed25519 según `signature_policy` (ADR-0193/0194), sobre los bytes guardados.
/// No hay atajo por ser «local»: si lo hubiera, la copia sería una vía de carga de código sin
/// verificar, y eso es peor que el problema que resuelve.
///
/// Varias pasadas porque `hub_module` no guarda orden topológico y el runtime exige que las
/// `depends_on` estén registradas: se repite mientras la vuelta anterior haya repuesto algo.
pub async fn restore_from_local_packages(
    cache_root: &std::path::Path,
    runtime: &mut erplora_runtime::Runtime,
    missing: &[(String, String)],
    signature_policy: &cloud_client::SignaturePolicy,
) -> Vec<String> {
    let mut pending: Vec<String> = missing.iter().map(|(id, _)| id.clone()).collect();
    let mut restored: Vec<String> = Vec::new();

    while !pending.is_empty() {
        let mut retry: Vec<String> = Vec::new();
        let mut progressed = false;
        for module_id in std::mem::take(&mut pending) {
            match restore_one(cache_root, runtime, &module_id, signature_policy).await {
                Ok(true) => {
                    eprintln!("✓ módulo repuesto de la copia local: {module_id}");
                    restored.push(module_id);
                    progressed = true;
                }
                // Sin copia guardada no hay nada que reintentar: otra pasada daría lo mismo.
                Ok(false) => eprintln!(
                    "✗ {module_id}: sin copia local (se instaló antes de hub#571 o no se pudo guardar)"
                ),
                // Con copia pero sin montar: puede ser el turno (le faltaba una dependencia que
                // otra entrada de esta misma tanda repone), así que vuelve a la cola.
                Err(e) => {
                    eprintln!("✗ reposición local de {module_id}: {e}");
                    retry.push(module_id);
                }
            }
        }
        if !progressed {
            break;
        }
        pending = retry;
    }
    restored
}

/// Repone UN módulo de su copia local. `Ok(false)` = este hub no tiene copia guardada.
pub(crate) async fn restore_one(
    cache_root: &std::path::Path,
    runtime: &mut erplora_runtime::Runtime,
    module_id: &str,
    signature_policy: &cloud_client::SignaturePolicy,
) -> Result<bool, InstallError> {
    let stored = erplora_runtime::module_package::load(runtime.db(), runtime.hub_id(), module_id)
        .await
        .map_err(InstallError::from_runtime)?;
    let Some(stored) = stored else {
        return Ok(false);
    };

    // La firma se guardó tal cual llegó del marketplace. Ilegible ⇒ `None`, que bajo `Enforce`
    // es un rechazo — nunca un pase: una firma que no se puede leer no es una firma válida.
    let signature = stored
        .signature_json
        .as_deref()
        .and_then(|raw| serde_json::from_str::<cloud_client::ModuleSignature>(raw).ok());
    let version = ModuleVersion {
        version: stored.version.clone(),
        changelog: String::new(),
        is_active: true,
        file_size_bytes: 0,
        sha256: Some(stored.sha256.clone()),
        signature: signature.clone(),
        min_erplora_version: None,
    };
    let store = ModuleStore::new(cache_root);
    let dir = acquire(
        &store,
        module_id,
        &version,
        &stored.sha256,
        signature,
        stored.zip,
        signature_policy,
    )?;
    register(runtime, &dir, module_id, None).await?;
    Ok(true)
}

/// Resultado de pedir una actualización de módulo (hub#516).
///
/// `updated == false` **no es un fallo**: es «ya está en la versión que le toca». Es el caso normal
/// de un botón que se puede pulsar siempre, y también el de una versión nueva **en cuarentena**,
/// que sencillamente no se ofrece.
#[derive(Debug, Clone)]
pub struct Updated {
    pub module_id: String,
    pub from: String,
    pub to: String,
    pub updated: bool,
}

/// La versión que el marketplace ofrece hoy para un módulo instalado (hub#516).
///
/// **El mismo resolutor que usa el arranque** (`erplora_runtime::module_update::resolve`): el botón
/// no puede ofrecer algo distinto de lo que la actualización automática haría sola — respeta la
/// cuarentena, respeta el pin de soporte y nunca va hacia atrás. Si el Cloud no contesta, el
/// resultado es «quédate donde estás»: adivinar es peor.
pub async fn resolve_target(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    module_id: &str,
    installed: &str,
    pinned: Option<&str>,
) -> erplora_runtime::module_update::Target {
    resolve_offer(http, cloud_base_url, auth, module_id, installed, pinned)
        .await
        .0
}

/// [`resolve_target`] plus the ERPlora floor of the version it offers (hub#2082).
///
/// The floor is `Some` only for an UPDATE and only when that very version declares one: it is read
/// off the same `versions/` answer the resolver chose from, so a newer version the resolver skipped
/// (quarantine) never lends its floor to the one offered. The pin short-circuits exactly as in
/// [`resolve_target`] — nothing is offered, nothing is asked.
pub async fn resolve_offer(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    module_id: &str,
    installed: &str,
    pinned: Option<&str>,
) -> (erplora_runtime::module_update::Target, Option<String>) {
    use erplora_runtime::module_update::{resolve, Target};

    if let Some(pin) = pinned {
        return (Target::StayPut(pin.to_string()), None);
    }

    let published = versions_as_published(http, cloud_base_url, auth, module_id).await;
    let target = resolve(installed, None, &as_available(&published));
    let floor = if target.is_update() {
        published
            .into_iter()
            .find(|v| v.version == target.version())
            .and_then(|v| v.min_erplora_version)
    } else {
        None
    };
    (target, floor)
}

/// Lo que el marketplace publica hoy para un módulo (`versions/`), tal cual.
///
/// Si el Cloud no contesta se devuelve **vacío**, y eso NO es «no hay versiones»: es «no lo sé».
/// Los dos llamantes lo tratan igual porque la conclusión es la misma —el hub se queda donde está y
/// no se ofrece nada—, y adivinar sería peor que callar.
pub async fn available_versions(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    module_id: &str,
) -> Vec<erplora_runtime::module_update::Available> {
    as_available(&versions_as_published(http, cloud_base_url, auth, module_id).await)
}

/// What the resolver needs from each published version.
fn as_available(published: &[ModuleVersion]) -> Vec<erplora_runtime::module_update::Available> {
    published
        .iter()
        .map(|v| erplora_runtime::module_update::Available {
            version: v.version.clone(),
            is_active: v.is_active,
        })
        .collect()
}

/// The marketplace's `versions/` answer as published, or empty when it could not be read — the
/// same «I don't know» [`available_versions`] documents.
async fn versions_as_published(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    module_id: &str,
) -> Vec<ModuleVersion> {
    let request = CloudClient::new(cloud_base_url).versions(auth, module_id);
    let mut call = http.get(&request.url);
    for (name, value) in &request.headers {
        call = call.header(*name, value);
    }
    match call.send().await {
        Ok(response) => response
            .json::<Vec<ModuleVersion>>()
            .await
            .unwrap_or_default(),
        Err(error) => {
            tracing::warn!(
                module_id = %module_id,
                error = %error,
                "no se pudo leer versions/: se mantiene la versión instalada"
            );
            Vec::new()
        }
    }
}

/// Las versiones entre las que este hub puede elegir para `module_id` (hub#675), de la más nueva a
/// la más vieja. Vacío = no hay nada que elegir.
///
/// **No recibe el `Runtime` a propósito**: lo que necesita del hub —la versión instalada y el pin—
/// se lee antes, se suelta el candado y solo entonces se llama al Cloud. Sostener el guard del
/// runtime durante un round-trip de red retendría a un escritor en cola (una instalación) y, tras
/// él, a `/api/query` y `/api/command` —el TPV— mientras el marketplace tarda en contestar
/// (hub#978). Es el mismo cuidado que ya tiene `list_module_updates`.
///
/// La política la pone `module_update::offer`, **el mismo sitio donde vive la de `resolve`**: que la
/// lista y la resolución automática no puedan discrepar es el punto — si el desplegable tuviera su
/// propia política, sería la puerta por la que entra lo que la otra impide.
pub async fn offered_versions(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    module_id: &str,
    installed: Option<&str>,
    pinned: Option<&str>,
) -> Vec<String> {
    let available = available_versions(http, cloud_base_url, auth, module_id).await;
    erplora_runtime::module_update::offer(installed, pinned, &available)
}

/// La versión que corre este hub, o `None` si el módulo **no está instalado** — que es el caso de
/// instalar por primera vez, no un error.
pub fn installed_version(runtime: &erplora_runtime::Runtime, module_id: &str) -> Option<String> {
    runtime
        .registry()
        .is_installed(module_id)
        .then(|| runtime.registry().module_version(module_id))
}

/// A qué versión debe ir un módulo instalado si se le pide actualizar (hub#516).
///
/// Una versión **explícita** es nuestra (soporte): manda tal cual, sin resolver — es la única forma
/// de bajar a alguien a `sales@3.1` mientras se arregla la `3.2`. Vacío o `latest` es el botón del
/// dueño y el arranque, y ahí decide el **resolutor del arranque**: nunca una versión en cuarentena,
/// nunca hacia atrás, y el pin de soporte gana.
///
/// Devuelve **siempre una versión concreta** (la instalada si no hay nada mejor), porque quien la
/// pide necesita saber a dónde volver si el intento se cae.
pub async fn resolve_update_target(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    runtime: &erplora_runtime::Runtime,
    module_id: &str,
    requested_version: &str,
) -> String {
    let installed = runtime.registry().module_version(module_id);
    match requested_version.trim() {
        "" | "latest" => {
            let pin = support_pin(runtime, module_id).await;
            resolve_target(
                http,
                cloud_base_url,
                auth,
                module_id,
                &installed,
                pin.as_deref(),
            )
            .await
            .version()
            .to_string()
        }
        explicit => explicit.to_string(),
    }
}

/// El pin de soporte de un módulo en este hub, si lo tiene (`hub_module.pinned_version`).
///
/// No es una opción de producto —el dueño no elige— sino la salida de emergencia: dejar a un
/// cliente en `sales@3.1` mientras se arregla la `3.2`, **sin tocar a los demás**.
pub async fn support_pin(runtime: &erplora_runtime::Runtime, module_id: &str) -> Option<String> {
    erplora_runtime::installer::installed_with_pin(runtime.db(), runtime.hub_id())
        .await
        .ok()?
        .into_iter()
        .find(|(id, _, _)| id == module_id)
        .and_then(|(_, _, pin)| pin)
}

/// **Actualiza un módulo ya instalado** (hub#516). La ruta que faltaba: sin ella, publicar la v2 de
/// un módulo con un bug corregido no llegaba a ningún hub que ya tuviera la v1.
///
/// Es el **mismo pipeline verificado** que instalar —`InstallGrant` → SHA256 obligatorio
/// (ADR-0015) → firma ed25519 (ADR-0193/0194) → manifest validado → plan/topo-orden de
/// `depends_on` → migraciones → capacidades → `mark_installed`—, con tres diferencias:
///
/// - **Se exige que el módulo esté instalado.** Actualizar no es una puerta trasera para instalar.
/// - **El módulo no se salta por «ya instalado»**, que es justo lo que impedía que el arreglo
///   llegara.
/// - **Se resuelve a qué versión ir** con el resolutor del arranque, así que el botón hace lo mismo
///   que la actualización automática: nunca una versión en cuarentena, nunca hacia atrás, y el pin
///   de soporte gana.
///
/// Si algo falla, lo que estaba corriendo **sigue corriendo**: la verificación y la validación del
/// manifest ocurren antes de tocar nada, y a partir de ahí el runtime repone la versión anterior
/// (`installer::install`). Lo único que no se deshace es el esquema — las migraciones son aditivas
/// y hacia delante (ADR-0269 §3.4/§7).
#[allow(clippy::too_many_arguments)]
pub async fn update_from_cloud(
    http: &reqwest::Client,
    cloud_base_url: &str,
    cache_root: &std::path::Path,
    auth: &Auth,
    runtime: &mut erplora_runtime::Runtime,
    module_id: &str,
    requested_version: &str,
    on_progress: OnProgress<'_>,
    signature_policy: &cloud_client::SignaturePolicy,
) -> Result<Updated, InstallError> {
    if !runtime.registry().is_installed(module_id) {
        return Err(InstallError::NotInstalled(module_id.to_string()));
    }
    let from = runtime.registry().module_version(module_id);
    let to = resolve_update_target(
        http,
        cloud_base_url,
        auth,
        runtime,
        module_id,
        requested_version,
    )
    .await;

    if to == from {
        // No hay nada más nuevo (o lo que hay está en cuarentena, o el pin dice que aquí se queda).
        // No se descarga nada y no es un error: el botón se puede pulsar siempre.
        return Ok(Updated {
            module_id: module_id.to_string(),
            from: from.clone(),
            to: from,
            updated: false,
        });
    }

    let installed = acquire_and_install(
        http,
        cloud_base_url,
        cache_root,
        auth,
        runtime,
        module_id,
        &to,
        on_progress,
        signature_policy,
        Some(module_id),
    )
    .await?;

    // `to` sale de lo que se instaló DE VERDAD, no de lo que se pidió, y `updated` se deriva de la
    // comparación: si el plan acabó dejando la misma versión (drift raro entre lo que el Cloud
    // planifica y lo que el registry tiene), decir «actualizado 1.0.0 → 1.0.0» sería mentir.
    let to = installed.version;
    Ok(Updated {
        module_id: installed.module_id,
        updated: to != from,
        from,
        to,
    })
}

/// A plan call that failed. Only a SILENT marketplace ends the install here (hub#2251): the
/// manifest fallback would ask the same marketplace again and double the wait in front of
/// «Installing…». Any other failure degrades as before.
fn plan_unreachable(e: reqwest::Error) -> PlanUnavailable {
    if e.is_timeout() {
        PlanUnavailable::Blocked(cloud_unreachable(e))
    } else {
        PlanUnavailable::Degraded(e.to_string())
    }
}

/// Por qué no hay plan ejecutable.
enum PlanUnavailable {
    /// The plan DID arrive and says `blocked` (a domain error), or the marketplace did not answer
    /// in time (hub#2251): the error ends the install, there is no fallback.
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
    updating: Option<&str>,
) -> Result<cloud_client::InstallPlan, PlanUnavailable> {
    let installed: Vec<String> = runtime
        .registry()
        .installed
        .iter()
        .map(|m| m.id.clone())
        // hub#516: el módulo que se actualiza NO va en el set instalado. Si fuera, el Cloud lo
        // daría por `already_satisfied` y el plan volvería vacío — sin su versión nueva y, peor,
        // sin las dependencias que esa versión añade (que son las que pueden estar bloqueadas).
        .filter(|id| Some(id.as_str()) != updating)
        .collect();
    let cloud = CloudClient::new(cloud_base_url);
    let prepared = cloud.install_plan(auth, module_id, requested_version, &installed);

    let mut r = http
        .request(reqwest::Method::POST, &prepared.request.url)
        .json(&prepared.body);
    for (k, v) in &prepared.request.headers {
        r = r.header(*k, v);
    }
    let resp = r.send().await.map_err(plan_unreachable)?;
    let status = resp.status();
    let body = resp.text().await.map_err(plan_unreachable)?;
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
                let p = n
                    .purchase
                    .clone()
                    .unwrap_or(cloud_client::InstallPlanPurchase {
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

/// How executing a Cloud plan ended, when it did not fail outright.
enum PlanOutcome {
    /// The plan closure was executed; carries the requested module ("headline").
    Installed(Installed),
    /// hub#672: the downloaded manifest of `module_id` declares dependencies that are neither
    /// installed nor anywhere in the plan's closure — the plan is incomplete (Cloud graph drift,
    /// e.g. saas#1352 shipped every plan as a single node). Nothing broken was installed: the
    /// caller must fall back to the manifest-nested resolution, which recovers.
    Incomplete {
        module_id: String,
        missing: Vec<String>,
    },
}

/// Executes the plan **in order** (dependencies first). Per node: `download/?version=` → verify
/// the sha256 FROM THE PLAN → `install_from_dir` → `mark_installed`. No `versions/` round-trip.
///
/// The plan is the Cloud's claim; the downloaded manifest is the authoritative truth. Before
/// registering each node, its `depends_on` is checked against what is installed plus the plan's
/// own closure: a plan that omits declared dependencies (hub#672) returns
/// [`PlanOutcome::Incomplete`] so the caller degrades to the manifest fallback instead of dying
/// in the runtime's `MissingDependency` net. That net (installer step 6) stays as the last line
/// for drift the manifest check cannot see (e.g. a plan ordered wrong).
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
    updating: Option<&str>,
) -> Result<PlanOutcome, InstallError> {
    let cloud = CloudClient::new(cloud_base_url);
    let mut headline: Option<Installed> = None;
    // hub#1130: every node OTHER than the requested module that this call actually installs
    // (the loop below `continue`s past whatever was already installed), in plan order — the same
    // topological order the Cloud computed. Reported back so the caller can say what got dragged
    // in instead of staying silent about it.
    let mut dragged_in: Vec<String> = Vec::new();

    // The plan's own closure: a dependency listed anywhere in the plan will be installed by it
    // (dependencies-first order), so only deps outside this set make the plan incomplete.
    let planned: std::collections::HashSet<&str> =
        plan.plan.iter().map(|n| n.module_id.as_str()).collect();

    for node in &plan.plan {
        // Idempotencia / drift: el plan excluye lo ya instalado, pero si el registry lo tiene
        // igualmente (instalación concurrente, set desfasado) no se reinstala.
        //
        // La excepción es el módulo que se está ACTUALIZANDO (hub#516): saltarlo por «ya
        // instalado» era exactamente lo que dejaba un bug de módulo sin arreglo posible.
        if runtime.registry().is_installed(&node.module_id)
            && Some(node.module_id.as_str()) != updating
        {
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
        let (zip_file, downloaded_sha) =
            download_to_temp_file(http, &dl_req, cache_root, &node.module_id).await?;

        on_progress(&node.module_id, "verifying");
        // ADR-0015, mismo contrato que siempre: el SHA calculado sobre la marcha debe casar con
        // el del plan ANTES de tocar nada. Un mismatch suelta `zip_file` → el temp se borra solo.
        cloud_client::integrity::verify_sha256_hex(&downloaded_sha, sha)
            .map_err(|e| InstallError::Source(e.into()))?;
        let store = ModuleStore::new(cache_root);
        let version = ModuleVersion {
            version: node.version.clone(),
            changelog: String::new(),
            is_active: true,
            file_size_bytes: 0,
            sha256: Some(sha.to_string()),
            signature: signature.clone(),
            min_erplora_version: None,
        };
        let dir = acquire_from_file(
            &store,
            &node.module_id,
            &version,
            sha,
            signature.clone(),
            zip_file.path(),
            signature_policy,
        )?;

        // hub#672: check the REAL manifest's `depends_on` against the plan's closure BEFORE
        // registering. A dependency that is neither installed nor planned means the Cloud's graph
        // drifted (e.g. saas#1352: every plan came back single-node): bail out so the caller
        // falls back to manifest resolution. Registering would only die in `MissingDependency`.
        let missing: Vec<String> = runtime
            .missing_dependencies(&dir)
            .map_err(InstallError::from_runtime)?
            .into_iter()
            .filter(|dep| !planned.contains(dep.as_str()))
            .collect();
        if !missing.is_empty() {
            return Ok(PlanOutcome::Incomplete {
                module_id: node.module_id.clone(),
                missing,
            });
        }

        on_progress(&node.module_id, "installing");
        let installed_id = register(runtime, &dir, &node.module_id, updating).await?;

        // hub#571: la copia propia del hub, para el arranque en el que el marketplace no conteste.
        remember_package_from_file(
            runtime,
            &node.module_id,
            &node.version,
            sha,
            signature.as_ref(),
            zip_file.path(),
        )
        .await;

        mark_installed(http, &cloud, auth, &node.module_id, &node.version).await;

        // hub#1130: this node just got installed by THIS call. If it is not the headline, it is
        // something the caller did not ask for by name — record it so the response can say so.
        if node.module_id != module_id {
            dragged_in.push(installed_id.clone());
        }

        let installed = Installed {
            module_id: installed_id,
            version: node.version.clone(),
            dir,
            // Filled in below once the whole plan finished executing: at this point in the loop
            // there could still be more dependents after the headline (the plan is not required to
            // put `requested` last), so the final list is only complete once the loop is done.
            also_installed: Vec::new(),
        };
        if node.module_id == module_id {
            headline = Some(installed);
        }
    }

    // The requested module may be absent from the plan because it was ALREADY installed
    // (`already_satisfied`): reinstalling adds nothing, so report what is there.
    match headline {
        Some(mut i) => {
            i.also_installed = dragged_in;
            Ok(PlanOutcome::Installed(i))
        }
        None if runtime.registry().is_installed(module_id) => {
            Ok(PlanOutcome::Installed(Installed {
                module_id: module_id.to_string(),
                version: runtime.registry().module_version(module_id),
                dir: cache_root.to_path_buf(),
                also_installed: dragged_in,
            }))
        }
        // Empty plan and the module is not installed: the Cloud does not consider it installable here.
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
    // hub#1130: ids installed anywhere in this recursion, in the order they finished installing
    // (depth-first ⇒ topological). Shared by mutable reference across every frame, including the
    // outermost (the requested module itself is never pushed — only its dependencies are).
    dragged_in: &'a mut Vec<String>,
    on_progress: OnProgress<'a>,
    signature_policy: &'a cloud_client::SignaturePolicy,
    updating: Option<String>,
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

        // (2) Descargar el ZIP binario **en streaming a disco** (hub#981), con el SHA256
        //     calculado sobre la marcha: el archivo no se bufferiza en RAM.
        on_progress(&module_id, "downloading");
        let dl_req = cloud.download(auth, &module_id, &version.version);
        let (zip_file, downloaded_sha) =
            download_to_temp_file(http, &dl_req, cache_root, &module_id).await?;

        // (3) Verificar SHA256 (ADR-0015, ANTES de tocar nada; un fallo suelta el temp file, que
        //     se borra solo) + firma ed25519 (hub#239, DEFAULT deny según policy) + descomprimir
        //     de forma segura + cachear.
        on_progress(&module_id, "verifying");
        cloud_client::integrity::verify_sha256_hex(&downloaded_sha, &sha)
            .map_err(|e| InstallError::Source(e.into()))?;
        let store = ModuleStore::new(cache_root);
        let dir = acquire_from_file(
            &store,
            &module_id,
            &version,
            &sha,
            version.signature.clone(),
            zip_file.path(),
            signature_policy,
        )?;

        // (4) INSTALACIÓN ANIDADA: instala las dependencias declaradas que falten ANTES del módulo.
        //     El runtime exige que las deps estén registradas al instalar (installer.rs::install);
        //     aquí se satisface ese contrato descargándolas del Cloud en orden de profundidad.
        let missing = runtime
            .missing_dependencies(&dir)
            .map_err(InstallError::from_runtime)?;
        installing.insert(module_id.clone());
        for dep in missing {
            // Ya en la cadena en curso (ciclo) o ya instalada por otra rama (dep en diamante): saltar.
            if installing.contains(&dep) || runtime.registry().is_installed(&dep) {
                continue;
            }
            let installed_dep = install_recursive(
                http,
                cloud_base_url,
                cache_root,
                auth,
                &mut *runtime,
                dep,
                "latest".to_string(),
                &mut *installing,
                &mut *dragged_in,
                on_progress,
                signature_policy,
                // Una dependencia nunca es «el módulo que se actualiza»: se instala si falta.
                None,
            )
            .await?;
            // hub#1130: record it AFTER it (and everything IT dragged in) is fully installed —
            // depth-first push order is topological order.
            dragged_in.push(installed_dep.module_id);
        }

        // (5) Instalar el módulo (migra, registra, activa) — ya con sus deps presentes.
        on_progress(&module_id, "installing");
        let installed_id = register(runtime, &dir, &module_id, updating.as_deref()).await?;

        // (5bis) hub#571: guardar la copia propia del hub, para el arranque en el que el
        //        marketplace no conteste. Después de instalar, nunca antes.
        remember_package_from_file(
            runtime,
            &module_id,
            &version.version,
            &sha,
            version.signature.as_ref(),
            zip_file.path(),
        )
        .await;

        // (6) Registrar la instalación en el Cloud (best-effort: no aborta si falla).
        mark_installed(http, &cloud, auth, &module_id, &version.version).await;

        Ok(Installed {
            module_id: installed_id,
            version: version.version,
            dir,
            // hub#1130: this frame's own dependencies are already in the SHARED `dragged_in` by
            // now; the caller (outermost `acquire_and_install`) reads that accumulator directly
            // once the whole recursion finishes, so this field is left empty here on purpose —
            // filling it in per-frame would just be discarded (and double-count on the way back up).
            also_installed: Vec::new(),
        })
    })
}

/// Registra en el runtime el paquete ya descargado y verificado de `dir`.
///
/// Entra por la puerta de **update** cuando este es el módulo que se está actualizando (hub#516) y
/// por la de **install** en cualquier otro caso. Las dos acaban en `installer::install` —así que la
/// versión anterior vuelve si el intento falla—; la diferencia es el contrato: `update_from_dir`
/// **se niega** si el módulo no está instalado, de modo que una actualización nunca puede acabar
/// instalando algo que este hub no tenía.
pub(crate) async fn register(
    runtime: &mut erplora_runtime::Runtime,
    dir: &std::path::Path,
    module_id: &str,
    updating: Option<&str>,
) -> Result<String, InstallError> {
    let is_update = updating == Some(module_id) && runtime.registry().is_installed(module_id);
    let result = if is_update {
        runtime.update_from_dir(dir).await.map(|u| u.module_id)
    } else {
        runtime.install_from_dir(dir).await
    };
    result.map_err(InstallError::from_runtime)
}

#[cfg(test)]
mod register_tests {
    use super::*;

    /// hub#1620 — `register` is also reached WITHOUT the `missing_dependencies` read that catches
    /// the floor first on a fresh install: restoring the local copy (`restore_one`) and the
    /// reconciler go straight here. It has to keep the same stable fact, not flatten it into
    /// `install_runtime_failed`.
    #[tokio::test]
    async fn register_keeps_the_newer_hub_refusal_as_its_own_code() {
        let dir = std::env::temp_dir().join(format!(
            "erplora-hub1620-register-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("temp dir");
        std::fs::write(
            dir.join("module.json"),
            r#"{"id":"whatsapp_inbox","name":"whatsapp_inbox","version":"1.0.0",
                "compatibility":{"min_erplora_version":"999.0.0"}}"#,
        )
        .expect("manifest");

        let mut rt =
            erplora_runtime::Runtime::new(Box::new(erplora_db::testutil::fresh_db().await));
        let err = register(&mut rt, &dir, "whatsapp_inbox", None)
            .await
            .expect_err("a module that needs a newer hub is refused");

        assert_eq!(err.code(), "core_version_too_old", "{err:?}");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
