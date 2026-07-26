//! erplora-installer — pipeline de instalación de un módulo de principio a fin
//! (ARQUITECTURA.md §2.2, §4).
//!
//! Este crate es el **pegamento** que encadena las piezas ya implementadas en
//! `erplora-cloud-client`, `erplora-source` y `erplora-runtime` para convertir un
//! `module_id`@`version` en un módulo realmente instalado y activo:
//!
//!  1. **Cloud** — `CloudClient::request_install` construye la petición (URL + cabeceras
//!     de `Auth`) al marketplace del Portal.
//!  2. **Transporte** — `Transport::get_text` ejecuta esa petición y devuelve el JSON del
//!     grant (URL S3 firmada + sha256 esperado).
//!  3. **Grant** — `InstallGrant::parse` deserializa la respuesta del Portal.
//!  4. **Source** — `ModuleStore::install` descarga el zip (vía el mismo `Transport`, que
//!     es a la vez `Fetcher`), **verifica el SHA256**, lo descomprime de forma segura y lo
//!     cachea; idempotente por cache.
//!  5. **Runtime** — `Runtime::install_from_dir` valida el manifest, migra, registra
//!     capacidades y deja el módulo activo.
//!
//! El I/O de red queda **inyectable** detrás del trait [`Transport`]: el binario real del
//! server/Tauri inyecta una implementación con `reqwest`/`ureq`; los tests inyectan un mock
//! sin red. Así un único transporte sirve para pedir el grant (`get_text`) y para descargar
//! el zip (`fetch`, heredado de [`source::Fetcher`]).

use std::path::PathBuf;

use cloud_client::{Auth, CloudClient, InstallGrant, PreparedRequest};
use erplora_runtime::Runtime;
use source::{Fetcher, ModuleStore, SourceError};

pub use cloud_client;
pub use erplora_runtime;
pub use source;

/// Transporte HTTP inyectable usado por el pipeline. Un único transporte sirve para:
///  - (a) pedir el **grant** JSON al Cloud (`get_text`, con las cabeceras de `Auth`), y
///  - (b) **descargar el zip** binario del módulo (`fetch`, heredado de [`source::Fetcher`]).
///
/// El llamador real implementa esto con `reqwest`/`ureq`; los tests con un mock sin red.
pub trait Transport: Fetcher {
    /// Ejecuta una petición GET (texto) con cabeceras dadas y devuelve el cuerpo como `String`.
    fn get_text(&self, url: &str, headers: &[(&str, String)]) -> Result<String, InstallError>;
}

/// Resultado de una instalación correcta.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstallOutcome {
    /// Id del módulo instalado (confirmado por el runtime).
    pub module_id: String,
    /// Versión instalada.
    pub version: String,
    /// Carpeta extraída en el cache local desde la que se instaló.
    pub path: PathBuf,
    /// `true` si el artefacto ya estaba en cache (no se volvió a descargar).
    pub from_cache: bool,
}

/// Errores del pipeline de instalación.
#[derive(Debug, thiserror::Error)]
pub enum InstallError {
    /// Fallo hablando con el Cloud Portal (capa de transporte/HTTP al pedir el grant).
    #[error("cloud: {0}")]
    Cloud(String),
    /// Fallo de transporte genérico (descarga / red).
    #[error("transporte: {0}")]
    Transport(String),
    /// El JSON del grant del Portal no se pudo parsear.
    #[error("grant inválido: {0}")]
    Grant(#[from] serde_json::Error),
    /// Fallo en la adquisición del artefacto (descarga, integridad SHA256, descompresión).
    #[error(transparent)]
    Source(#[from] SourceError),
    /// Fallo del runtime al instalar desde la carpeta (manifest, migraciones, dependencias).
    /// `RuntimeError` no es `Clone`, se conserva como texto.
    #[error("runtime: {0}")]
    Runtime(String),
}

/// Orquestador del pipeline de instalación. Une el cliente del Cloud con el cache de módulos
/// y delega el ciclo de vida final al runtime.
pub struct Installer<'a> {
    cloud: &'a CloudClient,
    store: &'a ModuleStore,
}

impl<'a> Installer<'a> {
    /// Construye el orquestador sobre un `CloudClient` y un `ModuleStore` ya configurados.
    pub fn new(cloud: &'a CloudClient, store: &'a ModuleStore) -> Self {
        Self { cloud, store }
    }

    /// Instala `module_id`@`version` de principio a fin.
    ///
    /// Encadena: `request_install` (Cloud) → `get_text` (Transport) → `InstallGrant::parse`
    /// → `ModuleStore::install` (descarga + verifica SHA256 + descomprime, idempotente por
    /// cache) → `Runtime::install_from_dir` (migra + registra + activa).
    pub async fn install(
        &self,
        transport: &dyn Transport,
        auth: &Auth,
        runtime: &mut Runtime,
        module_id: &str,
        version: &str,
    ) -> Result<InstallOutcome, InstallError> {
        // (1) Cloud: construir la petición de instalación (URL + cabeceras de Auth).
        // NOTA: `request_install` está DEPRECADO (endpoint ficticio). El flujo real vive ahora
        // en `erplora-server` (versions/ → download/ → mark_installed/). Este crate orquestador
        // se migrará por separado; se silencia el warning para mantener el build sin avisos.
        #[allow(deprecated)]
        let req: PreparedRequest = self.cloud.request_install(auth, module_id, version);

        // (2) Transporte: pedir el grant JSON al Portal.
        let body = transport
            .get_text(&req.url, &req.headers)
            .map_err(|e| InstallError::Cloud(e.to_string()))?;

        // (3) Grant: parsear la respuesta del Portal.
        let grant = InstallGrant::parse(&body)?;

        // ¿Estaba ya en cache? (determina `from_cache` y si hubo descarga).
        let from_cache = self.store.is_cached(&grant.module_id, &grant.version);

        // (4) Source: descargar (si hace falta) + verificar SHA256 + descomprimir + cachear.
        let path = self.store.install(transport, &grant)?;

        // (5) Runtime: instalar desde la carpeta extraída (migra, registra, activa).
        let installed_id = runtime
            .install_from_dir(&path)
            .await
            .map_err(|e| InstallError::Runtime(e.to_string()))?;

        Ok(InstallOutcome {
            module_id: installed_id,
            version: grant.version,
            path,
            from_cache,
        })
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Transporte HTTP real (feature `reqwest-transport`)
// ─────────────────────────────────────────────────────────────────────────────
//
// Implementación concreta de [`Transport`] (y por tanto de [`source::Fetcher`]) sobre un
// cliente HTTP de verdad (`reqwest::blocking`, rustls — sin OpenSSL del sistema).
//
// Un único `ReqwestTransport` sirve para las DOS llamadas del pipeline:
//  - `get_text(url, headers)` → pide el grant JSON al Cloud Portal (GET con las cabeceras
//    de `Auth`: `Authorization: Bearer …` + `X-Hub-Id`, etc.).
//  - `fetch(url)` (heredado de `source::Fetcher`) → descarga el zip binario desde S3.
//
// Esta es la pieza que inyecta el **binario de producción** (`erplora-server`): construye el
// transporte una vez y se lo pasa a `Installer::install`.
// Los tests siguen usando `MockTransport` en memoria, de modo que el build por defecto del
// workspace NO arrastra reqwest (queda detrás de la feature `reqwest-transport`). El diseño
// es **blocking** a propósito: encaja con los traits síncronos sin requerir tokio.
#[cfg(feature = "reqwest-transport")]
mod reqwest_transport {
    use super::{Fetcher, InstallError, Transport};
    use source::Result as SourceResult;

    /// [`Transport`] real sobre `reqwest::blocking::Client`.
    ///
    /// Reusa un único `Client` (pool de conexiones + TLS negociado) para grant y descarga.
    #[derive(Debug, Clone)]
    pub struct ReqwestTransport {
        client: reqwest::blocking::Client,
    }

    impl ReqwestTransport {
        /// Crea un transporte con un cliente blocking por defecto.
        ///
        /// Devuelve `InstallError::Transport` si reqwest no puede inicializar TLS.
        pub fn new() -> Result<Self, InstallError> {
            let client = reqwest::blocking::Client::builder()
                .build()
                .map_err(|e| InstallError::Transport(e.to_string()))?;
            Ok(Self { client })
        }

        /// Construye el transporte sobre un `Client` ya configurado (timeouts, proxy, etc.).
        pub fn with_client(client: reqwest::blocking::Client) -> Self {
            Self { client }
        }
    }

    impl Fetcher for ReqwestTransport {
        fn fetch(&self, url: &str) -> SourceResult<Vec<u8>> {
            let resp = self
                .client
                .get(url)
                .send()
                .map_err(|e| source::SourceError::Fetch(e.to_string()))?;
            let resp = resp
                .error_for_status()
                .map_err(|e| source::SourceError::Fetch(e.to_string()))?;
            let bytes = resp
                .bytes()
                .map_err(|e| source::SourceError::Fetch(e.to_string()))?;
            Ok(bytes.to_vec())
        }
    }

    impl Transport for ReqwestTransport {
        fn get_text(&self, url: &str, headers: &[(&str, String)]) -> Result<String, InstallError> {
            let mut req = self.client.get(url);
            for (k, v) in headers {
                req = req.header(*k, v);
            }
            let resp = req
                .send()
                .map_err(|e| InstallError::Transport(e.to_string()))?;
            let resp = resp
                .error_for_status()
                .map_err(|e| InstallError::Transport(e.to_string()))?;
            resp.text().map_err(|e| InstallError::Transport(e.to_string()))
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        /// Solo CONSTRUYE el transporte (sin red): valida que la integración compila y que
        /// implementa los dos traits. Las pruebas con red van `#[ignore]`.
        #[test]
        fn builds_transport_without_network() {
            let t = ReqwestTransport::new().expect("debe construir el cliente blocking");
            // Asegura que sirve como `&dyn Transport` (y, vía supertrait, como Fetcher).
            let _dyn: &dyn Transport = &t;
        }
    }
}

#[cfg(feature = "reqwest-transport")]
pub use reqwest_transport::ReqwestTransport;

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::io::Write;
    use std::path::Path;

    use cloud_client::integrity::sha256_hex;
    use erplora_db::testutil::fresh_db;
    use erplora_runtime::{ModuleStatus, RequestContext};
    use source::Result as SourceResult;

    /// Carpeta del fixture real del runtime (su `module.json` + SQL).
    fn fixture_dir() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../runtime/tests/fixture_inventory")
    }

    /// Construye un zip en memoria con todos los ficheros del fixture del runtime,
    /// preservando rutas relativas (module.json, migrations/, queries/, commands/).
    fn fixture_zip() -> Vec<u8> {
        let root = fixture_dir();
        let mut files: Vec<(String, Vec<u8>)> = Vec::new();
        collect_files(&root, &root, &mut files);
        // Asegura que el manifest está presente (contrato de source/runtime).
        assert!(files.iter().any(|(n, _)| n == "module.json"), "fixture sin module.json");

        let mut buf = Vec::new();
        {
            let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
            let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
            for (name, content) in &files {
                w.start_file(name, opts).unwrap();
                w.write_all(content).unwrap();
            }
            w.finish().unwrap();
        }
        buf
    }

    fn collect_files(root: &Path, dir: &Path, out: &mut Vec<(String, Vec<u8>)>) {
        for entry in std::fs::read_dir(dir).unwrap() {
            let entry = entry.unwrap();
            let path = entry.path();
            if path.is_dir() {
                collect_files(root, &path, out);
            } else {
                let rel = path.strip_prefix(root).unwrap();
                // Normaliza separadores a `/` para el zip.
                let name = rel.to_string_lossy().replace('\\', "/");
                out.push((name, std::fs::read(&path).unwrap()));
            }
        }
    }

    /// Transporte mock: sirve el grant por `get_text` y el zip por `fetch`. Cuenta llamadas.
    struct MockTransport {
        zip: Vec<u8>,
        grant_calls: Cell<usize>,
        fetch_calls: Cell<usize>,
        /// sha a anunciar en el grant (puede no coincidir con el zip para forzar error).
        announced_sha: String,
    }

    impl MockTransport {
        fn new(zip: Vec<u8>) -> Self {
            let announced_sha = sha256_hex(&zip);
            Self {
                announced_sha,
                zip,
                grant_calls: Cell::new(0),
                fetch_calls: Cell::new(0),
            }
        }

        /// Variante con un sha del grant que NO coincide con el zip (fuerza Integrity).
        fn with_bad_announced_sha(mut self) -> Self {
            self.announced_sha = sha256_hex(b"otros-bytes-distintos");
            self
        }
    }

    impl Fetcher for MockTransport {
        fn fetch(&self, _url: &str) -> SourceResult<Vec<u8>> {
            self.fetch_calls.set(self.fetch_calls.get() + 1);
            Ok(self.zip.clone())
        }
    }

    impl Transport for MockTransport {
        fn get_text(&self, _url: &str, _headers: &[(&str, String)]) -> Result<String, InstallError> {
            self.grant_calls.set(self.grant_calls.get() + 1);
            // download_url ficticio en memoria; el sha es el anunciado.
            Ok(format!(
                r#"{{"module_id":"inventory","version":"1.0.0","download_url":"mem://inventory","sha256":"{}"}}"#,
                self.announced_sha
            ))
        }
    }

    fn auth() -> Auth {
        Auth::UserJwt { hub_id: "hub-1".into(), access: "tok".into() }
    }

    fn ctx() -> RequestContext {
        RequestContext::new("hub-1", "user-1", ["*".to_string()])
    }

    async fn runtime() -> Runtime {
        let db: Box<dyn erplora_db::DatabaseAdapter> =
            Box::new(fresh_db().await);
        Runtime::new(db)
    }

    #[tokio::test]
    async fn install_e2e_module_active_and_query_works() {
        let tmp = tempfile::tempdir().unwrap();
        let cloud = CloudClient::new("https://erplora.com");
        let store = ModuleStore::new(tmp.path());
        let installer = Installer::new(&cloud, &store);
        let transport = MockTransport::new(fixture_zip());
        let mut rt = runtime().await;

        let outcome = installer
            .install(&transport, &auth(), &mut rt, "inventory", "1.0.0")
            .await
            .unwrap();

        assert_eq!(outcome.module_id, "inventory");
        assert_eq!(outcome.version, "1.0.0");
        assert!(!outcome.from_cache);
        assert!(outcome.path.join("module.json").is_file());

        // El runtime lo lista activo.
        let mods = rt.modules();
        assert_eq!(mods.len(), 1);
        assert_eq!(mods[0].id, "inventory");
        assert_eq!(mods[0].status, ModuleStatus::Active);

        // Una query del módulo funciona (tabla recién migrada → vacía).
        let rows = rt
            .execute_query("inventory.products.list", &erplora_db::Params::new(), &ctx())
            .await
            .unwrap();
        assert_eq!(rows.len(), 0);

        // Una sola llamada al Cloud y una sola descarga.
        assert_eq!(transport.grant_calls.get(), 1);
        assert_eq!(transport.fetch_calls.get(), 1);
    }

    #[tokio::test]
    async fn second_install_uses_cache_no_refetch() {
        let tmp = tempfile::tempdir().unwrap();
        let cloud = CloudClient::new("https://erplora.com");
        let store = ModuleStore::new(tmp.path());
        let installer = Installer::new(&cloud, &store);
        let transport = MockTransport::new(fixture_zip());

        // Primera instalación: descarga real.
        let mut rt1 = runtime().await;
        let first = installer.install(&transport, &auth(), &mut rt1, "inventory", "1.0.0").await.unwrap();
        assert!(!first.from_cache);
        assert_eq!(transport.grant_calls.get(), 1);
        assert_eq!(transport.fetch_calls.get(), 1);

        // Segunda instalación (mismo cache): hit, sin volver a descargar el zip.
        // (get_text aún se llama: el grant trae el sha que decide el cache; fetch NO.)
        let mut rt2 = runtime().await;
        let second = installer.install(&transport, &auth(), &mut rt2, "inventory", "1.0.0").await.unwrap();
        assert!(second.from_cache);
        assert_eq!(transport.fetch_calls.get(), 1, "no debe re-descargar el zip");
    }

    #[tokio::test]
    async fn bad_sha_fails_and_runtime_stays_empty() {
        let tmp = tempfile::tempdir().unwrap();
        let cloud = CloudClient::new("https://erplora.com");
        let store = ModuleStore::new(tmp.path());
        let installer = Installer::new(&cloud, &store);
        let transport = MockTransport::new(fixture_zip()).with_bad_announced_sha();
        let mut rt = runtime().await;

        let err = installer
            .install(&transport, &auth(), &mut rt, "inventory", "1.0.0")
            .await
            .unwrap_err();

        // El fallo de integridad sube como Source(Integrity).
        assert!(
            matches!(err, InstallError::Source(SourceError::Integrity(_))),
            "esperado error de integridad, fue: {err:?}"
        );
        // El runtime no quedó con el módulo y el cache no quedó poblado.
        assert!(rt.modules().is_empty());
        assert!(!store.is_cached("inventory", "1.0.0"));
    }
}
