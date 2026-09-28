//! erplora-server — servidor Axum del runtime del tenant en modo cloud (ARQUITECTURA.md §7.5).
//!
//! Expone `execute_query`/`execute_command` por HTTP, los eventos por WebSocket (`/ws`), y la
//! **gestión de módulos** (listar / instalar / activar / desactivar / desinstalar = hot-plug).
//!
//! Rutas:
//!   GET  /healthz
//!   GET  /api/navigation                     menú de módulos ACTIVOS
//!   GET  /api/modules                        módulos instalados + estado
//!   POST /api/modules/install   {dir}        instala desde carpeta (extraída por erplora-source).
//!                                            **Solo dev** (`HUB_DEV_MODE`) y confinado al staging
//!                                            del hub — ver `install_guard` (hub#239).
//!   GET  /api/modules/updates                qué versión ofrece hoy el marketplace por módulo
//!                                            instalado (hub#516). Bajo demanda, no en bucle.
//!   POST /api/modules/:id/activate
//!   POST /api/modules/:id/deactivate
//!   POST /api/modules/:id/uninstall
//!   POST /api/modules/:id/update {version?}  actualiza un módulo instalado (hub#516). Mismo
//!                                            pipeline verificado que instalar; sin `version`,
//!                                            resuelve la que toca (cuarentena y pin mandan).
//!   POST /api/query   {name, params}
//!   POST /api/command {name, payload}
//!   GET  /ws                                 stream de eventos (solo push)
//!   GET  /ws/print                           canal del host de impresión (bidireccional, hub#343)

use axum::body::Body;
use axum::extract::{Path, Query, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::{json, Map, Value};

pub mod activity;
pub mod address_guard;
/// **Server-side agent runner** (ADR-0283 K5, hub#665): the tool loop of an `ai` step, in Rust and
/// outside the runtime's global lock. It lives here and not in the runtime because it needs
/// `cloud-client` — the runtime has no network by design.
pub mod agent_runner;
pub mod api_keys;
pub mod assistant;
pub mod assistant_report;
pub mod auth;
pub mod boot_announce;
pub mod call_budget;
pub mod cloud_call;
/// The other end of the hub's `report-uri`: what the browser refused, said out loud — hub#1447.
pub mod csp_report;
pub mod daily_usage;
/// `shared` (counter till) vs `personal` (somebody's own device) — plan step 2b, hub#357.
pub mod device_mode;
/// The devices of a business and the gesture that cuts a lost one off — hub#455.
pub mod devices;
/// Step-up approvals: the manager's PIN, verified in the runtime, buys ONE action — hub#361.
pub mod elevation;
pub mod embed;
pub mod entitlement;
pub mod error_sink;
pub mod event_stream;
pub mod export_import;
/// The I/O half of a flow step (hub#662): the call itself, outside the runtime's global lock.
pub mod flow_io;
pub mod flows_api;
pub mod gateway_enrolment;
pub mod hub_users;
pub mod inbound_poll;
pub mod ingest;
pub mod install;
pub mod install_guard;
/// Shared `tracing` capture for the tests of this crate (hub#1796). Test-only: it never ships.
#[cfg(test)]
mod log_capture;
pub mod logging;
pub mod login_throttle;
pub mod media;
pub mod members;
pub mod module_reconcile;
pub mod module_storage;
pub mod notify_transport;
pub mod openapi;
/// Catalogue of the operations this hub's dispatcher accepts, by exact name — hub#1757.
pub mod operations_catalog;
/// Operable dead-letter of the event outbox: list · retry · discard — hub#660 (ADR-0127 phase 2).
pub mod outbox_admin;
pub mod policies_api;
pub mod print;
pub mod print_ws;
pub mod profile;
pub mod public_door;
pub mod readiness;
/// El otorgamiento de representación firmado (hub#817): se captura aquí y lo custodia el SaaS.
pub mod representation_grant;
pub mod reset;
pub mod router;
pub mod settings;
pub mod shutdown;
pub mod state;
pub mod system;
pub mod system_metrics;
pub mod tenant;
pub mod usage_series;
pub mod version;
pub mod whatsapp_connect;
pub mod whatsapp_quota;
pub mod whatsapp_templates;
pub mod whatsapp_header_samples;
pub mod whatsapp_media;

pub use state::{
    marketplace_client, AppState, AuthMode, HubConfig, HubId, MachineToken, SharedRuntime,
    SignatureMode, WsEvent, DEV_HUB_ID, MARKETPLACE_STALL_TIMEOUT,
};
pub use tenant::{
    EnvOrgResolver, OrgDescriptor, OrgId, OrgResolver, RuntimeFactory, TenantError, TenantRouter,
};

// `lib.rs` split by responsibility (hub#1404). `boot` is the composition root —
// the ONLY server module allowed to name concrete native plugins.
mod assistant_api;
mod auth_api;
mod boot;
mod cloud_proxy;
mod config;
mod dispatch_api;
mod load_shed;
mod module_api;
mod routes;

pub(crate) use assistant_api::*;
pub(crate) use auth_api::*;
pub use boot::serve;
pub(crate) use cloud_proxy::*;
pub use config::{default_csp, normalize_pg_dsn, resolve_csp, ServeConfig};
pub(crate) use dispatch_api::*;
pub(crate) use load_shed::*;
pub use load_shed::{with_load_shedding, DEFAULT_MAX_INFLIGHT_REQUESTS, MAX_INFLIGHT_ENV};
pub(crate) use module_api::*;
pub(crate) use routes::*;
pub use routes::{
    app, build_router, build_serving_router, with_csp, with_noindex, with_static_frontend,
};
