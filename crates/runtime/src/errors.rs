//! Errores del runtime.
use erplora_db::DbError;

#[derive(Debug, thiserror::Error)]
pub enum RuntimeError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("manifest inválido ({path}): {source}")]
    Manifest { path: String, source: serde_json::Error },
    #[error("db: {0}")]
    Db(#[from] DbError),
    #[error("query no encontrada: {0}")]
    QueryNotFound(String),
    #[error("command no encontrado: {0}")]
    CommandNotFound(String),
    #[error("permiso denegado: requiere `{0}`")]
    PermissionDenied(String),
    #[error("dependencia no satisfecha: el módulo `{module}` requiere `{dep}`")]
    MissingDependency { module: String, dep: String },
    #[error("ciclo de dependencias entre módulos en `{module}` (depends_on cíclico)")]
    DependencyCycle { module: String },
    #[error("ciclo de eventos demasiado profundo (posible bucle de listeners)")]
    EventLoop,
    #[error("característica no implementada: {0}")]
    NotImplemented(&'static str),
    #[error("error de handler WASM: {0}")]
    Wasm(String),
    #[error("error de plugin nativo: {0}")]
    Native(String),
    /// El payload del llamador no cumple el JSON Schema declarado por la query/command.
    /// Se rechaza ANTES de tocar la BD (Rust = única autoridad de payload, §8).
    #[error("payload inválido para `{name}`: {detail}")]
    InvalidPayload { name: String, detail: String },
    /// El JSON Schema declarado por una query/command no compila (se detecta al instalar).
    #[error("schema inválido en `{name}`: {detail}")]
    Schema { name: String, detail: String },
    /// Fallo del motor de sync local↔cloud (ADR-0031).
    #[error("sync: {0}")]
    Sync(String),
}

pub type Result<T> = std::result::Result<T, RuntimeError>;
