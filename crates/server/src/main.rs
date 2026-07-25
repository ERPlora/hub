//! Binario del server: arranque del runtime del tenant (Hub Cloud, Postgres-only — ADR-0154). Toda
//! la lógica de arranque vive en [`erplora_server::serve`]; aquí solo se lee la config del entorno.
//! Sirve en `HUB_BIND` (def 127.0.0.1:8787). ARQUITECTURA.md §7.5, §8.
//!
//! Subcomando de ops `--backfill-money` (ADR-0007): convierte el dinero euros→céntimos en un hub
//! ya desplegado y sale, **sin** arrancar el server. Idempotente (marcador `_hub_meta`), seguro
//! de re-ejecutar. Ver `erplora_runtime::money_backfill`.
use erplora_server::{normalize_pg_dsn, serve, ServeConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parseo mínimo de subcomandos (sin clap): el server normal no toma args.
    if std::env::args().any(|a| a == "--backfill-money") {
        return backfill_money().await;
    }
    serve(ServeConfig::from_env()).await
}

/// Conecta al Postgres del hub (`HUB_DATABASE_URL`, igual que `serve`) y corre el backfill de dinero.
async fn backfill_money() -> Result<(), Box<dyn std::error::Error>> {
    use erplora_runtime::money_backfill;

    let dsn = normalize_pg_dsn(std::env::var("HUB_DATABASE_URL").unwrap_or_default().trim());
    if dsn.is_empty() {
        return Err("HUB_DATABASE_URL es obligatoria para --backfill-money (ADR-0154)".into());
    }
    eprintln!("[backfill-money] conectando al Postgres del hub …");
    let db = erplora_db::PgAdapter::connect(&dsn).await?;
    money_backfill::run_logged(&db).await?;
    Ok(())
}
