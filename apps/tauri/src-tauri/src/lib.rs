//! ERPlora Shell — cliente **FINO** de escritorio (ADR-0159).
//!
//! La ventana carga ORÍGENES REMOTOS: el **onboarding del SaaS** (`{saas}/shell/`) en el primer
//! arranque y, una vez capturado, la **PWA del hub cloud** (`hub_url`). El contrato de captura es
//! el marcador `?shell=1`: el SaaS redirige al hub con él (`/shell/open/<id>/` → 302 a
//! `{hub}/?shell=1`) y el shell persiste el ORIGEN de esa navegación como `hub.url`; los arranques
//! siguientes cargan el hub directo. `forget_hub` (p. ej. Cloud 410 `hub_not_found`) borra la
//! captura y devuelve la ventana al onboarding.
//!
//! Qué NO hay aquí (ADR-0154 lo retiró; 0159 no lo resucita): runtime embebido, SQLite,
//! entitlement gate, token de máquina/keychain. El entitlement lo aplica el hub cloud server-side;
//! la identidad de máquina la inyecta el deployment. `invoke` queda SOLO para lo nativo
//! (`device_context`, `forget_hub`) y el HARDWARE (`erplora_*` → `erplora-peripherals`: el shell
//! ES el bridge, ADR-0050 §2.7).

use std::path::{Path, PathBuf};

use serde::Serialize;

/// Id de dispositivo estable por instalación (`X-Device-Id` del login; sesión única ADR-0154).
const DEVICE_ID_FILE: &str = "device.id";
/// Origen persistido de la PWA del hub capturado por `?shell=1` (modo app).
const HUB_URL_FILE: &str = "hub.url";
/// Registro persistente de dispositivos de hardware (mismo formato que el bridge standalone).
const DEVICES_FILE: &str = "devices.json";

/// Base del SaaS (onboarding). Default horneado; solo un fork/self-host la toca.
pub const ENV_SAAS_URL: &str = "ERPLORA_SAAS_URL";
/// Override de la URL inicial COMPLETA (solo desarrollo: apuntar a un SaaS local o a una PWA dev).
pub const ENV_SHELL_URL: &str = "ERPLORA_SHELL_URL";
const DEFAULT_SAAS_URL: &str = "https://erplora.com";

/// Error del shell serializado como string hacia el frontend (mismo patrón que el bridge).
#[derive(Debug, thiserror::Error)]
pub enum ShellError {
    #[error("io error: {0}")]
    Io(String),
}

impl Serialize for ShellError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

// ── Identidad de dispositivo (X-Device-Id) ───────────────────────────────────────────────────────

/// Identidad de dispositivo que el frontend envía al hacer login (sesión única por dispositivo,
/// ADR-0154 §5). El frontend la manda como `X-Client-Type` + `X-Device-Id` + `X-Device-Platform`.
#[derive(Debug, Clone, Serialize)]
pub struct DeviceContext {
    pub id: String,
    pub client_type: String,
    pub platform: String,
}

/// Lee (o crea y persiste) un id de dispositivo estable por instalación en `app_data_dir`.
/// Sobrevive a limpiezas de caché del webview: identifica **esta** instalación del shell.
fn ensure_device_id(cache_dir: &Path) -> Result<String, ShellError> {
    let path = cache_dir.join(DEVICE_ID_FILE);
    if let Ok(existing) = std::fs::read_to_string(&path) {
        let trimmed = existing.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }
    let id = uuid::Uuid::new_v4().to_string();
    std::fs::create_dir_all(cache_dir).map_err(|e| ShellError::Io(e.to_string()))?;
    std::fs::write(&path, &id).map_err(|e| ShellError::Io(e.to_string()))?;
    Ok(id)
}

/// Comando `invoke` que devuelve la identidad de dispositivo para el login.
#[tauri::command]
fn device_context(app: tauri::AppHandle) -> Result<DeviceContext, ShellError> {
    use tauri::Manager;
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| ShellError::Io(e.to_string()))?;
    let id = ensure_device_id(&cache_dir)?;
    // Verificado en el emulador (API 37): sin la rama `android` el shell se anunciaba como
    // `hub-desktop`/`desktop` DESDE UN MÓVIL, así que el Cloud no podía distinguir una tablet de
    // un TPV de mostrador — ni en la lista de sesiones ni en la sesión única de ADR-0154.
    let platform = if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else if cfg!(target_os = "android") {
        "android"
    } else if cfg!(target_os = "ios") {
        "ios"
    } else {
        "desktop"
    };
    let client_type = if cfg!(any(target_os = "android", target_os = "ios")) {
        "hub-mobile"
    } else {
        "hub-desktop"
    };
    Ok(DeviceContext {
        id,
        // Taxonomía del Cloud; la plataforma concreta viaja aparte en X-Device-Platform.
        client_type: client_type.to_string(),
        platform: platform.to_string(),
    })
}

// ── Estado del shell: captura y persistencia del hub_url (ADR-0159) ──────────────────────────────

/// Normaliza la base del SaaS: sin espacios ni `/` final.
fn normalize_base(base: &str) -> String {
    base.trim().trim_end_matches('/').to_string()
}

/// URL del onboarding del SaaS que carga el primer arranque.
fn onboarding_url(base: &str) -> String {
    format!("{}/shell/", normalize_base(base))
}

/// Base del SaaS: env [`ENV_SAAS_URL`] o el default horneado.
fn saas_base_url() -> String {
    normalize_base(
        &std::env::var(ENV_SAAS_URL)
            .ok()
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| DEFAULT_SAAS_URL.to_string()),
    )
}

/// Contrato de captura (ADR-0159): si la navegación lleva el marcador `?shell=1`, devuelve el
/// ORIGEN a persistir como `hub_url`. Solo `https` — o `http` a loopback (dev). Cualquier otra
/// cosa (esquemas raros, http remoto, sin marcador) → `None`.
fn shell_capture_origin(url: &tauri::Url) -> Option<String> {
    let has_marker = url.query_pairs().any(|(k, v)| k == "shell" && v == "1");
    if !has_marker {
        return None;
    }
    match url.scheme() {
        "https" => {}
        "http" => {
            // http SOLO a loopback (desarrollo): el hub cloud es siempre https.
            let loopback = matches!(url.host_str(), Some("127.0.0.1") | Some("localhost") | Some("[::1]"));
            if !loopback {
                return None;
            }
        }
        _ => return None,
    }
    let origin = url.origin();
    if !origin.is_tuple() {
        return None; // origen opaco (data:, blob:, …) — nada que persistir
    }
    Some(origin.ascii_serialization())
}

/// Lee el `hub.url` persistido (origen de la PWA), si existe y no está vacío.
fn load_hub_url(cache_dir: &Path) -> Option<String> {
    std::fs::read_to_string(cache_dir.join(HUB_URL_FILE))
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

/// Persiste el origen capturado como `hub.url` (crea `cache_dir` si no existe).
fn persist_hub_url(cache_dir: &Path, origin: &str) -> Result<(), ShellError> {
    std::fs::create_dir_all(cache_dir).map_err(|e| ShellError::Io(e.to_string()))?;
    std::fs::write(cache_dir.join(HUB_URL_FILE), origin).map_err(|e| ShellError::Io(e.to_string()))
}

/// Olvida el hub capturado (best-effort: no falla si no existía).
fn clear_hub_url(cache_dir: &Path) {
    let _ = std::fs::remove_file(cache_dir.join(HUB_URL_FILE));
}

/// Qué contesta el hub recordado cuando se le pregunta al arrancar.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HubProbe {
    /// Contestó con este código HTTP.
    Status(u16),
    /// No se pudo contactar: sin red, DNS caído, timeout.
    Unreachable,
}

/// ¿Hay que olvidar el `hub.url` recordado?
///
/// **Solo** si el hub ya no existe. Es una decisión asimétrica a propósito: olvidarlo de más le
/// borra al usuario su hub y le manda a rehacer el onboarding, mientras que olvidarlo de menos
/// solo le deja una pantalla fea que se arregla sola en cuanto el hub vuelva. Ante la duda, se
/// conserva.
///
/// Existe porque [`forget_hub`] **no alcanza este caso**: a ese lo llama el frontend al recibir un
/// 410 del Cloud, y si el hub fue borrado la PWA no llega a cargarse nunca — el 404 lo sirve el
/// edge. Sin esto la app abre en «404 page not found» de forma permanente y sin salida por la UI.
/// Medido en un Mac el 2026-08-01 con un hub que la purga de prod se había llevado por delante.
fn should_forget_hub(probe: HubProbe) -> bool {
    match probe {
        // El hub no está. 410 es además el contrato explícito `hub_not_found` del Cloud.
        HubProbe::Status(404) | HubProbe::Status(410) => true,
        // Todo lo demás —vivo, redirigiendo al login, sin autenticar, caído o inalcanzable— es un
        // hub que SÍ existe.
        _ => false,
    }
}

/// URL inicial de la ventana, por precedencia: override dev ([`ENV_SHELL_URL`]) → `hub.url`
/// persistido (modo app) → onboarding del SaaS. Pura para poder testearla.
fn initial_url_for(override_url: Option<&str>, persisted: Option<&str>, saas_base: &str) -> String {
    if let Some(dev) = override_url {
        return dev.to_string();
    }
    if let Some(origin) = persisted {
        return format!("{}/", normalize_base(origin));
    }
    onboarding_url(saas_base)
}

/// Olvida el hub capturado y devuelve la ventana al onboarding del SaaS. Lo invoca el frontend
/// cuando el Cloud responde 410 `hub_not_found` (hub borrado/revocado). CONSERVA `device.id`
/// (ancla estable de la instalación). Best-effort en la navegación (sin ventana no falla).
#[tauri::command]
fn forget_hub(app: tauri::AppHandle) -> Result<(), ShellError> {
    use tauri::Manager;
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| ShellError::Io(e.to_string()))?;
    clear_hub_url(&cache_dir);
    if let Some(window) = app.get_webview_window("main") {
        if let Ok(url) = onboarding_url(&saas_base_url()).parse::<tauri::Url>() {
            let _ = window.navigate(url);
        }
    }
    Ok(())
}

/// Pregunta en segundo plano si el hub recordado sigue existiendo y, si no, lo olvida y devuelve
/// la ventana al onboarding.
///
/// En segundo plano a propósito: la ventana ya está abierta y mostrando el hub, así que en el
/// caso normal —el hub existe— esto no se nota. En el caso malo el usuario ve el 404 un instante
/// y acaba en el onboarding, que es de donde puede salir. Bloquear el arranque para evitar ese
/// parpadeo penalizaría **todos** los arranques por un caso raro.
///
/// Un `HEAD` basta y no descarga la PWA entera. El timeout es corto porque no hay prisa: si no
/// contesta a tiempo se conserva el hub, que es la decisión segura ([`should_forget_hub`]).
///
/// Va por el runtime **async** de Tauri y con el cliente async de reqwest, NO por
/// `std::thread` + `reqwest::blocking`. Medido en el emulador API 37: con el cliente blocking la
/// petición **no llegaba a salir** en Android —ni un solo `HEAD` en el servidor— así que el
/// rescate no existía justo en la plataforma donde el usuario no puede borrar datos de la app a
/// mano. En macOS sí funcionaba, que es lo que lo hacía fácil de dar por bueno.
fn spawn_hub_liveness_check(app: tauri::AppHandle, cache_dir: PathBuf, origin: String) {
    tauri::async_runtime::spawn(async move {
        use tauri::Manager;

        let url = format!("{}/", normalize_base(&origin));
        let probe = match reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(6))
            .build()
        {
            Ok(c) => match c.head(&url).send().await {
                Ok(r) => HubProbe::Status(r.status().as_u16()),
                Err(e) => {
                    log::warn!("shell: no se pudo consultar el hub recordado ({origin}): {e}");
                    HubProbe::Unreachable
                }
            },
            Err(e) => {
                log::warn!("shell: no se pudo crear el cliente HTTP: {e}");
                HubProbe::Unreachable
            }
        };
        if !should_forget_hub(probe) {
            return;
        }

        log::info!("shell: el hub recordado ({origin}) ya no existe ({probe:?}); vuelvo al onboarding");
        clear_hub_url(&cache_dir);
        if let Some(window) = app.get_webview_window("main") {
            if let Ok(url) = onboarding_url(&saas_base_url()).parse::<tauri::Url>() {
                let _ = window.navigate(url);
            }
        }
    });
}

/// Crea la ventana principal apuntando a [`initial_url_for`] y registra el `on_navigation` que
/// captura `?shell=1` → persiste el origen como `hub.url` (una sola escritura por cambio).
fn open_main_window(app: &tauri::App, cache_dir: Option<PathBuf>) -> tauri::Result<()> {
    use tauri::{WebviewUrl, WebviewWindowBuilder};

    let persisted = cache_dir.as_deref().and_then(load_hub_url);
    let override_url = std::env::var(ENV_SHELL_URL)
        .ok()
        .filter(|v| !v.trim().is_empty());
    let initial = initial_url_for(override_url.as_deref(), persisted.as_deref(), &saas_base_url());
    let url = match initial.parse::<tauri::Url>() {
        Ok(u) => WebviewUrl::External(u),
        Err(e) => {
            // Degradado: página estática empaquetada (shell-dist). No debería pasar salvo un
            // ERPLORA_SHELL_URL/ERPLORA_SAAS_URL malformado.
            eprintln!("shell: URL inicial inválida ({initial}): {e}; cargo la página degradada");
            WebviewUrl::App("index.html".into())
        }
    };

    // Si se arranca contra un hub recordado, hay que comprobar que sigue existiendo — pero DESPUÉS
    // de abrir la ventana, no antes: bloquear el arranque de un TPV por una petición de red sería
    // peor que la pantalla que se intenta evitar.
    if override_url.is_none() {
        if let (Some(dir), Some(origin)) = (cache_dir.clone(), persisted.clone()) {
            spawn_hub_liveness_check(app.handle().clone(), dir, origin);
        }
    }

    let last = std::sync::Mutex::new(persisted);
    WebviewWindowBuilder::new(app, "main", url)
        .title("ERPlora")
        .inner_size(1280.0, 800.0)
        .min_inner_size(960.0, 600.0)
        .on_navigation(move |nav| {
            if let (Some(dir), Some(origin)) = (cache_dir.as_deref(), shell_capture_origin(nav)) {
                if let Ok(mut guard) = last.lock() {
                    if guard.as_deref() != Some(origin.as_str()) {
                        match persist_hub_url(dir, &origin) {
                            Ok(()) => *guard = Some(origin),
                            Err(e) => eprintln!("shell: no se pudo persistir hub.url: {e}"),
                        }
                    }
                }
            }
            true // el shell nunca bloquea la navegación; solo observa el marcador
        })
        .build()?;
    Ok(())
}

// ── Camino de hardware: handlers `invoke` → erplora-peripherals ──────────────────────────────────
//
// El shell ES el bridge (no hay proceso bridge aparte, §2.7): el hardware se expone por handlers
// `invoke` que delegan en `erplora-peripherals`, el mismo crate que usa el bridge standalone
// (`apps/bridge`) vía WebSocket. El contrato de datos es idéntico al de las frames WS del bridge:
// `discoverPrinters`/`getDevices` devuelven el array de `protocol::{PrinterInfo,Device}`
// (serde-serializado igual que `BridgePrinter`/`BridgeDevice` del SDK);
// `print`/`testPrint`/`openDrawer` no devuelven nada.
//
// El `Watchdog` del registry corre como tarea async del shell (auto-recuperación de IP por DHCP),
// y la `PrintQueue` con reintentos drena en segundo plano — igual que `apps/bridge`. Los outcomes
// y eventos del watchdog se loguean (en el bridge standalone viajan por WS; aquí el canal a la UI
// se cablearía con eventos Tauri en una fase posterior — columna del humano).

use erplora_peripherals::discovery::{self, parse_printer_id};
use erplora_peripherals::drawer;
use erplora_peripherals::escpos::{self, DocumentType};
use erplora_peripherals::protocol::{Device, PrinterInfo};
use erplora_peripherals::queue::{JobOutcome, PrintJob, PrintQueue, RetryPolicy};
use erplora_peripherals::registry::DeviceRegistry;

/// Estado de hardware compartido entre handlers `invoke`: registro persistente de dispositivos +
/// cola de impresión con reintentos. Vive en el estado gestionado de Tauri (`app.manage`). El
/// registro y la cola van tras `Arc` para que las tareas de fondo (watchdog + worker de la cola)
/// compartan las mismas instancias que los handlers `invoke`.
struct PeripheralsState {
    registry: std::sync::Arc<DeviceRegistry>,
    queue: std::sync::Arc<PrintQueue>,
}

/// Construye el estado de hardware y **lanza** las tareas de fondo en el runtime tokio actual:
///   - worker de la `PrintQueue` (envío con reintentos; cada `JobOutcome` se loguea),
///   - `Watchdog` del registry (health-check + recovery por MAC ante cambio de IP DHCP).
/// Espejo de `spawn_queue_worker`/`spawn_watchdog` del bridge standalone (`apps/bridge/src/main.rs`).
fn build_peripherals_state(devices_path: PathBuf) -> PeripheralsState {
    let registry = std::sync::Arc::new(DeviceRegistry::load(devices_path));
    let queue = std::sync::Arc::new(PrintQueue::new(RetryPolicy::default()));

    // Worker de la cola de impresión: drena y reintenta; loguea cada outcome. `async_runtime::spawn`
    // usa el runtime tokio global de Tauri, así que funciona desde el `setup` hook.
    let worker_queue = queue.clone();
    tauri::async_runtime::spawn(async move {
        let (outcomes_tx, mut outcomes_rx) = tokio::sync::mpsc::unbounded_channel::<JobOutcome>();
        tauri::async_runtime::spawn(async move {
            while let Some(outcome) = outcomes_rx.recv().await {
                match outcome {
                    JobOutcome::Completed { job_id } => {
                        eprintln!("peripherals: trabajo de impresión completado ({job_id:?})")
                    }
                    JobOutcome::Failed { job_id, error } => {
                        eprintln!("peripherals: trabajo de impresión fallido ({job_id:?}): {error}")
                    }
                }
            }
        });
        worker_queue.run(outcomes_tx).await;
        eprintln!("peripherals: worker de la cola de impresión terminado (cola cerrada)");
    });

    // Watchdog del registry: auto-recuperación de dispositivos tras cambio de IP por DHCP.
    let watchdog_registry = registry.clone();
    tauri::async_runtime::spawn(async move {
        use erplora_peripherals::registry::{Watchdog, WatchdogConfig, WatchdogEvent};
        let (events_tx, mut events_rx) = tokio::sync::mpsc::unbounded_channel::<WatchdogEvent>();
        tauri::async_runtime::spawn(async move {
            while let Some(ev) = events_rx.recv().await {
                match ev {
                    // `key` y no `mac`: es la identidad estable del dispositivo y siempre existe
                    // (la MAC es `None` cuando ARP no resuelve — siempre en Android).
                    WatchdogEvent::Recovered(d) => {
                        eprintln!("peripherals: dispositivo recuperado {} ({})", d.name, d.key)
                    }
                    WatchdogEvent::Lost(d) => {
                        eprintln!("peripherals: dispositivo perdido {} ({})", d.name, d.key)
                    }
                }
            }
        });
        let watchdog = Watchdog::new(WatchdogConfig::default()).with_events(events_tx);
        watchdog.run(&watchdog_registry).await;
    });

    PeripheralsState { registry, queue }
}

/// Error de los handlers de hardware. Se serializa como string para el frontend (igual que el
/// `Event::Error` del bridge standalone se mapea a un rechazo de la promesa en el SDK).
#[derive(Debug, thiserror::Error)]
pub enum HardwareError {
    #[error("{0}")]
    Peripheral(#[from] erplora_peripherals::PeripheralError),
}

impl Serialize for HardwareError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// `erplora_bridge_status` — el `IpcBridgeTransport.detect()` lo invoca para saber si el canal de
/// hardware existe (en el shell siempre existe: el shell ES el bridge). Devuelve la versión.
#[tauri::command]
fn erplora_bridge_status() -> serde_json::Value {
    serde_json::json!({ "version": env!("CARGO_PKG_VERSION") })
}

/// `erplora_discover_printers` — re-escanea la red (mDNS + subred), registra y devuelve las
/// impresoras. Espejo de `Command::DiscoverPrinters` del bridge; devuelve el array directo.
#[tauri::command]
async fn erplora_discover_printers(
    state: tauri::State<'_, PeripheralsState>,
) -> Result<Vec<PrinterInfo>, HardwareError> {
    Ok(discovery::discover_printers(&state.registry).await?)
}

/// `erplora_get_devices` — contenido del registro persistente de dispositivos (con sus roles).
#[tauri::command]
fn erplora_get_devices(state: tauri::State<'_, PeripheralsState>) -> Vec<Device> {
    state.registry.get_all()
}

/// `erplora_print` — renderiza el documento ESC/POS y lo **encola** para envío con reintentos
/// (mismo flujo que `Command::Print` del bridge). Errores previos al encolado (printer_id/payload
/// inválidos) se devuelven; el resultado del envío llega por el worker de la cola (log).
#[tauri::command]
fn erplora_print(
    state: tauri::State<'_, PeripheralsState>,
    printer_id: String,
    document_type: String,
    data: serde_json::Value,
    job_id: Option<String>,
) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    let payload = escpos::render_document(DocumentType::from_wire(&document_type), &data)?;
    state.queue.enqueue(PrintJob {
        job_id,
        target,
        payload,
        attempts: 0,
    })?;
    Ok(())
}

/// `erplora_test_print` — encola una página de prueba en la impresora dada.
#[tauri::command]
fn erplora_test_print(
    state: tauri::State<'_, PeripheralsState>,
    printer_id: String,
) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    let payload = escpos::render_test_page(&printer_id);
    state.queue.enqueue(PrintJob {
        job_id: None,
        target,
        payload,
        attempts: 0,
    })?;
    Ok(())
}

/// `erplora_open_drawer` — abre el cajón vía kick ESC/POS por el socket de la impresora.
#[tauri::command]
async fn erplora_open_drawer(printer_id: String, pin: Option<u8>) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    drawer::open_drawer(&target, pin.unwrap_or(2)).await?;
    Ok(())
}

/// `erplora_set_device_role` — asigna rol (receipt/kitchen/bar/label) y devuelve el registro
/// actualizado. Espejo de `Command::SetDeviceRole`.
#[tauri::command]
fn erplora_set_device_role(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
    role: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.set_role(&mac, &role)?;
    Ok(state.registry.get_all())
}

/// `erplora_set_device_name` — renombra un dispositivo y devuelve el registro actualizado.
#[tauri::command]
fn erplora_set_device_name(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
    name: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.set_name(&mac, &name)?;
    Ok(state.registry.get_all())
}

/// `erplora_remove_device` — elimina un dispositivo del registro y devuelve el registro actualizado.
#[tauri::command]
fn erplora_remove_device(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.remove(&mac)?;
    Ok(state.registry.get_all())
}

/// `erplora_notify` — notificación del SISTEMA (la del SO, no un toast dentro de la app).
///
/// Para eso existe: avisar cuando **nadie está mirando la pantalla**. El caso que la motiva es la
/// comanda — entra un pedido y cocina tiene que enterarse aunque la tablet esté en otra vista o
/// bloqueada. Un toast de la app no sirve ahí.
///
/// Lo expone el SHELL y no `apps/bridge` porque en Tauri el shell **es** el bridge (ADR-0050 §2.7);
/// el binario suelto ya lo hacía con `notify_rust` para el caso «PWA en Chrome». El protocolo lo
/// declaraba desde el principio (`Command::SendNotification`) y este era el lado que faltaba: sin
/// él, ningún módulo podía avisar de nada desde la app.
///
/// **Nunca falla hacia arriba.** Si el usuario denegó el permiso o la plataforma no puede
/// mostrarla, se registra y se sigue: una notificación que no sale no puede tumbar la comanda que
/// la provocó.
#[tauri::command]
fn erplora_notify(app: tauri::AppHandle, title: String, body: String) {
    use tauri_plugin_notification::NotificationExt;

    if let Err(e) = app.notification().builder().title(&title).body(&body).show() {
        eprintln!("notify: la plataforma no pudo mostrar «{title}» ({e}) — se sigue igualmente");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_erplora_android::init())
        .setup(|app| {
            use tauri::Manager;
            // Raíz de datos por-instalación: device.id + hub.url + devices.json. Si no se puede
            // resolver, el shell arranca igualmente (sin persistencia) — cliente fino, sin BD.
            let cache_dir = match app.path().app_data_dir() {
                Ok(dir) => {
                    if let Err(e) = std::fs::create_dir_all(&dir) {
                        eprintln!("shell: no se pudo crear app_data_dir ({}): {e}", dir.display());
                    }
                    Some(dir)
                }
                Err(e) => {
                    eprintln!("shell: app_data_dir no disponible: {e}");
                    None
                }
            };
            // Estado de hardware: registro de dispositivos + cola de impresión + watchdog.
            let devices_path = cache_dir
                .as_deref()
                .map(|d| d.join(DEVICES_FILE))
                .unwrap_or_else(|| PathBuf::from(DEVICES_FILE));
            app.manage(build_peripherals_state(devices_path));
            // Ventana única: onboarding del SaaS o el hub capturado (modo app).
            if let Err(e) = open_main_window(app, cache_dir) {
                eprintln!("no se pudo crear la ventana principal: {e}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            device_context,
            forget_hub,
            // Datos: NO van por `invoke` (ADR-0050) — la PWA habla HTTP+WS con su hub cloud.
            // Camino de hardware: impresoras de red ESC/POS + cajón → peripherals.
            erplora_bridge_status,
            erplora_discover_printers,
            erplora_get_devices,
            erplora_print,
            erplora_test_print,
            erplora_open_drawer,
            erplora_set_device_role,
            erplora_set_device_name,
            erplora_remove_device,
            erplora_notify
        ])
        .run(tauri::generate_context!())
        .expect("error while running ERPlora shell");
}

// ── Tests (TDD, ADR-0159) ────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn url(s: &str) -> tauri::Url {
        s.parse().expect("url de test válida")
    }

    fn tempdir() -> PathBuf {
        let dir = std::env::temp_dir().join(format!("erplora-shell-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).expect("tempdir");
        dir
    }

    // ── shell_capture_origin: el contrato del marcador ?shell=1 ──────────────────────────────

    #[test]
    fn capture_requiere_el_marcador_shell_1() {
        assert_eq!(shell_capture_origin(&url("https://demo.erplora.com/")), None);
        assert_eq!(
            shell_capture_origin(&url("https://demo.erplora.com/?shell=2")),
            None
        );
        assert_eq!(
            shell_capture_origin(&url("https://demo.erplora.com/?other=1")),
            None
        );
    }

    #[test]
    fn capture_devuelve_el_origen_https() {
        assert_eq!(
            shell_capture_origin(&url("https://demo.erplora.com/pos?shell=1&x=2")),
            Some("https://demo.erplora.com".to_string())
        );
    }

    #[test]
    fn capture_conserva_el_puerto_no_default() {
        assert_eq!(
            shell_capture_origin(&url("https://hub.example.com:8443/?shell=1")),
            Some("https://hub.example.com:8443".to_string())
        );
    }

    #[test]
    fn capture_http_solo_loopback() {
        // http remoto NO se captura (el hub cloud es siempre https).
        assert_eq!(shell_capture_origin(&url("http://evil.com/?shell=1")), None);
        // loopback sí (desarrollo local: runtime :8787 / Vite :5173).
        assert_eq!(
            shell_capture_origin(&url("http://127.0.0.1:8787/?shell=1")),
            Some("http://127.0.0.1:8787".to_string())
        );
        assert_eq!(
            shell_capture_origin(&url("http://localhost:5173/?shell=1")),
            Some("http://localhost:5173".to_string())
        );
    }

    #[test]
    fn capture_rechaza_esquemas_no_http() {
        assert_eq!(shell_capture_origin(&url("tauri://localhost/?shell=1")), None);
        assert_eq!(shell_capture_origin(&url("file:///tmp/x?shell=1")), None);
    }

    // ── persistencia de hub.url ──────────────────────────────────────────────────────────────

    #[test]
    fn hub_url_roundtrip_persist_load_clear() {
        let dir = tempdir();
        assert_eq!(load_hub_url(&dir), None);
        persist_hub_url(&dir, "https://demo.erplora.com").expect("persist");
        assert_eq!(load_hub_url(&dir), Some("https://demo.erplora.com".to_string()));
        clear_hub_url(&dir);
        assert_eq!(load_hub_url(&dir), None);
        clear_hub_url(&dir); // best-effort: repetir no falla
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_hub_url_ignora_vacios_y_recorta() {
        let dir = tempdir();
        std::fs::write(dir.join(HUB_URL_FILE), "  \n").expect("write");
        assert_eq!(load_hub_url(&dir), None);
        std::fs::write(dir.join(HUB_URL_FILE), "https://a.erplora.com\n").expect("write");
        assert_eq!(load_hub_url(&dir), Some("https://a.erplora.com".to_string()));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn persist_hub_url_crea_el_directorio() {
        let dir = tempdir().join("anidado");
        persist_hub_url(&dir, "https://b.erplora.com").expect("persist");
        assert_eq!(load_hub_url(&dir), Some("https://b.erplora.com".to_string()));
        let _ = std::fs::remove_dir_all(dir.parent().unwrap());
    }

    // ── URL inicial: precedencia override dev → hub persistido → onboarding ──────────────────

    #[test]
    fn initial_url_precedencia() {
        // Override de desarrollo gana siempre.
        assert_eq!(
            initial_url_for(
                Some("http://127.0.0.1:8001/shell/"),
                Some("https://demo.erplora.com"),
                "https://erplora.com"
            ),
            "http://127.0.0.1:8001/shell/"
        );
        // Hub persistido → modo app (origen + "/").
        assert_eq!(
            initial_url_for(None, Some("https://demo.erplora.com"), "https://erplora.com"),
            "https://demo.erplora.com/"
        );
        // Nada persistido → onboarding del SaaS.
        assert_eq!(
            initial_url_for(None, None, "https://erplora.com"),
            "https://erplora.com/shell/"
        );
    }

    // ── El hub recordado ya no existe: la app NO puede quedarse tapiada ──────────────────────

    #[test]
    fn un_hub_borrado_se_olvida_al_arrancar() {
        // Medido en un Mac el 2026-08-01: `hub.url` apuntaba a un hub que la purga de prod había
        // borrado, y la app abría en «404 page not found» — para siempre y SIN salida. El
        // `forget_hub` que ya existe no sirve aquí: lo invoca el frontend al recibir un 410, y en
        // este caso la PWA no llega a cargarse nunca porque el 404 lo sirve el edge.
        assert!(should_forget_hub(HubProbe::Status(404)));
        // 410 es el contrato explícito de `hub_not_found` del Cloud.
        assert!(should_forget_hub(HubProbe::Status(410)));
    }

    #[test]
    fn un_hub_vivo_no_se_olvida() {
        assert!(!should_forget_hub(HubProbe::Status(200)));
        // El hub redirige al login: existe.
        assert!(!should_forget_hub(HubProbe::Status(302)));
    }

    #[test]
    fn no_estar_autenticado_no_es_que_el_hub_no_exista() {
        // Confundirlo echaría al usuario al onboarding cada vez que le caduca la sesión.
        assert!(!should_forget_hub(HubProbe::Status(401)));
        assert!(!should_forget_hub(HubProbe::Status(403)));
    }

    #[test]
    fn un_hub_caido_no_se_olvida() {
        // Caído ≠ inexistente. Olvidarlo por una caída de 30 s le borraría al usuario su hub y le
        // obligaría a rehacer el onboarding, que es MUCHO peor que esperar.
        for s in [500, 502, 503, 504] {
            assert!(!should_forget_hub(HubProbe::Status(s)), "{s} no debe olvidar el hub");
        }
    }

    #[test]
    fn sin_red_no_se_olvida_nada() {
        // Un TPV arranca en locales con wifi malo, con el router reiniciándose o con el portátil
        // aún sin asociar. Borrar el hub por no poder contactarlo sería catastrófico: el hub está
        // perfectamente vivo y el usuario acabaría en el onboarding sin entender por qué.
        assert!(!should_forget_hub(HubProbe::Unreachable));
    }

    #[test]
    fn onboarding_url_normaliza_la_base() {
        assert_eq!(onboarding_url("https://erplora.com"), "https://erplora.com/shell/");
        assert_eq!(
            initial_url_for(None, None, "https://erplora.com/"),
            "https://erplora.com/shell/"
        );
        assert_eq!(normalize_base("  https://erplora.com/  "), "https://erplora.com");
    }

    // ── identidad de dispositivo ─────────────────────────────────────────────────────────────

    #[test]
    fn ensure_device_id_estable_entre_llamadas() {
        let dir = tempdir();
        let a = ensure_device_id(&dir).expect("primera");
        let b = ensure_device_id(&dir).expect("segunda");
        assert_eq!(a, b);
        assert!(!a.is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
