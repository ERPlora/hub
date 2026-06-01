//! Binario del server: abre SQLite (path por `HUB_SQLITE_PATH`), instala los módulos del
//! directorio `HUB_MODULES_DIR` y sirve en `HUB_BIND` (por defecto 127.0.0.1:8787).
//! ARQUITECTURA.md §7.5, §8.
use std::path::PathBuf;

use erplora_db::SqliteAdapter;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let sqlite_path = std::env::var("HUB_SQLITE_PATH").unwrap_or_else(|_| "erplora.db".into());
    let bind = std::env::var("HUB_BIND").unwrap_or_else(|_| "127.0.0.1:8787".into());

    let db = SqliteAdapter::open(&sqlite_path)?;
    let mut runtime = Runtime::new(Box::new(db));

    if let Ok(dir) = std::env::var("HUB_MODULES_DIR") {
        for entry in std::fs::read_dir(&dir)? {
            let path: PathBuf = entry?.path();
            if path.join("module.json").exists() {
                match runtime.install_from_dir(&path) {
                    Ok(id) => eprintln!("✓ módulo instalado: {id}"),
                    Err(e) => eprintln!("✗ módulo {}: {e}", path.display()),
                }
            }
        }
    }

    let state = AppState::new(runtime);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    eprintln!("erplora-server escuchando en http://{bind}");
    axum::serve(listener, app(state)).await?;
    Ok(())
}
