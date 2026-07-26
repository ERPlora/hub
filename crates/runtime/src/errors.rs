//! Errores del runtime.
use erplora_db::DbError;

#[derive(Debug, thiserror::Error)]
pub enum RuntimeError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("manifest inválido ({path}): {source}")]
    Manifest {
        path: String,
        source: serde_json::Error,
    },
    #[error("db: {0}")]
    Db(#[from] DbError),
    #[error("query no encontrada: {0}")]
    QueryNotFound(String),
    /// El MÓDULO dueño de la operación no está instalado en este hub. Distinto de
    /// `QueryNotFound` (módulo presente, query inexistente = contrato roto): esta distinción es
    /// la que permite a `queryOptional` del SDK devolver `undefined` SOLO ante la ausencia del
    /// módulo, sin tragarse contratos rotos (ADR-0127).
    #[error("módulo no instalado: `{module}` (requerido por `{operation}`)")]
    ModuleNotInstalled { module: String, operation: String },
    /// El módulo está instalado pero DESACTIVADO (manual o en cascada, ADR-0128). Para
    /// `queryOptional` equivale a ausencia; un consumidor obligatorio nunca pregunta, porque la
    /// cascada lo apagó junto a su dependencia.
    #[error("módulo desactivado: `{module}` (requerido por `{operation}`)")]
    ModuleInactive { module: String, operation: String },
    #[error("command no encontrado: {0}")]
    CommandNotFound(String),
    #[error("permiso denegado: requiere `{0}`")]
    PermissionDenied(String),
    /// El módulo necesita una **capability** (ADR-0079: red/certificado/impresora/notify) que el
    /// usuario NO ha concedido (default-deny). Distinto de `PermissionDenied` (RBAC de usuario):
    /// esto es el permiso módulo→host, gestionado en Settings → Permisos.
    #[error("permiso del módulo `{module}` denegado: requiere la capability `{capability}` (concédela en Ajustes → Permisos)")]
    CapabilityDenied { module: String, capability: String },
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
    /// Fallo de la capacidad de host `host.notify` (ADR-0012): el transporte de un canal
    /// (email/sms/whatsapp) no pudo entregar. El relay del outbox lo trata como un listener
    /// fallido → reintento con backoff y, tras `MAX_ATTEMPTS`, dead-letter.
    #[error("host.notify: {0}")]
    Notify(String),
    /// Fallo al materializar o escribir la carpeta persistente declarada por un módulo.
    #[error("host.module_storage: {0}")]
    Storage(String),
    /// Fallo de la capacidad de host `host.certificate` (ADR-0079): el primitivo de firma/identidad
    /// con el certificado del negocio (`_hub_certificate`, parse PKCS#12 + identidad mTLS) no pudo
    /// completar — certificado ausente, contraseña incorrecta, PKCS#12 inválido. La clave nunca sale
    /// del core: el módulo (verifactu, B2B…) solo PIDE la operación, no ve el `.p12`.
    #[error("host.certificate: {0}")]
    Certificate(String),
    /// Error genérico que no encaja en una variante específica (p. ej. fallo del hasher argon2id
    /// al fijar un PIN, hub#15). Mensaje libre.
    #[error("{0}")]
    Other(String),
}

pub type Result<T> = std::result::Result<T, RuntimeError>;
