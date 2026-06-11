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
    #[error("ciclo de eventos demasiado profundo (posible bucle de listeners)")]
    EventLoop,
    #[error("característica no implementada: {0}")]
    NotImplemented(&'static str),
    #[error("error de handler WASM: {0}")]
    Wasm(String),
    #[error("error de plugin nativo: {0}")]
    Native(String),
}

pub type Result<T> = std::result::Result<T, RuntimeError>;
