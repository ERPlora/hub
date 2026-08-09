//! `erplora-peripherals` — lógica de hardware POS reutilizable, **solo red** (ESC/POS sobre
//! TCP, puerto 9100). ARQUITECTURA.md §2.7.
//!
//! Este crate concentra lo que era el Bridge Python (`bridge/ERPlora-Bridge-desktop`) en una
//! librería sin I/O de UI ni servidor WebSocket — el consumidor monta su propio transporte. Desde
//! ADR-0196 (ejecutado en hub#340) queda **uno solo**: la app instalable `apps/tauri`, que llama a
//! este crate **in-process** por `invoke`. El standalone `apps/bridge`, que lo servía por un
//! WebSocket en `localhost:12321`, ya no existe: no hay puerto local, ni token de emparejamiento.
//!
//! Decisión red-only (§2.7): USB/Bluetooth se descartan; el escáner por HID lo maneja el
//! SO/navegador como teclado. Por eso aquí **no** hay `usb`/`bluetooth`/`scanner`.
//!
//! Estado: **implementado** — render ESC/POS (`escpos`), descubrimiento (`discovery`), registro +
//! watchdog (`registry`), cajón (`drawer`) y cola con reintentos (`queue`). El mapeo Python→Rust
//! por módulo está en `README.md`.
//!
//! Hubo además un `printer` con una capa de traits (`Printer`/`CashDrawer`) y **su propia**
//! política de reintentos: nunca tuvo consumidor —la app encola por `queue` y abre el cajón por
//! `drawer`— y dos políticas de reintento coexistiendo son una que nadie mantiene. hub#379 la
//! borró y pasó su cobertura a las vías vivas.

pub mod discovery;
pub mod drawer;
pub mod escpos;
pub mod protocol;
pub mod queue;
pub mod registry;

#[cfg(test)]
mod test_support;

/// Puerto estándar ESC/POS por red (raw printing).
pub const ESCPOS_NETWORK_PORT: u16 = 9100;

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
