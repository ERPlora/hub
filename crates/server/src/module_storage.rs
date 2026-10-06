//! Backend de `module.json.static_files`.
//!
//! El contrato lógico es siempre `media/modules/<folder>/...`, **lo sirva quien lo sirva**: un
//! módulo no puede notar en qué despliegue corre. Hay dos backends y los elige [`backend_for`]:
//!
//! | | Backend | Por qué |
//! |---|---|---|
//! | Producción | [`ModuleMediaStorage`] — proxy autenticado Hub→Cloud→Object Storage (ADR-0154) | Sin credenciales de almacenamiento en el Hub |
//! | Desarrollo | [`ModuleDiskStorage`] — `HUB_MEDIA_DIR/modules/<folder>` | No hay token de máquina, y sin él **nada** con `static_files` se puede instalar |
//!
//! El backend de disco lo prometía un comentario de `boot.rs` desde el principio, pero no existía
//! (hub#1477). Su ausencia tenía un efecto concreto: `verifactu` es el único de los 27 módulos
//! publicados que declara `static_files`, así que era **el único módulo del catálogo que no se
//! podía instalar sin Cloud** — ni en local ni en el corredor de baterías de la CI.

use std::path::{Path, PathBuf};

use erplora_runtime::module_storage::{
    valid_module_folder, valid_relative_file_path, ModuleStorage,
};
use erplora_runtime::{Result, RuntimeError};

use crate::MachineToken;

/// Implementación que el server inyecta en el runtime antes de instalar módulos: proxy al Cloud.
#[derive(Clone)]
pub struct ModuleMediaStorage {
    base_url: String,
    hub_id: String,
    machine_token: MachineToken,
    http: reqwest::Client,
}

impl std::fmt::Debug for ModuleMediaStorage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ModuleMediaStorage")
            .field("cloud", &self.base_url)
            .field("hub_id", &self.hub_id)
            .finish_non_exhaustive()
    }
}

impl ModuleMediaStorage {
    pub fn cloud(
        base_url: impl Into<String>,
        hub_id: impl Into<String>,
        machine_token: MachineToken,
    ) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_string(),
            hub_id: hub_id.into(),
            machine_token,
            // The same limits as every other call to erplora.com (hub#2509); the upload asks for
            // the transfer ceiling on its own request.
            http: crate::state::cloud_client(
                crate::state::CLOUD_CONNECT_TIMEOUT,
                crate::state::CLOUD_CALL_TIMEOUT,
            ),
        }
    }

    fn cloud_token(machine_token: &MachineToken) -> Result<String> {
        machine_token
            .read()
            .ok()
            .and_then(|guard| guard.clone())
            .filter(|token| !token.trim().is_empty())
            .ok_or_else(|| RuntimeError::Storage("Hub Cloud sin token de máquina".to_string()))
    }

    async fn cloud_folder(
        http: &reqwest::Client,
        base_url: &str,
        hub_id: &str,
        token: &str,
        parent: &str,
        name: &str,
    ) -> Result<()> {
        let url = format!("{base_url}/api/v1/hub/device/media/folder/");
        let auth = cloud_client::Auth::HubToken {
            hub_id: hub_id.to_string(),
            token: token.to_string(),
        };
        let headers = cloud_client::CloudClient::new(base_url).headers_for(&url, &auth);
        let mut request = http.post(&url).json(&serde_json::json!({
            "parent": parent,
            "name": name,
        }));
        for (key, value) in headers {
            request = request.header(key, value);
        }
        let response = request.send().await.map_err(|error| {
            RuntimeError::Storage(format!(
                "Cloud media/folder: {}",
                crate::cloud_proxy::cloud_unreachable(&error.to_string())
            ))
        })?;
        if !response.status().is_success() {
            return Err(RuntimeError::Storage(format!(
                "Cloud rechazó media/folder ({})",
                response.status()
            )));
        }
        Ok(())
    }

    async fn ensure_cloud_path(
        http: &reqwest::Client,
        base_url: &str,
        hub_id: &str,
        token: &str,
        folder: &str,
        relative_parent: Option<&str>,
    ) -> Result<String> {
        Self::cloud_folder(http, base_url, hub_id, token, "", "modules").await?;
        Self::cloud_folder(http, base_url, hub_id, token, "modules", folder).await?;

        let mut parent = format!("modules/{folder}");
        if let Some(relative_parent) = relative_parent {
            for segment in relative_parent.split('/').filter(|part| !part.is_empty()) {
                Self::cloud_folder(http, base_url, hub_id, token, &parent, segment).await?;
                parent.push('/');
                parent.push_str(segment);
            }
        }
        Ok(parent)
    }
}

#[async_trait::async_trait]
impl ModuleStorage for ModuleMediaStorage {
    async fn ensure_module_folder(&self, _hub_id: &str, folder: &str) -> Result<()> {
        let token = Self::cloud_token(&self.machine_token)?;
        Self::ensure_cloud_path(
            &self.http,
            &self.base_url,
            &self.hub_id,
            &token,
            folder,
            None,
        )
        .await
        .map(|_| ())
    }

    async fn write_module_file(
        &self,
        _hub_id: &str,
        folder: &str,
        relative_path: &str,
        bytes: &[u8],
        content_type: &str,
    ) -> Result<String> {
        if !valid_relative_file_path(relative_path) {
            return Err(RuntimeError::Storage(
                "ruta relativa de fichero inválida".to_string(),
            ));
        }
        let media_path = format!("modules/{folder}/{relative_path}");
        let token = Self::cloud_token(&self.machine_token)?;
        let (relative_parent, file_name) = match relative_path.rsplit_once('/') {
            Some((parent, name)) => (Some(parent), name),
            None => (None, relative_path),
        };
        let upload_folder = Self::ensure_cloud_path(
            &self.http,
            &self.base_url,
            &self.hub_id,
            &token,
            folder,
            relative_parent,
        )
        .await?;
        let part = reqwest::multipart::Part::bytes(bytes.to_vec())
            .file_name(file_name.to_string())
            .mime_str(content_type)
            .map_err(|error| RuntimeError::Storage(error.to_string()))?;
        let form = reqwest::multipart::Form::new()
            .text("folder", upload_folder)
            .part("files", part);
        let auth = cloud_client::Auth::HubToken {
            hub_id: self.hub_id.clone(),
            token,
        };
        let url = format!("{}/api/v1/hub/device/media/", self.base_url);
        let headers = cloud_client::CloudClient::new(&self.base_url).headers_for(&url, &auth);
        let mut request = self
            .http
            .post(&url)
            .multipart(form)
            .timeout(crate::state::CLOUD_TRANSFER_TIMEOUT);
        for (key, value) in headers {
            request = request.header(key, value);
        }
        let response = request.send().await.map_err(|error| {
            RuntimeError::Storage(format!(
                "Cloud media/upload: {}",
                crate::cloud_proxy::cloud_unreachable(&error.to_string())
            ))
        })?;
        if !response.status().is_success() {
            return Err(RuntimeError::Storage(format!(
                "Cloud rechazó media/upload ({})",
                response.status()
            )));
        }
        Ok(media_path)
    }
}

/// Qué backend de ficheros de módulos le toca a este despliegue (hub#1477).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Backend {
    /// `HUB_MEDIA_DIR/modules/<folder>` — desarrollo.
    Disk,
    /// Proxy Hub→Cloud→Object Storage — producción.
    Cloud,
}

/// **Producción siempre por el Cloud, aunque no haya token.**
///
/// Es el mismo interruptor que ya decide si se escanea `HUB_MODULES_DIR`
/// (`install_guard::boot_scan_dir`), y por la misma razón: si el hub instala módulos de disco, sus
/// ficheros también van a disco.
///
/// La tentación era elegir por «¿hay token?» en vez de por «¿es desarrollo?». Se descartó: un hub
/// **real** sin token tiene un problema de despliegue, y caer a disco lo taparía — arrancaría
/// «bien» y el fallo saldría más tarde, en otro sitio y sin relación aparente con el secreto que
/// falta. Que falle donde falla es lo correcto; lo que faltaba era que se **viera**, y de eso se
/// encarga la otra mitad de hub#1477 (`Registry::failed_installs` → `/readyz`).
pub fn backend_for(dev_mode: bool) -> Backend {
    if dev_mode {
        Backend::Disk
    } else {
        Backend::Cloud
    }
}

/// Backend de disco: `<media_dir>/modules/<folder>/...`.
///
/// `media_dir` es el mismo `HUB_MEDIA_DIR` que ya usan perfiles y adjuntos (`AppState::media_dir`),
/// así que no añade una ruta nueva que configurar ni que respaldar.
#[derive(Debug, Clone)]
pub struct ModuleDiskStorage {
    media_dir: PathBuf,
}

impl ModuleDiskStorage {
    pub fn new(media_dir: impl Into<PathBuf>) -> Self {
        Self {
            media_dir: media_dir.into(),
        }
    }

    /// La carpeta del módulo en disco, validando el segmento **aquí también**: el `folder` sale del
    /// `module.json` de un paquete de terceros, que es frontera hostil.
    fn folder_path(&self, folder: &str) -> Result<PathBuf> {
        if !valid_module_folder(folder) {
            return Err(RuntimeError::Storage(format!(
                "carpeta inválida en `static_files.folder`: `{folder}`"
            )));
        }
        Ok(self.media_dir.join("modules").join(folder))
    }
}

#[async_trait::async_trait]
impl ModuleStorage for ModuleDiskStorage {
    async fn ensure_module_folder(&self, _hub_id: &str, folder: &str) -> Result<()> {
        let path = self.folder_path(folder)?;
        tokio::fs::create_dir_all(&path).await.map_err(|error| {
            RuntimeError::Storage(format!("no se pudo crear {}: {error}", path.display()))
        })
    }

    async fn write_module_file(
        &self,
        _hub_id: &str,
        folder: &str,
        relative_path: &str,
        bytes: &[u8],
        _content_type: &str,
    ) -> Result<String> {
        if !valid_relative_file_path(relative_path) {
            return Err(RuntimeError::Storage(
                "ruta relativa de fichero inválida".to_string(),
            ));
        }
        let target = self.folder_path(folder)?.join(relative_path);
        // `valid_relative_file_path` ya descarta `..`, rutas absolutas y separadores de Windows, así
        // que `parent()` no puede salirse de la carpeta del módulo.
        if let Some(parent) = target.parent() {
            create_dir_all(parent).await?;
        }
        tokio::fs::write(&target, bytes).await.map_err(|error| {
            RuntimeError::Storage(format!("no se pudo escribir {}: {error}", target.display()))
        })?;
        // El MISMO valor que devuelve el backend del Cloud: se guarda y se sirve después, así que si
        // los dos no coincidieran, un hub migrado dejaría de encontrar sus propios ficheros.
        Ok(format!("modules/{folder}/{relative_path}"))
    }
}

async fn create_dir_all(path: &Path) -> Result<()> {
    tokio::fs::create_dir_all(path).await.map_err(|error| {
        RuntimeError::Storage(format!("no se pudo crear {}: {error}", path.display()))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use axum::extract::{Request, State};
    use axum::http::StatusCode;
    use axum::Router;
    use std::sync::{Arc, Mutex, RwLock};

    #[derive(Clone, Default)]
    struct Capture(Arc<Mutex<Vec<(String, String, Vec<u8>)>>>);

    async fn capture(State(capture): State<Capture>, request: Request) -> StatusCode {
        let path = request.uri().path().to_string();
        let token = request
            .headers()
            .get("x-hub-token")
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_string();
        let body = to_bytes(request.into_body(), 1024 * 1024)
            .await
            .unwrap()
            .to_vec();
        capture.0.lock().unwrap().push((path, token, body));
        StatusCode::CREATED
    }

    /// Las rutas de escape se rechazan ANTES de tocar la red (contrato backend-agnóstico).
    #[tokio::test]
    async fn rejects_escape_paths() {
        let token = Arc::new(RwLock::new(Some("machine-secret".to_string())));
        let storage = ModuleMediaStorage::cloud("http://cloud.invalid", "hub-1", token);
        let error = storage
            .write_module_file(
                "hub-1",
                "verifactu",
                "../escape.xml",
                b"x",
                "application/xml",
            )
            .await
            .unwrap_err();
        assert!(matches!(error, RuntimeError::Storage(_)));
    }

    #[tokio::test]
    async fn cloud_storage_creates_prefixes_and_uploads_through_cloud() {
        let capture_state = Capture::default();
        let app = Router::new()
            .fallback(capture)
            .with_state(capture_state.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let token = Arc::new(RwLock::new(Some("machine-secret".to_string())));
        let storage = ModuleMediaStorage::cloud(format!("http://{address}"), "hub-cloud", token);

        storage
            .ensure_module_folder("hub-cloud", "verifactu")
            .await
            .unwrap();
        let path = storage
            .write_module_file(
                "hub-cloud",
                "verifactu",
                "xml/record-1.xml",
                b"<soap />",
                "application/xml",
            )
            .await
            .unwrap();

        assert_eq!(path, "modules/verifactu/xml/record-1.xml");
        let calls = capture_state.0.lock().unwrap();
        assert_eq!(
            calls
                .iter()
                .filter(|(path, _, _)| path.ends_with("/media/folder/"))
                .count(),
            5,
            "2 carpetas al instalar + 3 idempotentes al subir (modules/verifactu/xml)"
        );
        let upload = calls
            .iter()
            .find(|(path, _, _)| path.ends_with("/media/"))
            .expect("multipart upload");
        assert_eq!(upload.1, "machine-secret");
        let body = String::from_utf8_lossy(&upload.2);
        assert!(body.contains("modules/verifactu/xml"));
        assert!(body.contains("record-1.xml"));
        assert!(body.contains("<soap />"));
        drop(calls);
        server.abort();
    }
}

#[cfg(test)]
mod disk_backend_tests {
    //! hub#1477: sin backend de disco, el ÚNICO módulo con `static_files` (`verifactu`) no se puede
    //! instalar sin token de máquina — ni en local, ni en el corredor de baterías de la CI.
    use super::*;
    use std::path::PathBuf;

    fn media_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "erplora-hub1477-{tag}-{}-{:?}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// El contrato lógico es el MISMO que en Cloud: `media/modules/<folder>/`. Lo que cambia es
    /// dónde aterriza, no cómo se nombra — un módulo no puede notar en qué despliegue corre.
    #[tokio::test]
    async fn ensure_materializes_the_folder_under_media_modules() {
        let root = media_dir("ensure");
        let storage = ModuleDiskStorage::new(&root);

        storage
            .ensure_module_folder("hub-1", "verifactu")
            .await
            .unwrap();

        assert!(root.join("modules/verifactu").is_dir());
        std::fs::remove_dir_all(root).unwrap();
    }

    /// Idempotente por contrato del trait: el instalador la llama en CADA arranque.
    #[tokio::test]
    async fn ensure_can_run_twice_without_complaining() {
        let root = media_dir("idempotent");
        let storage = ModuleDiskStorage::new(&root);

        storage
            .ensure_module_folder("hub-1", "verifactu")
            .await
            .unwrap();
        storage
            .ensure_module_folder("hub-1", "verifactu")
            .await
            .unwrap();

        assert!(root.join("modules/verifactu").is_dir());
        std::fs::remove_dir_all(root).unwrap();
    }

    /// **Devuelve exactamente lo que devolvería el Cloud.** Ese valor se guarda y se sirve después;
    /// si los dos backends no coincidieran, un hub migrado de Local a Cloud dejaría de encontrar
    /// sus propios ficheros.
    #[tokio::test]
    async fn write_returns_the_same_logical_path_the_cloud_backend_returns() {
        let root = media_dir("write");
        let storage = ModuleDiskStorage::new(&root);
        storage
            .ensure_module_folder("hub-1", "verifactu")
            .await
            .unwrap();

        let path = storage
            .write_module_file(
                "hub-1",
                "verifactu",
                "xml/record-1.xml",
                b"<x/>",
                "application/xml",
            )
            .await
            .unwrap();

        assert_eq!(path, "modules/verifactu/xml/record-1.xml");
        assert_eq!(
            std::fs::read(root.join("modules/verifactu/xml/record-1.xml")).unwrap(),
            b"<x/>".to_vec()
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    /// El `folder` sale del `module.json` de un paquete de terceros: frontera hostil. El instalador
    /// ya lo valida, y aquí se vuelve a validar — un backend que se fía de que alguien validó antes
    /// es un escape de directorio esperando a que cambie el orden de las llamadas.
    #[tokio::test]
    async fn a_folder_that_escapes_the_media_dir_is_refused() {
        let root = media_dir("escape-folder");
        let storage = ModuleDiskStorage::new(&root);

        for folder in ["../escape", "/etc", "..", "a/b"] {
            let error = storage
                .ensure_module_folder("hub-1", folder)
                .await
                .unwrap_err();
            assert!(
                error.to_string().contains("static_files.folder"),
                "`{folder}` tenía que rechazarse: {error}"
            );
        }
        assert!(!root.parent().unwrap().join("escape").exists());
        std::fs::remove_dir_all(root).unwrap();
    }

    /// Lo mismo para la ruta del fichero, con la misma regla que ya aplica el backend del Cloud.
    #[tokio::test]
    async fn a_relative_path_that_escapes_the_folder_is_refused() {
        let root = media_dir("escape-path");
        let storage = ModuleDiskStorage::new(&root);
        storage
            .ensure_module_folder("hub-1", "verifactu")
            .await
            .unwrap();

        for path in ["../../etc/passwd", "/etc/passwd", "xml/../../../x"] {
            let error = storage
                .write_module_file("hub-1", "verifactu", path, b"x", "text/plain")
                .await
                .unwrap_err();
            assert!(
                error.to_string().contains("ruta relativa"),
                "`{path}` tenía que rechazarse: {error}"
            );
        }
        std::fs::remove_dir_all(root).unwrap();
    }

    // ── Qué backend le toca a cada despliegue ────────────────────────────────────────

    /// En desarrollo NO hay token de máquina, y es el mismo interruptor que ya decide si se escanea
    /// `HUB_MODULES_DIR` (`install_guard::boot_scan_dir`): si el hub instala de disco, sus ficheros
    /// también van a disco.
    #[test]
    fn development_writes_module_files_to_disk() {
        assert_eq!(backend_for(true), Backend::Disk);
    }

    /// **En producción, nunca disco.** Un hub real sin token tiene un problema de despliegue, y un
    /// backend de disco lo que haría es taparlo: arrancaría «bien» y el fallo aparecería más tarde
    /// y en otro sitio. Que falle aquí es lo correcto — y desde hub#1477 además se ve.
    #[test]
    fn production_always_goes_through_the_cloud_even_without_a_token() {
        assert_eq!(backend_for(false), Backend::Cloud);
    }
}
