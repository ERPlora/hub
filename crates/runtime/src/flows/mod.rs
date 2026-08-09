//! **Automation kernel** (ADR-0283 K1+K2+K7 — hub#661): the last family of primitives the core
//! grows before it freezes.
//!
//! A flow is a core row (`_flow`) with a versioned JSON document; it runs with **its own explicit
//! grants** (`_flow_grants`, default-deny) instead of borrowing a human's role; and it is advanced
//! by the tick that already runs the outbox relay and the scheduler. What is NOT here — the visual
//! editor, the templates, the connectors, the inbox as a screen — lives in modules, and that split
//! is the whole point of the ADR: the core can be frozen only if the product half is somewhere else.
//!
//! Load [`architecture/hub/flows.md`](../../../../architecture/hub/flows.md) before touching any of
//! this; the design is accepted and this is its implementation.
//!
//! ```text
//!   event in the outbox ──┐
//!   cron / at due ────────┼──▶ _flow_runs (one row = one execution, claimed with a lease)
//!   POST …/run ───────────┘            │
//!                                      ▼
//!                      flows_tick ──▶ step: command | condition | delay
//!                                      │        │
//!                                      │        └─ Origin::Automation → _flow_grants (per step)
//!                                      └─ http | ai | notify → claim → I/O → complete (hub#662/665)
//! ```
//!
//! Submodules, in the order the data flows through them:
//! - [`def`] — the frozen document, the mapping language and the conditions;
//! - [`grants`] — what a flow is allowed to do, read fresh at every step;
//! - [`store`] — the CRUD the REST layer sits on, plus materialising triggers;
//! - [`triggers`] — event matching in the relay, and the cron/`at` clock;
//! - [`executor`] — the tick that advances runs.
pub mod def;
pub mod executor;
pub mod grants;
pub mod store;
pub mod triggers;

pub use def::{Condition, FlowDefinition, StepKind, TriggerKind, SCHEMA_VERSION};
pub use executor::tick;
pub use store::{Flow, FlowRun, FlowRunStep, NewFlow};

/// Identity of the flow behind an [`crate::commands::Origin::Automation`] call, carried in the
/// [`crate::registry::RequestContext`]. See [`crate::registry::AutomationCtx`] for why the HTTP
/// layer cannot construct one.
pub use crate::registry::AutomationCtx;

/// Shared fixtures for the colocated tests of this kernel: a synthetic registry and the system
/// schema, so each submodule tests its own logic instead of re-deriving how to build a module.
#[cfg(test)]
pub(crate) mod test_support {
    use crate::manifest::CommandDef;
    use crate::registry::RegisteredCommand;
    use erplora_db::DatabaseAdapter;

    /// A declarative Tier-0 command, the shape the installer produces.
    pub(crate) fn command(
        module: &str,
        permission: &str,
        sql: &str,
        emit: Vec<String>,
    ) -> RegisteredCommand {
        RegisteredCommand {
            module_id: module.to_string(),
            def: CommandDef {
                permission: permission.to_string(),
                reads: Vec::new(),
                transaction: true,
                sql: vec![sql.to_string()],
                emit,
                min_affected_rows: None,
                expect_rows: None,
                handler: None,
                ai: None,
                schema: None,
                expose_api: false,
                internal: false,
            },
            sql: vec![sql.to_string()],
            wasm: None,
            schema: None,
        }
    }

    /// The system schema a real boot lays down, so the flow tables exist as they will in a hub.
    pub(crate) async fn ensure_schema(db: &dyn DatabaseAdapter, hub_id: &str) {
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        crate::outbox::ensure_tables(db).await.unwrap();
        crate::system_migrations::apply(db, hub_id).await.unwrap();
        // The boot path arms these right after the migrations (hub#666); a fixture that skipped
        // them would be testing a schema no hub ever has.
        crate::flows::store::ensure_indexes(db).await.unwrap();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Every error this kernel reports is namespaced `flow.…`, like a module's domain errors
    /// (hub#139): the module `flows` and the UI program against the CODE, and a code that drifts
    /// out of the namespace is one nobody can catch generically.
    #[test]
    fn every_error_code_lives_in_the_flow_namespace() {
        for code in [
            def::ERR_UNKNOWN_SCHEMA_VERSION,
            def::ERR_INVALID_DEFINITION,
            def::ERR_STEP_KIND_NOT_AVAILABLE,
            def::ERR_UNKNOWN_OPERATOR,
            def::ERR_SECRET_NOT_AVAILABLE,
            grants::ERR_GRANT_DENIED,
            grants::ERR_UNKNOWN_GRANT_KIND,
            store::ERR_FLOW_NOT_FOUND,
        ] {
            assert!(
                code.starts_with("flow."),
                "`{code}` must live in the `flow.` namespace"
            );
        }
    }
}
