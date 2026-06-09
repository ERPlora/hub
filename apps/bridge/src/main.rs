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
use erplora_peripherals::queue::{PrintJob, PrintQueue, RetryPolicy};
use erplora_peripherals::registry::DeviceRegistry;
use erplora_peripherals::BRIDGE_WS_PORT;

const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Estado compartido entre conexiones: registro de dispositivos + cola de impresión.
struct AppState {
    registry: DeviceRegistry,
    queue: PrintQueue,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    // `devices.json` configurable; por defecto en el cwd (afinar a un config-dir en empaquetado).
    let devices_path = std::env::var("ERPLORA_BRIDGE_DEVICES")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("devices.json"));

    let state = Arc::new(AppState {
        registry: DeviceRegistry::load(devices_path),
        queue: PrintQueue::new(RetryPolicy::default()),
    });

    let app = Router::new()
        .route("/status", get(status))
        .route("/ws", get(ws_upgrade))
        .with_state(state);

    let bind = format!("127.0.0.1:{BRIDGE_WS_PORT}");
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind bridge port");
    tracing::info!("erplora-bridge escuchando en http://{bind}");
    axum::serve(listener, app).await.expect("serve");
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

/// Bucle por conexión: parsea `Command`, despacha y responde con `Event`(s) en JSON.
async fn handle_socket(mut socket: WebSocket, state: Arc<AppState>) {
    // Al conectar, el Bridge Python emite un `status` inicial.
    if let Ok(text) = serde_json::to_string(&initial_status()) {
        let _ = socket.send(Message::Text(text)).await;
    }

    while let Some(Ok(msg)) = socket.recv().await {
        let Message::Text(raw) = msg else { continue };
        let reply = match serde_json::from_str::<Command>(&raw) {
            Ok(cmd) => dispatch(cmd, &state).await,
            Err(e) => Some(Event::Error {
                message: format!("comando inválido: {e}"),
                code: "bad_command".into(),
            }),
        };
        // Algunos comandos (p.ej. notificaciones) no producen evento de respuesta.
        if let Some(event) = reply {
            if let Ok(text) = serde_json::to_string(&event) {
                if socket.send(Message::Text(text)).await.is_err() {
                    break;
                }
            }
        }
    }
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
            Some(print_job(state, &printer_id, DocumentType::from_wire(&document_type), &data, job_id).await)
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
            Some(match state.queue.send_once(&job).await {
                Ok(()) => Event::PrintComplete { job_id: None },
                Err(e) => Event::PrintError { job_id: None, error: e.to_string() },
            })
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

/// Renderiza el documento y lo envía (un intento) por la cola; mapea el resultado a evento.
async fn print_job(
    state: &AppState,
    printer_id: &str,
    doc: DocumentType,
    data: &serde_json::Value,
    job_id: Option<String>,
) -> Event {
    let target = match parse_printer_id(printer_id) {
        Ok(t) => t,
        Err(e) => return Event::PrintError { job_id, error: e.to_string() },
    };
    let payload = match escpos::render_document(doc, data) {
        Ok(bytes) => bytes,
        Err(e) => return Event::PrintError { job_id, error: e.to_string() },
    };
    let job = PrintJob { job_id: job_id.clone(), target, payload, attempts: 0 };
    match state.queue.send_once(&job).await {
        Ok(()) => Event::PrintComplete { job_id },
        Err(e) => Event::PrintError { job_id, error: e.to_string() },
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
