//! Bus de eventos en proceso. Al emitir un evento: (1) notifica al `EventSink` (→ WS) y
//! (2) ejecuta los commands suscritos de **módulos activos**. ARQUITECTURA.md §4, §5.4.
use erplora_db::{DatabaseAdapter, Params};

use crate::commands;
use crate::errors::Result;
use crate::registry::{Registry, RequestContext};

/// Despacha un evento: notifica observadores y ejecuta cada command suscrito (módulos activos).
pub fn dispatch(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    event: &str,
    payload: &Params,
    ctx: &RequestContext,
    depth: u32,
) -> Result<()> {
    // Observadores externos (p. ej. el WS del server).
    if let Some(sink) = &registry.event_sink {
        sink.emit(event, &serde_json::Value::Object(payload.clone()));
    }
    for command in registry.listeners_for(event) {
        commands::execute_at(db, registry, &command, payload, ctx, depth)?;
    }
    Ok(())
}
