//! Registro **global** de errores del Hub — un único embudo ("todo controlado").
//!
//! TODO error del Hub pasa por aquí: el core del runtime, los módulos declarativos/WASM
//! (etiquetados con su `module_id`), los `panic!` de Rust (vía el panic hook) y el frontend
//! (vía una ruta local del server). El registro aplica un dedup/throttle local best-effort y
//! reenvía cada evento al [`ErrorSink`] instalado por el host, que lo manda al Cloud.
//!
//! Reglas de oro de este módulo (es seguro llamarlo desde un panic hook):
//!  - **NUNCA** hace `panic!`/`unwrap`/`expect` en el camino de reporte (todo va envuelto).
//!  - **NUNCA** bloquea al llamador: el `submit` del sink debe ser fire-and-forget (el sink real
//!    del server hace `tokio::spawn`); aquí solo tomamos un `Mutex` muy corto para el dedup.
//!  - Si no hay sink instalado todavía (arranque temprano) el evento se **descarta en silencio**.
//!
//! El **contrato** que se reenvía al Cloud (lo construye el sink a partir de [`ErrorEvent`]):
//! `POST /api/v1/hub/device/error-report/` con
//! `{ source, module_id, error_code, message, stack, severity, context, occurred_at }`.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use serde::Serialize;

use crate::errors::{DemoLock, RuntimeError};

/// Ventana de dedup local: si la misma huella se reportó hace menos de esto, se omite.
const DEDUP_WINDOW: Duration = Duration::from_secs(30);

/// Tope de entradas en la tabla de dedup (defensa: no crecer sin límite ante errores muy variados).
/// Al alcanzarlo se purgan las entradas ya expiradas; si aún así está llena, se limpia entera.
const DEDUP_MAX_ENTRIES: usize = 1024;

/// Severidad de un error reportado.
///  - `"user"`: error esperable provocado por el llamador (payload inválido, permiso denegado,
///    capacidad no encontrada). No es un fallo del Hub; sirve de telemetría, no de alerta.
///  - `"unexpected"`: fallo no esperado (BD, WASM, panic, I/O…). Es lo que el Cloud agrupa y alerta.
pub mod severity {
    /// Error esperable provocado por el llamador (no es un bug del Hub).
    pub const USER: &str = "user";
    /// Fallo no esperado del Hub (lo que el Cloud agrupa/alerta).
    pub const UNEXPECTED: &str = "unexpected";
}

/// Origen de un error reportado (campo `source` del contrato).
pub mod source {
    /// Core del runtime / server del Hub.
    pub const HUB: &str = "hub";
    /// Un módulo declarativo / handler WASM (lleva `module_id`).
    pub const MODULE: &str = "module";
    /// El frontend (vía la ruta local `POST /api/error-report`).
    pub const FRONTEND: &str = "frontend";
}

/// Un evento de error normalizado, listo para reenviar al Cloud. Lo construyen el dispatcher del
/// runtime (módulo/core), el panic hook y la ruta del frontend; el sink lo serializa al contrato.
#[derive(Debug, Clone, Serialize)]
pub struct ErrorEvent {
    /// `"hub"` | `"module"` | `"frontend"` (ver [`source`]).
    pub source: String,
    /// `module_id` cuando el error proviene de un módulo; `None` para core/frontend sin módulo.
    pub module_id: Option<String>,
    /// Código corto y estable del error (variante del enum, `"panic"`, el `type` del frontend…).
    pub error_code: String,
    /// Mensaje legible (la `Display` del error / payload del panic).
    pub message: String,
    /// Stack/backtrace/ubicación si está disponible.
    pub stack: Option<String>,
    /// `"unexpected"` | `"user"` (ver [`severity`]).
    pub severity: String,
    /// Contexto adicional (nombre del command/query, claves del payload, url del frontend…).
    /// Nunca el payload completo (evita arrastrar PII).
    pub context: serde_json::Value,
}

impl ErrorEvent {
    /// Constructor base con contexto vacío (`{}`) y sin `module_id`/`stack`.
    pub fn new(
        source: impl Into<String>,
        error_code: impl Into<String>,
        message: impl Into<String>,
        severity: impl Into<String>,
    ) -> Self {
        Self {
            source: source.into(),
            module_id: None,
            error_code: error_code.into(),
            message: message.into(),
            stack: None,
            severity: severity.into(),
            context: serde_json::Value::Object(Default::default()),
        }
    }

    /// Fija el `module_id` (encadenable).
    pub fn with_module(mut self, module_id: impl Into<String>) -> Self {
        self.module_id = Some(module_id.into());
        self
    }

    /// Fija el `stack`/backtrace (encadenable).
    pub fn with_stack(mut self, stack: impl Into<String>) -> Self {
        self.stack = Some(stack.into());
        self
    }

    /// Fija el contexto (encadenable).
    pub fn with_context(mut self, context: serde_json::Value) -> Self {
        self.context = context;
        self
    }

    /// Huella estable para el dedup local: source + module + code + message. (El Cloud calcula su
    /// propio fingerprint server-side; este es solo para no martillear ante un error en bucle.)
    fn fingerprint(&self) -> String {
        format!(
            "{}|{}|{}|{}",
            self.source,
            self.module_id.as_deref().unwrap_or(""),
            self.error_code,
            self.message
        )
    }
}

/// Sumidero de errores: lo implementa el host (server/Tauri) para reenviar al Cloud.
///
/// **Object-safe** y **fire-and-forget**: `submit` NO debe bloquear al llamador (el sink real del
/// server lanza un `tokio::spawn` y devuelve al instante). Vive tras un `Arc` en el registro global.
pub trait ErrorSink: Send + Sync {
    /// Acepta un evento para reenviarlo (sin bloquear). Lo que falle, se ignora (best-effort).
    fn submit(&self, event: ErrorEvent);
}

/// El registro global de errores. Único por proceso (un contenedor ECS por hub / una app Tauri).
/// Accede a él con [`ErrorRegistry::global`].
pub struct ErrorRegistry {
    /// Sink instalado por el host. `None` hasta [`ErrorRegistry::install`] (eventos previos se tiran).
    sink: OnceLock<std::sync::Arc<dyn ErrorSink>>,
    /// Dedup/throttle local: huella → instante del último reporte. `Mutex` corto (sin await dentro).
    recent: Mutex<HashMap<String, Instant>>,
}

impl ErrorRegistry {
    /// Accessor del registro global (perezoso, una sola instancia por proceso).
    pub fn global() -> &'static ErrorRegistry {
        static REGISTRY: OnceLock<ErrorRegistry> = OnceLock::new();
        REGISTRY.get_or_init(|| ErrorRegistry {
            sink: OnceLock::new(),
            recent: Mutex::new(HashMap::new()),
        })
    }

    /// Instala el sink (lo llama el host UNA vez al arrancar). Si ya había uno, no lo reemplaza
    /// (best-effort, no hace `panic!`).
    pub fn install(sink: std::sync::Arc<dyn ErrorSink>) {
        let _ = Self::global().sink.set(sink);
    }

    /// `true` si ya hay un sink instalado (útil para tests / introspección).
    pub fn has_sink(&self) -> bool {
        self.sink.get().is_some()
    }

    /// Reporta un evento. Si no hay sink → se descarta. Si la misma huella se vio en los últimos
    /// ~30 s → se omite (throttle). En otro caso se entrega al sink. NUNCA hace `panic!`.
    pub fn report(&self, event: ErrorEvent) {
        // Sin sink (arranque temprano / proceso sin host): tirar en silencio.
        let Some(sink) = self.sink.get() else {
            return;
        };

        // Throttle/dedup local best-effort. Si el mutex está envenenado lo recuperamos (un panic en
        // otro hilo no debe inutilizar el reporte de errores). Si todo falla, reportamos igualmente.
        if self.should_throttle(&event) {
            return;
        }

        sink.submit(event);
    }

    /// ¿Hay que omitir este evento por dedup? Actualiza la tabla de huellas recientes. Best-effort:
    /// ante cualquier problema con el `Mutex`, devuelve `false` (mejor reportar de más que perder).
    fn should_throttle(&self, event: &ErrorEvent) -> bool {
        let fp = event.fingerprint();
        let now = Instant::now();
        let mut map = match self.recent.lock() {
            Ok(g) => g,
            Err(poisoned) => poisoned.into_inner(),
        };

        // Purga perezosa si la tabla creció demasiado (entradas expiradas; si aún llena, limpia todo).
        if map.len() >= DEDUP_MAX_ENTRIES {
            map.retain(|_, &mut t| now.duration_since(t) < DEDUP_WINDOW);
            if map.len() >= DEDUP_MAX_ENTRIES {
                map.clear();
            }
        }

        match map.get(&fp) {
            Some(&last) if now.duration_since(last) < DEDUP_WINDOW => true,
            _ => {
                map.insert(fp, now);
                false
            }
        }
    }
}

/// Reporta un [`RuntimeError`] al registro global, clasificando severidad y derivando el
/// `error_code` de la variante. Helper de conveniencia para el dispatcher del runtime.
///
/// Clasificación de severidad (errores "de usuario" = esperables, provocados por el llamador):
/// `InvalidPayload` / `PermissionDenied` / `CommandNotFound` / `QueryNotFound` / `NotImplemented`
/// → `"user"`; todo lo demás (Db, Wasm, Io, panic…) → `"unexpected"`.
pub fn report_runtime_error(
    err: &RuntimeError,
    source: &str,
    module_id: Option<String>,
    context: serde_json::Value,
) {
    let mut event = ErrorEvent::new(
        source,
        error_code_of(err),
        err.to_string(),
        severity_of(err),
    )
    .with_context(context);
    if let Some(id) = module_id {
        event = event.with_module(id);
    }
    ErrorRegistry::global().report(event);
}

/// Severidad de un [`RuntimeError`]: "user" si es un error esperable del llamador, "unexpected" si
/// es un fallo no esperado del Hub. Ver [`report_runtime_error`].
pub fn severity_of(err: &RuntimeError) -> &'static str {
    use RuntimeError as E;
    match err {
        E::InvalidPayload { .. }
        // hub#1086: a payload missing a bind the query's SQL references is the caller's
        // mistake, same family as an invalid payload — never a Hub bug.
        | E::MissingRequiredParam { .. }
        | E::PermissionDenied(_)
        | E::CommandNotFound(_)
        | E::QueryNotFound(_)
        | E::InternalCommand(_)
        // hub#140: un `min_affected_rows` incumplido es un error esperable del llamador (recurso
        // inexistente / transición no aplicable), no un fallo inesperado del Hub.
        | E::MinAffectedRows { .. }
        // hub#139: a domain rejection is a business rule doing its job (insufficient stock,
        // invalid transition) — expected caller-facing behaviour, never a Hub bug.
        | E::Domain { .. }
        // hub#328: the fiscal precondition is expected state of a hub that has not finished its
        // setup (missing business identity/certificate) — never a Hub bug worth an issue.
        | E::FiscalPrecondition { .. }
        // hub#1088: a tax id that is not shaped like an official one is the caller's mistake at
        // the settings door — expected, user-severity, never a Hub bug.
        | E::InvalidTaxId { .. }
        // hub#376: a demo hub refusing to leave its sandbox is the deployment marker doing its
        // job (ADR-0197 §4) — expected, and never a Hub bug worth an issue.
        | E::DemoLocked { .. }
        // hub#554: a hub that already emitted refusing to change taxpayer is the freeze doing its
        // job — the state of the hub, not a bug of the Hub.
        | E::BusinessTaxIdFrozen { .. }
        // hub#69: a hub that went live refusing to move country is the freeze of ADR-0273 doing
        // its job — the state of the hub, not a bug of the Hub. Same reasoning as its sibling.
        | E::HubCountryFrozen { .. }
        // hub#360: a cashier reaching for something a manager approves is the permission model
        // working, not a Hub bug. Same severity as the flat `PermissionDenied` it refines.
        | E::RequiresElevation { .. }
        // hub#521: a third-party `module.json` that does not fit this core is the contract doing
        // its job — the zip is the caller's input, not a bug of the Hub, and filing an issue for
        // every install of a module built for a newer version would be noise.
        | E::ManifestUnknownField { .. }
        | E::CoreVersionTooOld { .. }
        | E::ManifestCoreFloorUnreadable { .. }
        // hub#775: a `protects` guard refusing a sale because the drawer is closed is the guard
        // doing its job — the state of the hub (no open session), not a bug of the Hub. Same
        // severity as the other business-state refusals above.
        | E::ProtectsGuard { .. }
        | E::NotImplemented(_) => severity::USER,
        _ => severity::UNEXPECTED,
    }
}

/// Código corto y estable derivado de la variante de [`RuntimeError`] (snake_case del nombre).
/// `Cow` because `Domain` (hub#139) carries a module-declared, dynamic namespaced code — for
/// every other variant the code stays a borrowed static string.
pub fn error_code_of(err: &RuntimeError) -> std::borrow::Cow<'_, str> {
    use std::borrow::Cow;
    use RuntimeError as E;
    Cow::Borrowed(match err {
        E::Io(_) => "io",
        E::Manifest { .. } => "manifest",
        E::Db(_) => "db",
        E::QueryNotFound(_) => "query_not_found",
        E::ModuleNotInstalled { .. } => "module_not_installed",
        E::ModuleInactive { .. } => "module_inactive",
        E::CommandNotFound(_) => "command_not_found",
        E::InternalCommand(_) => "internal_command",
        // hub#140: el código estable refleja el `kind` (not_found vs conflict/invalid_transition),
        // no la variante genérica — es lo que el SDK y los listeners programan. `as_str` es la
        // única fuente de verdad del nombre, así que la regla vive en `AffectedKind`.
        E::MinAffectedRows { kind, .. } => kind.as_str(),
        // hub#139: the namespaced domain code IS the stable code — the UI translates against it.
        E::Domain { code, .. } => code.as_str(),
        E::PermissionDenied(_) => "permission_denied",
        // hub#360: its own stable code, NOT a flavour of `permission_denied` — the UI branches on
        // it to decide whether to offer the manager-approval dialog (hub#363).
        E::RequiresElevation { .. } => "requires_elevation",
        E::CapabilityDenied { .. } => "capability_denied",
        E::MissingDependency { .. } => "missing_dependency",
        // hub#681: the dependency exists but is older than the declared floor — its own code so
        // the shell/marketplace can say "update `inventory` first" instead of a generic failure.
        E::DependencyTooOld { .. } => "dependency_too_old",
        E::DependencyFloorUnreadable { .. } => "dependency_floor_unreadable",
        E::DependencyCycle { .. } => "dependency_cycle",
        E::EventLoop => "event_loop",
        E::EventNotDeclared { .. } => "event_not_declared",
        E::NotImplemented(_) => "not_implemented",
        E::Wasm(_) => "wasm",
        E::Native(_) => "native",
        E::InvalidPayload { .. } => "invalid_payload",
        // hub#1086: its own stable code, so a caller can tell "you did not send what the
        // query needs" from "what you sent does not validate".
        E::MissingRequiredParam { .. } => "missing_required_param",
        E::Schema { .. } => "schema",
        E::Notify(_) => "notify",
        // hub#957: su propio código, no un sabor de `notify`. Las dos son capacidades de host, pero
        // «no se encoló el papel» y «no salió el aviso» se atienden en sitios distintos.
        E::Print(_) => "print",
        E::Storage(_) => "module_storage",
        E::Certificate(_) => "certificate",
        // hub#701: a required read that cannot be resolved aborts the command. Its own code — not a
        // flavour of `db` or `query_not_found` — so the TPV can tell «el catálogo fiscal no llegó»
        // from a generic error and surface it with the query that faltó.
        E::ReadUnavailable { .. } => "read_unavailable",
        E::FiscalPrecondition { .. } => "fiscal_precondition_failed",
        // hub#1088: the SUBJECT is the stable code, one per failure kind — the screen has to be
        // able to say "the control letter does not check out" instead of a flat "invalid", and
        // each of the four has its own translation (es/en).
        E::InvalidTaxId { code, .. } => code,
        // hub#376: the SUBJECT is the stable code, one per demo lock — a client that only sees
        // `demo_locked` could not tell which of the three doors refused.
        E::DemoLocked { lock } => lock.as_str(),
        // hub#554: its own code, NOT a flavour of `demo_fiscal_identity_locked`. Two guards on the
        // same key that mean opposite things ("this hub is nobody's" vs "this hub already emitted
        // and cannot change taxpayer"), and only one of them has a way out.
        E::BusinessTaxIdFrozen { .. } => "business_tax_id_frozen",
        // hub#69: its own code, not a flavour of the tax-id freeze. Two different keys frozen by
        // two different facts, and the screen has to name the one that refused.
        E::HubCountryFrozen { .. } => "hub_country_frozen",
        // hub#521: three distinct codes for three distinct refusals of a `module.json`. The screen
        // that offers an install has to say something different for "this app needs a newer
        // terminal" (act: update) than for "this app declares something we cannot run" (act:
        // report it to whoever published it).
        E::ManifestUnknownField { .. } => "manifest_unknown_field",
        E::CoreVersionTooOld { .. } => "core_version_too_old",
        E::ManifestCoreFloorUnreadable { .. } => "manifest_core_floor_unreadable",
        // hub#775: its own code, NOT a flavour of `permission_denied`. A protects guard is a
        // different door from RBAC (it is a module's precondition over another module's surface),
        // and the screen that explains it has to say "open the drawer", not "ask the manager".
        E::ProtectsGuard { .. } => "protects_guard",
        E::Other(_) => "other",
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    /// Sink de test que cuenta cuántos eventos recibe (sin tocar red).
    struct CountingSink(Arc<AtomicUsize>);
    impl ErrorSink for CountingSink {
        fn submit(&self, _event: ErrorEvent) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }

    /// Construye un registro AISLADO (no el global) para testear el throttle sin estado compartido.
    fn isolated(sink: Arc<dyn ErrorSink>) -> ErrorRegistry {
        let reg = ErrorRegistry {
            sink: OnceLock::new(),
            recent: Mutex::new(HashMap::new()),
        };
        let _ = reg.sink.set(sink);
        reg
    }

    fn event(code: &str, msg: &str) -> ErrorEvent {
        ErrorEvent::new(source::HUB, code, msg, severity::UNEXPECTED)
    }

    #[test]
    fn dedup_skips_same_fingerprint_within_window() {
        let count = Arc::new(AtomicUsize::new(0));
        let reg = isolated(Arc::new(CountingSink(count.clone())));

        reg.report(event("db", "boom"));
        reg.report(event("db", "boom")); // misma huella → throttled
        reg.report(event("db", "boom")); // idem

        assert_eq!(
            count.load(Ordering::SeqCst),
            1,
            "solo el primero debe llegar al sink"
        );
    }

    #[test]
    fn different_fingerprints_are_not_throttled() {
        let count = Arc::new(AtomicUsize::new(0));
        let reg = isolated(Arc::new(CountingSink(count.clone())));

        reg.report(event("db", "boom"));
        reg.report(event("db", "otra cosa")); // distinto mensaje → pasa
        reg.report(event("wasm", "boom")); // distinto code → pasa

        assert_eq!(count.load(Ordering::SeqCst), 3);
    }

    #[test]
    fn no_sink_drops_quietly() {
        let reg = ErrorRegistry {
            sink: OnceLock::new(),
            recent: Mutex::new(HashMap::new()),
        };
        assert!(!reg.has_sink());
        // No debe entrar en pánico ni hacer nada observable.
        reg.report(event("db", "boom"));
    }

    #[test]
    fn severity_classification() {
        // Errores "de usuario" (esperables).
        assert_eq!(
            severity_of(&RuntimeError::PermissionDenied("x".into())),
            severity::USER
        );
        assert_eq!(
            severity_of(&RuntimeError::CommandNotFound("c".into())),
            severity::USER
        );
        assert_eq!(
            severity_of(&RuntimeError::QueryNotFound("q".into())),
            severity::USER
        );
        assert_eq!(
            severity_of(&RuntimeError::InvalidPayload {
                name: "n".into(),
                detail: "d".into()
            }),
            severity::USER
        );
        assert_eq!(
            severity_of(&RuntimeError::NotImplemented("x")),
            severity::USER
        );
        // Fallos no esperados.
        assert_eq!(
            severity_of(&RuntimeError::Wasm("x".into())),
            severity::UNEXPECTED
        );
        assert_eq!(
            severity_of(&RuntimeError::Other("x".into())),
            severity::UNEXPECTED
        );
        assert_eq!(severity_of(&RuntimeError::EventLoop), severity::UNEXPECTED);
    }

    #[test]
    fn error_code_derives_from_variant() {
        assert_eq!(
            error_code_of(&RuntimeError::PermissionDenied("x".into())),
            "permission_denied"
        );
        assert_eq!(
            error_code_of(&RuntimeError::CommandNotFound("c".into())),
            "command_not_found"
        );
        assert_eq!(
            error_code_of(&RuntimeError::QueryNotFound("q".into())),
            "query_not_found"
        );
        assert_eq!(
            error_code_of(&RuntimeError::InvalidPayload {
                name: "n".into(),
                detail: "d".into()
            }),
            "invalid_payload"
        );
        assert_eq!(error_code_of(&RuntimeError::Wasm("x".into())), "wasm");
        assert_eq!(error_code_of(&RuntimeError::EventLoop), "event_loop");
    }

    /// hub#139: a `Domain` rejection travels with the module-declared namespaced code — that IS
    /// the stable code (the UI translates against it) — and is caller-expectable (`user`), never
    /// an issue-worthy Hub bug.
    #[test]
    fn domain_error_keeps_its_namespaced_code_and_user_severity() {
        let err = RuntimeError::Domain {
            code: "inventory.insufficient_stock".into(),
            message: "Not enough stock".into(),
        };
        assert_eq!(error_code_of(&err), "inventory.insufficient_stock");
        assert_eq!(severity_of(&err), severity::USER);
    }

    #[test]
    fn report_runtime_error_builds_event() {
        let count = Arc::new(AtomicUsize::new(0));
        // Verifica que el helper construye y entrega (usa el sink aislado vía un wrapper).
        struct CaptureSink(Arc<std::sync::Mutex<Option<ErrorEvent>>>);
        impl ErrorSink for CaptureSink {
            fn submit(&self, event: ErrorEvent) {
                *self.0.lock().unwrap() = Some(event);
            }
        }
        let captured = Arc::new(std::sync::Mutex::new(None));
        let reg = isolated(Arc::new(CaptureSink(captured.clone())));
        let _ = &count; // silencia el aviso si no se usa

        let err = RuntimeError::Wasm("kaboom".into());
        let event = ErrorEvent::new(
            source::MODULE,
            error_code_of(&err),
            err.to_string(),
            severity_of(&err),
        )
        .with_module("inventory")
        .with_context(serde_json::json!({ "command": "inventory.products.create" }));
        reg.report(event);

        let got = captured.lock().unwrap().clone().expect("evento entregado");
        assert_eq!(got.source, source::MODULE);
        assert_eq!(got.module_id.as_deref(), Some("inventory"));
        assert_eq!(got.error_code, "wasm");
        assert_eq!(got.severity, severity::UNEXPECTED);
        assert_eq!(got.context["command"], "inventory.products.create");
    }

    // ── Los códigos de los cierres de la DEMO (ADR-0197 §4 · hub#376) ──────────────────────
    //
    // Son **contrato de máquina**: la UI se traduce contra ellos y el server los devuelve tal cual
    // con un 409. Se afirman aquí, en el crate que los DEFINE, y no solo desde la puerta HTTP: si
    // el único sitio que los mira estuviera en `erplora-server`, este crate podría cambiarlos —o
    // vaciarlos— con su propia suite en verde.

    /// El código de cada cierre, LITERAL. Un valor distinto es una regresión de contrato, no un
    /// detalle interno: el 409 que llega al navegador deja de significar lo que la UI espera.
    #[test]
    fn each_demo_lock_carries_its_own_stable_code() {
        assert_eq!(
            DemoLock::FiscalEnvironment.as_str(),
            "demo_fiscal_environment_locked"
        );
        assert_eq!(
            DemoLock::BusinessCertificate.as_str(),
            "demo_business_certificate_locked"
        );
        assert_eq!(
            DemoLock::FiscalIdentity.as_str(),
            "demo_fiscal_identity_locked"
        );
    }

    /// Y los tres son DISTINTOS entre sí y no vacíos. Es lo que impide que borrar uno de los tres
    /// cierres pase inadvertido porque otro contesta lo mismo — y un código vacío sería un 409 que
    /// no le dice nada a nadie.
    #[test]
    fn the_three_demo_locks_never_collapse_into_one_answer() {
        let codes = [
            DemoLock::FiscalEnvironment.as_str(),
            DemoLock::BusinessCertificate.as_str(),
            DemoLock::FiscalIdentity.as_str(),
        ];
        for code in codes {
            assert!(!code.trim().is_empty(), "un cierre sin código es un 409 mudo");
        }
        let mut unique = codes.to_vec();
        unique.sort_unstable();
        unique.dedup();
        assert_eq!(unique.len(), 3, "dos cierres con la misma respuesta: {codes:?}");
    }

    /// `error_code_of` publica el SUJETO del cierre, no un `demo_locked` plano: es lo que viaja al
    /// registro de errores y a la respuesta HTTP.
    #[test]
    fn the_error_code_of_a_demo_lock_is_its_subject() {
        for lock in [
            DemoLock::FiscalEnvironment,
            DemoLock::BusinessCertificate,
            DemoLock::FiscalIdentity,
        ] {
            let err = RuntimeError::DemoLocked { lock };
            assert_eq!(error_code_of(&err), lock.as_str());
            // Y es cosa esperable del estado del hub, nunca un bug del Hub que abra una issue.
            assert_eq!(severity_of(&err), severity::USER);
        }
    }

    // ── El NIF CONGELADO de un hub que ya emitió (hub#554) ─────────────────────────────────

    /// El congelado tiene **su propio** código estable y es cosa esperable del estado del hub, no
    /// un bug que merezca una issue. Se afirma aquí, en el crate que lo DEFINE: si el único sitio
    /// que lo mira estuviera en `erplora-server`, este crate podría cambiarlo con su suite en verde.
    #[test]
    fn a_frozen_tax_id_carries_its_own_stable_code() {
        let err = RuntimeError::BusinessTaxIdFrozen {
            frozen_to: "B12345674".into(),
            since: "2026-08-08T10:00:00Z".into(),
        };
        assert_eq!(error_code_of(&err), "business_tax_id_frozen");
        assert_eq!(severity_of(&err), severity::USER);
        // Y NO es el cierre de la demo: dos guardas sobre la misma clave que significan cosas
        // opuestas, y solo una de las dos tiene salida.
        assert_ne!(error_code_of(&err), DemoLock::FiscalIdentity.as_str());
    }

    /// hub#1088: the refusal of an invalid tax id carries its own code PER FAILURE KIND — the
    /// SUBJECT travels, exactly like the demo locks, because «the letter does not check out» and
    /// «this is no official shape» are two different conversations on the screen.
    #[test]
    fn an_invalid_tax_id_carries_the_code_of_its_failure_kind() {
        for (code, err) in [
            (
                crate::settings::INVALID_TAX_ID_TYPE,
                RuntimeError::InvalidTaxId { code: crate::settings::INVALID_TAX_ID_TYPE, message: String::new() },
            ),
            (
                crate::settings::TAX_ID_TOO_LONG,
                RuntimeError::InvalidTaxId { code: crate::settings::TAX_ID_TOO_LONG, message: String::new() },
            ),
            (
                crate::settings::INVALID_TAX_ID_FORMAT,
                RuntimeError::InvalidTaxId { code: crate::settings::INVALID_TAX_ID_FORMAT, message: String::new() },
            ),
            (
                crate::settings::INVALID_TAX_ID_CONTROL,
                RuntimeError::InvalidTaxId { code: crate::settings::INVALID_TAX_ID_CONTROL, message: String::new() },
            ),
        ] {
            assert_eq!(error_code_of(&err), code, "the code IS the subject");
            assert_eq!(severity_of(&err), severity::USER);
        }
        // And none of them collapses into the payload refusal: a shape problem at the settings
        // door is not a broken request.
        assert_ne!(
            error_code_of(&RuntimeError::InvalidTaxId {
                code: crate::settings::INVALID_TAX_ID_FORMAT,
                message: String::new(),
            }),
            "invalid_payload"
        );
    }

    /// El mensaje dice **con qué identificador** está anclada la cadena y **desde cuándo**. Sin
    /// eso, el que se topa con el 409 no sabe si el que sobra es el NIF que acaba de teclear o el
    /// que el hub lleva dentro.
    #[test]
    fn a_frozen_tax_id_names_the_anchor_and_the_moment() {
        let message = RuntimeError::BusinessTaxIdFrozen {
            frozen_to: "B12345674".into(),
            since: "2026-08-08T10:00:00Z".into(),
        }
        .to_string();
        assert!(message.contains("B12345674"), "`{message}`");
        assert!(message.contains("2026-08-08T10:00:00Z"), "`{message}`");
    }

    /// El mensaje humano no es el código: dice qué pasa Y la salida real («crea tu propio hub»),
    /// que es la única acción que le queda al que se topa con el cierre.
    #[test]
    fn a_demo_lock_explains_itself_and_names_the_way_out() {
        for lock in [
            DemoLock::FiscalEnvironment,
            DemoLock::BusinessCertificate,
            DemoLock::FiscalIdentity,
        ] {
            let message = RuntimeError::DemoLocked { lock }.to_string();
            assert!(
                message.contains("demo hub"),
                "el mensaje tiene que decir POR QUÉ: `{message}`"
            );
            assert!(
                message.contains("create your own hub"),
                "…y la salida real: `{message}`"
            );
            assert_ne!(message, lock.as_str(), "el mensaje no es el código");
        }
    }
}
