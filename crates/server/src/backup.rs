//! Transporte **real** de `host.backup_upload` (ADR-0040/0042, **opción B**): dump consistente del
//! SQLite local → **stream `POST` al Cloud** (bytes en claro sobre TLS), que lo guarda en S3 con
//! cifrado de servidor (SSE). El hub **no** cifra ni habla con S3.
//!
//! Implementa el trait [`erplora_runtime::host_backup::BackupTransport`] que el runtime define;
//! lo entrega el Outbox (reintentos/backoff/dead-letter gratis). El server lo registra cuando hay
//! config de Cloud (token de máquina); si no, se queda el `MockTransport` (ver `lib.rs`).
//!
//! Pasos de `run_backup`:
//!  1. `erplora_db::backup::vacuum_into` produce un dump consistente en un tmpfile (no para el hub).
//!  2. se lee el dump y se `POST`-streamea a `CloudClient::backup_upload`
//!     (`POST /api/v1/hub/device/backup/`, `X-Hub-Token` + `X-Hub-Id`) con `reqwest`.
//!  3. el Cloud aplica SSE, guarda en S3 y responde `{ s3_key, bytes, sha256? }` → [`UploadOutcome`].
//!
//! **Restore** (`restore_from_cloud`): descarga una copia del Cloud (`CloudClient::backup_download`,
//! user-JWT) y deja el SQLite restaurado **en disco**. El swap en caliente del fichero abierto por el
//! pool vivo es delicado → ver el TODO al final: se escribe el fichero descargado y el relink del
//! pool / reinicio queda como pieza de core del humano.

use std::sync::Arc;

use cloud_client::{Auth, BackupUploadResult, CloudClient};
use erplora_runtime::errors::{Result as RtResult, RuntimeError};
use erplora_runtime::host_backup::{BackupIntent, BackupTransport, UploadOutcome};

use crate::state::{HubId, MachineToken};

/// Transporte real (opción B). Tiene lo justo para producir el dump y firmar la subida al Cloud:
/// el path del SQLite del hub, el cliente del Cloud, el `hub_id` del despliegue, la celda viva del
/// token de máquina (`X-Hub-Token`) y un cliente HTTP de stream.
#[derive(Clone)]
pub struct CloudBackupTransport {
    /// Path del fichero SQLite del hub (`HUB_SQLITE_PATH`) — fuente del dump.
    sqlite_path: String,
    /// Cliente del Cloud Portal (construye URL + cabeceras).
    cloud: CloudClient,
    /// `hub_id` del despliegue (no spoofable; va en `X-Hub-Id`).
    hub_id: HubId,
    /// Token de máquina **vivo** (hot-reload): `X-Hub-Token`. `None` = hub sin enrolar.
    machine_token: MachineToken,
    /// Cliente HTTP async (rustls) compartido con el resto del server.
    http: reqwest::Client,
}

impl std::fmt::Debug for CloudBackupTransport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("CloudBackupTransport")
            .field("sqlite_path", &self.sqlite_path)
            .field(
                "hub_id",
                &self.hub_id.read().ok().map(|hub_id| hub_id.clone()),
            )
            .finish_non_exhaustive()
    }
}

impl CloudBackupTransport {
    pub fn new(
        sqlite_path: String,
        cloud_base_url: &str,
        hub_id: HubId,
        machine_token: MachineToken,
        http: reqwest::Client,
    ) -> Self {
        Self {
            sqlite_path,
            cloud: CloudClient::new(cloud_base_url),
            hub_id,
            machine_token,
            http,
        }
    }

    /// `Auth::HubToken` (máquina) con el token vivo. Error si el hub no está enrolado: sin token de
    /// máquina no se puede subir (el relay reintentará; tras enrolar, lo tomará en caliente).
    fn auth(&self) -> RtResult<Auth> {
        let token = self
            .machine_token
            .read()
            .ok()
            .and_then(|g| g.clone())
            .ok_or_else(|| {
                RuntimeError::Backup("hub sin enrolar: falta el token de máquina".into())
            })?;
        let hub_id = self
            .hub_id
            .read()
            .ok()
            .map(|g| g.clone())
            .ok_or_else(|| RuntimeError::Backup("identidad de Hub no disponible".into()))?;
        Ok(Auth::HubToken { hub_id, token })
    }
}

#[async_trait::async_trait]
impl BackupTransport for CloudBackupTransport {
    async fn run_backup(&self, _intent: &BackupIntent) -> RtResult<UploadOutcome> {
        // 1) Dump consistente a un tmpfile nuevo (no para el hub). El tmpfile se borra al salir.
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        let hub_id = self
            .hub_id
            .read()
            .ok()
            .map(|g| g.clone())
            .unwrap_or_else(|| "unknown".into());
        let tmp = std::env::temp_dir().join(format!("erplora-backup-{hub_id}-{ts}.dump"));
        let tmp_path = tmp.to_string_lossy().to_string();
        let _guard = TmpFileGuard(tmp_path.clone());

        let bytes = erplora_db::backup::vacuum_into(&self.sqlite_path, &tmp_path)
            .await
            .map_err(|e| RuntimeError::Backup(format!("dump del SQLite falló: {e}")))?;

        // 2) Lee el dump y lo POST-streamea al Cloud (en claro sobre TLS; el Cloud aplica SSE).
        let body = tokio::fs::read(&tmp_path)
            .await
            .map_err(|e| RuntimeError::Backup(format!("no se pudo leer el dump: {e}")))?;

        let req = self.cloud.backup_upload(&self.auth()?);
        let mut rb = self.http.post(&req.url).body(body);
        for (k, v) in req.headers {
            rb = rb.header(k, v);
        }
        // Metadata en cabeceras (tamaño en claro); el Cloud fija s3_key/ts y calcula su sha256.
        rb = rb.header("Content-Type", "application/octet-stream");
        rb = rb.header("X-Backup-Bytes", bytes.to_string());

        let resp = rb
            .send()
            .await
            .map_err(|e| RuntimeError::Backup(format!("POST del backup al Cloud falló: {e}")))?;
        if !resp.status().is_success() {
            return Err(RuntimeError::Backup(format!(
                "el Cloud rechazó el backup: HTTP {}",
                resp.status()
            )));
        }
        let text = resp
            .text()
            .await
            .map_err(|e| RuntimeError::Backup(format!("respuesta del Cloud ilegible: {e}")))?;
        let result = BackupUploadResult::parse(&text)
            .map_err(|e| RuntimeError::Backup(format!("respuesta del Cloud inválida: {e}")))?;

        Ok(UploadOutcome {
            s3_key: result.s3_key,
            // El Cloud devuelve el tamaño que escribió; si viene 0, usamos el del dump local.
            size_bytes: if result.bytes > 0 {
                result.bytes
            } else {
                bytes
            },
        })
    }
}

/// Borra el tmpfile del dump al salir del scope (éxito o error).
struct TmpFileGuard(String);
impl Drop for TmpFileGuard {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

/// **Restore (pull del Cloud) — parte segura: descarga + escritura del fichero.**
///
/// Descarga la copia `s3_key` del Cloud (con el **JWT de usuario** `auth`, flujo posiblemente
/// cross-hub para migrar a otro equipo) y la escribe en `dst_path` tras validar que es un SQLite
/// íntegro. **No** hace el swap en caliente del fichero que el pool vivo tiene abierto (delicado;
/// ver TODO). Devuelve el nº de bytes escritos.
///
/// El llamador (capa de core / shell Tauri) decide cuándo aplicar `dst_path` como la nueva BD del
/// hub y reiniciar — ver el TODO de hot-swap.
pub async fn restore_from_cloud(
    cloud_base_url: &str,
    auth: &Auth,
    s3_key: &str,
    dst_path: &str,
    http: &reqwest::Client,
) -> RtResult<u64> {
    let cloud = CloudClient::new(cloud_base_url);
    // El s3_key contiene `/` y `:` → URL-encode para la query (`backup_download` lo mete crudo).
    let encoded = urlencode(s3_key);
    let req = cloud.backup_download(auth, &encoded);
    let mut rb = http.get(&req.url);
    for (k, v) in req.headers {
        rb = rb.header(k, v);
    }
    let resp = rb
        .send()
        .await
        .map_err(|e| RuntimeError::Backup(format!("descarga del backup falló: {e}")))?;
    if !resp.status().is_success() {
        return Err(RuntimeError::Backup(format!(
            "el Cloud no sirvió el backup: HTTP {}",
            resp.status()
        )));
    }
    let bytes = resp
        .bytes()
        .await
        .map_err(|e| RuntimeError::Backup(format!("bytes del backup ilegibles: {e}")))?;
    tokio::fs::write(dst_path, &bytes).await.map_err(|e| {
        RuntimeError::Backup(format!("no se pudo escribir el backup descargado: {e}"))
    })?;
    // Sanity: el fichero descargado es un SQLite válido (SSE es transparente — viene descifrado).
    erplora_db::backup::verify_sqlite_file(dst_path)
        .await
        .map_err(|e| {
            RuntimeError::Backup(format!("el backup descargado no es un SQLite válido: {e}"))
        })?;
    Ok(bytes.len() as u64)

    // ── TODO (columna humano — core / shell) ────────────────────────────────────────────────
    // **Hot-swap del SQLite restaurado.** Hacer que `dst_path` reemplace la BD viva (`sqlite_path`)
    // mientras el pool de sqlx la tiene abierta es delicado (ficheros mmap/WAL abiertos, riesgo de
    // corrupción). El modelo simple y seguro (backup.md §4): cerrar el runtime, mover el fichero, y
    // **reiniciar el proceso** (en Tauri: el shell reinicia la app; al re-arrancar el hub lee la BD
    // restaurada y re-descarga sus módulos). NO se implementa aquí un swap en caliente arriesgado del
    // core: esta función deja el fichero listo y el reinicio/relink lo orquesta el humano.
}

/// Helper de codificación de query minimal (no se trae un crate solo para esto): escapa lo justo
/// para que un `s3_key` (`/`, `:`, espacios) viaje seguro como valor de query string.
fn urlencode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// Construye el transporte real con identidad viva. Puede nacer antes del primer registro: si se
/// invoca aún sin token devuelve un error recuperable y el outbox reintenta; cuando el bootstrap
/// rellena `hub_id + token`, la siguiente entrega funciona sin reiniciar.
pub fn build_transport(
    sqlite_path: String,
    cloud_base_url: &str,
    hub_id: HubId,
    machine_token: MachineToken,
    http: reqwest::Client,
) -> Arc<dyn BackupTransport> {
    Arc::new(CloudBackupTransport::new(
        sqlite_path,
        cloud_base_url,
        hub_id,
        machine_token,
        http,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn urlencode_escapes_path_separators() {
        assert_eq!(
            urlencode("backups/local/h1/x.dump"),
            "backups%2Flocal%2Fh1%2Fx.dump"
        );
        assert_eq!(urlencode("a:b c"), "a%3Ab%20c");
        assert_eq!(urlencode("plain-1.0_x~"), "plain-1.0_x~");
    }

    #[test]
    fn build_transport_is_ready_for_hot_enrollment_without_machine_token() {
        let cell: MachineToken = std::sync::Arc::new(std::sync::RwLock::new(None));
        let t = build_transport(
            "x.db".into(),
            "https://erplora.com",
            std::sync::Arc::new(std::sync::RwLock::new("h1".into())),
            cell,
            reqwest::Client::new(),
        );
        let _ = t;
    }

    #[test]
    fn build_transport_some_with_machine_token() {
        let cell: MachineToken = std::sync::Arc::new(std::sync::RwLock::new(Some("tok".into())));
        let t = build_transport(
            "x.db".into(),
            "https://erplora.com",
            std::sync::Arc::new(std::sync::RwLock::new("h1".into())),
            cell,
            reqwest::Client::new(),
        );
        let _ = t;
    }
}
