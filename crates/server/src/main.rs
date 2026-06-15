//! Binario del server: arranque del runtime del tenant (modo cloud / web). Toda la lógica de
//! arranque vive en [`erplora_server::serve`] (compartida con el shell Tauri in-process, §11);
//! aquí solo se lee la config del entorno. Sirve en `HUB_BIND` (def 127.0.0.1:8787).
//! ARQUITECTURA.md §7.5, §8, §11.
//!
//! Subcomando de ops `--backfill-money` (ADR-0007): convierte el dinero euros→céntimos en un hub
//! ya desplegado y sale, **sin** arrancar el server. Idempotente (marcador `_hub_meta`), seguro
//! de re-ejecutar. Ver `erplora_runtime::money_backfill`.
use erplora_server::{serve, ServeConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parseo mínimo de subcomandos (sin clap): el server normal no toma args.
    if std::env::args().any(|a| a == "--backfill-money") {
        return backfill_money().await;
    }
    serve(ServeConfig::from_env()).await
}

/// Abre el SQLite del hub (`HUB_SQLITE_PATH`, igual que `serve`) y corre el backfill de dinero.
async fn backfill_money() -> Result<(), Box<dyn std::error::Error>> {
    use erplora_db::SqliteAdapter;
    use erplora_runtime::money_backfill;

    let sqlite_path = std::env::var("HUB_SQLITE_PATH").unwrap_or_else(|_| "erplora.db".into());
    // `mode=rw`: NO crear la BD si no existe — el backfill solo aplica a un hub real ya desplegado.
    let sqlite_url = format!("sqlite://{sqlite_path}?mode=rw");
    eprintln!("[backfill-money] abriendo {sqlite_path} …");
    let db = SqliteAdapter::connect(&sqlite_url).await?;
    money_backfill::run_logged(&db).await?;
    Ok(())
}
