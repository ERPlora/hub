//! `erplora-peripherals` — lógica de hardware POS reutilizable, **solo red** (ESC/POS sobre
//! TCP, puerto 9100). ARQUITECTURA.md §2.7.
//!
//! Este crate concentra lo que era el Bridge Python (`bridge/ERPlora-Bridge-desktop`) en una
//! librería sin I/O de UI ni servidor WebSocket — el consumidor monta su propio transporte:
//!   - **`apps/bridge`** (standalone, combo `cloud + web-PWA`) → servidor Axum `GET /status` + `WS /ws`.
//!
//! Decisión red-only (§2.7): USB/Bluetooth se descartan; el escáner por HID lo maneja el
//! SO/navegador como teclado. Por eso aquí **no** hay `usb`/`bluetooth`/`scanner`.
//!
//! Estado: **implementado** — render ESC/POS (`escpos`), descubrimiento (`discovery`), registro +
//! watchdog (`registry`), cajón (`drawer`), cola con reintentos (`queue`) e impresora por red con
//! traits (`printer`). El mapeo Python→Rust por módulo está en `README.md`.

pub mod discovery;
pub mod drawer;
pub mod escpos;
pub mod printer;
pub mod protocol;
pub mod queue;
pub mod registry;

/// Puerto estándar ESC/POS por red (raw printing).
pub const ESCPOS_NETWORK_PORT: u16 = 9100;

/// Puerto por defecto del servidor WebSocket del Bridge (compat con `hub/static/js/bridge.js`).
pub const BRIDGE_WS_PORT: u16 = 12321;

/// Error común de la capa de periféricos.
#[derive(Debug, thiserror::Error)]
pub enum PeripheralError {
    #[error("printer id inválido: {0}")]
    InvalidPrinterId(String),
    #[error("impresora inalcanzable: {0}")]
    Unreachable(String),
    #[error("tipo de documento desconocido: {0}")]
    UnknownDocumentType(String),
    #[error("payload inválido: {0}")]
    InvalidPayload(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, PeripheralError>;
