//! erplora-runtime — host genérico de módulos (ARQUITECTURA.md §4).
//!
//! Rust NO tiene lógica de negocio hardcodeada. Despachador genérico:
//!   `execute_command("pos.sale.create", payload)` / `execute_query("inventory.products.list", params)`
//!
//! Ciclo de vida (hot-plug): instalar → activar/desactivar → desinstalar. Solo los módulos
//! ACTIVOS exponen menú, queries, commands y listeners. Estado persistido en `hub_module`.

use std::path::Path;
use std::sync::Arc;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

pub mod access_email;
pub mod api_keys;
pub mod capabilities;
pub mod certificate;
pub mod commands;
pub mod core_version;
pub mod device_mode;
pub mod devices;
pub mod e2e_support;
pub mod elevation;
pub mod error_registry;
pub mod errors;
pub mod event_shape;
pub mod events;
pub mod export;
pub mod cloud_call;
pub mod fiscal_profile;
pub mod flows;
pub mod gateway_identity;
pub mod host_notify;
pub mod host_print;
pub mod hub_meta;
pub mod hub_users;
pub mod identity;
pub mod import;
pub mod import_sql;
pub mod installer;
pub mod loader;
pub mod manifest;
pub mod manifest_warning_grandfather;
pub mod migration_guard;
pub mod migrations;
pub mod module_package;
pub mod module_storage;
pub mod module_update;
pub mod money_backfill;
pub mod native;
pub mod outbox;
pub mod permissions;
pub mod pin_policy;
pub mod print_drain;
pub mod print_hosts;
pub mod print_queue;
pub mod print_routes;
pub mod print_stations;
pub mod producer_facts;
pub mod public_claim;
pub mod queries;
pub mod registry;
pub mod reset;
pub mod retention;
pub mod roles;
pub mod scheduler;
pub mod secret_box;
pub mod seed;
pub mod settings;
pub mod setup_status;
pub mod system_migrations;
pub mod ui;
pub mod update_history;
pub mod user_profile;
pub mod wasm;
pub mod wasm_cache;

pub use error_registry::{ErrorEvent, ErrorRegistry, ErrorSink};
pub use errors::{DemoLock, Result, RuntimeError};
pub use manifest::{Manifest, ManifestWarning, CORE_VERSION, CORE_VERSION_CORROBORATED};
pub use module_update::ModuleUpdate;
pub use registry::{
    AutomationCtx, EventSink, EventSource, ModuleSnapshot, ModuleStatus, NavEntry, Principal,
    Registry, RequestContext,
};
// Re-export del guard de e2e para los tests de integración (ERPlora/hub#253): raíz corta
// `erplora_runtime::require_modules_workspace()` en vez del path completo del módulo.
// `modules_root` travels with the guard on purpose: a test that resolves module paths by hand
// diverges from the guard and reintroduces hub#253 (the guard says "run", every path is wrong,
// the test skips itself and still reports `ok`).
pub use e2e_support::{
    modules_root, published_module_dirs, require_module_version, require_modules_workspace,
};

/// One declared domain error code of an installed module (ADR-0398), as `/api/modules` exposes it.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ErrorInfo {
    pub code: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deprecated: Option<String>,
}

/// Descripción de un módulo instalado (para `/api/modules`).
#[derive(Debug, Clone, serde::Serialize)]
pub struct ModuleInfo {
    pub id: String,
    pub name: String,
    pub version: String,
    pub status: ModuleStatus,
    /// Dependencias declaradas (`depends_on`): la UI del shell las usa para avisar de la CASCADA
    /// (ADR-0128) antes de desactivar («también desactivará: …»).
    pub depends_on: Vec<String>,
    /// What this core did not understand of the module's manifest and installed anyway (hub#521).
    ///
    /// Empty for every module that fits the contract. What the published catalogue is still
    /// allowed to warn about is enumerated, pair by pair, in
    /// [`crate::manifest_warning_grandfather::GRANDFATHERED_MANIFEST_WARNINGS`], and two tests in
    /// `installer` pin the catalogue to exactly that list so it can only shrink (hub#1243) — the
    /// count used to live in this comment and went stale twice.
    ///
    /// It travels here — and not only to a log — because "the hub ignores it in silence" is not
    /// fixed by writing the silence down somewhere nobody looks: whoever is staring at a module
    /// that half works has to be able to ASK.
    pub manifest_warnings: Vec<crate::manifest::ManifestWarning>,
    /// Domain error codes the module declares (ADR-0398), sorted by code. Empty when the module
    /// has no `errors` catalog yet — consumers (hub tests, the UI) read this instead of prose.
    pub errors: Vec<ErrorInfo>,
}

/// **What one event set off** (hub#666): the event itself, the flow runs it started and the events
/// its delivery caused. One level of the chain, because a transitive walk is a single query that
/// can traverse the whole outbox — the caller follows the links it cares about.
#[derive(Debug, Clone, serde::Serialize)]
pub struct EventTrace {
    pub event: outbox::CorrelatedEvent,
    pub runs: Vec<flows::FlowRun>,
    pub caused: Vec<outbox::CorrelatedEvent>,
}

/// `hub_id` de desarrollo por defecto (mismo UUID fijo que `crates/server::DEV_HUB_ID`). El host
/// real (server/Tauri) sobreescribe con el del despliegue vía [`Runtime::with_hub_id`].
pub const DEV_HUB_ID: &str = "00000000-0000-0000-0000-000000000001";

/// El runtime: une el adaptador de BD con el registro de módulos y ejecuta queries/commands.
pub struct Runtime {
    db: Box<dyn DatabaseAdapter>,
    registry: Registry,
    /// `hub_id` del despliegue (§2.5). Scoping del estado de módulos (`hub_module`) y de las
    /// migraciones de sistema. Lo inyecta el host; en tests por defecto = [`DEV_HUB_ID`].
    hub_id: String,
    /// Live **step-up approvals** (hub#361). In memory and nowhere else: an approval describes
    /// somebody standing at the till right now, so it dies with the process on purpose — see
    /// [`elevation`] for why persisting it would be worse than losing it.
    elevation: elevation::Grants,
}

// `impl Runtime` split by responsibility (hub#1403). Private modules: every
// method keeps its path (`Runtime::...`); only `system_params` needs a re-export.
mod access;
mod dispatch;
mod events_api;
mod fiscal;
mod flows_api;
mod lifecycle;
mod module_lifecycle;
mod printing;
mod settings_api;

pub(crate) use dispatch::effective_caller_lang;
pub use dispatch::system_params;
