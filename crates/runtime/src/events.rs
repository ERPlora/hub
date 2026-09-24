//! Notificación de eventos al observador externo (WS) — **efímera**, para UI en vivo.
//! La entrega DURABLE a los listeners de cada evento la hace el relay desde `_event_outbox`
//! (ver `outbox.rs`): at-least-once, con backoff y dead-letter. ARQUITECTURA.md §4, §5.4.
use erplora_db::Params;

use crate::registry::{EventSource, Registry};

/// Notifica al `EventSink` (→ WebSocket) que se emitió un evento. No garantiza entrega ni
/// dispara listeners: es solo para que la UI reaccione en vivo. Se llama **tras** el commit
/// del command emisor (o de cada entrega del relay), nunca antes.
///
/// `source` says **who emitted** (hub#529). It travels with the event because the fan-out filters
/// by module and the caller is the only one who knows: here the dispatcher holds `cmd.module_id`,
/// and the core says so explicitly ([`EventSource::Core`]).
pub fn notify_sink(registry: &Registry, source: EventSource<'_>, event: &str, payload: &Params) {
    notify_sink_from(registry, source, None, event, payload);
}

/// [`notify_sink`] for an event a REQUEST caused: `client_instance` is the shell tab that sent it
/// ([`crate::RequestContext::client_instance`], hub#1980), so the live frame can say which till
/// charged the sale and only that till prints it.
pub fn notify_sink_from(
    registry: &Registry,
    source: EventSource<'_>,
    client_instance: Option<&str>,
    event: &str,
    payload: &Params,
) {
    if let Some(sink) = &registry.event_sink {
        sink.emit_from(
            source,
            client_instance,
            event,
            &serde_json::Value::Object(payload.clone()),
        );
    }
}
