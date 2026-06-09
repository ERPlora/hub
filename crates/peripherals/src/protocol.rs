//! Contrato JSON Hub ↔ Bridge sobre WebSocket — **fuente única de verdad** del protocolo.
//!
//! Espejo de `bridge/ERPlora-Bridge-desktop/erplora_bridge/protocol.py` y de `Protocol.kt`
//! (Android). `hub/static/js/bridge.js` consume este formato sin cambios.
//!
//! Cambios de superficie por la decisión red-only (§2.7) respecto al protocolo Python:
//!   - **Eliminadas** las acciones/eventos de escáner y teclado virtual: `toggle_keyboard`,
//!     evento `barcode`, evento `keyboard_toggled` (el escáner HID lo maneja el SO/navegador).
//!   - `printer_id` queda siempre `network:{ip}:{port}` (sin `usb:` ni `bluetooth:`).

use serde::{Deserialize, Serialize};

/// Mensaje Hub → Bridge. Discriminado por la clave `action`.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "action", rename_all = "snake_case")]
pub enum Command {
    /// Versión del bridge + impresoras cacheadas.
    GetStatus,
    /// Re-escanea la red en busca de impresoras.
    DiscoverPrinters,
    /// Imprime un documento.
    Print {
        printer_id: String,
        document_type: String,
        data: serde_json::Value,
        #[serde(default)]
        job_id: Option<String>,
    },
    /// Abre el cajón vía kick ESC/POS por el socket de la impresora.
    OpenDrawer {
        printer_id: String,
        #[serde(default = "default_drawer_pin")]
        pin: u8,
    },
    /// Página de prueba.
    TestPrint { printer_id: String },
    /// Notificación a nivel de SO.
    SendNotification { title: String, body: String },
    /// Contenido del registro de dispositivos.
    GetDevices,
    /// Asigna rol a un dispositivo (`receipt` | `kitchen` | `bar` | `label`).
    SetDeviceRole { mac: String, role: String },
    /// Renombra un dispositivo.
    SetDeviceName { mac: String, name: String },
    /// Elimina un dispositivo del registro.
    RemoveDevice { mac: String },
}

/// Mensaje Bridge → Hub. Discriminado por la clave `event`.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "event", rename_all = "snake_case")]
pub enum Event {
    Status {
        version: String,
        printers: Vec<PrinterInfo>,
        /// Siempre `false` en red-only; se conserva por compatibilidad con `bridge.js`.
        scanner: bool,
    },
    Printers { printers: Vec<PrinterInfo> },
    Devices { devices: Vec<Device> },
    DeviceRecovered { device: Device },
    DeviceLost { device: Device },
    PrintComplete { job_id: Option<String> },
    PrintError { job_id: Option<String>, error: String },
    DrawerOpened { printer_id: String },
    Error { message: String, code: String },
}

/// Info estandarizada de una impresora (espejo de `printer_info()` en Python).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PrinterInfo {
    /// `network:{ip}:{port}`.
    pub id: String,
    pub name: String,
    /// Siempre `"network"` en red-only.
    #[serde(rename = "type")]
    pub kind: String,
    /// `ready` | `busy` | `error` | `offline`.
    pub status: String,
    pub paper_width: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mac: Option<String>,
}

/// Entrada del registro persistente de dispositivos (espejo del dict en `network.py`).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Device {
    pub mac: String,
    pub ip: String,
    pub port: u16,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
    #[serde(rename = "type")]
    pub kind: String,
    pub first_seen: String,
    pub last_seen: String,
    /// `online` | `offline`.
    pub status: String,
}

fn default_drawer_pin() -> u8 {
    2
}
