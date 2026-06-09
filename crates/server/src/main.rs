//! Binario del server: abre SQLite (path por `HUB_SQLITE_PATH`), instala los módulos del
//! directorio `HUB_MODULES_DIR` y sirve en `HUB_BIND` (por defecto 127.0.0.1:8787).
//! ARQUITECTURA.md §7.5, §8.
use std::path::PathBuf;

use erplora_db::SqliteAdapter;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};

/// Trae la clave pública RSA del Cloud (`GET /api/v1/auth/public-key/` → `{public_key, algorithm}`)
/// para verificar los JWT de usuario offline. `None` si el Cloud no responde o no la trae.
async fn fetch_jwt_public_key(cloud_base_url: &str) -> Option<String> {
    let url = format!("{}/api/v1/auth/public-key/", cloud_base_url.trim_end_matches('/'));
    let resp = reqwest::Client::new().get(&url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: serde_json::Value = resp.json().await.ok()?;
    v.get("public_key").and_then(|k| k.as_str()).filter(|s| !s.is_empty()).map(|s| s.to_string())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let sqlite_path = std::env::var("HUB_SQLITE_PATH").unwrap_or_else(|_| "erplora.db".into());
    let bind = std::env::var("HUB_BIND").unwrap_or_else(|_| "127.0.0.1:8787".into());

    // sqlx-style URL: `sqlite://<path>?mode=rwc` creates the file if missing.
    let db = SqliteAdapter::connect(&format!("sqlite://{sqlite_path}?mode=rwc")).await?;
    let mut runtime = Runtime::new(Box::new(db));

    if let Ok(dir) = std::env::var("HUB_MODULES_DIR") {
        for entry in std::fs::read_dir(&dir)? {
            let path: PathBuf = entry?.path();
            if path.join("module.json").exists() {
                match runtime.install_from_dir(&path).await {
                    Ok(id) => eprintln!("✓ módulo instalado: {id}"),
                    Err(e) => eprintln!("✗ módulo {}: {e}", path.display()),
                }
            }
        }
    }

    // Configuración de despliegue + resolución de auth. En modo `HUB_AUTH=session` el login local
    // por PIN no necesita Cloud; la clave pública RSA solo hace falta para el **login cloud**
    // (`/api/auth/cloud`). Se intenta obtener (env `HUB_JWT_PUBLIC_KEY` o `/api/v1/auth/public-key/`)
    // y, si no se logra, se sigue arrancando: el login cloud quedará no disponible (PIN sí funciona).
    let mut config = HubConfig::from_env();
    if config.auth_mode == AuthMode::Session && config.jwt_public_key.is_none() {
        config.jwt_public_key = fetch_jwt_public_key(&config.cloud_base_url).await;
        if config.jwt_public_key.is_none() {
            eprintln!("auth: sin clave pública del Cloud → login cloud no disponible (PIN sí)");
        }
    }
    eprintln!("auth: modo {:?}", config.auth_mode);
    let state = AppState::with_config(runtime, config);

    // Tablas de sistema del runtime (outbox de eventos) — para el caso de hub vacío sin módulos.
    state.runtime.lock().await.ensure_system_tables().await?;

    // Relay de eventos: entrega at-least-once asíncrona de los eventos del outbox a sus listeners
    // (ARQUITECTURA.md §5.4). Poll cada 1s; las filas con fallo se reprograman con backoff. Para
    // 1–30 usuarios por hub, tomar el lock del runtime por ciclo es suficiente (§7.5).
    {
        let runtime = state.runtime.clone();
        tokio::spawn(async move {
            loop {
                {
                    let rt = runtime.lock().await;
                    if let Err(e) = rt.process_outbox().await {
                        eprintln!("relay outbox: {e}");
                    }
                }
                tokio::time::sleep(std::time::Duration::from_millis(1000)).await;
            }
        });
    }

    let listener = tokio::net::TcpListener::bind(&bind).await?;
    eprintln!("erplora-server escuchando en http://{bind}");
    axum::serve(listener, app(state)).await?;
    Ok(())
}
