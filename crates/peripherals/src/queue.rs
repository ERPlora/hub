//! Cola de impresión con reintentos. Cubre el requisito §2.7 "cola + reintentos (impresora
//! apagada / sin papel)". No existe como módulo separado en el Bridge Python (allí la impresión
//! es síncrona); aquí se modela explícito para no perder trabajos cuando la impresora no responde.

use std::time::Duration;

use tokio::io::AsyncWriteExt;
use tokio::net::TcpStream;
use tokio::sync::mpsc::{self, UnboundedReceiver, UnboundedSender};
use tokio::sync::Mutex;

use crate::discovery::NetworkTarget;
use crate::{PeripheralError, Result};

/// Un trabajo de impresión encolado.
#[derive(Debug, Clone)]
pub struct PrintJob {
    pub job_id: Option<String>,
    pub target: NetworkTarget,
    /// Bytes ya renderizados por `escpos::render_document`.
    pub payload: Vec<u8>,
    /// Intentos ya realizados.
    pub attempts: u32,
}

/// Resultado de procesar un trabajo (para emitir `print_complete` / `print_error`).
#[derive(Debug, Clone)]
pub enum JobOutcome {
    Completed { job_id: Option<String> },
    Failed { job_id: Option<String>, error: String },
}

/// Política de reintentos.
#[derive(Debug, Clone, Copy)]
pub struct RetryPolicy {
    pub max_attempts: u32,
    pub backoff_ms: u64,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self { max_attempts: 3, backoff_ms: 2000 }
    }
}

/// Cola de impresión. Encola trabajos y los procesa con reintentos contra el socket TCP.
pub struct PrintQueue {
    policy: RetryPolicy,
    /// Productor de la cola: `enqueue` empuja trabajos aquí.
    tx: UnboundedSender<PrintJob>,
    /// Consumidor de la cola, tras un `Mutex` para que `run(&self)` pueda tomar `&mut` al recibir.
    rx: Mutex<UnboundedReceiver<PrintJob>>,
}

impl PrintQueue {
    pub fn new(policy: RetryPolicy) -> Self {
        let (tx, rx) = mpsc::unbounded_channel();
        Self { policy, tx, rx: Mutex::new(rx) }
    }

    /// Encola un trabajo para envío asíncrono.
    pub fn enqueue(&self, job: PrintJob) -> Result<()> {
        self.tx.send(job).map_err(|e| {
            PeripheralError::InvalidPayload(format!("cola de impresión cerrada: {e}"))
        })
    }

    /// Envía un trabajo: abre socket al destino y escribe el payload. Un intento.
    pub async fn send_once(&self, job: &PrintJob) -> Result<()> {
        let mut stream = TcpStream::connect(job.target.socket_addr()).await?;
        stream.write_all(&job.payload).await?;
        Ok(())
    }

    /// Bucle worker: drena la cola y reintenta según la política; emite cada `JobOutcome` por
    /// `outcomes` (el consumidor lo mapea a `print_complete` / `print_error`).
    pub async fn run(&self, outcomes: UnboundedSender<JobOutcome>) {
        while let Some(job) = {
            let mut rx = self.rx.lock().await;
            rx.recv().await
        } {
            let outcome = self.process(job).await;
            match &outcome {
                JobOutcome::Completed { job_id } => {
                    tracing::info!(?job_id, "trabajo de impresión completado");
                }
                JobOutcome::Failed { job_id, error } => {
                    tracing::warn!(?job_id, %error, "trabajo de impresión fallido");
                }
            }
            // Si el consumidor se fue, solo se pierde el reporte (no el procesado de la cola).
            let _ = outcomes.send(outcome);
        }
    }

    /// Procesa un trabajo con reintentos/backoff según la política. Reintenta hasta
    /// `policy.max_attempts` veces; entre intentos fallidos espera `policy.backoff_ms`.
    async fn process(&self, mut job: PrintJob) -> JobOutcome {
        loop {
            match self.send_once(&job).await {
                Ok(()) => return JobOutcome::Completed { job_id: job.job_id },
                Err(e) => {
                    job.attempts += 1;
                    if job.attempts < self.policy.max_attempts {
                        tracing::debug!(
                            attempts = job.attempts,
                            max = self.policy.max_attempts,
                            error = %e,
                            "reintentando trabajo de impresión",
                        );
                        tokio::time::sleep(Duration::from_millis(self.policy.backoff_ms)).await;
                    } else {
                        return JobOutcome::Failed { job_id: job.job_id, error: e.to_string() };
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::escpos::{self, DocumentType};
    use crate::test_support::{unreachable_target, MockPrinter};
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::sync::Arc;
    use tokio::io::AsyncReadExt;
    use tokio::net::TcpListener;

    /// Reintentos rápidos: los tests no deben pagar los 2 s de backoff de producción.
    fn fast_policy(max_attempts: u32) -> RetryPolicy {
        RetryPolicy {
            max_attempts,
            backoff_ms: 10,
        }
    }

    /// Arranca el worker de la cola y devuelve el receptor de outcomes.
    fn spawn_worker(queue: Arc<PrintQueue>) -> UnboundedReceiver<JobOutcome> {
        let (tx, rx) = mpsc::unbounded_channel();
        tokio::spawn(async move { queue.run(tx).await });
        rx
    }

    fn job(target: NetworkTarget, payload: &[u8]) -> PrintJob {
        PrintJob {
            job_id: Some("j1".into()),
            target,
            payload: payload.to_vec(),
            attempts: 0,
        }
    }

    /// **Lo encolado llega a la impresora byte por byte.** Es toda la razón de ser de la cola: el
    /// comando de Tauri (`erplora_print`) devuelve `Ok` en cuanto encola, así que si el worker
    /// mutila o pierde el payload nadie se entera hasta mirar el papel.
    #[tokio::test]
    async fn an_enqueued_job_reaches_the_printer_byte_for_byte() {
        let mock = MockPrinter::start().await;
        let queue = Arc::new(PrintQueue::new(fast_policy(3)));
        let mut outcomes = spawn_worker(queue.clone());

        let payload = b"hello escpos";
        queue.enqueue(job(mock.target.clone(), payload)).unwrap();

        assert!(
            matches!(outcomes.recv().await, Some(JobOutcome::Completed { .. })),
            "un envío que llega se reporta como completado"
        );
        assert_eq!(mock.captured_bytes().await, payload);
        assert!(mock.accepted(), "se abrió la conexión a la impresora");
    }

    /// Un recibo real renderizado por `escpos` sobrevive el viaje entero: el corte `GS V 1` y el
    /// nombre del negocio (cp437) tienen que salir por el cable, no solo del renderizador.
    #[tokio::test]
    async fn a_rendered_receipt_travels_whole_including_the_paper_cut() {
        let mock = MockPrinter::start().await;
        let queue = Arc::new(PrintQueue::new(fast_policy(3)));
        let mut outcomes = spawn_worker(queue.clone());

        let bytes = escpos::render_document(
            DocumentType::Receipt,
            &serde_json::json!({
                "business_name": "Bar Pepe",
                "receipt_id": "T-001",
                "items": [{ "name": "Cafe", "quantity": 2, "total": 3.0 }],
                "total": 3.0,
            }),
        )
        .expect("un recibo bien formado renderiza");
        queue.enqueue(job(mock.target.clone(), &bytes)).unwrap();
        outcomes.recv().await.expect("hay outcome");

        let got = mock.captured_bytes().await;
        assert!(
            got.windows(3).any(|w| w == [0x1d, 0x56, 0x01]),
            "sin el corte, el siguiente tique sale pegado a este"
        );
        assert!(
            got.windows(8).any(|w| w == b"Bar Pepe"),
            "el nombre del negocio debe llegar al papel"
        );
    }

    /// **La impresora apagada un momento no pierde el trabajo.** Es el requisito §2.7 entero: el
    /// primer intento falla con el puerto cerrado y un reintento posterior, ya con la impresora de
    /// vuelta, entrega. Sin esto un tique se pierde cada vez que alguien tropieza con el cable.
    #[tokio::test]
    async fn a_printer_that_comes_back_still_gets_its_job() {
        // Reserva un puerto y ciérralo: "impresora apagada" en una dirección que luego revive.
        let probe = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = probe.local_addr().unwrap();
        drop(probe);

        let captured = Arc::new(tokio::sync::Mutex::new(Vec::new()));
        let accepted = Arc::new(AtomicU32::new(0));

        let cap = captured.clone();
        let seen = accepted.clone();
        let revive = tokio::spawn(async move {
            // Vuelve a levantarse mientras la cola hace backoff.
            tokio::time::sleep(Duration::from_millis(40)).await;
            let listener = TcpListener::bind(addr).await.expect("rebind del puerto");
            if let Ok((mut sock, _)) = listener.accept().await {
                seen.fetch_add(1, Ordering::SeqCst);
                let mut buf = Vec::new();
                let _ = sock.read_to_end(&mut buf).await;
                *cap.lock().await = buf;
            }
        });

        let queue = Arc::new(PrintQueue::new(RetryPolicy {
            max_attempts: 8,
            backoff_ms: 20,
        }));
        let mut outcomes = spawn_worker(queue.clone());
        let target = NetworkTarget {
            host: addr.ip().to_string(),
            port: addr.port(),
        };
        queue.enqueue(job(target, b"resilient job")).unwrap();

        assert!(
            matches!(outcomes.recv().await, Some(JobOutcome::Completed { .. })),
            "el trabajo se completa tras la recuperación, no se descarta"
        );
        revive.await.unwrap();
        assert_eq!(accepted.load(Ordering::SeqCst), 1);
        assert_eq!(
            *captured.lock().await,
            b"resilient job".to_vec(),
            "y el payload entregado es el original, no uno truncado por los intentos fallidos"
        );
    }

    /// **Cuando se agotan los intentos el trabajo se reporta como fallido, no desaparece.** El
    /// consumidor mapea este outcome a `print_error`; un `Completed` optimista aquí sería un tique
    /// que nadie imprimió y nadie echó en falta.
    #[tokio::test]
    async fn a_job_that_never_lands_ends_as_failed_with_the_reason() {
        let queue = Arc::new(PrintQueue::new(fast_policy(3)));
        let mut outcomes = spawn_worker(queue.clone());

        queue
            .enqueue(job(unreachable_target(), b"never lands"))
            .unwrap();

        match outcomes.recv().await {
            Some(JobOutcome::Failed { job_id, error }) => {
                assert_eq!(job_id.as_deref(), Some("j1"), "el id vuelve para poder correlacionarlo");
                assert!(!error.is_empty(), "el fallo tiene que decir por qué");
            }
            other => panic!("una impresora inalcanzable no puede completar: {other:?}"),
        }
    }

    /// La política se **respeta**: con `max_attempts: 1` no hay reintento. Fijarlo evita que un
    /// bucle mal contado convierta un solo intento en tres (o al revés, que el default de 3 se
    /// quede en uno y la recuperación de arriba deje de existir).
    #[tokio::test]
    async fn a_single_attempt_policy_does_not_retry() {
        let queue = Arc::new(PrintQueue::new(fast_policy(1)));
        let started = std::time::Instant::now();
        let outcome = queue
            .process(job(unreachable_target(), b"one shot"))
            .await;

        assert!(matches!(outcome, JobOutcome::Failed { .. }));
        assert!(
            started.elapsed() < Duration::from_millis(10),
            "con un solo intento no se espera ningún backoff (tardó {:?})",
            started.elapsed()
        );
    }

    /// Encolar en una cola cuyo worker murió es un error explícito, no un trabajo que se evapora.
    #[tokio::test]
    async fn enqueueing_into_a_closed_queue_is_refused() {
        let queue = PrintQueue::new(fast_policy(1));
        queue.rx.lock().await.close();
        let err = queue
            .enqueue(job(unreachable_target(), b"nowhere"))
            .expect_err("la cola cerrada no acepta trabajos");
        assert!(matches!(err, PeripheralError::InvalidPayload(_)));
    }
}
