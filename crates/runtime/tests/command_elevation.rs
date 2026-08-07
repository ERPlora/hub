//! hub#360 (paso 2b, 1/4) — a denial a MANAGER could approve is distinguishable at the dispatcher.
//!
//! Rule 1 of the PIN-elevation design: the dispatcher must not answer a flat `permission_denied`
//! to everything. If the missing permission is one a **manager** holds, the caller gets
//! `requires_elevation` **naming that permission**, so the UI knows whether to offer the approval
//! dialog or a plain error. Rule 5 draws the line: only the `manager` level is elevable —
//! `admin` territory (fiscal identity, plan, deletion, installing apps) is never approved by PIN,
//! the owner signs in with their own account.
//!
//! Three properties are load-bearing, and this file exists to make each of them impossible to
//! lose. **Elevation is a LABEL on a refusal, never a permit**: this issue adds no way to get in,
//! only a better-typed way to be kept out (the PIN itself is hub#361). **A manifest cannot mint
//! elevability**: the offer is derived from what the OWNING module grants verbatim to `manager`,
//! so no third-party `module.zip` can make somebody else's — or the core's — permission
//! manager-approvable, and a `"*"` grant buys nothing. **The client decides nothing**: the whole
//! decision is taken from the registry and the request context, never from the payload.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn module_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_elevation")
}

/// A hub with the `till` fixture installed: `manager` holds `till.take_payment`, `employee` does
/// not, and `till.manage_settings` is granted to nobody but `admin` (through its `"*"`).
async fn fresh_runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&module_dir())
        .await
        .expect("till installs");
    rt
}

/// Installs an extra module from an inline manifest (used for the hostile ones).
async fn install_manifest(rt: &mut Runtime, manifest: &str) {
    let dir = std::env::temp_dir().join(format!("erplora-elevation-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    rt.install_from_dir(&dir)
        .await
        .expect("the extra module installs");
    std::fs::remove_dir_all(dir).unwrap();
}

/// The cashier: everything `employee` is granted, and not a permission more.
fn cashier() -> RequestContext {
    RequestContext::new(
        "h1",
        "u-cashier",
        ["till.view_sale".to_string(), "till.add_sale".to_string()],
    )
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u-owner", ["*".to_string()])
}

async fn sales_count(rt: &Runtime) -> usize {
    rt.execute_query("till.sales.list", &Params::new(), &admin())
        .await
        .expect("the admin may always read")
        .len()
}

// ─────────────────────────────────────────────────────────────────────────────
// Rule 1 — the refusal is distinguishable, and names the permission
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_manager_level_refusal_asks_for_elevation_and_names_the_permission() {
    let rt = fresh_runtime().await;

    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &params(json!({ "label": "table 4" })),
            &cashier(),
        )
        .await
        .expect_err("a cashier does not take payment on their own");

    // The permission travels as a FIELD, not buried in a free-text message: the dialog of
    // hub#363 has to name what it is asking approval for, and hub#361 has to re-check exactly
    // that permission — neither may parse a sentence.
    assert!(
        matches!(&err, RuntimeError::RequiresElevation { permission } if permission == "till.take_payment"),
        "got {err:?}"
    );
}

#[tokio::test]
async fn the_stable_code_is_requires_elevation_and_it_is_an_expected_user_error() {
    use erplora_runtime::error_registry::{error_code_of, severity_of};
    let err = RuntimeError::RequiresElevation {
        permission: "till.take_payment".into(),
    };
    // A cashier asking for something a manager approves is the system working, not a Hub bug:
    // it must never raise an issue in the error registry.
    assert_eq!(error_code_of(&err), "requires_elevation");
    assert_eq!(severity_of(&err), "user");
}

// ─────────────────────────────────────────────────────────────────────────────
// Elevation is a LABEL on a refusal — never a permit
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn asking_for_elevation_is_still_a_refusal_and_writes_nothing() {
    let rt = fresh_runtime().await;

    for _ in 0..3 {
        rt.execute_command(
            "till.sale.take_payment",
            &params(json!({ "label": "table 4" })),
            &cashier(),
        )
        .await
        .expect_err("still refused");
    }

    // The whole point: hub#360 makes the "no" better typed, it does not make it a "yes".
    assert_eq!(
        sales_count(&rt).await,
        0,
        "a refusal that asks for elevation must not have executed the command"
    );
}

#[tokio::test]
async fn the_caller_cannot_switch_the_requirement_off_from_the_payload() {
    let rt = fresh_runtime().await;

    // Everything a hostile client might try to smuggle in. The decision is taken from the
    // registry and the context — the payload is data, never authority.
    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &params(json!({
                "label": "table 4",
                "requires_elevation": false,
                "elevated": true,
                "elevation": { "approved": true, "pin": "1234" },
                "approved_by": "u-manager",
                "permissions": ["*"],
                "role": "admin"
            })),
            &cashier(),
        )
        .await
        .expect_err("a payload never grants a permission");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { permission } if permission == "till.take_payment"),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0, "nothing ran");
}

// ─────────────────────────────────────────────────────────────────────────────
// Rule 5 — only the `manager` level is elevable
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn an_admin_only_permission_is_never_elevable() {
    let rt = fresh_runtime().await;

    // `till.manage_settings` reaches `admin` only through its `"*"`; no `manager` grant names it.
    let err = rt
        .execute_command(
            "till.settings.save",
            &params(json!({ "label": "x" })),
            &cashier(),
        )
        .await
        .expect_err("administering the till is not approved by PIN");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "till.manage_settings"),
        "an admin permission must stay a flat refusal, got {err:?}"
    );
}

#[tokio::test]
async fn a_permission_granted_only_to_a_declared_role_is_not_elevable() {
    let mut rt = fresh_runtime().await;
    // `chef` is a role the module invented. It is not `manager`, so there is no manager to
    // approve on its behalf: the refusal stays flat.
    install_manifest(
        &mut rt,
        r#"{"id":"kds","name":"KDS","version":"1.0.0",
            "roles":[{"key":"chef","label":"Chef","extends":"employee"}],
            "role_permissions":{"chef":["kds.purge_tickets"]},
            "commands":{"kds.tickets.purge":{"permission":"kds.purge_tickets",
              "transaction":true,"sql":[]}}}"#,
    )
    .await;

    let err = rt
        .execute_command("kds.tickets.purge", &Params::new(), &cashier())
        .await
        .expect_err("the cashier has no such permission");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "kds.purge_tickets"),
        "only the `manager` level is elevable, got {err:?}"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// A manifest cannot mint elevability (the lesson of hub#351, applied here)
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_wildcard_grant_to_manager_makes_nothing_elevable() {
    let mut rt = fresh_runtime().await;
    // The most generous grant a manifest can write against the `manager` key. If `"*"` counted,
    // ANY module could make every permission in the hub — including the admin ones — approvable
    // by a four-digit PIN. It counts for nothing.
    install_manifest(
        &mut rt,
        r#"{"id":"greedy","name":"Greedy","version":"1.0.0",
            "role_permissions":{"manager":["*"]}}"#,
    )
    .await;

    let err = rt
        .execute_command(
            "till.settings.save",
            &params(json!({ "label": "x" })),
            &cashier(),
        )
        .await
        .expect_err("still refused");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "till.manage_settings"),
        "a `\"*\"` grant to `manager` must not make an admin permission elevable, got {err:?}"
    );
}

#[tokio::test]
async fn a_module_cannot_make_another_modules_permission_elevable() {
    let mut rt = fresh_runtime().await;
    // A module nobody reviewed, naming somebody else's permissions verbatim: the till's admin
    // one and a CORE one. Elevability is owned by the module the permission belongs to.
    install_manifest(
        &mut rt,
        r#"{"id":"rogue","name":"Rogue","version":"1.0.0",
            "role_permissions":{"manager":["till.manage_settings","hub.users.view"]}}"#,
    )
    .await;

    let err = rt
        .execute_command(
            "till.settings.save",
            &params(json!({ "label": "x" })),
            &cashier(),
        )
        .await
        .expect_err("still refused");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "till.manage_settings"),
        "a third-party manifest must not make another module's permission elevable, got {err:?}"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// What must NOT change
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_command_the_caller_may_run_is_untouched() {
    let rt = fresh_runtime().await;

    rt.execute_command(
        "till.sale.create",
        &params(json!({ "label": "table 4" })),
        &cashier(),
    )
    .await
    .expect("the cashier opens the ticket as before");

    assert_eq!(sales_count(&rt).await, 1);
}

#[tokio::test]
async fn an_administrator_never_sees_the_elevation_error() {
    let rt = fresh_runtime().await;

    rt.execute_command(
        "till.sale.take_payment",
        &params(json!({ "label": "table 4" })),
        &admin(),
    )
    .await
    .expect("the wildcard holds every permission");

    assert_eq!(sales_count(&rt).await, 1);
}

#[tokio::test]
async fn a_query_is_refused_flat_even_when_a_manager_could_read_it() {
    let rt = fresh_runtime().await;

    // `till.reports.revenue` is gated by `till.take_payment` — a manager-level permission. A READ
    // is still refused flat on purpose: elevation exists to attribute an ACTION to the manager
    // who approved it (rule 3, `created_by`/`approved_by`). A PIN that unlocks a report leaves no
    // such trace and would turn the manager's PIN into a see-everything key.
    let err = rt
        .execute_query("till.reports.revenue", &Params::new(), &cashier())
        .await
        .expect_err("the cashier may not read the revenue report");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "till.take_payment"),
        "queries never offer elevation, got {err:?}"
    );
}

#[tokio::test]
async fn an_internal_command_is_refused_before_elevation_is_even_considered() {
    let rt = fresh_runtime().await;

    // `till._settle` is internal (leading `_`) AND gated by a manager-level permission. The
    // origin gate runs first: an internal command is invisible from outside, and answering
    // `requires_elevation` would advertise a door the PIN dialog can never open.
    let err = rt
        .execute_command("till._settle", &params(json!({ "label": "x" })), &cashier())
        .await
        .expect_err("an internal command is not callable from outside");

    assert!(
        matches!(&err, RuntimeError::InternalCommand(c) if c == "till._settle"),
        "got {err:?}"
    );
}
