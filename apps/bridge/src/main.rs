//! Bridge de hardware **standalone** — combo `cloud + web-PWA` (ARQUITECTURA.md §2.7).
//!
//! Expone el mismo contrato que el Bridge Python para que `hub/static/js/bridge.js` funcione
//! sin cambios:
//!   - `GET /status` — health check (el navegador detecta el bridge con timeout corto).
//!   - `WS  /ws`     — comandos (`Command`) y eventos (`Event`) en JSON.
//!
//! Toda la lógica de hardware vive en `erplora-peripherals`; este binario es solo el transporte
//! WebSocket + (a futuro) la bandeja del sistema. El sidecar Tauri reusará el mismo crate vía
//! `invoke` en lugar de este servidor.

use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::response::IntoResponse;
use axum::routing::get;
use axum::{Json, Router};

use erplora_peripherals::discovery::{self, parse_printer_id};
use erplora_peripherals::drawer;
use erplora_peripherals::escpos::{self, DocumentType};
use erplora_peripherals::protocol::{Command, Event};
use erplora_peripherals::queue::{JobOutcome, PrintJob, PrintQueue, RetryPolicy};
use erplora_peripherals::registry::{DeviceRegistry, Watchdog, WatchdogConfig, WatchdogEvent};
use erplora_peripherals::BRIDGE_WS_PORT;
use tokio::sync::{broadcast, mpsc};

const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Capacidad del canal de broadcast hacia las conexiones WS (los eventos son pequeños; si un
/// cliente se retrasa más de esto, pierde los más antiguos — `RecvError::Lagged`).
const EVENT_BUS_CAPACITY: usize = 64;

/// Estado compartido entre conexiones: registro de dispositivos + cola de impresión + bus de
/// eventos (bridge#8): los outcomes de la cola y los eventos del watchdog se publican aquí y
/// cada conexión WS abierta los reenvía al Hub.
struct AppState {
    registry: DeviceRegistry,
    queue: PrintQueue,
    events: broadcast::Sender<Event>,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    // `devices.json` configurable; por defecto en el cwd (afinar a un config-dir en empaquetado).
    let devices_path = std::env::var("ERPLORA_BRIDGE_DEVICES")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("devices.json"));

    let (events_tx, _) = broadcast::channel(EVENT_BUS_CAPACITY);
    let state = Arc::new(AppState {
        registry: DeviceRegistry::load(devices_path),
        queue: PrintQueue::new(RetryPolicy::default()),
        events: events_tx,
    });

    spawn_queue_worker(state.clone());
    spawn_watchdog(state.clone());

    let app = Router::new()
        .route("/status", get(status))
        .route("/ws", get(ws_upgrade))
        .with_state(state);

    let bind = format!("127.0.0.1:{BRIDGE_WS_PORT}");
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind bridge port");
    tracing::info!("erplora-bridge escuchando en http://{bind}");
    axum::serve(listener, app).await.expect("serve");
}

/// Spawnea el worker de la cola de impresión (`PrintQueue::run`, reintentos según
/// `RetryPolicy`) y el puente outcome → evento WS: cada `JobOutcome` se publica en el bus
/// como `print_complete` / `print_error` (bridge#8).
fn spawn_queue_worker(state: Arc<AppState>) {
    let (outcomes_tx, mut outcomes_rx) = mpsc::unbounded_channel::<JobOutcome>();

    let worker_state = state.clone();
    tokio::spawn(async move {
        worker_state.queue.run(outcomes_tx).await;
        tracing::warn!("worker de la cola de impresión terminado (cola cerrada)");
    });

    tokio::spawn(async move {
        while let Some(outcome) = outcomes_rx.recv().await {
            let event = match outcome {
                JobOutcome::Completed { job_id } => Event::PrintComplete { job_id },
                JobOutcome::Failed { job_id, error } => Event::PrintError { job_id, error },
            };
            // Sin conexiones WS abiertas no hay receptores; el evento simplemente se descarta.
            let _ = state.events.send(event);
        }
    });
}

/// Spawnea el `Watchdog` (config por defecto: check 30s / recovery 120s) y el puente
/// `WatchdogEvent` → evento WS (`device_recovered` / `device_lost`) (bridge#8).
fn spawn_watchdog(state: Arc<AppState>) {
    let (events_tx, mut events_rx) = mpsc::unbounded_channel::<WatchdogEvent>();

    let watchdog_state = state.clone();
    tokio::spawn(async move {
        let watchdog = Watchdog::new(WatchdogConfig::default()).with_events(events_tx);
        watchdog.run(&watchdog_state.registry).await;
    });

    tokio::spawn(async move {
        while let Some(wd_event) = events_rx.recv().await {
            let event = match wd_event {
                WatchdogEvent::Recovered(device) => Event::DeviceRecovered { device },
                WatchdogEvent::Lost(device) => Event::DeviceLost { device },
            };
            let _ = state.events.send(event);
        }
    });
}

/// `GET /status` — usado por el navegador para detectar el bridge (timeout ~500ms en `bridge.js`).
async fn status() -> impl IntoResponse {
    Json(serde_json::json!({
        "service": "erplora-bridge",
        "version": VERSION,
        "ok": true,
    }))
}

/// `GET /ws` → upgrade a WebSocket.
async fn ws_upgrade(State(state): State<Arc<AppState>>, ws: WebSocketUpgrade) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

/// Bucle por conexión: parsea `Command`, despacha y responde con `Event`(s) en JSON. Además
/// reenvía los eventos del bus compartido (outcomes de la cola + watchdog) a esta conexión
/// (bridge#8): `print_complete` / `print_error` / `device_recovered` / `device_lost` llegan a
/// todas las conexiones WS abiertas.
async fn handle_socket(mut socket: WebSocket, state: Arc<AppState>) {
    // Al conectar, el Bridge Python emite un `status` inicial.
    if let Ok(text) = serde_json::to_string(&initial_status()) {
        let _ = socket.send(Message::Text(text)).await;
    }

    let mut bus = state.events.subscribe();

    loop {
        tokio::select! {
            incoming = socket.recv() => {
                let Some(Ok(msg)) = incoming else { break };
                let Message::Text(raw) = msg else { continue };
                let reply = match serde_json::from_str::<Command>(&raw) {
                    Ok(cmd) => dispatch(cmd, &state).await,
                    Err(e) => Some(Event::Error {
                        message: format!("comando inválido: {e}"),
                        code: "bad_command".into(),
                    }),
                };
                // Algunos comandos (p.ej. print encolado, notificaciones) no producen evento
                // de respuesta inmediato.
                if let Some(event) = reply {
                    if send_event(&mut socket, &event).await.is_err() {
                        break;
                    }
                }
            }
            published = bus.recv() => {
                match published {
                    Ok(event) => {
                        if send_event(&mut socket, &event).await.is_err() {
                            break;
                        }
                    }
                    // Cliente lento: se pierden los eventos más antiguos, seguimos.
                    Err(broadcast::error::RecvError::Lagged(missed)) => {
                        tracing::warn!(missed, "conexión WS retrasada: eventos del bus perdidos");
                    }
                    // El emisor vive en AppState; si se cierra, terminó el proceso.
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
        }
    }
}

/// Serializa y envía un evento por el socket. `Err(())` si el socket está roto.
async fn send_event(socket: &mut WebSocket, event: &Event) -> std::result::Result<(), ()> {
    let Ok(text) = serde_json::to_string(event) else { return Ok(()) };
    socket.send(Message::Text(text)).await.map_err(|_| ())
}

/// Evento `status` inicial / de `get_status`.
fn initial_status() -> Event {
    Event::Status { version: VERSION.to_string(), printers: Vec::new(), scanner: false }
}

/// Despacha un comando a `erplora-peripherals` y produce el evento de respuesta (o `None`).
async fn dispatch(cmd: Command, state: &AppState) -> Option<Event> {
    match cmd {
        Command::GetStatus => Some(initial_status()),

        Command::DiscoverPrinters => Some(match discovery::discover_printers(&state.registry).await {
            Ok(printers) => Event::Printers { printers },
            Err(e) => err_event(&e),
        }),

        Command::Print { printer_id, document_type, data, job_id } => {
            print_job(state, &printer_id, DocumentType::from_wire(&document_type), &data, job_id).await
        }

        Command::TestPrint { printer_id } => {
            let target = match parse_printer_id(&printer_id) {
                Ok(t) => t,
                Err(e) => return Some(err_event(&e)),
            };
            let job = PrintJob {
                job_id: None,
                target,
                payload: escpos::render_test_page(&printer_id),
                attempts: 0,
            };
            enqueue_job(state, job)
        }

        Command::OpenDrawer { printer_id, pin } => {
            let target = match parse_printer_id(&printer_id) {
                Ok(t) => t,
                Err(e) => return Some(err_event(&e)),
            };
            Some(match drawer::open_drawer(&target, pin).await {
                Ok(()) => Event::DrawerOpened { printer_id },
                Err(e) => err_event(&e),
            })
        }

        // No hay evento de ACK en el protocolo; mostramos la notificación de SO (pendiente) y
        // no respondemos. Por ahora solo se registra.
        Command::SendNotification { title, body } => {
            tracing::info!(%title, %body, "notificación (OS notification pendiente de implementar)");
            None
        }

        Command::GetDevices => Some(Event::Devices { devices: state.registry.get_all() }),

        Command::SetDeviceRole { mac, role } => Some(devices_after(state.registry.set_role(&mac, &role), state)),
        Command::SetDeviceName { mac, name } => Some(devices_after(state.registry.set_name(&mac, &name), state)),
        Command::RemoveDevice { mac } => Some(devices_after(state.registry.remove(&mac), state)),
    }
}

/// Renderiza el documento y lo encola para envío asíncrono con reintentos (bridge#8). El
/// resultado (`print_complete` / `print_error`) llega vía el bus de eventos cuando el worker
/// de la cola procesa el trabajo; aquí solo se reportan los errores previos al encolado
/// (printer_id o payload inválidos).
async fn print_job(
    state: &AppState,
    printer_id: &str,
    doc: DocumentType,
    data: &serde_json::Value,
    job_id: Option<String>,
) -> Option<Event> {
    let target = match parse_printer_id(printer_id) {
        Ok(t) => t,
        Err(e) => return Some(Event::PrintError { job_id, error: e.to_string() }),
    };
    let payload = match escpos::render_document(doc, data) {
        Ok(bytes) => bytes,
        Err(e) => return Some(Event::PrintError { job_id, error: e.to_string() }),
    };
    enqueue_job(state, PrintJob { job_id, target, payload, attempts: 0 })
}

/// Encola un trabajo en la `PrintQueue`. `None` si se encoló (el outcome llegará por el bus);
/// `print_error` inmediato solo si la cola está cerrada (no debería ocurrir en operación).
fn enqueue_job(state: &AppState, job: PrintJob) -> Option<Event> {
    let job_id = job.job_id.clone();
    match state.queue.enqueue(job) {
        Ok(()) => None,
        Err(e) => Some(Event::PrintError { job_id, error: e.to_string() }),
    }
}

/// Tras una mutación del registro, devuelve la lista actualizada (o un error).
fn devices_after(result: erplora_peripherals::Result<()>, state: &AppState) -> Event {
    match result {
        Ok(()) => Event::Devices { devices: state.registry.get_all() },
        Err(e) => err_event(&e),
    }
}

fn err_event(e: &erplora_peripherals::PeripheralError) -> Event {
    Event::Error { message: e.to_string(), code: "peripheral_error".into() }
}
