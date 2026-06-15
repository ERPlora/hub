//! Plugins **nativos first-party** (ADR-0009). Segunda clase de handler junto al WASM
//! Tier 2: un crate Rust horneado en el binario del runtime (no descargable, no para
//! terceros) para módulos compliance-crítico (`verifactu`, `payroll`).
//!
//! Contrato (idéntico en espíritu al WASM, ARQUITECTURA.md §5.3): el plugin **nunca
//! escribe en la BD**. Recibe `{payload, context}` + un [`NativeHost`] para **lecturas
//! mediadas** (solo `SELECT`; el runtime ejecuta la lectura, el plugin no abre conexión
//! propia), calcula y devuelve un [`Output`] con *intenciones* (operaciones `sql` que
//! referencian commands del **mismo módulo** + eventos) que el runtime valida y persiste
//! en UNA transacción (`commands.rs::execute_native`).
//!
//! A diferencia del WASM, un plugin nativo sí puede usar red/cripto plenas (TLS mutua,
//! PKCS#12) — esa es justamente la razón de su existencia (ADR-0009).
use erplora_db::{DatabaseAdapter, Params};
use erplora_wasm_host::Output;
use serde_json::Value as Json;

use crate::errors::{Result, RuntimeError};

/// Lecturas mediadas por el runtime para un plugin nativo. Solo sentencias `SELECT`
/// (las escrituras van SIEMPRE como intenciones en el [`Output`], nunca directas).
#[async_trait::async_trait]
pub trait NativeHost: Send + Sync {
    /// Ejecuta un `SELECT` con parámetros nombrados (`:name`) y devuelve las filas JSON.
    async fn read(&self, sql: &str, params: &Params) -> Result<Vec<Json>>;
}

/// Un plugin nativo first-party: el motor de un módulo, horneado en el runtime y
/// registrado por `module_id` ([`crate::Runtime::register_native`]). `function` es el
/// nombre declarado en `module.json` (`handler.function`); una función desconocida debe
/// devolver [`RuntimeError::Native`].
#[async_trait::async_trait]
pub trait NativeHandler: Send + Sync + std::fmt::Debug {
    async fn call(&self, function: &str, input: &Json, host: &dyn NativeHost) -> Result<Output>;
}

/// [`NativeHost`] real sobre el adaptador de BD del runtime.
pub(crate) struct DbHost<'a> {
    pub db: &'a dyn DatabaseAdapter,
}

#[async_trait::async_trait]
impl NativeHost for DbHost<'_> {
    async fn read(&self, sql: &str, params: &Params) -> Result<Vec<Json>> {
        if !sql.trim_start().to_ascii_uppercase().starts_with("SELECT") {
            return Err(RuntimeError::Native(
                "lectura nativa rechazada: solo se permite SELECT".to_string(),
            ));
        }
        Ok(self.db.query(sql, params).await?.rows)
    }
}
