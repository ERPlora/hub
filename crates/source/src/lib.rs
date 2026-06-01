//! erplora-source — Adquisición de artefactos de módulos (ARQUITECTURA.md §2.2, §4).
//!
//! Dado un [`InstallGrant`] del Cloud Portal (URL de descarga + sha256 esperado), este crate:
//!  1. descarga el `module.zip` (vía un [`Fetcher`] inyectable → testeable sin red),
//!  2. **verifica el SHA256** (reusa `erplora-cloud-client`),
//!  3. lo **descomprime** de forma segura (rechaza zip-slip) en un cache local
//!     (`root/<module_id>/<version>/`),
//!
//! dejándolo listo para que `erplora-runtime::install_from_dir` lo instale desde carpeta.
//!
//! No incluye un cliente HTTP: el llamador inyecta la implementación real (reqwest/ureq).

use std::fs;
use std::io;
use std::path::{Component, Path, PathBuf};

pub use cloud_client::{InstallGrant, IntegrityError};

/// Errores de adquisición de artefactos.
#[derive(Debug, thiserror::Error)]
pub enum SourceError {
    /// La descarga (responsabilidad del `Fetcher` inyectado) falló.
    #[error("fallo de descarga: {0}")]
    Fetch(String),
    /// El SHA256 del zip no coincide con el esperado en el grant.
    #[error(transparent)]
    Integrity(#[from] IntegrityError),
    /// El zip está corrupto o una entrada intenta escapar del destino (zip-slip).
    #[error("zip inválido: {0}")]
    Zip(String),
    /// Error de I/O al escribir el cache.
    #[error("io: {0}")]
    Io(#[from] io::Error),
    /// El zip descomprimido no contiene `module.json` en su raíz.
    #[error("falta module.json en el módulo")]
    MissingManifest,
}

pub type Result<T> = std::result::Result<T, SourceError>;

/// Abstracción de descarga HTTP. El llamador inyecta la implementación real (reqwest/ureq);
/// así los tests no usan red.
pub trait Fetcher {
    /// Descarga `url` y devuelve sus bytes crudos.
    fn fetch(&self, url: &str) -> Result<Vec<u8>>;
}

/// Cache local de módulos descomprimidos. Layout: `root/<module_id>/<version>/`.
#[derive(Debug, Clone)]
pub struct ModuleStore {
    root: PathBuf,
}

impl ModuleStore {
    /// Crea un store sobre `root` (el directorio se crea perezosamente al instalar).
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// Directorio destino (descomprimido) para `module_id`@`version`.
    pub fn path_for(&self, module_id: &str, version: &str) -> PathBuf {
        self.root.join(module_id).join(version)
    }

    /// `true` si el módulo ya está descomprimido en cache (existe su `module.json`).
    pub fn is_cached(&self, module_id: &str, version: &str) -> bool {
        self.path_for(module_id, version).join("module.json").is_file()
    }

    /// Adquiere e instala el módulo del `grant` en el cache; devuelve el directorio listo
    /// para `install_from_dir`.
    ///
    /// Si ya está cacheado, devuelve el path sin descargar. Si no: descarga → verifica SHA256
    /// → descomprime → valida que existe `module.json`. Ante cualquier fallo limpia el dir
    /// parcial para no dejar basura.
    pub fn install(&self, fetcher: &dyn Fetcher, grant: &InstallGrant) -> Result<PathBuf> {
        let dest = self.path_for(&grant.module_id, &grant.version);
        if self.is_cached(&grant.module_id, &grant.version) {
            return Ok(dest);
        }

        let bytes = fetcher.fetch(&grant.download_url)?;
        grant.verify(&bytes)?;

        // Descomprime a un dir temporal hermano; promoción atómica al final.
        let staging = self.staging_dir(&grant.module_id, &grant.version);
        // Limpia restos de un intento previo.
        let _ = fs::remove_dir_all(&staging);
        if let Err(e) = self.unzip_into(&bytes, &staging) {
            let _ = fs::remove_dir_all(&staging);
            return Err(e);
        }

        if !staging.join("module.json").is_file() {
            let _ = fs::remove_dir_all(&staging);
            return Err(SourceError::MissingManifest);
        }

        // Promoción: deja `dest` como el staging validado.
        let _ = fs::remove_dir_all(&dest);
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }
        if let Err(e) = fs::rename(&staging, &dest) {
            let _ = fs::remove_dir_all(&staging);
            return Err(SourceError::Io(e));
        }
        Ok(dest)
    }

    /// Borra del cache el módulo `module_id`@`version` (para uninstall). No falla si no existe.
    pub fn remove(&self, module_id: &str, version: &str) -> Result<()> {
        let dir = self.path_for(module_id, version);
        match fs::remove_dir_all(&dir) {
            Ok(()) => Ok(()),
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
            Err(e) => Err(SourceError::Io(e)),
        }
    }

    fn staging_dir(&self, module_id: &str, version: &str) -> PathBuf {
        self.root.join(module_id).join(format!(".{version}.tmp"))
    }

    /// Descomprime `bytes` (un zip) bajo `dest`, rechazando entradas que escapen del destino.
    fn unzip_into(&self, bytes: &[u8], dest: &Path) -> Result<()> {
        let reader = io::Cursor::new(bytes);
        let mut archive =
            zip::ZipArchive::new(reader).map_err(|e| SourceError::Zip(e.to_string()))?;

        fs::create_dir_all(dest)?;
        // Canonicaliza el destino para comparar de forma fiable.
        let dest_canon = fs::canonicalize(dest)?;

        for i in 0..archive.len() {
            let mut entry = archive.by_index(i).map_err(|e| SourceError::Zip(e.to_string()))?;
            let raw = entry
                .enclosed_name()
                .ok_or_else(|| SourceError::Zip(format!("nombre de entrada inseguro: {}", entry.name())))?;
            // Defensa adicional contra zip-slip: rechaza cualquier componente `..` o raíz.
            if raw.components().any(|c| matches!(c, Component::ParentDir | Component::RootDir | Component::Prefix(_))) {
                return Err(SourceError::Zip(format!("ruta que escapa del destino: {}", entry.name())));
            }
            let out = dest_canon.join(&raw);
            if !out.starts_with(&dest_canon) {
                return Err(SourceError::Zip(format!("ruta que escapa del destino: {}", entry.name())));
            }

            if entry.is_dir() {
                fs::create_dir_all(&out)?;
            } else {
                if let Some(parent) = out.parent() {
                    fs::create_dir_all(parent)?;
                }
                let mut f = fs::File::create(&out)?;
                io::copy(&mut entry, &mut f)?;
            }
        }
        Ok(())
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Transporte HTTP real (feature `reqwest-transport`)
// ─────────────────────────────────────────────────────────────────────────────
//
// Implementación concreta de [`Fetcher`] que descarga el zip del módulo desde la URL
// S3 firmada del grant usando un cliente HTTP de verdad (`reqwest::blocking`, sobre
// rustls — sin OpenSSL del sistema).
//
// Esta es la pieza que inyectan los **binarios de producción** (`erplora-server` y, en
// el futuro, `apps/tauri`): en runtime construyen un `ReqwestFetcher` y se lo pasan a
// `ModuleStore::install`. Los tests del crate siguen usando el `MockFetcher` en memoria,
// así que el build por defecto del workspace NO arrastra reqwest (queda detrás de la
// feature `reqwest-transport`). El diseño es **síncrono/blocking** a propósito: encaja con
// el `trait Fetcher` (que no es `async`) sin necesidad de un runtime tokio.
#[cfg(feature = "reqwest-transport")]
mod reqwest_transport {
    use super::{Fetcher, Result, SourceError};

    /// [`Fetcher`] real sobre `reqwest::blocking::Client`.
    ///
    /// Reusa internamente un único `Client` (pool de conexiones + TLS ya negociado),
    /// por lo que conviene construirlo una vez y compartirlo.
    #[derive(Debug, Clone)]
    pub struct ReqwestFetcher {
        client: reqwest::blocking::Client,
    }

    impl ReqwestFetcher {
        /// Crea un fetcher con un cliente blocking por defecto.
        ///
        /// Falla solo si reqwest no puede inicializar su backend TLS (extremadamente raro).
        pub fn new() -> Result<Self> {
            let client = reqwest::blocking::Client::builder()
                .build()
                .map_err(|e| SourceError::Fetch(e.to_string()))?;
            Ok(Self { client })
        }

        /// Construye el fetcher sobre un `Client` ya configurado por el llamador
        /// (timeouts, proxy, user-agent, etc.).
        pub fn with_client(client: reqwest::blocking::Client) -> Self {
            Self { client }
        }
    }

    impl Fetcher for ReqwestFetcher {
        fn fetch(&self, url: &str) -> Result<Vec<u8>> {
            let resp = self
                .client
                .get(url)
                .send()
                .map_err(|e| SourceError::Fetch(e.to_string()))?;
            let resp = resp
                .error_for_status()
                .map_err(|e| SourceError::Fetch(e.to_string()))?;
            let bytes = resp.bytes().map_err(|e| SourceError::Fetch(e.to_string()))?;
            Ok(bytes.to_vec())
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        /// Solo CONSTRUYE el cliente (sin red): valida que la integración compila y que el
        /// backend TLS arranca. Los tests con red real van marcados `#[ignore]` abajo.
        #[test]
        fn builds_fetcher_without_network() {
            let f = ReqwestFetcher::new().expect("debe poder construir el cliente blocking");
            // Lo movemos a `&dyn Fetcher` para asegurar que el trait object compila.
            let _dyn: &dyn Fetcher = &f;
        }

        /// Descarga real contra la red. No se ejecuta por defecto.
        /// Ejecútalo con: `cargo test -p erplora-source --features reqwest-transport -- --ignored`.
        #[test]
        #[ignore = "hace red real; ejecutar manualmente con --ignored"]
        fn fetch_real_url() {
            let f = ReqwestFetcher::new().unwrap();
            let bytes = f.fetch("https://example.com").unwrap();
            assert!(!bytes.is_empty());
        }
    }
}

#[cfg(feature = "reqwest-transport")]
pub use reqwest_transport::ReqwestFetcher;

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::io::Write;

    /// `Fetcher` de test: devuelve bytes fijos y cuenta llamadas.
    struct MockFetcher {
        bytes: Vec<u8>,
        calls: Cell<usize>,
    }

    impl MockFetcher {
        fn new(bytes: Vec<u8>) -> Self {
            Self { bytes, calls: Cell::new(0) }
        }
    }

    impl Fetcher for MockFetcher {
        fn fetch(&self, _url: &str) -> Result<Vec<u8>> {
            self.calls.set(self.calls.get() + 1);
            Ok(self.bytes.clone())
        }
    }

    /// Construye en memoria un zip con las entradas `(nombre, contenido)` dadas.
    fn build_zip(entries: &[(&str, &[u8])]) -> Vec<u8> {
        let mut buf = Vec::new();
        {
            let mut w = zip::ZipWriter::new(io::Cursor::new(&mut buf));
            let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
            for (name, content) in entries {
                w.start_file(*name, opts).unwrap();
                w.write_all(content).unwrap();
            }
            w.finish().unwrap();
        }
        buf
    }

    /// Zip de módulo válido: `module.json` + una migración anidada.
    fn valid_module_zip() -> Vec<u8> {
        build_zip(&[
            ("module.json", br#"{"id":"inventory","version":"1.0.0"}"# as &[u8]),
            ("migrations/sqlite/001_init.sql", b"CREATE TABLE t(id TEXT);"),
        ])
    }

    fn grant_for(bytes: &[u8], module_id: &str, version: &str) -> InstallGrant {
        let sha = cloud_client::integrity::sha256_hex(bytes);
        let json = format!(
            r#"{{"module_id":"{module_id}","version":"{version}","download_url":"https://s3/x.zip","sha256":"{sha}"}}"#
        );
        InstallGrant::parse(&json).unwrap()
    }

    #[test]
    fn install_ok_creates_cache_and_returns_path() {
        let tmp = tempfile::tempdir().unwrap();
        let store = ModuleStore::new(tmp.path());
        let zip = valid_module_zip();
        let grant = grant_for(&zip, "inventory", "1.0.0");
        let fetcher = MockFetcher::new(zip);

        assert!(!store.is_cached("inventory", "1.0.0"));
        let path = store.install(&fetcher, &grant).unwrap();

        assert_eq!(path, store.path_for("inventory", "1.0.0"));
        assert!(path.join("module.json").is_file());
        assert!(path.join("migrations/sqlite/001_init.sql").is_file());
        assert!(store.is_cached("inventory", "1.0.0"));
        assert_eq!(fetcher.calls.get(), 1);
    }

    #[test]
    fn install_bad_sha_errors_and_leaves_no_garbage() {
        let tmp = tempfile::tempdir().unwrap();
        let store = ModuleStore::new(tmp.path());
        let zip = valid_module_zip();
        // grant con sha de otros bytes → mismatch
        let mut grant = grant_for(&zip, "inventory", "1.0.0");
        grant.sha256 = cloud_client::integrity::sha256_hex(b"otros");
        let fetcher = MockFetcher::new(zip);

        let err = store.install(&fetcher, &grant).unwrap_err();
        assert!(matches!(err, SourceError::Integrity(_)));
        assert!(!store.is_cached("inventory", "1.0.0"));
        // El dir de versión no debe quedar con contenido.
        let dir = store.path_for("inventory", "1.0.0");
        assert!(!dir.join("module.json").is_file());
    }

    #[test]
    fn second_install_uses_cache_no_refetch() {
        let tmp = tempfile::tempdir().unwrap();
        let store = ModuleStore::new(tmp.path());
        let zip = valid_module_zip();
        let grant = grant_for(&zip, "inventory", "1.0.0");
        let fetcher = MockFetcher::new(zip);

        store.install(&fetcher, &grant).unwrap();
        assert_eq!(fetcher.calls.get(), 1);
        // Segunda vez: cache hit, sin fetch.
        store.install(&fetcher, &grant).unwrap();
        assert_eq!(fetcher.calls.get(), 1);
    }

    #[test]
    fn zip_slip_is_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let store = ModuleStore::new(tmp.path());
        // Entrada maliciosa que intenta escapar del destino.
        let zip = build_zip(&[
            ("module.json", br#"{"id":"x","version":"1"}"# as &[u8]),
            ("../evil.txt", b"pwned"),
        ]);
        let grant = grant_for(&zip, "x", "1");
        let fetcher = MockFetcher::new(zip);

        let err = store.install(&fetcher, &grant).unwrap_err();
        assert!(matches!(err, SourceError::Zip(_)));
        // No debe haber escrito nada fuera del root.
        assert!(!tmp.path().parent().unwrap().join("evil.txt").exists());
        assert!(!store.is_cached("x", "1"));
    }

    #[test]
    fn missing_manifest_errors() {
        let tmp = tempfile::tempdir().unwrap();
        let store = ModuleStore::new(tmp.path());
        let zip = build_zip(&[("readme.txt", b"no manifest here")]);
        let grant = grant_for(&zip, "x", "1");
        let fetcher = MockFetcher::new(zip);

        let err = store.install(&fetcher, &grant).unwrap_err();
        assert!(matches!(err, SourceError::MissingManifest));
        assert!(!store.is_cached("x", "1"));
    }

    #[test]
    fn remove_deletes_cache() {
        let tmp = tempfile::tempdir().unwrap();
        let store = ModuleStore::new(tmp.path());
        let zip = valid_module_zip();
        let grant = grant_for(&zip, "inventory", "1.0.0");
        let fetcher = MockFetcher::new(zip);

        store.install(&fetcher, &grant).unwrap();
        assert!(store.is_cached("inventory", "1.0.0"));
        store.remove("inventory", "1.0.0").unwrap();
        assert!(!store.is_cached("inventory", "1.0.0"));
        // remove idempotente.
        store.remove("inventory", "1.0.0").unwrap();
    }
}
