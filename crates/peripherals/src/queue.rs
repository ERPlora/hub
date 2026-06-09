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
#[derive(Debug)]
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

    /// Bucle worker: drena la cola y reintenta según la política; emite `JobOutcome`.
    pub async fn run(&self) {
        while let Some(job) = {
            let mut rx = self.rx.lock().await;
            rx.recv().await
        } {
            match self.process(job).await {
                JobOutcome::Completed { job_id } => {
                    tracing::info!(?job_id, "trabajo de impresión completado");
                }
                JobOutcome::Failed { job_id, error } => {
                    tracing::warn!(?job_id, %error, "trabajo de impresión fallido");
                }
            }
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
