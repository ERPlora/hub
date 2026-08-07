//! Permisos de RUNTIME de Android para el shell de ERPlora.
//!
//! Declarar un permiso en el manifest no basta, y los dos que necesita el TPV fallan **en
//! silencio**:
//!
//! - sin `ACCESS_LOCAL_NETWORK` (API 37+) el barrido del puerto 9100 son 254 **timeouts**, así que
//!   el descubrimiento devuelve `[]` y parece que el local no tiene impresoras;
//! - sin `POST_NOTIFICATIONS` (API 33+) la notificación no aparece, y la comanda entra en cocina
//!   sin que nadie se entere.
//!
//! Verificado en el emulador API 37 antes de existir este plugin: `erplora_discover_printers`
//! devolvía una lista vacía sin la menor queja hasta conceder el permiso a mano con `adb`.
//!
//! En escritorio no hay nada que pedir: los comandos existen igual y responden «concedido», para
//! que la PWA pueda llamarlos sin ramificar por plataforma.

use serde::{Deserialize, Serialize};
use tauri::{
    plugin::{Builder, TauriPlugin},
    Manager, Runtime,
};

/// Estado de un permiso tal y como lo ve la PWA: `{ "android.permission.X": true }`.
pub type PermissionStatus = std::collections::HashMap<String, bool>;

/// Local network access (API 37+). Without it the printer sweep is 254 silent timeouts.
///
/// Mirror of `PermissionPolicy.ACCESS_LOCAL_NETWORK` on the Kotlin side. The key of the map above
/// **is** the permission string, so Rust needs the same literal to read the answer — and a test
/// below checks the two never drift apart.
pub const ACCESS_LOCAL_NETWORK: &str = "android.permission.ACCESS_LOCAL_NETWORK";

/// System notifications (API 33+). Mirror of `PermissionPolicy.POST_NOTIFICATIONS`.
pub const POST_NOTIFICATIONS: &str = "android.permission.POST_NOTIFICATIONS";

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("{0}")]
    PluginInvoke(String),
}

impl Serialize for Error {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

#[derive(Debug, Default, Serialize, Deserialize)]
pub struct Empty {}

#[cfg(target_os = "android")]
const PLUGIN_IDENTIFIER: &str = "com.erplora.android";

/// Estado del plugin: en Android guarda el handle del módulo Kotlin; en escritorio, nada.
#[cfg(target_os = "android")]
pub struct ErploraAndroid<R: Runtime>(tauri::plugin::PluginHandle<R>);

#[cfg(not(target_os = "android"))]
pub struct ErploraAndroid<R: Runtime>(std::marker::PhantomData<fn() -> R>);

impl<R: Runtime> ErploraAndroid<R> {
    /// Permisos concedidos ahora mismo. En escritorio, siempre vacío: no hay nada que conceder.
    pub fn check_permissions(&self) -> Result<PermissionStatus, Error> {
        #[cfg(target_os = "android")]
        {
            return self
                .0
                .run_mobile_plugin("checkPermissions", Empty {})
                .map_err(|e| Error::PluginInvoke(e.to_string()));
        }
        #[cfg(not(target_os = "android"))]
        Ok(PermissionStatus::new())
    }

    /// Pide lo que falte. Idempotente: si ya está todo, no sale ningún diálogo.
    pub fn request_permissions(&self) -> Result<PermissionStatus, Error> {
        #[cfg(target_os = "android")]
        {
            return self
                .0
                .run_mobile_plugin("requestPermissions", Empty {})
                .map_err(|e| Error::PluginInvoke(e.to_string()));
        }
        #[cfg(not(target_os = "android"))]
        Ok(PermissionStatus::new())
    }
}

pub trait ErploraAndroidExt<R: Runtime> {
    fn erplora_android(&self) -> &ErploraAndroid<R>;
}

impl<R: Runtime, T: Manager<R>> ErploraAndroidExt<R> for T {
    fn erplora_android(&self) -> &ErploraAndroid<R> {
        self.state::<ErploraAndroid<R>>().inner()
    }
}

#[tauri::command]
async fn check_permissions<R: Runtime>(app: tauri::AppHandle<R>) -> Result<PermissionStatus, Error> {
    app.erplora_android().check_permissions()
}

#[tauri::command]
async fn request_permissions<R: Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<PermissionStatus, Error> {
    app.erplora_android().request_permissions()
}

pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("erplora-android")
        .invoke_handler(tauri::generate_handler![check_permissions, request_permissions])
        .setup(|app, _api| {
            #[cfg(target_os = "android")]
            let handle = _api.register_android_plugin(PLUGIN_IDENTIFIER, "ErploraAndroidPlugin")?;
            #[cfg(target_os = "android")]
            app.manage(ErploraAndroid(handle));

            #[cfg(not(target_os = "android"))]
            app.manage(ErploraAndroid::<R>(std::marker::PhantomData));

            Ok(())
        })
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_estado_serializa_como_un_mapa_permiso_a_booleano() {
        // Es el contrato que consume la PWA: `{ "android.permission.X": true }`.
        let mut estado = PermissionStatus::new();
        estado.insert("android.permission.POST_NOTIFICATIONS".into(), true);
        let json = serde_json::to_string(&estado).unwrap();
        assert!(json.contains("\"android.permission.POST_NOTIFICATIONS\":true"));
    }

    /// The Kotlin policy is the only place that can actually ASK for these permissions, and the
    /// map it returns is keyed by the raw string. If the two sides ever spelled one differently,
    /// Rust would read `None` for a permission Android had denied and the till would go back to
    /// reporting zero printers with a straight face (hub#338).
    const PERMISSION_POLICY_KT: &str =
        include_str!("../android/src/main/java/com/erplora/android/PermissionPolicy.kt");

    #[test]
    fn rust_and_kotlin_spell_the_permissions_the_same_way() {
        for permission in [ACCESS_LOCAL_NETWORK, POST_NOTIFICATIONS] {
            assert!(
                PERMISSION_POLICY_KT.contains(permission),
                "{permission} is not in PermissionPolicy.kt — the status map would never mention it"
            );
        }
    }

    #[test]
    fn el_error_llega_al_frontend_como_texto_plano() {
        // Mismo patrón que el resto del shell: la promesa se rechaza con un mensaje legible.
        let e = Error::PluginInvoke("sin actividad".into());
        assert_eq!(serde_json::to_string(&e).unwrap(), "\"sin actividad\"");
    }
}
