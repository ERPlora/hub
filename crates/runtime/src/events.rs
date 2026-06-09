//! Notificación de eventos al observador externo (WS) — **efímera**, para UI en vivo.
//! La entrega DURABLE a los listeners de cada evento la hace el relay desde `_event_outbox`
//! (ver `outbox.rs`): at-least-once, con backoff y dead-letter. ARQUITECTURA.md §4, §5.4.
use erplora_db::Params;

use crate::registry::Registry;

/// Notifica al `EventSink` (→ WebSocket) que se emitió un evento. No garantiza entrega ni
/// dispara listeners: es solo para que la UI reaccione en vivo. Se llama **tras** el commit
/// del command emisor (o de cada entrega del relay), nunca antes.
pub fn notify_sink(registry: &Registry, event: &str, payload: &Params) {
    if let Some(sink) = &registry.event_sink {
        sink.emit(event, &serde_json::Value::Object(payload.clone()));
    }
}
