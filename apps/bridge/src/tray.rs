//! Icono de la **bandeja del sistema** del Bridge (ADR-0154, hub#201).
//!
//! El **modelo** del menú es puro (sin GUI): a partir del emparejamiento produce las etiquetas
//! (estado + «Configure» + «Quit»), y se testea sin display. El icono real vive detrás de la
//! **feature `tray`** (`tray-icon`), OFF por defecto: así `cargo test` y el binario headless (CI)
//! compilan sin dependencias gráficas ni event-loop de plataforma.
//!
//! **Limitación (documentada, ADR-0154):** `tray-icon` exige el event-loop nativo en el hilo
//! principal (NSApplication en macOS; gtk/winit en Linux/Windows). El binario standalone corre
//! `#[tokio::main]` en ese hilo, así que aquí solo se **construye** el tray; el bombeo de eventos
//! del menú (clicks en Configure/Quit) lo cablea el shell que embebe el Bridge (sidecar Tauri) o un
//! arranque con event-loop dedicado. El pairing NO depende del tray: sin feature/headless el Bridge
//! degrada a logs (código de emparejamiento por consola).

use crate::pairing::{status_label, Pairing};

/// Etiquetas del menú de la bandeja, derivadas del emparejamiento. Puro y testeable sin GUI. Lo
/// consume el icono real (feature `tray`) y los tests; sin la feature (headless) no se cablea en el
/// binario → `allow(dead_code)`.
#[allow(dead_code)]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrayModel {
    /// Línea de estado (informativa, deshabilitada en el menú): «Paired with X» / «Not paired».
    pub status: String,
    /// Entrada que abre el navegador de emparejamiento.
    pub configure_label: String,
    /// Entrada de salida.
    pub quit_label: String,
}

/// Construye el modelo del menú a partir del emparejamiento actual (reutiliza [`status_label`]).
/// Consumido bajo la feature `tray` y por los tests → `allow(dead_code)` en el binario headless.
#[allow(dead_code)]
pub fn tray_model(pairing: Option<&Pairing>) -> TrayModel {
    TrayModel {
        status: status_label(pairing),
        configure_label: "Configure".to_string(),
        quit_label: "Quit".to_string(),
    }
}

/// API del icono real de la bandeja — solo con la feature `tray`.
#[cfg(feature = "tray")]
pub use platform::build_tray;

#[cfg(feature = "tray")]
mod platform {
    use super::TrayModel;
    use tray_icon::menu::{Menu, MenuItem, PredefinedMenuItem};
    use tray_icon::{Icon, TrayIcon, TrayIconBuilder};

    /// Construye el `TrayIcon` con su menú (estado deshabilitado + Configure + Quit). Devuelve el
    /// handle: mantenerlo vivo mantiene el icono. Requiere un event-loop nativo para que el menú
    /// responda (ver doc del módulo); el handle debe conservarse mientras el proceso viva.
    pub fn build_tray(model: &TrayModel) -> Result<TrayIcon, String> {
        let menu = Menu::new();
        let status = MenuItem::new(&model.status, false, None); // informativo → deshabilitado
        let configure = MenuItem::new(&model.configure_label, true, None);
        let quit = PredefinedMenuItem::quit(Some(&model.quit_label));
        menu.append(&status).map_err(|e| e.to_string())?;
        menu.append(&PredefinedMenuItem::separator()).map_err(|e| e.to_string())?;
        menu.append(&configure).map_err(|e| e.to_string())?;
        menu.append(&quit).map_err(|e| e.to_string())?;

        // Icono mínimo 1×1 (azul ERPlora) — el asset real lo aporta el empaquetado del shell.
        let icon = Icon::from_rgba(vec![0x00, 0x7A, 0xCC, 0xFF], 1, 1).map_err(|e| e.to_string())?;

        TrayIconBuilder::new()
            .with_tooltip("ERPlora Bridge")
            .with_menu(Box::new(menu))
            .with_icon(icon)
            .build()
            .map_err(|e| e.to_string())
    }
}

#[cfg(test)]
#[path = "tray_test.rs"]
mod tests;
