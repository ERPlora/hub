//! erplora-sync — Cliente de eventos en vivo del WebSocket `/ws` (ARQUITECTURA.md §7.5, §7.7).
//!
//! Consume los mensajes JSON `{ "name": "...", "payload": {...} }` que el server emite por
//! `/ws` (ver `erplora-server` → `WsEvent`), los deserializa a [`Event`] y los entrega a un
//! [`EventHandler`], con **reconexión automática** y backoff exponencial.
//!
//! El transporte de stream es **inyectable** ([`EventStream`]): los tests inyectan un stream en
//! memoria y el binario real lo implementa con un cliente WS (tungstenite/tokio-tungstenite),
//! que NO es dependencia obligatoria de este crate. Igual para la espera entre reconexiones
//! ([`Sleeper`]): el diseño es síncrono para ser simple y testeable sin red ni tokio.

use std::time::Duration;

use serde::Deserialize;
use serde_json::Value as Json;

/// Errores del cliente de sincronización.
#[derive(Debug, thiserror::Error)]
pub enum SyncError {
    /// El stream se cerró de forma limpia.
    #[error("stream closed")]
    Closed,
    /// Un mensaje no pudo deserializarse a [`Event`].
    #[error("decode error: {0}")]
    Decode(String),
    /// Error del transporte subyacente (red, WS, etc.).
    #[error("transport error: {0}")]
    Transport(String),
}

/// Evento recibido del server. Reusa el shape de `WsEvent` (`{ name, payload }`) sin depender
/// de `erplora-server`.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct Event {
    /// Nombre del evento (p. ej. `pos.sale.completed`).
    pub name: String,
    /// Payload arbitrario asociado al evento.
    pub payload: Json,
}

/// Abstracción de una fuente de mensajes (líneas/frames de texto).
///
/// Cada llamada devuelve el siguiente mensaje crudo (un JSON serializado). `None` indica que
/// el stream se cerró y debe reconectarse.
pub trait EventStream {
    /// Siguiente mensaje del stream. `None` = stream cerrado.
    fn next_message(&mut self) -> Option<Result<String, SyncError>>;
}

/// Receptor de eventos ya parseados.
pub trait EventHandler {
    /// Llamado una vez por cada [`Event`] válido recibido.
    fn on_event(&mut self, ev: &Event);
}

/// Adapta cualquier `FnMut(&Event)` a [`EventHandler`].
impl<F: FnMut(&Event)> EventHandler for F {
    fn on_event(&mut self, ev: &Event) {
        self(ev)
    }
}

/// Abstracción de la espera entre reconexiones, para poder saltarla en tests.
pub trait Sleeper {
    /// Bloquea durante `dur`.
    fn sleep(&mut self, dur: Duration);
}

/// [`Sleeper`] real que duerme el hilo actual.
#[derive(Debug, Default, Clone, Copy)]
pub struct ThreadSleeper;

impl Sleeper for ThreadSleeper {
    fn sleep(&mut self, dur: Duration) {
        std::thread::sleep(dur);
    }
}

/// Política de backoff exponencial con tope.
#[derive(Debug, Clone)]
pub struct Backoff {
    initial: Duration,
    max: Duration,
    factor: u32,
    current: Duration,
}

impl Backoff {
    /// Crea un backoff que empieza en `initial`, multiplica por `factor` y topa en `max`.
    pub fn new(initial: Duration, max: Duration, factor: u32) -> Self {
        Self { initial, max, factor, current: initial }
    }

    /// Devuelve el delay actual y avanza el siguiente (×`factor`, topado en `max`).
    pub fn next_delay(&mut self) -> Duration {
        let delay = self.current;
        let next = self.current.saturating_mul(self.factor.max(1));
        self.current = next.min(self.max);
        delay
    }

    /// Reinicia la secuencia al delay inicial.
    pub fn reset(&mut self) {
        self.current = self.initial;
    }
}

impl Default for Backoff {
    /// Por defecto: 250ms → ×2 → tope 30s.
    fn default() -> Self {
        Self::new(Duration::from_millis(250), Duration::from_secs(30), 2)
    }
}

/// Cliente que bombea eventos de un [`EventStream`] hacia un [`EventHandler`].
#[derive(Debug, Default, Clone, Copy)]
pub struct EventClient;

impl EventClient {
    /// Crea un cliente.
    pub fn new() -> Self {
        Self
    }

    /// Lee mensajes del `stream`, parsea cada uno a [`Event`] y se lo pasa al `handler`.
    ///
    /// Los mensajes que no parsean (JSON inválido o shape incorrecto) se descartan; un error
    /// de transporte también descarta ese mensaje. Termina cuando el stream devuelve `None`.
    pub fn pump(&self, stream: &mut dyn EventStream, handler: &mut dyn EventHandler) {
        while let Some(msg) = stream.next_message() {
            let raw = match msg {
                Ok(raw) => raw,
                Err(_e) => {
                    // Error de transporte puntual: descartamos este mensaje y seguimos.
                    continue;
                }
            };
            match serde_json::from_str::<Event>(&raw) {
                Ok(ev) => handler.on_event(&ev),
                Err(_e) => {
                    // Mensaje inválido: lo ignoramos a propósito (no abortamos el pump).
                    continue;
                }
            }
        }
    }
}

/// Conecta, bombea hasta que el stream muera, espera el backoff y reconecta.
///
/// - `connect` produce un nuevo [`EventStream`] en cada intento (inyectable en tests).
/// - `handler` recibe los eventos de todas las sesiones.
/// - `backoff` controla la espera entre reconexiones; se resetea tras un pump con éxito.
/// - `sleeper` ejecuta la espera (mock en tests para no dormir).
/// - `max_attempts = Some(n)` limita el número de conexiones; `None` corre indefinidamente.
pub fn run_with_reconnect(
    mut connect: impl FnMut() -> Result<Box<dyn EventStream>, SyncError>,
    handler: &mut dyn EventHandler,
    backoff: &mut Backoff,
    sleeper: &mut dyn Sleeper,
    max_attempts: Option<usize>,
) {
    let client = EventClient::new();
    let mut attempts = 0usize;

    loop {
        if let Some(max) = max_attempts {
            if attempts >= max {
                break;
            }
        }
        attempts += 1;

        match connect() {
            Ok(mut stream) => {
                client.pump(stream.as_mut(), handler);
                // Sesión consumida con éxito: la próxima reconexión parte del delay inicial.
                backoff.reset();
            }
            Err(_e) => {
                // No se pudo conectar; el backoff sigue creciendo abajo.
            }
        }

        // ¿Hay otro intento por delante? Si no, no dormimos de más.
        let will_retry = match max_attempts {
            Some(max) => attempts < max,
            None => true,
        };
        if will_retry {
            sleeper.sleep(backoff.next_delay());
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Transporte WebSocket real (feature `ws`)
// ─────────────────────────────────────────────────────────────────────────────
//
// Implementación concreta de [`EventStream`] sobre una conexión WebSocket de verdad
// (`tungstenite`, sobre rustls con raíces webpki — sin OpenSSL del sistema).
//
// Esta es la pieza que inyectan los **binarios de producción** (`erplora-server` y, en el
// futuro, `apps/tauri`): en arranque llaman a [`connect_ws`] para abrir el socket `/ws` y
// pasan el resultado como `connect` a [`run_with_reconnect`], que reconecta con backoff si
// el stream muere. Los tests siguen usando el `MockStream` en memoria, así que el build por
// defecto del workspace NO arrastra tungstenite (queda detrás de la feature `ws`). El diseño
// es **bloqueante/síncrono** a propósito: encaja con `EventStream` sin requerir tokio.
#[cfg(feature = "ws")]
mod ws {
    use super::{EventStream, SyncError};
    use tungstenite::stream::MaybeTlsStream;
    use tungstenite::{Message, WebSocket};

    /// [`EventStream`] real sobre una conexión `tungstenite` (texto = mensaje JSON).
    pub struct WsStream {
        socket: WebSocket<MaybeTlsStream<std::net::TcpStream>>,
    }

    impl WsStream {
        /// Envuelve un socket tungstenite ya conectado.
        pub fn new(socket: WebSocket<MaybeTlsStream<std::net::TcpStream>>) -> Self {
            Self { socket }
        }

        /// Cierra el socket de forma limpia (best-effort).
        pub fn close(&mut self) {
            let _ = self.socket.close(None);
        }
    }

    impl EventStream for WsStream {
        fn next_message(&mut self) -> Option<Result<String, SyncError>> {
            loop {
                match self.socket.read() {
                    Ok(Message::Text(txt)) => return Some(Ok(txt)),
                    // Binario: lo entregamos como texto si es UTF-8 válido; si no, lo saltamos.
                    Ok(Message::Binary(bin)) => match String::from_utf8(bin) {
                        Ok(txt) => return Some(Ok(txt)),
                        Err(_) => continue,
                    },
                    // Ping/Pong/frames de control: tungstenite ya responde a Ping
                    // automáticamente; seguimos leyendo el siguiente frame de datos.
                    Ok(Message::Ping(_)) | Ok(Message::Pong(_)) | Ok(Message::Frame(_)) => continue,
                    // Cierre limpio del servidor: fin de stream → reconectar.
                    Ok(Message::Close(_)) => return None,
                    // El otro extremo cerró la conexión sin handshake de cierre: fin de stream.
                    Err(tungstenite::Error::ConnectionClosed)
                    | Err(tungstenite::Error::AlreadyClosed) => return None,
                    // Cualquier otro error de red lo reportamos como transporte.
                    Err(e) => return Some(Err(SyncError::Transport(e.to_string()))),
                }
            }
        }
    }

    /// Abre una conexión WebSocket a `url` (`ws://…` o `wss://…`) y la envuelve en un
    /// [`WsStream`] listo para [`run_with_reconnect`].
    ///
    /// Pensado para usarse como el `connect` de `run_with_reconnect`:
    /// ```no_run
    /// # use erplora_sync::{Backoff, ThreadSleeper, EventStream, SyncError, connect_ws, run_with_reconnect};
    /// let url = "wss://hub.erplora.com/ws";
    /// let mut backoff = Backoff::default();
    /// let mut sleeper = ThreadSleeper;
    /// let mut handler = |ev: &erplora_sync::Event| println!("{}", ev.name);
    /// run_with_reconnect(
    ///     || connect_ws(url).map(|s| Box::new(s) as Box<dyn EventStream>),
    ///     &mut handler,
    ///     &mut backoff,
    ///     &mut sleeper,
    ///     None,
    /// );
    /// ```
    pub fn connect_ws(url: &str) -> Result<WsStream, SyncError> {
        let (socket, _resp) =
            tungstenite::connect(url).map_err(|e| SyncError::Transport(e.to_string()))?;
        Ok(WsStream::new(socket))
    }
}

#[cfg(feature = "ws")]
pub use ws::{connect_ws, WsStream};

#[cfg(test)]
mod tests {
    use super::*;

    /// Stream en memoria: entrega mensajes pre-cargados y luego `None`.
    struct MockStream {
        messages: std::vec::IntoIter<Result<String, SyncError>>,
    }

    impl MockStream {
        fn new(msgs: Vec<Result<String, SyncError>>) -> Self {
            Self { messages: msgs.into_iter() }
        }
    }

    impl EventStream for MockStream {
        fn next_message(&mut self) -> Option<Result<String, SyncError>> {
            self.messages.next()
        }
    }

    /// Sleeper que cuenta llamadas sin dormir.
    struct MockSleeper {
        count: usize,
    }

    impl Sleeper for MockSleeper {
        fn sleep(&mut self, _dur: Duration) {
            self.count += 1;
        }
    }

    /// Handler que acumula los eventos recibidos.
    #[derive(Default)]
    struct Collector {
        events: Vec<Event>,
    }

    impl EventHandler for Collector {
        fn on_event(&mut self, ev: &Event) {
            self.events.push(ev.clone());
        }
    }

    #[test]
    fn pump_parses_valid_and_drops_invalid() {
        let mut stream = MockStream::new(vec![
            Ok(r#"{"name":"pos.sale.completed","payload":{"id":1}}"#.into()),
            Ok(r#"{"name":"inventory.low_stock","payload":["sku-1","sku-2"]}"#.into()),
            Ok("this is not json".into()),
            Ok(r#"{"name":"hub.ready","payload":null}"#.into()),
        ]);
        let mut collector = Collector::default();
        let client = EventClient::new();

        client.pump(&mut stream, &mut collector);

        assert_eq!(collector.events.len(), 3, "el mensaje inválido debe descartarse");
        assert_eq!(collector.events[0].name, "pos.sale.completed");
        assert_eq!(collector.events[0].payload, serde_json::json!({"id": 1}));
        assert_eq!(collector.events[1].name, "inventory.low_stock");
        assert_eq!(collector.events[1].payload, serde_json::json!(["sku-1", "sku-2"]));
        assert_eq!(collector.events[2].name, "hub.ready");
        assert_eq!(collector.events[2].payload, Json::Null);
    }

    #[test]
    fn pump_skips_transport_errors() {
        let mut stream = MockStream::new(vec![
            Err(SyncError::Transport("blip".into())),
            Ok(r#"{"name":"ok","payload":{}}"#.into()),
        ]);
        let mut collector = Collector::default();
        EventClient::new().pump(&mut stream, &mut collector);

        assert_eq!(collector.events.len(), 1);
        assert_eq!(collector.events[0].name, "ok");
    }

    #[test]
    fn pump_accepts_fnmut_handler() {
        let mut stream =
            MockStream::new(vec![Ok(r#"{"name":"x","payload":1}"#.into())]);
        let mut seen = Vec::new();
        let mut handler = |ev: &Event| seen.push(ev.name.clone());

        EventClient::new().pump(&mut stream, &mut handler);
        assert_eq!(seen, vec!["x".to_string()]);
    }

    #[test]
    fn backoff_grows_exponentially_and_caps() {
        let mut b = Backoff::new(
            Duration::from_millis(250),
            Duration::from_secs(30),
            2,
        );
        assert_eq!(b.next_delay(), Duration::from_millis(250));
        assert_eq!(b.next_delay(), Duration::from_millis(500));
        assert_eq!(b.next_delay(), Duration::from_millis(1000));
        assert_eq!(b.next_delay(), Duration::from_millis(2000));
        assert_eq!(b.next_delay(), Duration::from_millis(4000));
        assert_eq!(b.next_delay(), Duration::from_millis(8000));
        assert_eq!(b.next_delay(), Duration::from_millis(16000));
        // 32000ms toparía en 30000ms.
        assert_eq!(b.next_delay(), Duration::from_secs(30));
        // Se queda en el tope.
        assert_eq!(b.next_delay(), Duration::from_secs(30));
        assert_eq!(b.next_delay(), Duration::from_secs(30));
    }

    #[test]
    fn backoff_reset_returns_to_initial() {
        let mut b = Backoff::new(
            Duration::from_millis(250),
            Duration::from_secs(30),
            2,
        );
        let _ = b.next_delay();
        let _ = b.next_delay();
        assert_ne!(b.next_delay(), Duration::from_millis(250));
        b.reset();
        assert_eq!(b.next_delay(), Duration::from_millis(250));
    }

    #[test]
    fn run_with_reconnect_loops_max_attempts_and_accumulates_events() {
        let mut session = 0usize;
        // Cada conexión produce un stream que muere rápido tras un único evento.
        let connect = move || -> Result<Box<dyn EventStream>, SyncError> {
            session += 1;
            let msg = format!(r#"{{"name":"session","payload":{session}}}"#);
            Ok(Box::new(MockStream::new(vec![Ok(msg)])))
        };

        let mut collector = Collector::default();
        // Delays de 0 + backoff irrelevante porque el sleeper no duerme.
        let mut backoff = Backoff::new(Duration::ZERO, Duration::ZERO, 2);
        let mut sleeper = MockSleeper { count: 0 };

        run_with_reconnect(
            connect,
            &mut collector,
            &mut backoff,
            &mut sleeper,
            Some(3),
        );

        // connect se llamó 3 veces → 3 eventos, uno por sesión.
        assert_eq!(collector.events.len(), 3);
        assert_eq!(collector.events[0].payload, serde_json::json!(1));
        assert_eq!(collector.events[1].payload, serde_json::json!(2));
        assert_eq!(collector.events[2].payload, serde_json::json!(3));
        // Entre 3 intentos hay 2 esperas (no se duerme tras el último).
        assert_eq!(sleeper.count, 2);
    }

    #[test]
    fn run_with_reconnect_retries_after_connect_failure() {
        let mut attempt = 0usize;
        let connect = move || -> Result<Box<dyn EventStream>, SyncError> {
            attempt += 1;
            if attempt == 1 {
                Err(SyncError::Transport("refused".into()))
            } else {
                Ok(Box::new(MockStream::new(vec![Ok(
                    r#"{"name":"up","payload":true}"#.into(),
                )])))
            }
        };

        let mut collector = Collector::default();
        let mut backoff = Backoff::new(Duration::ZERO, Duration::ZERO, 2);
        let mut sleeper = MockSleeper { count: 0 };

        run_with_reconnect(
            connect,
            &mut collector,
            &mut backoff,
            &mut sleeper,
            Some(2),
        );

        // El primer intento falló (0 eventos), el segundo trajo 1 evento.
        assert_eq!(collector.events.len(), 1);
        assert_eq!(collector.events[0].name, "up");
    }
}
