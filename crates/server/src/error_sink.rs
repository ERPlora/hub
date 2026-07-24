//! Sink del **registro global de errores** (`erplora_runtime::error_registry`) que reenvía cada
//! evento al Cloud (`POST /api/v1/hub/device/error-report/`, `X-Hub-Token` + `X-Hub-Id`).
//!
//! "Todo controlado" = un único embudo: el runtime (core + módulos), el panic hook y la ruta local
//! del frontend reportan a `ErrorRegistry::global()`, y este sink es quien lo manda al Cloud. Es
//! **fire-and-forget**: `submit` lanza un `tokio::spawn` detached y vuelve al instante; un fallo de
//! red se ignora (best-effort, nunca bloquea ni hace `panic!`). Si el hub no está enrolado (sin
//! token de máquina) el evento se descarta en silencio (no hay credencial para hablar con el Cloud).
//!
//! Inyecta `hub_version` en `context` de cada evento (telemetría: qué build falló).

use cloud_client::{Auth, CloudClient};
use erplora_runtime::error_registry::{ErrorEvent, ErrorSink};

use crate::state::{HubId, MachineToken};

/// Sink que reenvía los `ErrorEvent` del registro global al Cloud. Clonable y barato (todo `Arc`/
/// valores cortos): vive tras un `Arc<dyn ErrorSink>` en el registro global del proceso.
#[derive(Clone)]
pub struct CloudErrorSink {
    cloud: CloudClient,
    hub_id: HubId,
    /// Token de máquina **vivo** (hot-reload): `X-Hub-Token`. `None` = hub sin enrolar.
    machine_token: MachineToken,
    http: reqwest::Client,
    /// Versión del build del hub, inyectada en `context.hub_version` de cada evento.
    hub_version: String,
}

impl CloudErrorSink {
    pub fn new(
        cloud_base_url: &str,
        hub_id: HubId,
        machine_token: MachineToken,
        http: reqwest::Client,
        hub_version: impl Into<String>,
    ) -> Self {
        Self {
            cloud: CloudClient::new(cloud_base_url),
            hub_id,
            machine_token,
            http,
            hub_version: hub_version.into(),
        }
    }

    /// Construye el body del contrato del Cloud a partir del `ErrorEvent`, inyectando `hub_version`
    /// en `context` y un `occurred_at` (ISO8601, RFC3339) del instante de envío.
    fn build_body(&self, event: &ErrorEvent) -> serde_json::Value {
        // Copia el contexto del evento y le añade la versión del hub (sin pisar claves del evento).
        let mut context = match &event.context {
            serde_json::Value::Object(map) => map.clone(),
            // Contexto no-objeto (no debería ocurrir): lo envolvemos para no perderlo.
            other => {
                let mut m = serde_json::Map::new();
                if !other.is_null() {
                    m.insert("value".into(), other.clone());
                }
                m
            }
        };
        context
            .entry("hub_version".to_string())
            .or_insert_with(|| serde_json::Value::String(self.hub_version.clone()));

        serde_json::json!({
            "source": event.source,
            "module_id": event.module_id,
            "error_code": event.error_code,
            "message": event.message,
            "stack": event.stack,
            "severity": event.severity,
            "context": context,
            "occurred_at": chrono_now_rfc3339(),
        })
    }
}

impl ErrorSink for CloudErrorSink {
    fn submit(&self, event: ErrorEvent) {
        // Sin token de máquina (hub sin enrolar) no hay credencial hub-scoped → descarta en silencio.
        let Some(token) = self.machine_token.read().ok().and_then(|g| g.clone()) else {
            return;
        };
        let Some(hub_id) = self.hub_id.read().ok().map(|g| g.clone()) else {
            return;
        };
        let auth = Auth::HubToken { hub_id, token };
        let req = self.cloud.report_error(&auth);
        let body = self.build_body(&event);
        let http = self.http.clone();

        // Fire-and-forget: no bloquea al llamador (puede ser un panic hook). Cualquier fallo se ignora.
        tokio::spawn(async move {
            let mut rb = http.post(&req.url).json(&body);
            for (k, v) in req.headers {
                rb = rb.header(k, v);
            }
            // Ignoramos el resultado a propósito: el reporte de errores es best-effort.
            let _ = rb.send().await;
        });
    }
}

/// `now()` en RFC3339 (ISO8601). Aislado para no depender de chrono en más sitios del server; el
/// runtime ya trae chrono, pero el server no lo lista como dep directa, así que usamos `time`-libre.
fn chrono_now_rfc3339() -> String {
    // Sin chrono en el server: formateamos el epoch como ISO8601 UTC a mano (suficiente para el
    // contrato `occurred_at`, que el Cloud reparsea). Si el reloj falla, devolvemos el epoch.
    let now = std::time::SystemTime::now();
    let secs = now
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format_epoch_utc(secs)
}

/// Formatea segundos epoch como `YYYY-MM-DDTHH:MM:SSZ` (UTC). Algoritmo civil de Howard Hinnant.
fn format_epoch_utc(secs: u64) -> String {
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    let (hh, mm, ss) = (rem / 3600, (rem % 3600) / 60, rem % 60);

    // days since 1970-01-01 → civil date (algoritmo de days_from_civil invertido).
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097; // [0, 146096]
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365; // [0, 399]
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); // [0, 365]
    let mp = (5 * doy + 2) / 153; // [0, 11]
    let d = doy - (153 * mp + 2) / 5 + 1; // [1, 31]
    let m = if mp < 10 { mp + 3 } else { mp - 9 }; // [1, 12]
    let y = if m <= 2 { y + 1 } else { y };

    format!("{y:04}-{m:02}-{d:02}T{hh:02}:{mm:02}:{ss:02}Z")
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_runtime::error_registry::{severity, source};
    use std::sync::{Arc, RwLock};

    fn sink() -> CloudErrorSink {
        CloudErrorSink::new(
            "https://erplora.com",
            Arc::new(RwLock::new("h1".into())),
            Arc::new(RwLock::new(Some("tok".into()))),
            reqwest::Client::new(),
            "v1.2.3",
        )
    }

    #[test]
    fn build_body_matches_contract_and_injects_hub_version() {
        let event = ErrorEvent::new(source::MODULE, "wasm", "kaboom", severity::UNEXPECTED)
            .with_module("inventory")
            .with_stack("at foo()")
            .with_context(serde_json::json!({ "command": "inventory.products.create" }));
        let body = sink().build_body(&event);

        assert_eq!(body["source"], "module");
        assert_eq!(body["module_id"], "inventory");
        assert_eq!(body["error_code"], "wasm");
        assert_eq!(body["message"], "kaboom");
        assert_eq!(body["stack"], "at foo()");
        assert_eq!(body["severity"], "unexpected");
        assert_eq!(body["context"]["command"], "inventory.products.create");
        assert_eq!(body["context"]["hub_version"], "v1.2.3");
        assert!(body["occurred_at"].is_string());
    }

    #[test]
    fn build_body_null_module_id_for_hub_source() {
        let event = ErrorEvent::new(source::HUB, "panic", "boom", severity::UNEXPECTED);
        let body = sink().build_body(&event);
        assert_eq!(body["source"], "hub");
        assert!(body["module_id"].is_null());
        assert!(body["stack"].is_null());
    }

    #[test]
    fn epoch_formatting_is_iso8601() {
        // 2026-06-22T00:00:00Z = 1782604800 (sanity de un día conocido).
        assert_eq!(format_epoch_utc(0), "1970-01-01T00:00:00Z");
        assert_eq!(format_epoch_utc(1_000_000_000), "2001-09-09T01:46:40Z");
    }
}
