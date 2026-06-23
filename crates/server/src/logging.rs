//! Logging del Hub → **consola (stderr) únicamente**.
//!
//! Decisión del humano (2026-06-23): el Hub **no escribe logs a fichero**. En AWS (hub cloud) los
//! captura **CloudWatch** desde stdout/stderr del contenedor; en local/Tauri basta la consola. Esto
//! elimina la dependencia de un directorio `media/` escribible al arrancar — antes el file-appender
//! (ADR-0047, `media/_logs/hub.YYYY-MM-DD`) fallaba en el contenedor cloud con
//! `media/_logs: Permission denied` y dejaba al runtime sin un dir local válido.
//!
//! Reemplaza el logging a `media/_logs/` de ADR-0047 (la "primera población" de la pantalla `/files`
//! deja de existir; si se quiere ver logs en el Hub UI será un follow-up que lea CloudWatch/stdout).
//! Los `eprintln!` de arranque conviven sin cambios (no pasan por `tracing`).

use std::path::Path;

use tracing_appender::non_blocking::WorkerGuard;

/// Inicializa el subscriber global de `tracing` con una **única capa de consola** (stderr).
/// Idempotente: si ya hay un subscriber (p. ej. el shell Tauri lo montó), no falla.
///
/// Devuelve `Option<WorkerGuard>` por compatibilidad de firma con los llamadores, pero **siempre
/// `None`**: ya no hay appender no-bloqueante a fichero, así que no hay guard que mantener vivo.
/// El parámetro `_media_dir` se conserva por compat y ya no se usa.
#[must_use]
pub fn init(_media_dir: &Path) -> Option<WorkerGuard> {
    use tracing_subscriber::layer::SubscriberExt;
    use tracing_subscriber::util::SubscriberInitExt;
    use tracing_subscriber::{fmt, EnvFilter, Layer};

    // Nivel por `RUST_LOG` (default "info").
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let console_layer = fmt::layer().with_writer(std::io::stderr).with_filter(filter);

    let initialized = tracing_subscriber::registry().with(console_layer).try_init().is_ok();
    if initialized {
        eprintln!("logging: logs → consola (stderr); en AWS los recoge CloudWatch");
    } else {
        eprintln!("logging: ya había un subscriber activo; no se re-inicializa");
    }

    None
}
