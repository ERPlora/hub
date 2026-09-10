//! **What this hub can be asked to do** (hub#1757) — `GET /api/hub/operations`.
//!
//! `POST /api/command` and `POST /api/query` take a `name`, and nothing on a running hub said which
//! names exist. They are module-specific — they live in each installed `module.json` — so anybody
//! outside the module's source had to guess, and guessing answers `404`. The three surfaces that
//! looked like they covered this do not:
//!
//! - `contracts/kernel/routes.snapshot` freezes the HTTP routes, not the dispatch names;
//! - the Postman collection ships `POST /api/command` with an empty `{{command}}` variable;
//! - [`crate::openapi`] covers ONLY what a module opted into with `expose_api` — the third-party
//!   REST door of ADR-0057 — and answers `404` while `api_docs_enabled` is off, which is its
//!   default. Read that spec and the operations the shell itself calls are simply not in it.
//!
//! So this is the dispatcher's own contract, read off the same [`Registry`] the dispatcher reads:
//! the exact name, the permission it checks, and the payload shape it validates against.
//!
//! **It never announces what the dispatcher would refuse.** That is the rule
//! [`Registry::exposed_commands`] already applies to the OpenAPI generator, and it is why an
//! internal command (hub#131/hub#145) and a deactivated module's operations are absent: a catalogue
//! that lists a name the dispatcher answers `403 internal_command` to is worse than no catalogue,
//! because it hands a reader a name to try and a reason to distrust the rest.
//!
//! **Not filtered by the caller's permissions**, on purpose: this is the hub's contract, not the
//! caller's menu. Each entry carries the permission it needs so a `403` can be read as «this
//! session lacks that», and the door below is the admin one — the whole map is not a cashier's.
use axum::extract::{Query, State};
use axum::http::HeaderMap;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Map, Value};

use erplora_runtime::manifest::{FilterOp, ListSpec};
use erplora_runtime::registry::CompiledSchema;
use erplora_runtime::Registry;

use crate::auth;
use crate::state::AppState;

/// The `module` a core query belongs to. The core is not a module, and the assistant's tool
/// catalogue already marks its own with the same string — one spelling of "the hub itself".
const CORE: &str = "hub";

#[derive(Deserialize)]
pub(crate) struct CatalogQuery {
    /// Narrow to one module (`?module=sales`, `?module=hub` for the core namespace). A hub runs 27
    /// modules; testing one of them should not mean reading all of them.
    module: Option<String>,
}

/// GET /api/hub/operations — every operation this hub's dispatcher accepts, by exact name.
///
/// **Two gates, the same two as `/api/hub/events`** (ADR-0312), and neither replaces the other.
/// First the human: an owner/admin session, so an anonymous caller gets `401` and a cashier `403`.
/// Then the module: if the request names one, that module needs `manage_flows` declared by its
/// manifest and granted by the owner.
///
/// The capability is not decoration. This is the map of every write command in the hub with the
/// payload each one takes, and [`crate::flows_api::require_module_capability`] is the gate that
/// stops an installed module reading it just because an administrator happens to be logged in —
/// the same escalation the flows door was gated against. `manage_flows` is the capability that
/// already means «the owner chose THIS module as the tool they administer the hub with», which is
/// exactly who has business reading the catalogue. A request that names no module — the shell,
/// `curl` with an admin session, the QA agent — passes on the session alone.
pub(crate) async fn list_operations(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<CatalogQuery>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(arc) => arc,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    // `auth_rejected`, not `unauthorized`: the two refusals are different facts and a caller acts
    // on them differently. An anonymous request gets `401` («log in»); a cashier's session gets
    // `403` («you are logged in, this is not yours») — collapsing both into `401` would send the
    // shell to the login screen a cashier has already passed.
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return crate::auth_rejected(e);
    }
    if let Err(response) = crate::flows_api::require_flows_capability(&headers, &rt).await {
        return response;
    }
    let only = q.module.as_deref().map(str::trim).filter(|m| !m.is_empty());
    Json(json!({ "ok": true, "data": build_catalog(rt.registry(), only) })).into_response()
}

/// The catalogue itself, sorted by name so two reads of an unchanged hub are the same document.
///
/// `only` narrows to one module id (or `hub` for the core namespace); a module this hub does not
/// have yields an empty list rather than an error, because «what does `payroll` expose here?» has
/// a true answer on a hub without `payroll`, and it is "nothing".
fn build_catalog(reg: &Registry, only: Option<&str>) -> Vec<Value> {
    let wanted = |module: &str| only.is_none_or(|m| m == module);
    let mut entries: Vec<Value> = Vec::new();

    // The reserved `hub.*` namespace (ADR-0192): served by the runtime, declared by no module, so
    // no manifest can reveal it. Its permission comes from the very function the dispatcher gates
    // with (`core_query_permission`), never from a second copy of the rule here.
    if wanted(CORE) {
        for rest in erplora_runtime::hub_users::CORE_QUERIES {
            entries.push(json!({
                "name": format!("{}{rest}", erplora_runtime::hub_users::CORE_NAMESPACE),
                "kind": "query",
                "module": CORE,
                "permission": erplora_runtime::hub_users::core_query_permission(rest),
                // The core namespace is not part of the third-party REST door (ADR-0057): it is
                // reached through `/api/query` only.
                "expose_api": false,
                "payload": Value::Null,
                "list": Value::Null,
            }));
        }
    }

    for module in &reg.installed {
        // A module the owner switched off answers `module_inactive` at the dispatcher. Offering
        // its operations would be offering a `404`.
        if !reg.is_active(&module.id) || !wanted(&module.id) {
            continue;
        }
        for (name, q) in reg.queries.iter().filter(|(_, q)| q.module_id == module.id) {
            entries.push(json!({
                "name": name,
                "kind": "query",
                "module": module.id,
                "permission": q.def.permission,
                "expose_api": q.def.expose_api,
                "payload": schema_of(q.schema.as_ref()),
                "list": q.def.list.as_ref().map(list_shape).unwrap_or(Value::Null),
            }));
        }
        for (name, c) in reg.commands.iter().filter(|(_, c)| c.module_id == module.id) {
            // Internal (hub#131 the `_` convention, hub#145 the explicit flag): only the runtime
            // itself invokes it, so publishing its name and payload would undo what those closed.
            if c.def.is_internal(name) {
                continue;
            }
            entries.push(json!({
                "name": name,
                "kind": "command",
                "module": module.id,
                "permission": c.def.permission,
                "expose_api": c.def.expose_api,
                "payload": schema_of(c.schema.as_ref()),
                "list": Value::Null,
            }));
        }
    }

    entries.sort_by(|a, b| a["name"].as_str().cmp(&b["name"].as_str()));
    entries
}

/// The payload's JSON Schema, raw, exactly as the module wrote it and the validator compiled it —
/// the same `raw` the OpenAPI generator hands to `requestBody`. `null` when the operation declares
/// none, said explicitly rather than by omitting the key: `payload: null` reads as «it takes
/// nothing», a missing key reads as «look somewhere else».
fn schema_of(schema: Option<&CompiledSchema>) -> Value {
    schema.map(|s| (*s.raw).clone()).unwrap_or(Value::Null)
}

/// What a list query can be searched, sorted, filtered and paged by — the half of its payload that
/// is not in a JSON Schema, because the runtime composes it (`queries.rs`) instead of validating it.
fn list_shape(list: &ListSpec) -> Value {
    let mut filters = Map::new();
    for (col, spec) in &list.filters {
        filters.insert(
            col.clone(),
            json!(match spec.op {
                FilterOp::Eq => "eq",
                FilterOp::Like => "like",
                FilterOp::Range => "range",
            }),
        );
    }
    json!({
        "search": list.search,
        "sort": list.sort,
        "default_sort": list.default_sort,
        "default_dir": list.default_dir,
        "filters": Value::Object(filters),
        "page_size": list.page_size,
    })
}
