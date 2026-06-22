//! Traits de periférico + impresora ESC/POS por red (TCP:9100) con reintentos.
//!
//! **Contrato (columna del humano — esta capa la propuso la IA, ajústala):** este módulo
//! introduce dos traits mínimos para que el resto del crate (cola, drawer, dispatcher del bridge)
//! dependa de una *interfaz* en vez de funciones sueltas, y para poder testear con mocks:
//!
//!   - [`Printer`]  — envía bytes ESC/POS ya renderizados (`escpos::render_document`) a un
//!     destino y reporta su estado de alcanzabilidad.
//!   - [`CashDrawer`] — abre el cajón (kick ESC/POS) por el socket de la impresora.
//!
//! Decisiones de diseño que el humano debe revisar:
//!   1. **El `Printer` recibe bytes ya renderizados, no un documento tipado.** El render
//!      (`document_type` + JSON → bytes) vive en `escpos.rs`; mantenerlo fuera del trait deja
//!      el trait agnóstico del formato y reusable para test pages / raw passthrough.
//!   2. **Reintento con backoff dentro de la impresora** (`NetworkPrinter::print_with_retry`),
//!      además del que ya hace `queue::PrintQueue`. Son dos niveles: la cola reintenta trabajos
//!      completos entre ellos; la impresora reintenta el socket de **un** envío. La cola puede
//!      construirse sobre `Printer` en el futuro (hoy abre el socket directamente).
//!   3. **`status()` es una sonda TCP best-effort**, no lee el estado real ESC/POS de la
//!      impresora (DLE EOT) — red-only + impresoras baratas no siempre lo soportan. Si el humano
//!      quiere estado de papel/tapa real, se amplía aquí.
//!   4. Los traits son **async** (`async_trait` no se usa; se devuelven futures vía métodos
//!      `async fn` en trait, estables desde Rust 1.75). Mockeables con un listener TCP local.

use std::time::Duration;

use tokio::io::AsyncWriteExt;
use tokio::net::TcpStream;

use crate::discovery::NetworkTarget;
use crate::drawer::kick_command;
use crate::{PeripheralError, Result};

/// Política de reintentos de un envío al socket de la impresora.
///
/// Espejo de [`crate::queue::RetryPolicy`] pero a nivel de **un envío** (la cola la usa a nivel de
/// **trabajo**). Se mantiene separada para poder afinar cada nivel por su cuenta.
#[derive(Debug, Clone, Copy)]
pub struct PrinterRetry {
    /// Intentos totales (>= 1). Con `1` no hay reintento.
    pub max_attempts: u32,
    /// Espera inicial entre intentos.
    pub base_backoff: Duration,
    /// Multiplicador del backoff por intento (backoff exponencial). `1.0` = backoff constante.
    pub backoff_factor: u32,
    /// Timeout del `connect` TCP por intento.
    pub connect_timeout: Duration,
}

impl Default for PrinterRetry {
    fn default() -> Self {
        Self {
            max_attempts: 3,
            base_backoff: Duration::from_millis(200),
            backoff_factor: 2,
            connect_timeout: Duration::from_secs(3),
        }
    }
}

impl PrinterRetry {
    /// Backoff a esperar tras el intento `attempt` (1-indexed): `base * factor^(attempt-1)`.
    fn backoff_for(&self, attempt: u32) -> Duration {
        let exp = self.backoff_factor.saturating_pow(attempt.saturating_sub(1));
        self.base_backoff.saturating_mul(exp)
    }
}

/// Estado de alcanzabilidad de un periférico (sonda best-effort, no estado ESC/POS real).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrinterStatus {
    /// Responde a la sonda TCP.
    Ready,
    /// No alcanzable (apagada, cable, IP cambiada por DHCP).
    Offline,
}

impl PrinterStatus {
    /// Cadena del protocolo (`PrinterInfo.status`).
    pub fn as_wire(self) -> &'static str {
        match self {
            PrinterStatus::Ready => "ready",
            PrinterStatus::Offline => "offline",
        }
    }
}

/// Impresora: envía bytes ESC/POS ya renderizados y reporta su estado.
///
/// **Trait propuesto por la IA — el humano lo ajusta.** Async-en-trait (Rust ≥1.75); las impls
/// reales (`NetworkPrinter`) y los mocks de test lo implementan por igual.
pub trait Printer {
    /// Envía `bytes` (ESC/POS ya renderizado) a la impresora. Reintenta según su política.
    fn print(&self, bytes: &[u8]) -> impl std::future::Future<Output = Result<()>> + Send;

    /// Sonda de estado (best-effort, TCP).
    fn status(&self) -> impl std::future::Future<Output = PrinterStatus> + Send;
}

/// Cajón portamonedas: abre el cajón vía kick ESC/POS por el socket de la impresora.
///
/// **Trait propuesto por la IA — el humano lo ajusta.**
pub trait CashDrawer {
    /// Abre el cajón conectado a la impresora. `pin` = 2 (DK pin 2) por defecto; otro → pin 5.
    fn open(&self, pin: u8) -> impl std::future::Future<Output = Result<()>> + Send;
}

/// Impresora ESC/POS por red (TCP, puerto 9100). Implementa [`Printer`] y [`CashDrawer`]: el cajón
/// se abre por el mismo socket de la impresora a la que está conectado (estándar POS).
#[derive(Debug, Clone)]
pub struct NetworkPrinter {
    target: NetworkTarget,
    retry: PrinterRetry,
}

impl NetworkPrinter {
    /// Crea una impresora apuntando a `target` con la política de reintentos por defecto.
    pub fn new(target: NetworkTarget) -> Self {
        Self { target, retry: PrinterRetry::default() }
    }

    /// Igual que `new` pero con una política de reintentos explícita.
    pub fn with_retry(target: NetworkTarget, retry: PrinterRetry) -> Self {
        Self { target, retry }
    }

    /// Destino al que apunta.
    pub fn target(&self) -> &NetworkTarget {
        &self.target
    }

    /// Abre el socket (con timeout) y escribe todos los `bytes`. **Un** intento.
    async fn send_once(&self, bytes: &[u8]) -> Result<()> {
        let addr = self.target.socket_addr();
        let connect = TcpStream::connect(&addr);
        let mut stream = match tokio::time::timeout(self.retry.connect_timeout, connect).await {
            Ok(Ok(s)) => s,
            Ok(Err(e)) => return Err(e.into()),
            // Timeout del connect → tratar como inalcanzable.
            Err(_elapsed) => {
                return Err(PeripheralError::Unreachable(addr));
            }
        };
        stream.write_all(bytes).await?;
        stream.flush().await?;
        Ok(())
    }

    /// Envía con reintentos/backoff. Reintenta solo ante fallo de socket (connect/write); el
    /// último error se propaga si se agotan los intentos.
    pub async fn print_with_retry(&self, bytes: &[u8]) -> Result<()> {
        let mut last_err: Option<PeripheralError> = None;
        for attempt in 1..=self.retry.max_attempts {
            match self.send_once(bytes).await {
                Ok(()) => {
                    if attempt > 1 {
                        tracing::info!(
                            attempt,
                            target = %self.target.socket_addr(),
                            "impresora recuperada tras reintento",
                        );
                    }
                    return Ok(());
                }
                Err(e) => {
                    tracing::warn!(
                        attempt,
                        max = self.retry.max_attempts,
                        target = %self.target.socket_addr(),
                        error = %e,
                        "fallo de envío a impresora",
                    );
                    last_err = Some(e);
                    if attempt < self.retry.max_attempts {
                        tokio::time::sleep(self.retry.backoff_for(attempt)).await;
                    }
                }
            }
        }
        Err(last_err
            .unwrap_or_else(|| PeripheralError::Unreachable(self.target.socket_addr())))
    }
}

impl Printer for NetworkPrinter {
    async fn print(&self, bytes: &[u8]) -> Result<()> {
        self.print_with_retry(bytes).await
    }

    async fn status(&self) -> PrinterStatus {
        let addr = self.target.socket_addr();
        let probe = TcpStream::connect(&addr);
        match tokio::time::timeout(self.retry.connect_timeout, probe).await {
            Ok(Ok(_stream)) => PrinterStatus::Ready,
            _ => PrinterStatus::Offline,
        }
    }
}

impl CashDrawer for NetworkPrinter {
    async fn open(&self, pin: u8) -> Result<()> {
        // El kick es un envío corto al mismo socket; lo pasamos por la misma vía con reintentos.
        self.print_with_retry(kick_command(pin)).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::escpos::{self, Align, DocumentType, EscposBuilder};
    use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
    use std::sync::Arc;
    use tokio::io::AsyncReadExt;
    use tokio::net::TcpListener;

    /// Impresora TCP de mentira: un listener local que acepta **una** conexión, lee todos los
    /// bytes hasta EOF y los deja disponibles para asertarlos. Captura el contrato de cable real
    /// sin hardware.
    struct MockPrinter {
        target: NetworkTarget,
        captured: Arc<tokio::sync::Mutex<Vec<u8>>>,
        accepted: Arc<AtomicBool>,
    }

    impl MockPrinter {
        /// Arranca un listener en un puerto efímero del loopback y spawnea el aceptador de **una**
        /// conexión. Devuelve el mock con el `NetworkTarget` que apunta a él.
        async fn start() -> Self {
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let addr = listener.local_addr().unwrap();
            let captured = Arc::new(tokio::sync::Mutex::new(Vec::new()));
            let accepted = Arc::new(AtomicBool::new(false));

            let cap = captured.clone();
            let acc = accepted.clone();
            tokio::spawn(async move {
                if let Ok((mut sock, _)) = listener.accept().await {
                    acc.store(true, Ordering::SeqCst);
                    let mut buf = Vec::new();
                    let _ = sock.read_to_end(&mut buf).await;
                    *cap.lock().await = buf;
                }
                // El listener se dropea aquí: el puerto deja de aceptar (modela impresora de un job).
            });

            Self {
                target: NetworkTarget { host: addr.ip().to_string(), port: addr.port() },
                captured,
                accepted,
            }
        }

        /// Espera (con un timeout corto) a que el aceptador haya leído hasta EOF y devuelve los bytes.
        async fn captured_bytes(&self) -> Vec<u8> {
            for _ in 0..100 {
                {
                    let guard = self.captured.lock().await;
                    if !guard.is_empty() {
                        return guard.clone();
                    }
                }
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
            self.captured.lock().await.clone()
        }
    }

    /// Una política de reintentos rápida para no ralentizar los tests.
    fn fast_retry() -> PrinterRetry {
        PrinterRetry {
            max_attempts: 3,
            base_backoff: Duration::from_millis(5),
            backoff_factor: 1,
            connect_timeout: Duration::from_millis(200),
        }
    }

    #[tokio::test]
    async fn print_ok_sends_exact_bytes() {
        let mock = MockPrinter::start().await;
        let printer = NetworkPrinter::with_retry(mock.target.clone(), fast_retry());

        let payload = b"hello escpos";
        Printer::print(&printer, payload).await.unwrap();

        let got = mock.captured_bytes().await;
        assert_eq!(got, payload, "la impresora debe recibir los bytes exactos enviados");
        assert!(mock.accepted.load(Ordering::SeqCst), "se aceptó una conexión");
    }

    #[tokio::test]
    async fn print_receipt_contains_cut_command() {
        let mock = MockPrinter::start().await;
        let printer = NetworkPrinter::with_retry(mock.target.clone(), fast_retry());

        // Renderiza un recibo real y compruébalo en el cable: debe acabar con el corte `GS V 1`.
        let data = serde_json::json!({
            "business_name": "Bar Pepe",
            "receipt_id": "T-001",
            "items": [{ "name": "Cafe", "quantity": 2, "total": 3.0 }],
            "total": 3.0,
        });
        let bytes = escpos::render_document(DocumentType::Receipt, &data).unwrap();
        Printer::print(&printer, &bytes).await.unwrap();

        let got = mock.captured_bytes().await;
        // `cut()` emite `\n\n\n` + GS V 1 = 1d 56 01 al final.
        assert!(
            got.windows(3).any(|w| w == [0x1d, 0x56, 0x01]),
            "el recibo impreso debe contener el comando de corte GS V 1",
        );
        // Y el nombre del negocio (codificado cp437) debe aparecer.
        assert!(
            got.windows(8).any(|w| w == b"Bar Pepe"),
            "el recibo debe contener el nombre del negocio",
        );
    }

    #[tokio::test]
    async fn open_drawer_sends_kick_pin2() {
        let mock = MockPrinter::start().await;
        let printer = NetworkPrinter::with_retry(mock.target.clone(), fast_retry());

        CashDrawer::open(&printer, 2).await.unwrap();

        let got = mock.captured_bytes().await;
        assert_eq!(
            got,
            crate::drawer::KICK_PIN_2,
            "open(2) debe enviar el kick ESC p 0 25 50 del pin 2",
        );
    }

    #[tokio::test]
    async fn open_drawer_pin5_uses_pin5_kick() {
        let mock = MockPrinter::start().await;
        let printer = NetworkPrinter::with_retry(mock.target.clone(), fast_retry());

        CashDrawer::open(&printer, 5).await.unwrap();

        let got = mock.captured_bytes().await;
        assert_eq!(got, crate::drawer::KICK_PIN_5, "open(5) debe usar el kick del pin 5");
    }

    #[tokio::test]
    async fn status_ready_when_listener_up_offline_when_down() {
        let mock = MockPrinter::start().await;
        let printer = NetworkPrinter::with_retry(mock.target.clone(), fast_retry());
        assert_eq!(Printer::status(&printer).await, PrinterStatus::Ready);

        // Impresora apagada: un target a un puerto cerrado del loopback.
        let dead = NetworkPrinter::with_retry(
            NetworkTarget { host: "127.0.0.1".into(), port: 1 },
            fast_retry(),
        );
        assert_eq!(Printer::status(&dead).await, PrinterStatus::Offline);
    }

    #[tokio::test]
    async fn printer_down_then_recovers_on_retry() {
        // Reserva un puerto, ciérralo (impresora "apagada"), y vuelve a abrir un listener en el
        // MISMO puerto a mitad de los reintentos → el envío debe recuperarse y completar.
        let probe = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = probe.local_addr().unwrap();
        drop(probe); // puerto ahora cerrado

        let captured = Arc::new(tokio::sync::Mutex::new(Vec::new()));
        let attempts_seen = Arc::new(AtomicU32::new(0));

        // Arranca el listener de recuperación tras un pequeño retraso (mientras la impresora
        // reintenta y hace backoff).
        let cap = captured.clone();
        let seen = attempts_seen.clone();
        let recover = tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(40)).await;
            let listener = TcpListener::bind(addr).await.expect("rebind del puerto de recuperación");
            if let Ok((mut sock, _)) = listener.accept().await {
                seen.fetch_add(1, Ordering::SeqCst);
                let mut buf = Vec::new();
                let _ = sock.read_to_end(&mut buf).await;
                *cap.lock().await = buf;
            }
        });

        let retry = PrinterRetry {
            max_attempts: 6,
            base_backoff: Duration::from_millis(20),
            backoff_factor: 1,
            connect_timeout: Duration::from_millis(100),
        };
        let printer = NetworkPrinter::with_retry(
            NetworkTarget { host: addr.ip().to_string(), port: addr.port() },
            retry,
        );

        // El primer intento falla (puerto cerrado); un reintento posterior, con el listener ya
        // arriba, completa.
        Printer::print(&printer, b"resilient job").await.unwrap();
        recover.await.unwrap();

        assert_eq!(attempts_seen.load(Ordering::SeqCst), 1, "el listener de recuperación aceptó 1 conexión");
        let got = {
            // Da un instante a que el read_to_end termine.
            for _ in 0..100 {
                if !captured.lock().await.is_empty() {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
            captured.lock().await.clone()
        };
        assert_eq!(got, b"resilient job", "el trabajo se entregó tras la recuperación");
    }

    #[tokio::test]
    async fn print_fails_after_exhausting_retries() {
        // Impresora siempre caída: puerto cerrado del loopback, pocos intentos rápidos.
        let printer = NetworkPrinter::with_retry(
            NetworkTarget { host: "127.0.0.1".into(), port: 1 },
            PrinterRetry {
                max_attempts: 3,
                base_backoff: Duration::from_millis(1),
                backoff_factor: 1,
                connect_timeout: Duration::from_millis(50),
            },
        );
        let err = Printer::print(&printer, b"never lands").await.unwrap_err();
        // El error debe ser de I/O o inalcanzable, no un Ok.
        match err {
            PeripheralError::Io(_) | PeripheralError::Unreachable(_) => {}
            other => panic!("error inesperado tras agotar reintentos: {other:?}"),
        }
    }

    #[test]
    fn backoff_is_exponential() {
        let policy = PrinterRetry {
            max_attempts: 4,
            base_backoff: Duration::from_millis(100),
            backoff_factor: 2,
            connect_timeout: Duration::from_secs(1),
        };
        assert_eq!(policy.backoff_for(1), Duration::from_millis(100));
        assert_eq!(policy.backoff_for(2), Duration::from_millis(200));
        assert_eq!(policy.backoff_for(3), Duration::from_millis(400));
    }

    #[test]
    fn builder_qr_and_cut_smoke() {
        // Sanidad del builder usado por los renderizadores: QR + corte producen bytes no vacíos
        // y con el sello de QR de Epson (GS ( k).
        let mut b = EscposBuilder::new();
        b.set(Align::Center, false, false, false).qr("https://erplora.com/v/abc").cut();
        let out = b.finish();
        assert!(out.windows(3).any(|w| w == [0x1d, 0x28, 0x6b]), "debe contener GS ( k (QR)");
        assert!(out.windows(3).any(|w| w == [0x1d, 0x56, 0x01]), "debe contener GS V 1 (corte)");
    }
}
