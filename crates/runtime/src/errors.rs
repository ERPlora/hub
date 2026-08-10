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
    /// The manifest declares a field this core does not understand, in a place where not
    /// understanding it changes what RUNS (hub#521): inside a command, a query, the migrations,
    /// the events or the capabilities.
    ///
    /// Until now serde dropped it without a word, which is the worst of the three possible
    /// outcomes: the module installs, looks complete, and is missing the guard, the reaction or
    /// the permission its author declared. `inventory` and `services` have shipped a `validates`
    /// block for months believing a tax category was checked (hub#610) — it never was.
    ///
    /// Refusing is not the same as being strict everywhere: a field whose loss costs a screen or a
    /// button is reported instead (`Manifest::warnings`), because bricking a till over a tab that
    /// does not render would be a worse trade. See `manifest::refuses_unknown_fields`.
    #[error("the module `{module}` declares `{path}`, which this hub's core (v{core}) does not understand — ignoring it would change what runs, so the module was NOT installed")]
    ManifestUnknownField {
        module: String,
        path: String,
        core: String,
    },
    /// The module declares (`compatibility.min_erplora_version`) that it needs a newer core than
    /// this hub runs (hub#521).
    ///
    /// The field existed on both sides of the wire and was read by neither: the SaaS stores it and
    /// republishes it as `min_core_version`, and the hub never looked. So a module built for a
    /// newer core installed anyway and quietly lacked whatever the new core would have given it.
    /// Saying no is the point — the user can act on "update your terminal"; they cannot act on a
    /// module that is subtly missing pieces.
    #[error("the module `{module}` needs a newer version of your terminal: it requires ERPlora {required} and this hub runs {core} — update the hub and install it again")]
    CoreVersionTooOld {
        module: String,
        required: String,
        core: String,
    },
    /// The declared core floor is not a version this hub can compare against (hub#521). Refused
    /// rather than ignored, the same direction as [`crate::manifest::Manifest::sold_under`]: a
    /// compatibility claim the runtime cannot check must not be read as "compatible".
    #[error("the module `{module}` declares `compatibility.min_erplora_version: {declared}`, which is not a version this hub can compare against")]
    ManifestCoreFloorUnreadable { module: String, declared: String },
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
    /// Stable business rejection (hub#139), coming either from a handler's `Output.error` or
    /// from the declarative `expect_rows` gate. `code` is namespaced (`<module>.<snake_case>`)
    /// and the UI programs/translates against it; `message` is the human fallback.
    #[error("{message}")]
    Domain { code: String, message: String },
    #[error("permiso denegado: requiere `{0}`")]
    PermissionDenied(String),
    /// The same refusal as [`RuntimeError::PermissionDenied`], reported as one a **manager**
    /// could approve (hub#360, PLAN paso 2b rule 1). It is a LABEL on a denial, never a permit:
    /// nothing ran, nothing was written, and this issue adds no way in — the PIN that actually
    /// authorises is hub#361. What it buys is that the caller can tell "ask the manager" from
    /// "this is not for you", which a flat `403` cannot.
    ///
    /// `permission` is the missing permission, carried as a **field** because both the dialog
    /// (hub#363) and the re-check (hub#361) must name it exactly — never parse it out of a
    /// sentence.
    ///
    /// Only the `manager` level reaches here (rule 5): `admin` territory — fiscal identity, plan,
    /// deletion, installing apps — is never approved by a four-digit PIN in front of customers.
    #[error("requires elevation: `{permission}` needs approval from a manager")]
    RequiresElevation { permission: String },
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
    /// A read marked `required` (ADR-0069, hub#701) could not be resolved — the module that owns
    /// it is absent, inactive, or the query itself failed. Distinct from the GRACEFUL default
    /// (regla 3 de ADR-0069): a `required` read aborts the command instead of letting the handler
    /// degrade with a silent empty catalog. The canonical case is the tax catalog: without it a
    /// handler cannot tell «this category has no rule» from «the catalog never arrived», and
    /// guessing the rate is exactly what sales#21 prohibits.
    #[error("required read `{query}` is unavailable — the command was aborted (hub#701)")]
    ReadUnavailable { query: String },
    /// Fiscal precondition failed (hub#328, ADR-0203): a command whose SQL stamps the hub's
    /// business identity into a document (it references the injected `:business_tax_id` /
    /// `:business_legal_name` params — ADR-0061) cannot run while that identity is missing.
    /// Without the gate, empty + empty produced an issued invoice with a BLANK issuer, and
    /// VeriFactu chains from it (ADR-0189: an accepted record is never re-sent). `missing`
    /// lists the unmet requirements: `business_legal_name`, `business_tax_id`, `certificate`
    /// (the latter only while an installed module declares the `certificate` capability).
    #[error("fiscal precondition failed: configure {} before issuing fiscal documents", missing.join(", "))]
    FiscalPrecondition { missing: Vec<&'static str> },
    /// `business_tax_id` is FROZEN: this hub already emitted its first fiscal record (ADR-0273,
    /// hub#554 — the ADR's own consequence: "`business_tax_id` stops being able to fork a live
    /// chain").
    ///
    /// The chain is anchored by `(hub_id, issuer_nif, environment)` (guard R4, hub#313), so a
    /// different identifier does not *edit* anything — it starts a SECOND chain from 1 and leaves
    /// the first abandoned half-way, without a word. And to the tax authority a different tax id
    /// is a different **taxpayer**: the business would carry on issuing under an identity that may
    /// not be its own.
    ///
    /// `hub_settings` remains the single, editable source of the business identity (ADR-0061):
    /// this closes ONE key, and only from the moment `_hub_fiscal_profile.first_record_at` says
    /// the damage would be real. Re-sending the SAME value is not a change and is accepted —
    /// Ajustes → Negocio posts the tax id, the legal name and the address together, so refusing
    /// the no-op would freeze the whole form. `business_legal_name` is NOT frozen: it anchors
    /// nothing.
    ///
    /// `frozen_to` is the identifier the emitted chain hangs from and `since` the instant it went
    /// out — both travel so the screen can say what happened instead of "409".
    #[error("the business tax id is frozen to `{frozen_to}`: this hub emitted its first fiscal record on {since} and the chain is anchored to that identifier")]
    BusinessTaxIdFrozen { frozen_to: String, since: String },
    /// This hub is an ephemeral DEMO (ADR-0197 §4) and the request would change something a demo
    /// hub does not own: its AEAT environment, its business certificate or its fiscal identity.
    /// The marker comes from the deployment (`HUB_DEMO`), never from the caller — see
    /// [`DemoLock`] for what each subject protects.
    #[error("{lock}")]
    DemoLocked { lock: DemoLock },
    /// Error genérico que no encaja en una variante específica (p. ej. fallo del hasher argon2id
    /// al fijar un PIN, hub#15). Mensaje libre.
    #[error("{0}")]
    Other(String),
}

/// What an ephemeral DEMO hub is NOT allowed to change (ADR-0197 §4, hub#376).
///
/// Three subjects, three **distinct** stable codes on purpose: they are three independent guards
/// at three different doors, so a client (and a test) can tell which one refused. Collapsing them
/// into one code would let any of the three be deleted with the suite still green.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DemoLock {
    /// The AEAT transmission environment is **pinned** to `testing`. A demo hub is anonymous,
    /// unregistered and disposable: a record it transmits to the real AEAT would be a fiscal
    /// record of a business that never asked for one. Pinning is the demo-hub case of the
    /// one-way fiscal environment switch (hub#485 owns the other case: a REAL hub that already
    /// went live can never go back to `testing`).
    FiscalEnvironment,
    /// The business PKCS#12 is neither uploadable, replaceable nor removable. A demo never gets
    /// an `own` certificate (ADR-0197 §2: the AEAT issues no fictitious one, so it would have to
    /// be ERPlora's real fiscal identity inside the most exposed container that exists).
    BusinessCertificate,
    /// `business_tax_id` / `business_legal_name` are read-only. The fiscal identity of a demo is
    /// nobody's: writing it would let an anonymous visitor publish a `BillingProfile` upstream
    /// and would issue documents under a tax id its typist does not own.
    FiscalIdentity,
}

impl DemoLock {
    /// Stable machine code (the UI translates against it). One per subject.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::FiscalEnvironment => "demo_fiscal_environment_locked",
            Self::BusinessCertificate => "demo_business_certificate_locked",
            Self::FiscalIdentity => "demo_fiscal_identity_locked",
        }
    }
}

impl std::fmt::Display for DemoLock {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let human = match self {
            Self::FiscalEnvironment => {
                "this is a demo hub: its tax authority environment stays on testing — \
                 to issue real invoices, create your own hub"
            }
            Self::BusinessCertificate => {
                "this is a demo hub: it cannot hold a business certificate — \
                 to issue real invoices, create your own hub"
            }
            Self::FiscalIdentity => {
                "this is a demo hub: its tax id and legal name are read-only — \
                 to issue real invoices, create your own hub"
            }
        };
        f.write_str(human)
    }
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

/// Validates the public ABI of domain error codes (hub#139): exactly `<module>.<snake_case>`,
/// owned by the emitting module — no spaces, no extra dots, no foreign namespace. It is the
/// single authority for the shape; both the installer (declarative `expect_rows`) and the
/// handler output path (`Output.error`) call it.
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
        // hub#139: the code is a public ABI (`<module>.<snake_case>`) the UI translates against.
        // A module may only speak in its own namespace — anything else is a broken contract.
        assert!(valid_domain_code(
            "inventory",
            "inventory.insufficient_stock"
        ));
        assert!(valid_domain_code("w140", "w140.insufficient_stock"));
        // Foreign namespace: a module must not mint codes on behalf of another module.
        assert!(!valid_domain_code("inventory", "sales.insufficient_stock"));
        // Shape violations: casing, extra dots, empty segments, oversized codes.
        assert!(!valid_domain_code(
            "inventory",
            "inventory.InsufficientStock"
        ));
        assert!(!valid_domain_code("inventory", "inventory.stock.low"));
        assert!(!valid_domain_code("inventory", "inventory."));
        assert!(!valid_domain_code("inventory", "inventory"));
        assert!(!valid_domain_code("inventory", ""));
        assert!(!valid_domain_code(
            "inventory",
            &format!("inventory.{}", "x".repeat(128))
        ));
    }
}
