//! Backend de `module.json.static_files`.
//!
//! El contrato lógico es siempre `media/modules/<folder>/...`; solo cambia el backend:
//! - Hub Local/demo (SQLite): disco bajo `HUB_MEDIA_DIR`.
//! - Hub Cloud (Postgres): proxy autenticado Hub→Cloud→S3, sin credenciales AWS en el Hub.

use std::path::{Path, PathBuf};

use erplora_runtime::module_storage::{valid_relative_file_path, ModuleStorage};
use erplora_runtime::{Result, RuntimeError};

use crate::MachineToken;

#[derive(Clone)]
enum Backend {
    Local {
        media_dir: PathBuf,
    },
    Cloud {
        base_url: String,
        hub_id: String,
        machine_token: MachineToken,
        http: reqwest::Client,
    },
}

/// Implementación que el server inyecta en el runtime antes de instalar módulos.
#[derive(Clone)]
pub struct ModuleMediaStorage {
    backend: Backend,
}

impl std::fmt::Debug for ModuleMediaStorage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match &self.backend {
            Backend::Local { media_dir } => f
                .debug_struct("ModuleMediaStorage")
                .field("local", media_dir)
                .finish(),
            Backend::Cloud {
                base_url, hub_id, ..
            } => f
                .debug_struct("ModuleMediaStorage")
                .field("cloud", base_url)
                .field("hub_id", hub_id)
                .finish_non_exhaustive(),
        }
    }
}

impl ModuleMediaStorage {
    pub fn local(media_dir: impl Into<PathBuf>) -> Self {
        Self {
            backend: Backend::Local {
                media_dir: media_dir.into(),
            },
        }
    }

    pub fn cloud(
        base_url: impl Into<String>,
        hub_id: impl Into<String>,
        machine_token: MachineToken,
    ) -> Self {
        Self {
            backend: Backend::Cloud {
                base_url: base_url.into().trim_end_matches('/').to_string(),
                hub_id: hub_id.into(),
                machine_token,
                http: reqwest::Client::new(),
            },
        }
    }

    fn local_target(media_dir: &Path, folder: &str, relative_path: &str) -> Result<PathBuf> {
        if !valid_relative_file_path(relative_path) {
            return Err(RuntimeError::Storage(
                "ruta relativa de fichero inválida".to_string(),
            ));
        }
        let root = media_dir.join("modules").join(folder);
        let target = crate::media::safe_join(&root, relative_path).ok_or_else(|| {
            RuntimeError::Storage("ruta relativa de fichero inválida".to_string())
        })?;
        Ok(target)
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
        let mut request = http.post(url).json(&serde_json::json!({
            "parent": parent,
            "name": name,
        }));
        for (key, value) in auth.headers() {
            request = request.header(key, value);
        }
        let response = request
            .send()
            .await
            .map_err(|error| RuntimeError::Storage(format!("Cloud media/folder: {error}")))?;
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
        match &self.backend {
            Backend::Local { media_dir } => {
                std::fs::create_dir_all(media_dir.join("modules").join(folder))
                    .map_err(|error| RuntimeError::Storage(error.to_string()))
            }
            Backend::Cloud {
                base_url,
                hub_id,
                machine_token,
                http,
            } => {
                let token = Self::cloud_token(machine_token)?;
                Self::ensure_cloud_path(http, base_url, hub_id, &token, folder, None)
                    .await
                    .map(|_| ())
            }
        }
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
        match &self.backend {
            Backend::Local { media_dir } => {
                let target = Self::local_target(media_dir, folder, relative_path)?;
                let parent = target.parent().ok_or_else(|| {
                    RuntimeError::Storage("el fichero no tiene carpeta padre".to_string())
                })?;
                std::fs::create_dir_all(parent)
                    .map_err(|error| RuntimeError::Storage(error.to_string()))?;

                // Escritura atómica en el mismo directorio: el XML anterior sigue disponible si el
                // proceso cae durante una retransmisión.
                let stamp = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_nanos();
                let tmp = target.with_extension(format!("tmp-{}-{stamp}", std::process::id()));
                std::fs::write(&tmp, bytes)
                    .map_err(|error| RuntimeError::Storage(error.to_string()))?;
                std::fs::rename(&tmp, &target)
                    .map_err(|error| RuntimeError::Storage(error.to_string()))?;
                Ok(media_path)
            }
            Backend::Cloud {
                base_url,
                hub_id,
                machine_token,
                http,
            } => {
                let token = Self::cloud_token(machine_token)?;
                let (relative_parent, file_name) = match relative_path.rsplit_once('/') {
                    Some((parent, name)) => (Some(parent), name),
                    None => (None, relative_path),
                };
                let upload_folder = Self::ensure_cloud_path(
                    http,
                    base_url,
                    hub_id,
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
                    hub_id: hub_id.clone(),
                    token,
                };
                let mut request = http
                    .post(format!("{base_url}/api/v1/hub/device/media/"))
                    .multipart(form);
                for (key, value) in auth.headers() {
                    request = request.header(key, value);
                }
                let response = request.send().await.map_err(|error| {
                    RuntimeError::Storage(format!("Cloud media/upload: {error}"))
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
    }
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

    #[tokio::test]
    async fn local_storage_materializes_and_writes_under_media_modules() {
        let root = std::env::temp_dir().join(format!(
            "erplora-module-media-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let storage = ModuleMediaStorage::local(&root);

        storage
            .ensure_module_folder("hub-1", "verifactu")
            .await
            .unwrap();
        let path = storage
            .write_module_file(
                "hub-1",
                "verifactu",
                "xml/record-1.xml",
                b"<xml />",
                "application/xml",
            )
            .await
            .unwrap();

        assert_eq!(path, "modules/verifactu/xml/record-1.xml");
        assert_eq!(
            std::fs::read(root.join(&path)).unwrap(),
            b"<xml />".to_vec()
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn local_storage_rejects_escape_paths() {
        let storage = ModuleMediaStorage::local(std::env::temp_dir());
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
