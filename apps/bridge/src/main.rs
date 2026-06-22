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

mod auth;

use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::http::{HeaderMap, Uri};
use axum::response::IntoResponse;
use axum::routing::get;
use axum::{Json, Router};

use auth::{AuthOutcome, BridgeAuth};

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
    /// Política de auth del handshake WS (allowlist de `Origin` + token de sesión). ADR-0050.
    auth: BridgeAuth,
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
        // Lee `BRIDGE_TOKEN` + `BRIDGE_ALLOWED_ORIGINS` del entorno (loggea un warn si falta el token).
        auth: BridgeAuth::from_env(),
    });

    spawn_queue_worker(state.clone());
    spawn_watchdog(state.clone());

    let app = build_router(state);

    let bind = format!("127.0.0.1:{BRIDGE_WS_PORT}");
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind bridge port");
    tracing::info!("erplora-bridge escuchando en http://{bind}");
    axum::serve(listener, app).await.expect("serve");
}

/// Construye el router con sus rutas (`/status` abierto, `/ws` gateado por auth). Extraído de
/// `main` para que los tests de integración ejerzan exactamente el mismo cableado.
fn build_router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/status", get(status))
        .route("/ws", get(ws_upgrade))
        .with_state(state)
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

/// `GET /status` — usado por el navegador para detectar el bridge (timeout corto en
/// `apps/web/src/lib/bridge-client.ts`).
///
/// Contrato mínimo común Rust↔Android (bridge#10): `{ "ok": true, "version": "<semver>" }` —
/// es lo único que consume `bridge-client.ts`. El resto de claves son informativas y pueden
/// variar por plataforma (`service` identifica esta línea; `devices`/`watchdog` espejan los
/// contadores que ya reporta la app Android).
async fn status(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(serde_json::json!({
        "ok": true,
        "version": VERSION,
        "service": "erplora-bridge",
        "devices": state.registry.get_all().len(),
        "watchdog": true,
    }))
}

/// `GET /ws` → upgrade a WebSocket, **gateado por auth** (ADR-0050 §seguridad).
///
/// Antes de hacer el upgrade valida el handshake con `BridgeAuth`:
///   - `Origin` debe estar en la allowlist (loopback / `tauri://` / `https://localhost` / extras),
///   - el token de sesión (cabecera `Authorization: Bearer` / `X-Hub-Session`, o `?token=`) debe
///     casar con el secreto del Bridge (si `BRIDGE_TOKEN` está configurado).
///
/// Si falla, responde **403** (origen) o **401** (token) y NO abre el WebSocket. El `HeaderMap` y
/// el `Uri` se extraen ANTES que `WebSocketUpgrade` (orden de extractores en axum: los que
/// consumen el body van al final).
async fn ws_upgrade(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    uri: Uri,
    ws: WebSocketUpgrade,
) -> axum::response::Response {
    match state.auth.evaluate(&headers, &uri) {
        AuthOutcome::Allowed => ws.on_upgrade(move |socket| handle_socket(socket, state)),
        rejected => {
            tracing::warn!(
                outcome = ?rejected,
                origin = ?headers.get(axum::http::header::ORIGIN),
                "handshake WS del Bridge rechazado",
            );
            (rejected.status_code(), "bridge handshake rechazado").into_response()
        }
    }
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

        // No hay evento de ACK en el protocolo; mostramos la notificación de SO y no
        // respondemos (bridge#9). `show()` es bloqueante (DBus/AppKit/WinRT) → spawn_blocking.
        // Si la plataforma no la soporta (headless, sin DBus…), degradamos a log sin panic.
        // En el sidecar Tauri esta capacidad la cubre el shell (plugin de notificaciones),
        // no este binario — ver architecture/bridge/websocket-interface.md.
        Command::SendNotification { title, body } => {
            tokio::task::spawn_blocking(move || {
                match notify_rust::Notification::new()
                    .appname("ERPlora Bridge")
                    .summary(&title)
                    .body(&body)
                    .show()
                {
                    Ok(_) => tracing::info!(%title, "notificación de SO mostrada"),
                    Err(e) => tracing::warn!(
                        %title,
                        error = %e,
                        "la plataforma no pudo mostrar la notificación de SO (degradado a log)"
                    ),
                }
            });
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

#[cfg(test)]
mod integration_tests {
    //! Tests de integración del handshake WS: arrancan el router real (`build_router`) en un puerto
    //! efímero y mandan peticiones HTTP/1.1 crudas para comprobar los códigos de estado del gate de
    //! auth (`/ws`) y que `/status` sigue abierto sin token. Cliente TCP a mano para no depender de
    //! un crate HTTP en los tests.

    use super::*;
    use std::time::Duration;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpStream;

    /// Estado mínimo para el router con una política de auth concreta (sin watchdog/cola worker;
    /// el handshake se rechaza/acepta antes de tocarlos).
    fn test_state(auth: BridgeAuth) -> Arc<AppState> {
        let (events_tx, _) = broadcast::channel(EVENT_BUS_CAPACITY);
        Arc::new(AppState {
            registry: DeviceRegistry::load(PathBuf::from(
                std::env::temp_dir().join("erplora-bridge-test-devices.json"),
            )),
            queue: PrintQueue::new(RetryPolicy::default()),
            events: events_tx,
            auth,
        })
    }

    /// Arranca el router en `127.0.0.1:0` y devuelve el puerto asignado.
    async fn spawn_server(auth: BridgeAuth) -> u16 {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let app = build_router(test_state(auth));
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        // Pequeña espera a que el serve esté escuchando.
        tokio::time::sleep(Duration::from_millis(20)).await;
        port
    }

    /// Manda una petición HTTP cruda y devuelve la primera línea de la respuesta (status line).
    async fn send_request(port: u16, request: &str) -> String {
        let mut stream = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
        stream.write_all(request.as_bytes()).await.unwrap();
        stream.flush().await.unwrap();

        let mut buf = Vec::new();
        // Lee hasta el primer CRLF (status line) o un poco de cabeceras; con un timeout corto.
        let read = tokio::time::timeout(Duration::from_secs(2), async {
            let mut tmp = [0u8; 1024];
            loop {
                let n = stream.read(&mut tmp).await.unwrap_or(0);
                if n == 0 {
                    break;
                }
                buf.extend_from_slice(&tmp[..n]);
                if buf.windows(2).any(|w| w == b"\r\n") {
                    break;
                }
            }
        })
        .await;
        let _ = read;
        let text = String::from_utf8_lossy(&buf);
        text.lines().next().unwrap_or("").to_string()
    }

    /// Construye una petición de upgrade WS con cabeceras opcionales extra.
    fn ws_upgrade_request(port: u16, path: &str, extra_headers: &[(&str, &str)]) -> String {
        let mut req = format!(
            "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\
             Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        );
        for (k, v) in extra_headers {
            req.push_str(&format!("{k}: {v}\r\n"));
        }
        req.push_str("\r\n");
        req
    }

    #[tokio::test]
    async fn status_endpoint_is_open_without_token() {
        let port = spawn_server(BridgeAuth::new(Some("s3cr3t".into()), vec![])).await;
        let status = send_request(port, &format!(
            "GET /status HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
        )).await;
        assert!(status.contains("200"), "/status debe responder 200 sin token, fue: {status:?}");
    }

    #[tokio::test]
    async fn ws_upgrade_succeeds_with_valid_origin_and_token() {
        let port = spawn_server(BridgeAuth::new(Some("s3cr3t".into()), vec![])).await;
        let req = ws_upgrade_request(port, "/ws", &[
            ("Origin", "http://localhost:5173"),
            ("Authorization", "Bearer s3cr3t"),
        ]);
        let status = send_request(port, &req).await;
        assert!(
            status.contains("101"),
            "upgrade con Origin+token válidos debe dar 101 Switching Protocols, fue: {status:?}"
        );
    }

    #[tokio::test]
    async fn ws_upgrade_accepts_token_via_query_param() {
        let port = spawn_server(BridgeAuth::new(Some("s3cr3t".into()), vec![])).await;
        let req = ws_upgrade_request(port, "/ws?token=s3cr3t", &[
            ("Origin", "http://localhost:5173"),
        ]);
        let status = send_request(port, &req).await;
        assert!(status.contains("101"), "token por query param debe permitir el upgrade, fue: {status:?}");
    }

    #[tokio::test]
    async fn ws_upgrade_rejected_without_token() {
        let port = spawn_server(BridgeAuth::new(Some("s3cr3t".into()), vec![])).await;
        let req = ws_upgrade_request(port, "/ws", &[("Origin", "http://localhost:5173")]);
        let status = send_request(port, &req).await;
        assert!(status.contains("401"), "sin token debe ser 401, fue: {status:?}");
    }

    #[tokio::test]
    async fn ws_upgrade_rejected_with_bad_token() {
        let port = spawn_server(BridgeAuth::new(Some("s3cr3t".into()), vec![])).await;
        let req = ws_upgrade_request(port, "/ws", &[
            ("Origin", "http://localhost:5173"),
            ("Authorization", "Bearer wrong"),
        ]);
        let status = send_request(port, &req).await;
        assert!(status.contains("401"), "token incorrecto debe ser 401, fue: {status:?}");
    }

    #[tokio::test]
    async fn ws_upgrade_rejected_with_forbidden_origin() {
        let port = spawn_server(BridgeAuth::new(Some("s3cr3t".into()), vec![])).await;
        let req = ws_upgrade_request(port, "/ws", &[
            ("Origin", "https://evil.example.com"),
            ("Authorization", "Bearer s3cr3t"),
        ]);
        let status = send_request(port, &req).await;
        assert!(status.contains("403"), "origen no permitido debe ser 403, fue: {status:?}");
    }

    #[tokio::test]
    async fn ws_upgrade_open_in_dev_mode_without_token() {
        // Modo dev (BRIDGE_DEV): `BridgeAuth` sin token desactiva la barrera; solo se exige buen
        // Origin. En producción `from_env` SIEMPRE resuelve un token (fail-closed); este caso no
        // ocurre salvo dev explícito.
        let port = spawn_server(BridgeAuth::new(None, vec![])).await;
        let req = ws_upgrade_request(port, "/ws", &[("Origin", "http://localhost:5173")]);
        let status = send_request(port, &req).await;
        assert!(status.contains("101"), "sin token configurado el upgrade pasa con buen Origin, fue: {status:?}");
    }
}
