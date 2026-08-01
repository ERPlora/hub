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
    /// El command existe y su módulo está activo, pero está marcado INTERNO (prefijo `_` en su
    /// último segmento, o `internal: true` en el manifest) y la invocación viene de un origen
    /// EXTERNO (HTTP, API pública, asistente) — hub#131, hub#145. Solo el propio runtime (relay
    /// del Outbox, scheduler) puede invocarlo. Distinto de `CommandNotFound`: aquí el nombre SÍ
    /// resuelve, pero el caller no tiene permitido usarlo por esta puerta.
    #[error("command interno: `{0}` no es invocable desde fuera del runtime")]
    InternalCommand(String),
    /// Un command declarativo declaró [`min_affected_rows`](crate::manifest::CommandDef) y la
    /// sentencia de mutación afectó **menos** filas de las exigidas (hub#140). Es el error
    /// **estable** que sustituye al "OK silencioso" de un `UPDATE … WHERE` que no casa: la
    /// transacción se revierte entera y NO se escribe ningún evento en el outbox (ni notificación
    /// al WS), porque el hecho declarado nunca ocurrió.
    ///
    /// `kind` distingue los dos casos que pide el issue: [`AffectedKind::NotFound`] (0 filas — el
    /// recurso no existe / la transición no aplica → `not_found`) y [`AffectedKind::TooFew`] (>0
    /// pero por debajo del mínimo exigido, p. ej. un batch que esperaba N y mutó menos →
    /// `conflict`). El campo `affected` lleva el conteo real para diagnóstico.
    #[error("el command `{command}` exigía {required} fila(s) afectada(s) pero mutó {affected} ({kind})")]
    MinAffectedRows {
        command: String,
        required: u64,
        affected: u64,
        kind: AffectedKind,
    },
    /// Rechazo de negocio estable emitido por un handler o por `expect_rows` (hub#139).
    /// El `code` es namespaced y la UI programa/traduce contra él; `message` es fallback humano.
    #[error("{message}")]
    Domain { code: String, message: String },
    /// Una read marcada `required:true` no pudo materializarse. La causa interna se registra en el
    /// host, pero el caller solo ve query/command: nunca SQL, parámetros ni filas sensibles.
    #[error("la lectura requerida `{query}` no está disponible para `{command}`")]
    RequiredReadFailed { command: String, query: String },
    /// Las filas pre-cargadas superan el presupuesto del sandbox.
    #[error("la lectura `{query}` de `{command}` supera el límite de {max_bytes} bytes")]
    ReadTooLarge {
        command: String,
        query: String,
        max_bytes: usize,
    },
    /// El canal `result` de un handler supera su límite independiente de operaciones/eventos.
    #[error("el resultado del handler de `{command}` supera el límite de {max_bytes} bytes")]
    HandlerResultTooLarge { command: String, max_bytes: usize },
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
    /// Un handler (WASM/nativo) devolvió un evento que su `module.json` NO declara (hub#240).
    /// El evento **no se encola**: el command falla entero, porque un nombre de evento es un
    /// contrato cross-módulo (y `*.reminder.due` llega a `host.notify`), no un dato del handler.
    #[error("el módulo `{module}` no declara el evento `{event}` (decláralo en `events.emits` de su module.json)")]
    EventNotDeclared { module: String, event: String },
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

/// Por qué no se cumplió [`RuntimeError::MinAffectedRows`] (hub#140). Determina el error estable
/// que ve el caller (`not_found` vs `conflict`) para que el SDK pueda reaccionar — no es un detalle
/// de diagnóstico, es parte del contrato de la gate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AffectedKind {
    /// 0 filas afectadas: el recurso no existe, o la transición ya no aplica (p. ej. confirmar una
    /// cita ya confirmada). Corresponde al error `not_found` del issue.
    NotFound,
    /// >0 filas pero por debajo del mínimo exigido (p. ej. un batch que esperaba N y mutó menos).
    /// Corresponde a `conflict` / `invalid_transition`.
    TooFew,
}

impl std::fmt::Display for AffectedKind {
    // thiserror `{kind}` exige `Display`; delega en el nombre estable para que el mensaje humano y
    // el `code` de máquina coincidan siempre (una sola fuente de verdad: `as_str`).
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

impl AffectedKind {
    /// Nombre estable del error, listo para el `code` del envelope de error del SDK (`§7.6`):
    /// `not_found` / `conflict`. El caller programa contra esto, no contra el mensaje libre.
    pub fn as_str(self) -> &'static str {
        match self {
            AffectedKind::NotFound => "not_found",
            AffectedKind::TooFew => "conflict",
        }
    }
}

/// Clasifica el fallo de la gate de `min_affected_rows` (hub#140) a partir del conteo real. Es la
/// única autoridad para mapear `affected` → [`AffectedKind`], así que vive junto al enum y todo
/// gate la usa (no se duplica la regla en cada call site).
///
/// - `0` filas → [`AffectedKind::NotFound`] (el recurso no existe / la transición no aplica).
/// - `>0` pero `< min` → [`AffectedKind::TooFew`] (mutó algo, pero no lo exigido — batch parcial).
pub fn affected_kind(affected: u64, min: u64) -> AffectedKind {
    if affected == 0 {
        AffectedKind::NotFound
    } else {
        // El caller ya garantiza `affected < min` (la gate falló); aquí solo se decide la forma.
        let _ = min;
        AffectedKind::TooFew
    }
}

/// Valida el ABI público de códigos de dominio: exactamente
/// `<module>.<snake_case>`, sin espacios, puntos extra ni namespace ajeno.
pub fn valid_domain_code(module: &str, code: &str) -> bool {
    let Some((namespace, name)) = code.split_once('.') else {
        return false;
    };
    code.len() <= 128
        && namespace == module
        && !name.contains('.')
        && valid_snake_segment(namespace)
        && valid_snake_segment(name)
}

fn valid_snake_segment(value: &str) -> bool {
    let mut chars = value.chars();
    matches!(chars.next(), Some('a'..='z'))
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

#[cfg(test)]
mod domain_code_tests {
    use super::valid_domain_code;

    #[test]
    fn accepts_only_owned_namespaced_snake_case_codes() {
        assert!(valid_domain_code(
            "inventory",
            "inventory.insufficient_stock"
        ));
        assert!(!valid_domain_code("inventory", "sales.insufficient_stock"));
        assert!(!valid_domain_code(
            "inventory",
            "inventory.InsufficientStock"
        ));
        assert!(!valid_domain_code("inventory", "inventory.stock.low"));
        assert!(!valid_domain_code("inventory", "inventory."));
        assert!(!valid_domain_code(
            "inventory",
            &format!("inventory.{}", "x".repeat(128))
        ));
    }
}
