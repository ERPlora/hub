//! hub#2410 — **a `required` read that did not resolve says WHY.**
//!
//! `preload_reads` aborts a command with `ReadUnavailable` in three different situations: the app
//! that owns the read is not installed, it is switched off, or it is there and the query itself
//! failed (a transient database fault, a table it cannot reach). Before this, the error carried
//! only the query, so every screen told the cashier «the app “taxes” is missing, ask an
//! administrator to install it» — also when `taxes` was installed, active and the read had merely
//! failed. The owner went to Apps, found the app there, and had nothing to do.
//!
//! The cause travels as a stable `reason` next to the code; the sentence is chosen from it by the
//! SDK. Each test below builds one of the three situations against the REAL `taxes` + `sales`
//! modules — `sales.complete_sale` declares `taxes.rules.list` as `required` — and checks the
//! reason the kernel reports.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::errors::ReadUnavailableReason;
use erplora_runtime::{ModuleStatus, RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn mdir(name: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(name)
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn rt_pos() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    for m in ["taxes", "inventory", "customers", "sales"] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    rt
}

async fn charge(rt: &Runtime, key: &str) -> RuntimeError {
    let ctx = admin();
    let cash = rt
        .execute_query("sales.payment_methods", &Params::new(), &ctx)
        .await
        .expect("sales.payment_methods")
        .into_iter()
        .find(|r| r["type"] == json!("cash"))
        .expect("the seeded catalogue carries the cash method");
    let payload = json!({
        "idempotency_key": key,
        "payment_method_id": cash["id"],
        "items": [{ "product_name": "X", "price": 1000, "quantity": 1_000_000, "tax_rate": 21.0 }],
        "tax_included": true,
        "amount_tendered": 1000,
        "payment_method_name": "Cash"
    });
    rt.execute_command(
        "sales.complete_sale",
        payload.as_object().expect("object"),
        &ctx,
    )
    .await
    .expect_err("a required read that does not resolve must abort the sale")
}

fn reason_of(e: &RuntimeError) -> ReadUnavailableReason {
    match e {
        RuntimeError::ReadUnavailable { query, reason } => {
            assert_eq!(query, "taxes.rules.list");
            *reason
        }
        other => panic!("expected read_unavailable, got {other:?}"),
    }
}

/// The case the issue is about: `taxes` installed and active, the read itself fails.
#[tokio::test]
async fn a_failing_query_of_an_installed_active_app_is_reported_as_query_failed() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = rt_pos().await;
    rt.db()
        .execute_batch("ALTER TABLE taxes_rule RENAME TO taxes_rule_gone")
        .await
        .expect("make the tax rules unreachable");

    let e = charge(&rt, "hub2410-query-failed").await;
    assert_eq!(reason_of(&e), ReadUnavailableReason::QueryFailed);
    assert_eq!(ReadUnavailableReason::QueryFailed.code(), "query_failed");
}

/// The owner is switched off in this task's registry (another task recorded it, hub#2039).
#[tokio::test]
async fn an_inactive_owner_is_reported_as_module_inactive() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut rt = rt_pos().await;
    assert!(rt.adopt_recorded_status("taxes", ModuleStatus::Inactive));

    let e = charge(&rt, "hub2410-inactive").await;
    assert_eq!(reason_of(&e), ReadUnavailableReason::ModuleInactive);
    assert_eq!(
        ReadUnavailableReason::ModuleInactive.code(),
        "module_inactive"
    );
}

/// The owner is gone from this task's registry (another task uninstalled it, hub#2039).
#[tokio::test]
async fn an_absent_owner_is_reported_as_module_not_installed() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut rt = rt_pos().await;
    assert!(rt.forget_uninstalled_elsewhere("taxes"));

    let e = charge(&rt, "hub2410-absent").await;
    assert_eq!(reason_of(&e), ReadUnavailableReason::ModuleNotInstalled);
    assert_eq!(
        ReadUnavailableReason::ModuleNotInstalled.code(),
        "module_not_installed"
    );
}
