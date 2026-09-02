//! Host de handlers WASM (Tier 2). ARQUITECTURA.md §5.3, §7.3.
//!
//! STUB: la ejecución WASM (vía Extism) se implementará en `erplora-wasm-host`. Hasta
//! entonces, un command sin SQL (que requeriría handler WASM) devuelve `NotImplemented`.
#![allow(dead_code)]
use crate::errors::Result;

/// Marcador: ejecutar un handler WASM aún no está soportado.
pub fn execute_handler(_function: &str) -> Result<()> {
    Err(crate::errors::RuntimeError::NotImplemented(
        "handler WASM (Extism) — Tier 2",
    ))
}
