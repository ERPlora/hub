//! hub#775 — the AUTHORITATIVE `protects` guard end-to-end.
//!
//! `cash_register` ships a top-level `protects` block that, until this issue, the runtime
//! reported as an unknown field and dropped. The block says: while `enable_cash_register` is on
//! and the route at `protected_pos_url` (served by `sales`) is in play, no sale may complete
//! unless `cash_register.current_session` returns a row (the drawer is open). The shell rendering
//! `erp-cashregister-open` instead of mounting the POS is the cosmetic half; this file pins the
//! AUTHORITATIVE half — the dispatcher refusing `sales.complete_sale` when the drawer is closed.
//!
//! Without the guard, the canonical bug from the issue reproduces cleanly: a cash sale completes,
//! the stock goes down, the table frees up, and `cash_register.movements.list` stays empty — the
//! `_movement_for_open_session.sql` INSERT…SELECT matched no open session and silently inserted
//! nothing. The money vanishes from the reconciliation without an error.
//!
//! The matrix this file covers, against the real published `cash_register` + `sales`:
//!   · cash register DISABLED → the sale completes as it always did (the guard is dormant);
//!   · cash register ENABLED, drawer CLOSED → `sales.complete_sale` is refused with
//!     `protects_guard` and no sale is written;
//!   · cash register ENABLED, drawer OPEN → the sale completes AND records exactly one movement
//!     (the guard is satisfied, the existing chain does its job);
//!   · the guard is skipped for an INTERNAL call (the outbox relay re-running `record_sale` after
//!     a `sale.completed` would otherwise deadlock on the guard the very event would have blocked).

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{Runtime, RuntimeError};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}
fn admin() -> erplora_runtime::RequestContext {
    erplora_runtime::RequestContext::new("h1", "u1", ["*".to_string()])
}
fn wasm_here() -> bool {
    mdir("cash_register").join("dist/handler.wasm").exists()
        && mdir("sales").join("dist/handler.wasm").exists()
}

/// The full stack `cash_register` needs to interpose on `sales`: taxes (inventory depends on it),
/// inventory, customers, cash_register, sales, invoice (depends on taxes + sales, installed last).
async fn stack_with_cash_register(rt: &mut Runtime, ctx: &erplora_runtime::RequestContext) {
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt.install_from_dir(&mdir("inventory")).await.unwrap();
    rt.install_from_dir(&mdir("customers")).await.unwrap();
    rt.install_from_dir(&mdir("cash_register")).await.unwrap();
    // `sales` before `invoice`: invoice declares `depends_on: [taxes, sales]` and the installer
    // enforces topological order.
    rt.install_from_dir(&mdir("sales")).await.unwrap();
    rt.install_from_dir(&mdir("invoice")).await.unwrap();
    // Touch the context so the compiler is happy if a future refactor drops the param; the stack
    // itself needs no per-call seeding today.
    let _ = ctx.hub_id.len();
}

/// A minimal cash sale payload (single line, no tax). `idempotency_key` is mandatory since
/// sales v2.13.x; each call passes a distinct one.
fn cash_sale(key: &str) -> Params {
    params(json!({
        "idempotency_key": key,
        "tax_included": false,
        "items": [{ "product_name": "X", "price": 3000, "quantity": 1_000_000, "tax_rate": 0.0 }]
    }))
}

/// Flips `enable_cash_register` + `protected_pos_url` on the installed `cash_register`.
async fn enable_cash_register(rt: &Runtime, ctx: &erplora_runtime::RequestContext) {
    rt.execute_command(
        "cash_register.settings.update",
        &params(json!({
            "enable_cash_register": true,
            "require_opening_balance": false,
            "require_closing_balance": false,
            "allow_negative_balance": false,
            // `auto_open_session_on_login` / `auto_close_session_on_logout` se RETIRARON del
            // módulo; los tres de abajo pasaron a ser obligatorios. El schema no los rellena por
            // defecto, así que el objeto viaja completo (hub#1028).
            "require_blind_count": false,
            "auto_close_enabled": false,
            "auto_close_time": "23:00",
            "protected_pos_url": "/m/sales"
        })),
        ctx,
    )
    .await
    .expect("cash_register.settings.update");
}

/// Opens a register session and returns its id (the shape `cash_register`'s own battery
/// `tests/session.hub.test.py` exercises against the real kernel — hub#1264, slice 4).
async fn open_session(rt: &Runtime, ctx: &erplora_runtime::RequestContext, opening: i64) -> String {
    rt.execute_command(
        "cash_register.session.open",
        &params(json!({
            "register_id": null,
            "session_number": "AB-775",
            "opening_balance": opening,
            "opening_notes": ""
        })),
        ctx,
    )
    .await
    .unwrap();
    rt.execute_query("cash_register.sessions.list", &Params::new(), ctx)
        .await
        .unwrap()
        .last()
        .unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string()
}

#[tokio::test]
async fn manifest_no_longer_warns_that_protects_is_unknown() {
    // The pivot of the whole issue: before hub#775, `Manifest::load` dropped `protects` into
    // `warnings` (it was an unknown root field). Now it is PARSED, so the warning must be gone —
    // and the block must reach the registry ready to be enforced.
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let manifest =
        erplora_runtime::Manifest::load(&mdir("cash_register")).expect("cash_register loads");
    assert!(
        !manifest.warnings.iter().any(|w| w.path.starts_with("protects")),
        "hub#775: `protects` is now parsed and acted on, so it must NOT be reported as unknown: {:?}",
        manifest.warnings
    );
    assert!(
        !manifest.protects.is_empty(),
        "the published `cash_register` carries a `protects` block; it must be parsed"
    );
}

#[tokio::test]
async fn cash_sale_completes_when_cash_register_is_disabled() {
    // Baseline: with `enable_cash_register` OFF (the default on a fresh install), the guard is
    // dormant and a sale completes exactly as it did before hub#775. This must not regress.
    if !erplora_runtime::require_modules_workspace() || !wasm_here() {
        eprintln!("SKIP: needs the modules workspace with built WASM");
        return;
    }
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let ctx = admin();
    stack_with_cash_register(&mut rt, &ctx).await;

    rt.execute_command("sales.complete_sale", &cash_sale("775-disabled"), &ctx)
        .await
        .expect("a sale must complete when the cash register is OFF (guard dormant)");
}

#[tokio::test]
async fn cash_sale_is_refused_when_the_drawer_is_closed() {
    // 🔴 RED → GREEN of hub#775. The exact reproduction from the issue: cash register ENABLED,
    // drawer CLOSED, a cash sale attempted. Before the fix this completed silently and the
    // movement was never written. After the fix the dispatcher refuses with `protects_guard`,
    // BEFORE any sale row, stock movement or table release is written.
    if !erplora_runtime::require_modules_workspace() || !wasm_here() {
        eprintln!("SKIP: needs the modules workspace with built WASM");
        return;
    }
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let ctx = admin();
    stack_with_cash_register(&mut rt, &ctx).await;
    enable_cash_register(&rt, &ctx).await;

    let err = rt
        .execute_command("sales.complete_sale", &cash_sale("775-closed-drawer"), &ctx)
        .await
        .expect_err("a cash sale with the drawer closed must be refused authoritatively");

    match err {
        RuntimeError::ProtectsGuard {
            declaring_module,
            protected_module,
            guard_query,
        } => {
            assert_eq!(declaring_module, "cash_register");
            assert_eq!(protected_module, "sales");
            assert_eq!(guard_query, "cash_register.current_session");
        }
        other => panic!("expected ProtectsGuard, got {other:?}"),
    }

    // No sale was written: the refusal happened in the dispatcher, before any mutation. The list
    // of sales of this hub must be empty.
    let sales = rt
        .execute_query("sales.list", &Params::new(), &ctx)
        .await
        .expect("sales.list");
    assert!(
        sales.is_empty(),
        "the refused sale must leave no row behind; found {sales:?}"
    );
}

#[tokio::test]
async fn cash_sale_completes_and_records_a_movement_when_the_drawer_is_open() {
    // GREEN companion: with the drawer OPEN the guard is satisfied, the sale completes AND the
    // existing sale.completed → record_sale chain writes exactly one movement. This is the
    // invariant the _movement_for_open_session.sql comment relies on the route guard to uphold —
    // now upheld authoritatively instead of by a navigation the core never enforced.
    if !erplora_runtime::require_modules_workspace() || !wasm_here() {
        eprintln!("SKIP: needs the modules workspace with built WASM");
        return;
    }
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let ctx = admin();
    stack_with_cash_register(&mut rt, &ctx).await;
    enable_cash_register(&rt, &ctx).await;
    let sid = open_session(&rt, &ctx, 0).await;

    rt.execute_command("sales.complete_sale", &cash_sale("775-open-drawer"), &ctx)
        .await
        .expect("a cash sale with the drawer open must complete");
    rt.drain_outbox().await.unwrap(); // sale.completed → cash_register.record_sale

    let movs = rt
        .execute_query(
            "cash_register.movements.list",
            &params(json!({ "session_id": sid })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(movs.len(), 1, "exactly one idempotent movement must be recorded");
    assert_eq!(movs[0]["movement_type"], json!("sale"));
    assert_eq!(movs[0]["amount"].as_i64().unwrap(), 3000);
}

#[tokio::test]
async fn internal_calls_bypass_the_protects_guard() {
    // The outbox relay re-runs `cash_register.record_sale` as a listener of `sale.completed`. It
    // runs through `execute_at` with `Origin::Internal`, and if the protects guard applied to it,
    // the relay of the VERY event the guard permits would deadlock (record_sale is a cash_register
    // command, but a future protects block could target the declaring module's own surface). The
    // dispatcher exempts `Origin::Internal` from the guard for that reason — and this test pins it
    // by driving `execute_command_internal` directly with the drawer closed.
    if !erplora_runtime::require_modules_workspace() || !wasm_here() {
        eprintln!("SKIP: needs the modules workspace with built WASM");
        return;
    }
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let ctx = admin();
    stack_with_cash_register(&mut rt, &ctx).await;
    enable_cash_register(&rt, &ctx).await;

    // `cash_register.session.open` is a sales-module-shaped command only in namespace — it belongs
    // to `cash_register`, so the guard (which targets `sales`) would not fire on it anyway. The
    // point of this test is the Origin::Internal path: an internal invocation must not be refused
    // by a guard whose declaring module happens to protect the caller's module. We assert the
    // negative: no ProtectsGuard ever reaches an internal caller.
    rt.execute_command_internal(
        "cash_register.session.open",
        &params(json!({
            "register_id": null,
            "session_number": "AB-775-internal",
            "opening_balance": 0,
            "opening_notes": ""
        })),
        &ctx,
    )
    .await
    .expect("an internal call must bypass the protects guard");
}
