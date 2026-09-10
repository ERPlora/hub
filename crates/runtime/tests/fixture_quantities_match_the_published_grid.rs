//! 🔴 **The ratchet that keeps this repo's fixture vocabulary calibrated against the catalogue it
//! is benched on** (hub#1772).
//!
//! ## The incident
//!
//! `inventory` v1.2.45 installed `ck_inventory_product_stock_on_grid` (migration 009,
//! inventory#42): every quantity written to the catalogue must sit on the grid its unit declares.
//! Fifteen fixtures of this repo still wrote `"stock": 10` — a raw count, not a quantity — so the
//! `e2e con módulos reales` job went red across **nine binaries and 54 tests**, all of them with
//! the same unreadable line:
//!
//! ```text
//! db: sqlx: error returned from database: new row for relation "inventory_product"
//! violates check constraint "ck_inventory_product_stock_on_grid" at line 2076
//! ```
//!
//! Nothing in that sentence says «you wrote a count where a quantity goes», and the only place to
//! read it was an Actions log. The job stayed red for eighteen hours.
//!
//! ## What this file guards, and why it is not a test of `inventory`
//!
//! [`erplora_runtime::e2e_support::QUANTITY_GRID`] is a number this repo believes about a module
//! it does not own. A believed number rots in silence: the day the catalogue moves its grid, every
//! fixture goes back to dying with a constraint name, and this file is the one thing that would
//! have to be wrong for that to happen quietly. So it asserts the BENCH's calibration, not
//! inventory's behaviour — the same shape, and the same reason, as
//! `money_columns_inventory.rs`, which checks the kernel's money inventory against the published
//! migrations rather than against a doc-comment.
//!
//! Both halves are here on purpose:
//!
//!   * a quantity built with [`units`] is ACCEPTED — without this, a checker that refused
//!     everything would pass the other half and disarm every fixture in the tree;
//!   * a value off the grid is REFUSED by the catalogue, and refused FIRST by
//!     [`on_grid`], in words. That second assertion is what makes the readable failure a contract
//!     instead of a courtesy.

use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_runtime::e2e_support::{on_grid, units, QUANTITY_GRID};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> erplora_db::Params {
    v.as_object().cloned().unwrap_or_default()
}

fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");
    rt.install_from_dir(&modules_root().join("inventory"))
        .await
        .expect("instalar inventory");
    rt
}

async fn create_with_stock(rt: &Runtime, sku: &str, stock: i64) -> Result<(), String> {
    rt.execute_command(
        "inventory.products.create",
        &params(json!({
            "name": sku, "sku": sku, "price": 450, "cost": 200,
            "stock": stock, "tax_category_key": "product.generic"
        })),
        &ctx(),
    )
    .await
    .map(|_| ())
    .map_err(|e| e.to_string())
}

/// The positive control. A grid that refused everything would make the test below pass while
/// checking nothing, and every fixture in this repo leans on `units()` producing something the
/// catalogue takes.
#[tokio::test]
async fn a_quantity_built_with_units_is_accepted_by_the_published_catalogue() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = fresh().await;

    create_with_stock(&rt, "ON-GRID", units(10))
        .await
        .expect("units(10) is a quantity the catalogue has to accept");
}

/// The ratchet itself: the catalogue still refuses what this repo's vocabulary calls off-grid. If
/// the published grid ever moves, THIS is what goes red — with a sentence — instead of fifty-four
/// tests dying on a constraint name.
#[tokio::test]
async fn a_value_off_the_grid_is_refused_by_the_published_catalogue() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = fresh().await;

    let off_grid = QUANTITY_GRID - 1;
    let refused = create_with_stock(&rt, "OFF-GRID", off_grid)
        .await
        .expect_err(
            "the catalogue accepted a quantity off the grid: either inventory retired its CHECK \
             or QUANTITY_GRID no longer matches it — the fixture vocabulary of this repo is stale",
        );

    assert!(
        refused.contains("stock_on_grid"),
        "refused for the wrong reason, so this test proves nothing about the grid: {refused}"
    );
}

/// And the point of the whole exercise: whatever the catalogue refuses, the bench refuses FIRST,
/// naming the value and the way out. A fixture never has to learn what `ck_…_on_grid` means.
#[test]
fn what_the_catalogue_refuses_the_bench_refuses_first_and_in_words() {
    let panic = std::panic::catch_unwind(|| on_grid(QUANTITY_GRID - 1))
        .expect_err("an off-grid value must not reach the database at all");
    let said = panic
        .downcast_ref::<String>()
        .map(String::as_str)
        .unwrap_or("<not a string>");

    assert!(
        said.contains("not on the grid"),
        "the bench has to say what is wrong, not echo the driver: {said}"
    );
}
