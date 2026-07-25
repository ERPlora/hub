//! Tests del modelo del tray (ADR-0154). Cuerpo del módulo `tests` de `tray.rs` (incluido con
//! `#[path]`). El modelo es PURO (sin GUI) para poder testear las etiquetas sin display/event-loop;
//! el icono real de la bandeja va detrás de la feature `tray` y no se ejercita en CI.

use super::*;
use crate::pairing::Pairing;

fn pairing(name: &str) -> Pairing {
    Pairing {
        hub_id: "hub-1".into(),
        hub_name: name.into(),
        hub_url: "https://hub-1.erplora.com".into(),
        bridge_device_token: "secret".into(),
        saas_public_key_url: None,
    }
}

#[test]
fn model_unpaired_shows_not_paired() {
    let m = tray_model(None);
    assert_eq!(m.status, "Not paired");
    assert_eq!(m.configure_label, "Configure");
    assert_eq!(m.quit_label, "Quit");
}

#[test]
fn model_paired_shows_hub_name() {
    let m = tray_model(Some(&pairing("Sur Restaurante")));
    assert_eq!(m.status, "Paired with Sur Restaurante");
    assert_eq!(m.configure_label, "Configure");
    assert_eq!(m.quit_label, "Quit");
}
