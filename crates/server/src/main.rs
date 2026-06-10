//! Binario del server: arranque del runtime del tenant (modo cloud / web). Toda la lógica de
//! arranque vive en [`erplora_server::serve`] (compartida con el shell Tauri in-process, §11);
//! aquí solo se lee la config del entorno. Sirve en `HUB_BIND` (def 127.0.0.1:8787).
//! ARQUITECTURA.md §7.5, §8, §11.
use erplora_server::{serve, ServeConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    serve(ServeConfig::from_env()).await
}
