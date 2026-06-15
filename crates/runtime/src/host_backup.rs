//! Capacidad de host `host.backup_upload` (ADR-0040): subida de la copia del SQLite local al
//! **Cloud**, **mediada por el runtime** porque el módulo (WASM, sandbox) no tiene ni filesystem
//! ni red.
//!
//! **Espejo de `host_notify.rs`** (mismo patrón trait + transporte inyectable + entrega por
//! Outbox). El módulo `backup` NO sube nada: su command `backup.create` emite un evento
//! `backup.requested` (nombre exacto [`crate::outbox::BACKUP_REQUESTED_EVENT`]) cuyo payload es la
//! intención [`BackupIntent`]; el runtime registra un **listener-host** sintético sobre ese evento
//! y el **relay** del outbox lo entrega con reintentos/backoff/dead-letter **gratis** (la misma
//! máquina ya probada del outbox). Aquí no se reimplementan los reintentos: solo el contrato con el
//! transporte que **streamea el dump** al Cloud.
//!
//! **Por qué Outbox y no inline** (justificación, columna del humano ya decidida en el patrón de
//! ADR-0012): un backup es una operación de red lenta y falible (dump + stream al Cloud). Hacerlo
//! inline en el command bloquearía la transacción del POS y perdería el backup si la red falla
//! puntualmente. Por el Outbox el command solo persiste la **intención** en su tx (atómico) y el
//! relay reintenta hasta entregar — idéntico a `host.notify`. Decisión: **entrega por Outbox**.
//!
//! Decisiones del humano ya tomadas (ADR-0040 + decisión 2026-06-13, **opción B**, NO se re-deciden
//! aquí):
//!  - **Transporte = stream del dump al Cloud.** El hub hace `POST` del dump (bytes en claro sobre
//!    TLS) a un endpoint del Cloud (`erplora_cloud_client::CloudClient::backup_upload` →
//!    `POST /api/v1/hub/device/backup/`, `X-Hub-Token`). **Sin** presign, **sin** STS, **sin**
//!    credenciales AWS en el dispositivo.
//!  - **Cifrado = en SERVIDOR (SSE-S3/KMS), NO en el hub.** El Cloud aplica SSE al escribir en S3.
//!    El hub **no** cifra: descartado el cifrado en cliente AES-GCM + la master key (no hay clave
//!    en el dispositivo). El blob va en claro al Cloud sobre TLS, que lo guarda con SSE.
//!
//! El **transporte real** (leer el dump del SQLite + `POST` stream al Cloud vía `crates/cloud-client`
//! con un cliente HTTP) es una **decisión de dependencia del humano** (qué cliente HTTP). Aquí se
//! define el TRAIT [`BackupTransport`] + un [`MockTransport`] que registra las subidas en memoria, de
//! modo que la mecánica Outbox (reintentos/dead-letter) queda real y testeada. La integración real
//! del transporte queda como TODO (ver más abajo).
use std::sync::{Arc, Mutex};

use serde::Deserialize;

use crate::errors::{Result, RuntimeError};

/// La intención de backup que el command `backup.create` emite en el payload del evento
/// `backup.requested`. El módulo solo construye esto (id de la fila de `backup_log` + metadatos);
/// el host resuelve el dump del SQLite y el stream al Cloud (que lo guarda en S3 con SSE).
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct BackupIntent {
    /// Id de la fila `backup_log` que el command insertó en estado `pending`. El host lo usa para
    /// que un listener del módulo (o el propio host) actualice el estado a `uploaded`/`failed`.
    #[serde(default)]
    pub backup_id: String,
    /// `hub_id` del despliegue (lo inyecta el runtime en el payload del command, no falsificable).
    #[serde(default)]
    pub hub_id: String,
    /// Etiqueta opcional del backup (manual vs programado), para trazabilidad.
    #[serde(default)]
    pub trigger: Option<String>,
}

impl BackupIntent {
    /// Extrae la intención del payload de un evento `backup.requested`. Tolerante: los campos son
    /// opcionales (el host completa lo que falte desde su contexto).
    pub fn from_event_payload(payload: &erplora_db::Params) -> Result<BackupIntent> {
        let value = serde_json::Value::Object(payload.clone());
        serde_json::from_value(value).map_err(|e| RuntimeError::InvalidPayload {
            name: "host.backup_upload".to_string(),
            detail: format!("intención de backup inválida: {e}"),
        })
    }
}

/// Resultado de una subida con éxito: dónde quedó el blob en S3 y su tamaño, para que el host
/// (o un listener del módulo) actualice `backup_log`. Lo devuelve el **Cloud** en la respuesta del
/// stream (`{ s3_key, bytes, ... }`), no el hub: el hub ya no calcula la ruta S3 (la fija el Cloud).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UploadOutcome {
    /// Clave S3 donde el Cloud dejó el blob (`backups/local/{hub}/{ts}.dump`). La devuelve el Cloud.
    pub s3_key: String,
    /// Tamaño en bytes del dump subido (en claro; el cifrado es SSE en el Cloud).
    pub size_bytes: u64,
}

/// Transporte de backup: el cliente real que ejecuta el flujo completo de una copia para `intent`
/// (**opción B**, decidida 2026-06-13):
///  1. **empaqueta** un dump consistente del SQLite del hub (acceso al FS, lado host),
///  2. lo **streamea al Cloud** (bytes en claro sobre TLS) vía
///     `erplora_cloud_client::CloudClient::backup_upload` (`POST /api/v1/hub/device/backup/`,
///     `X-Hub-Token` + `X-Hub-Id`),
///  3. el **Cloud** aplica SSE y lo guarda en S3, y responde con la [`UploadOutcome`] (`s3_key`/tamaño).
///
/// **El hub NO cifra** (sin AES-GCM ni master key): el cifrado es de servidor (SSE) en el Cloud.
///
/// **Trait inyectable** (espejo de `NotifyTransport`) para no atar el runtime a una dependencia
/// concreta de HTTP ni a la fuente del dump (decisión del humano). El host lo registra al arrancar;
/// un `Err` se traduce en reintento del relay (backoff) y, tras `MAX_ATTEMPTS`, dead-letter —
/// exactamente como un listener que falla.
#[async_trait::async_trait]
pub trait BackupTransport: Send + Sync + std::fmt::Debug {
    /// Ejecuta el backup descrito por `intent` (dump + stream al Cloud, que guarda en S3 con SSE).
    /// `Ok(UploadOutcome)` con la `s3_key`/tamaño que devolvió el Cloud; `Err` para que el relay
    /// reintente.
    async fn run_backup(&self, intent: &BackupIntent) -> Result<UploadOutcome>;
}

/// Transporte **mock** para tests y arranque sin transporte real configurado: simula el flujo
/// (produce un dump sintético y lo "streamea") y registra cada backup en memoria con el dump (en
/// claro — el cifrado es del Cloud, no del hub). Permite probar la mecánica Outbox
/// (reintentos/dead-letter) sin red ni FS. La integración real (dump del SQLite + `POST` stream al
/// Cloud) la conecta el host sustituyendo este transporte.
#[derive(Debug, Default, Clone)]
pub struct MockTransport {
    uploads: Arc<Mutex<Vec<(BackupIntent, Vec<u8>)>>>,
    /// Si `true`, `run_backup` devuelve `Err` (para probar el reintento/dead-letter del relay).
    fail: bool,
}

impl MockTransport {
    pub fn new() -> Self {
        Self::default()
    }

    /// Variante que siempre falla (para tests del backoff/dead-letter del relay).
    pub fn failing() -> Self {
        Self { uploads: Arc::default(), fail: true }
    }

    /// Backups registrados (clon): `(intención, dump en claro)` — para aserciones en tests.
    pub fn uploads(&self) -> Vec<(BackupIntent, Vec<u8>)> {
        self.uploads.lock().map(|g| g.clone()).unwrap_or_default()
    }
}

#[async_trait::async_trait]
impl BackupTransport for MockTransport {
    async fn run_backup(&self, intent: &BackupIntent) -> Result<UploadOutcome> {
        if self.fail {
            return Err(RuntimeError::Backup("transporte mock configurado para fallar".into()));
        }
        // Simula los pasos del transporte real: dump sintético → stream al Cloud (sin cifrar; el
        // Cloud guarda con SSE). El blob registrado es el dump EN CLARO.
        let dump = format!("-- dump del hub {} (backup {}) --", intent.hub_id, intent.backup_id);
        let dump = dump.into_bytes();
        if let Ok(mut g) = self.uploads.lock() {
            g.push((intent.clone(), dump.clone()));
        }
        // El Cloud fija la s3_key y la devuelve en la respuesta del stream (aquí el mock la simula).
        Ok(UploadOutcome {
            s3_key: format!("backups/local/{}/mock.dump", intent.hub_id),
            size_bytes: dump.len() as u64,
        })
    }
}

// ── Estado de implementación (opción B) ───────────────────────────────────────────────────────
// 1) **Empaquetado del dump del SQLite (host, FS).** HECHO: `erplora_db::backup::vacuum_into`
//    (`VACUUM INTO`) produce un snapshot consistente sin parar el hub; `verify_sqlite_file` valida
//    el fichero. El `MockTransport` sigue para tests/dev sin Cloud.
// 2) **Transporte real (opción B, stream al Cloud).** HECHO: `erplora_server::backup::CloudBackupTransport`
//    lee el dump (TODO 1) y lo `POST`-streamea con `reqwest` a `CloudClient::backup_upload`
//    (`POST /api/v1/hub/device/backup/`, `X-Hub-Token` + `X-Hub-Id`, en claro sobre TLS); el Cloud
//    aplica SSE y guarda en S3, y su `{ s3_key, bytes }` se mapea a [`UploadOutcome`]. El server lo
//    registra cuando el hub está enrolado (hay token de máquina); si no, el Mock.
// 3) **Restore (opción B, pull del Cloud).** PARCIAL: `erplora_server::backup::restore_from_cloud`
//    descarga la copia elegida (`CloudClient::backup_download`, user-JWT; SSE transparente), la
//    escribe a un path destino y valida que es un SQLite íntegro. **TODO core/humano:** el
//    **hot-swap** del fichero vivo + reinicio/relink del pool (delicado: el modelo seguro es cerrar
//    el runtime, mover el fichero y reiniciar el proceso — backup.md §4). El listado user-scoped lo
//    sirve `CloudClient::backup_list`.
// 4) **Endpoints Django del Cloud** (upload + list/download): implementados en
//    `cloud/apps/dashboard/hubs/main/` (rama de backup); contrato fijado en `crates/cloud-client`.

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::Params;
    use serde_json::json;

    fn intent_params(backup_id: &str) -> Params {
        let mut p = Params::new();
        p.insert("backup_id".into(), json!(backup_id));
        p.insert("hub_id".into(), json!("h1"));
        p.insert("trigger".into(), json!("manual"));
        p
    }

    #[test]
    fn parses_intent_from_event_payload() {
        let intent = BackupIntent::from_event_payload(&intent_params("b1")).unwrap();
        assert_eq!(intent.backup_id, "b1");
        assert_eq!(intent.hub_id, "h1");
        assert_eq!(intent.trigger.as_deref(), Some("manual"));
    }

    #[test]
    fn intent_tolerates_missing_fields() {
        // Un payload mínimo (solo hub_id) parsea: el host completa el resto desde su contexto.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("h1"));
        let intent = BackupIntent::from_event_payload(&p).unwrap();
        assert_eq!(intent.hub_id, "h1");
        assert_eq!(intent.backup_id, "");
        assert!(intent.trigger.is_none());
    }

    #[tokio::test]
    async fn mock_transport_records_plaintext_dump() {
        let t = MockTransport::new();
        let intent = BackupIntent::from_event_payload(&intent_params("b1")).unwrap();
        let out = t.run_backup(&intent).await.unwrap();
        assert!(out.size_bytes > 0);
        assert!(out.s3_key.contains("h1"));
        let ups = t.uploads();
        assert_eq!(ups.len(), 1);
        assert_eq!(ups[0].0.backup_id, "b1");
        // El blob registrado es el dump EN CLARO (opción B: el cifrado es SSE en el Cloud, no aquí).
        assert!(String::from_utf8_lossy(&ups[0].1).contains("dump del hub h1"));
    }

    #[tokio::test]
    async fn failing_transport_errors() {
        let t = MockTransport::failing();
        let intent = BackupIntent::from_event_payload(&intent_params("b1")).unwrap();
        assert!(t.run_backup(&intent).await.is_err());
    }
}
