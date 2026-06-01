//! Estado compartido del server: el runtime (tras un lock) + el canal de eventos para WS.
use std::sync::{Arc, Mutex};

use erplora_runtime::{EventSink, Runtime};
use serde_json::Value as Json;
use tokio::sync::broadcast;

/// Evento reenviado a los clientes WebSocket.
#[derive(Clone, Debug, serde::Serialize)]
pub struct WsEvent {
    pub name: String,
    pub payload: Json,
}

/// Implementa `EventSink` del runtime publicando en un canal broadcast (→ WebSocket).
#[derive(Debug)]
pub struct BroadcastSink {
    tx: broadcast::Sender<WsEvent>,
}

impl EventSink for BroadcastSink {
    fn emit(&self, event: &str, payload: &Json) {
        // Si no hay suscriptores, `send` falla; lo ignoramos a propósito.
        let _ = self.tx.send(WsEvent { name: event.to_string(), payload: payload.clone() });
    }
}

/// Estado de la app Axum. El runtime no es `Sync` para mutación, así que va tras un `Mutex`;
/// para 1–30 usuarios por hub (ARQUITECTURA.md §7.5) es más que suficiente.
#[derive(Clone)]
pub struct AppState {
    pub runtime: Arc<Mutex<Runtime>>,
    pub events: broadcast::Sender<WsEvent>,
}

impl AppState {
    /// Crea el estado y conecta el `EventSink` del runtime al canal broadcast.
    pub fn new(mut runtime: Runtime) -> Self {
        let (tx, _rx) = broadcast::channel::<WsEvent>(256);
        let sink = Arc::new(BroadcastSink { tx: tx.clone() });
        runtime.set_event_sink(sink);
        Self { runtime: Arc::new(Mutex::new(runtime)), events: tx }
    }
}
