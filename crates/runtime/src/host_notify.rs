//! Capacidad de host `host.notify(channel, payload)` (ADR-0012): envío externo de alto nivel
//! (`email`/`sms`/`whatsapp`) que el **runtime** ejecuta porque el WASM no tiene red.
//!
//! **Entrega vía Outbox (espejo de `outbox.rs`)**: un command de módulo NO envía inline. Emite
//! un evento `*.reminder.due` cuyo payload es la intención `{channel, to, template, vars}`; el
//! runtime registra un **listener-host** sintético sobre ese evento y el **relay** del outbox lo
//! entrega con reintentos/backoff/dead-letter **gratis** (la misma máquina ya probada). Aquí no
//! se reimplementan los reintentos: solo el cliente de cada canal + el routing del secreto.
//!
//! Routing del secreto por canal (ADR-0012, columna del humano — aquí solo se implementa):
//!  - **tenant** (SMTP propio, WhatsApp self-hosted) → secreto **local** cifrado del hub; el host
//!    llama directo, sin cuota ERPlora.
//!  - **WhatsApp premium de ERPlora** → la llamada sale **por el proxy de Cloud** (como los LLM);
//!    Cloud aplica `check_quota` (ADR-0006), inyecta el token de Meta y bloquea al agotar cuota.
//!
//! El **cliente real** (SMTP/SMS/HTTP) es una **decisión de dependencia del humano** (lettre,
//! reqwest…). Aquí se define el TRAIT [`NotifyTransport`] + un [`MockTransport`] que registra los
//! envíos en memoria, de modo que la mecánica Outbox (reintentos/dead-letter) queda real y
//! testeada. La integración real del transporte queda como TODO (ver más abajo).
use std::sync::{Arc, Mutex};

use serde::Deserialize;
use serde_json::Value as Json;

use crate::errors::{Result, RuntimeError};

/// Canal de notificación de alto nivel. Conjunto **cerrado** (ADR-0012: añadir uno = tocar el
/// runtime). El módulo declara qué canal usa en `notify.channels` del manifest, NO dónde viven
/// los secretos/cuota.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Channel {
    Email,
    Sms,
    Whatsapp,
}

impl Channel {
    /// Parsea el nombre del canal (`email`/`sms`/`whatsapp`).
    pub fn parse(s: &str) -> Option<Channel> {
        match s {
            "email" => Some(Channel::Email),
            "sms" => Some(Channel::Sms),
            "whatsapp" => Some(Channel::Whatsapp),
            _ => None,
        }
    }
}

/// La intención de notificación que un command emite en el payload del evento `*.reminder.due`.
/// El módulo de negocio solo construye esto; el host resuelve el transporte y el secreto.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct NotifyIntent {
    pub channel: Channel,
    /// Destinatario (email, teléfono E.164, wa_id…). Lo valida el transporte concreto.
    pub to: String,
    /// Plantilla a renderizar (el catálogo de plantillas lo resuelve el transporte/Cloud).
    pub template: String,
    /// Variables de la plantilla.
    #[serde(default)]
    pub vars: Json,
}

impl NotifyIntent {
    /// Extrae la intención del payload de un evento `*.reminder.due`. `Err` si falta/!encaja.
    pub fn from_event_payload(payload: &erplora_db::Params) -> Result<NotifyIntent> {
        let value = Json::Object(payload.clone());
        serde_json::from_value(value).map_err(|e| {
            RuntimeError::InvalidPayload {
                name: "host.notify".to_string(),
                detail: format!("intención de notificación inválida: {e}"),
            }
        })
    }
}

/// De dónde sale el secreto/transporte de un canal (ADR-0012). Lo decide el host por canal y por
/// `tier` del módulo, no el módulo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Routing {
    /// Secreto local cifrado del hub; el host llama directo (sin cuota ERPlora).
    Tenant,
    /// Proxy de Cloud con `check_quota` (WhatsApp premium de ERPlora).
    CloudProxy,
}

/// Resultado de un intento de envío. `Sent` = entregado al proveedor; `QuotaExceeded` = Cloud
/// bloqueó por cuota agotada (no se reintenta: el relay lo manda a dead-letter como fallo
/// terminal cuando el transporte lo marca así devolviendo `Err` con este detalle).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SendOutcome {
    Sent,
}

/// Transporte de notificación: el cliente real de un canal. **Trait inyectable** para no atar el
/// runtime a una dependencia concreta de SMTP/SMS/HTTP (decisión del humano). El host elige el
/// `Routing` y llama aquí; un `Err` se traduce en reintento del relay (backoff) y, tras
/// `MAX_ATTEMPTS`, dead-letter — exactamente como un listener que falla.
#[async_trait::async_trait]
pub trait NotifyTransport: Send + Sync + std::fmt::Debug {
    /// Envía `intent` por `routing`. `Ok(SendOutcome::Sent)` si se entregó al proveedor; `Err`
    /// para que el relay reintente (fallo transitorio) o, si es terminal (cuota agotada / canal
    /// no configurado), lo registre como fallo (acabará en dead-letter tras los reintentos).
    async fn send(&self, intent: &NotifyIntent, routing: Routing) -> Result<SendOutcome>;
}

/// Decide el routing de un canal según el `tier` del módulo (ADR-0012/ADR-0006). Hoy: WhatsApp en
/// un módulo `premium` de ERPlora sale por el proxy de Cloud (cuota); el resto (email/sms y
/// WhatsApp self-hosted del tenant) usa el secreto local. El `tier` lo conoce el host (no el
/// manifest del Hub: la clasificación vive en Cloud, ADR-0007) — se pasa como hint.
pub fn route_channel(channel: Channel, premium_whatsapp: bool) -> Routing {
    match channel {
        Channel::Whatsapp if premium_whatsapp => Routing::CloudProxy,
        _ => Routing::Tenant,
    }
}

/// Transporte **mock** para tests y arranque sin transporte real configurado: registra cada envío
/// en memoria y devuelve `Sent`. Permite probar la mecánica Outbox (reintentos/dead-letter) sin
/// red. La integración real (SMTP/SMS/WhatsApp) la conecta el host sustituyendo este transporte.
#[derive(Debug, Default, Clone)]
pub struct MockTransport {
    sent: Arc<Mutex<Vec<(NotifyIntent, Routing)>>>,
    /// Si `true`, `send` devuelve `Err` (para probar el camino de reintento/dead-letter del relay).
    fail: bool,
}

impl MockTransport {
    pub fn new() -> Self {
        Self::default()
    }

    /// Variante que siempre falla (para tests del backoff/dead-letter del relay).
    pub fn failing() -> Self {
        Self { sent: Arc::default(), fail: true }
    }

    /// Envíos registrados (clon) — para aserciones en tests.
    pub fn sent(&self) -> Vec<(NotifyIntent, Routing)> {
        self.sent.lock().map(|g| g.clone()).unwrap_or_default()
    }
}

#[async_trait::async_trait]
impl NotifyTransport for MockTransport {
    async fn send(&self, intent: &NotifyIntent, routing: Routing) -> Result<SendOutcome> {
        if self.fail {
            return Err(RuntimeError::Notify("transporte mock configurado para fallar".into()));
        }
        if let Ok(mut g) = self.sent.lock() {
            g.push((intent.clone(), routing));
        }
        Ok(SendOutcome::Sent)
    }
}

// ── TODO (decisión de dependencia del humano) ────────────────────────────────────────────────
// El transporte REAL requiere dependencias nuevas que son columna del humano:
//   - email  → `lettre` (SMTP) con el secreto SMTP local cifrado del hub.
//   - sms    → cliente HTTP (`reqwest`, ya en el workspace de server) al proveedor del tenant.
//   - whatsapp tenant   → Graph API de Meta (HTTP) con el token local cifrado del hub.
//   - whatsapp premium  → `erplora-cloud-client::notify_whatsapp` (proxy Cloud, check_quota).
// El cifrado del secreto local del hub debe seguir el patrón de ADR-0016 (Fernet/master key en
// env), igual que el PKCS#12 de verifactu. NO se inventa aquí: se deja el trait y el mock.

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::Params;
    use serde_json::json;

    fn intent_params(channel: &str) -> Params {
        let mut p = Params::new();
        p.insert("channel".into(), json!(channel));
        p.insert("to".into(), json!("a@b.com"));
        p.insert("template".into(), json!("appointment_reminder"));
        p.insert("vars".into(), json!({"when": "10:00"}));
        p
    }

    #[test]
    fn parses_intent_from_event_payload() {
        let intent = NotifyIntent::from_event_payload(&intent_params("email")).unwrap();
        assert_eq!(intent.channel, Channel::Email);
        assert_eq!(intent.to, "a@b.com");
        assert_eq!(intent.template, "appointment_reminder");
    }

    #[test]
    fn rejects_unknown_channel() {
        let err = NotifyIntent::from_event_payload(&intent_params("carrier_pigeon")).unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidPayload { .. }), "got {err:?}");
    }

    #[test]
    fn routing_premium_whatsapp_goes_to_cloud() {
        assert_eq!(route_channel(Channel::Whatsapp, true), Routing::CloudProxy);
        assert_eq!(route_channel(Channel::Whatsapp, false), Routing::Tenant);
        assert_eq!(route_channel(Channel::Email, true), Routing::Tenant);
        assert_eq!(route_channel(Channel::Sms, true), Routing::Tenant);
    }

    #[tokio::test]
    async fn mock_transport_records_send() {
        let t = MockTransport::new();
        let intent = NotifyIntent::from_event_payload(&intent_params("sms")).unwrap();
        let out = t.send(&intent, Routing::Tenant).await.unwrap();
        assert_eq!(out, SendOutcome::Sent);
        assert_eq!(t.sent().len(), 1);
        assert_eq!(t.sent()[0].1, Routing::Tenant);
    }

    #[tokio::test]
    async fn failing_transport_errors() {
        let t = MockTransport::failing();
        let intent = NotifyIntent::from_event_payload(&intent_params("email")).unwrap();
        assert!(t.send(&intent, Routing::Tenant).await.is_err());
    }
}
