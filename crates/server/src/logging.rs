//! Logging del Hub → consola + carpeta `media/_logs/` (ADR-0047).
//!
//! La carpeta `media/` es el path por defecto de TODOS los ficheros del hub; los **logs de sistema
//! son la primera población real** de esa carpeta (pantalla `/files`). Aquí se monta el subscriber
//! global de `tracing` con dos capas: **consola** (stderr, para dev/ECS) y **fichero rotado diario**
//! en `media/_logs/hub.YYYY-MM-DD`. Hay **retención de ~6 meses** con limpieza automática (al
//! arrancar + una vez al día): no tiene sentido guardar logs más viejos.
//!
//! Antes de esto el hub NO tenía subscriber → los `tracing::*` eran no-ops. Los `eprintln!` de
//! arranque conviven sin cambios (no pasan por `tracing`).

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use tracing_appender::non_blocking::WorkerGuard;

/// Retención de logs: ~6 meses. Más viejos se borran (decisión del humano, 2026-06-14).
const LOG_RETENTION_DAYS: u64 = 180;
/// Sub-carpeta de logs dentro de `media/`.
const LOG_SUBDIR: &str = "_logs";
/// Prefijo del fichero rotado (`hub.YYYY-MM-DD`).
const LOG_PREFIX: &str = "hub";

/// Inicializa el subscriber global (consola + fichero en `media/_logs/`) y arranca la limpieza por
/// retención. Devuelve el `WorkerGuard` del appender no-bloqueante: **debe mantenerse vivo mientras
/// corre el proceso** (al soltarlo se pierden los logs en cola). Idempotente: si ya hay un
/// subscriber (p. ej. el shell Tauri lo montó), no falla; devuelve `None`.
///
/// Debe llamarse dentro de un runtime de Tokio (lanza una tarea de limpieza diaria).
#[must_use]
pub fn init(media_dir: &Path) -> Option<WorkerGuard> {
    use tracing_subscriber::layer::SubscriberExt;
    use tracing_subscriber::util::SubscriberInitExt;
    use tracing_subscriber::{fmt, EnvFilter, Layer};

    let log_dir = media_dir.join(LOG_SUBDIR);
    if let Err(e) = std::fs::create_dir_all(&log_dir) {
        eprintln!("logging: no se pudo crear {}: {e}", log_dir.display());
        return None;
    }

    // Nivel por `RUST_LOG` (default "info"). Un filtro por capa (no se puede clonar `EnvFilter`).
    let mk_filter = || EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    // Fichero rotado diario → media/_logs/hub.YYYY-MM-DD (sin ANSI en disco).
    let file_appender = tracing_appender::rolling::daily(&log_dir, LOG_PREFIX);
    let (file_writer, guard) = tracing_appender::non_blocking(file_appender);

    let console_layer = fmt::layer().with_writer(std::io::stderr).with_filter(mk_filter());
    let file_layer = fmt::layer()
        .with_ansi(false)
        .with_writer(file_writer)
        .with_filter(mk_filter());

    let initialized = tracing_subscriber::registry()
        .with(console_layer)
        .with(file_layer)
        .try_init()
        .is_ok();

    if initialized {
        eprintln!("logging: logs → consola + {}", log_dir.display());
    } else {
        eprintln!("logging: ya había un subscriber activo; no se re-inicializa");
    }

    // Limpieza inmediata + tarea diaria de retención.
    prune_old_logs(&log_dir);
    spawn_pruner(log_dir);

    Some(guard)
}

/// Borra los ficheros de log con fecha de modificación anterior a la retención.
fn prune_old_logs(dir: &Path) {
    let Some(cutoff) = SystemTime::now().checked_sub(Duration::from_secs(LOG_RETENTION_DAYS * 86_400))
    else {
        return;
    };
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    let mut removed = 0u32;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let too_old = entry
            .metadata()
            .ok()
            .and_then(|m| m.modified().ok())
            .is_some_and(|m| m < cutoff);
        if too_old && std::fs::remove_file(&path).is_ok() {
            removed += 1;
        }
    }
    if removed > 0 {
        eprintln!("logging: limpiados {removed} fichero(s) de log > {LOG_RETENTION_DAYS} días");
    }
}

/// Tarea de fondo: aplica la retención una vez al día (la limpieza inicial ya corrió en `init`).
fn spawn_pruner(dir: PathBuf) {
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(24 * 3600)).await;
            let d = dir.clone();
            let _ = tokio::task::spawn_blocking(move || prune_old_logs(&d)).await;
        }
    });
}
