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

    /// **Capacidad de host `certificate` (ADR-0079).** Identidad TLS-cliente (mTLS) del certificado
    /// del negocio (`_hub_certificate`) para que el módulo transmita a Hacienda **sin ver el `.p12`**:
    /// la clave nunca cruza al módulo, el core hace toda la cripto. El gate de la capability lo aplica
    /// el dispatcher. Default: no disponible (host sin certificado).
    async fn certificate_identity(&self, _hub_id: &str) -> Result<reqwest::Identity> {
        Err(RuntimeError::Certificate(
            "la capability `certificate` no está disponible en este host".to_string(),
        ))
    }

    /// Caducidad (notAfter, ISO `YYYY-MM-DD`) del certificado del negocio. `Ok(None)` si no hay.
    async fn certificate_expiry(&self, _hub_id: &str) -> Result<Option<String>> {
        Ok(None)
    }

    /// Igual que [`certificate_identity`](Self::certificate_identity) pero sobre un `.p12` **provisto
    /// en memoria** (DER + contraseña) — validar/usar un certificado recién subido. La cripto PKCS#12
    /// (OpenSSL) vive SOLO en el core; el módulo no la implementa. Default = la cripto del core.
    async fn certificate_identity_from(
        &self,
        pkcs12_der: &[u8],
        password: &str,
    ) -> Result<reqwest::Identity> {
        crate::certificate::identity_from_der(pkcs12_der, password)
    }

    /// Caducidad de un `.p12` provisto en memoria (DER + contraseña). Cripto en el core.
    async fn certificate_expiry_from(
        &self,
        pkcs12_der: &[u8],
        password: &str,
    ) -> Result<Option<String>> {
        crate::certificate::expiry_from_der(pkcs12_der, password)
    }

    /// Escribe dentro de la carpeta `static_files` declarada por el módulo. La implementación real
    /// conoce el módulo que está ejecutándose y media el backend Local/Cloud; el plugin solo aporta
    /// una ruta relativa segura.
    async fn write_static_file(
        &self,
        _relative_path: &str,
        _bytes: &[u8],
        _content_type: &str,
    ) -> Result<String> {
        Err(RuntimeError::Storage(
            "la capacidad `static_files` no está disponible en este host".to_string(),
        ))
    }
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
    pub storage: Option<&'a dyn crate::module_storage::ModuleStorage>,
    pub hub_id: &'a str,
    pub module_id: &'a str,
    pub static_folder: Option<&'a str>,
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

    async fn certificate_identity(&self, hub_id: &str) -> Result<reqwest::Identity> {
        crate::certificate::identity(self.db, hub_id).await
    }

    async fn certificate_expiry(&self, hub_id: &str) -> Result<Option<String>> {
        crate::certificate::expiry(self.db, hub_id).await
    }

    async fn write_static_file(
        &self,
        relative_path: &str,
        bytes: &[u8],
        content_type: &str,
    ) -> Result<String> {
        if !crate::module_storage::valid_relative_file_path(relative_path) {
            return Err(RuntimeError::Storage(format!(
                "ruta de fichero inválida para `{}`",
                self.module_id
            )));
        }
        let folder = self.static_folder.ok_or_else(|| {
            RuntimeError::Storage(format!(
                "el módulo `{}` no declara `static_files.folder`",
                self.module_id
            ))
        })?;
        let storage = self.storage.ok_or_else(|| {
            RuntimeError::Storage("el host no configuró un backend de módulos".to_string())
        })?;
        storage
            .write_module_file(self.hub_id, folder, relative_path, bytes, content_type)
            .await
    }
}
