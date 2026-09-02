//! **hub#1086** — the declarative `list` engine bound an absent required parameter as NULL and
//! answered an empty page instead of failing.
//!
//! A bind the base SQL references (`WHERE cart_id = :cart_id`) can never be "optional": binding
//! NULL turns the equality into a filter that matches NOTHING, so the page returns `total: 0`
//! with full credibility — the movement WAS written, the query says it was not. That silent lie
//! cost QA a false diagnosis ("the sale→cash chain is broken") on 2026-08-21, reproduced on
//! `cart_checkout.items.list`, `cash_register.movements.list` and `cash_register.counts.list`.
//!
//! The distinction the fix draws (the issue's MATIZ):
//!
//!  * **Required** — a bind the base SQL references OUTSIDE a `COALESCE(<bind>, …)` wrapper.
//!    Absent or null → `MissingRequiredParam`, naming the parameter. Nothing runs.
//!  * **Optional** — a bind the module wrapped in `COALESCE(<…bind…>, default)`: the module
//!    HANDLED the null itself, in the SQL (the `services.services.list` `include_archived`
//!    idiom, services#44). Absent = the declared default scope, exactly as today.
//!
//! The engine's own vocabulary (`limit`, `offset`, `search`, `sort`, `dir`, `f_*` filters) is
//! optional by design: an absent filter means "no condition".
//!
//! Real Postgres, ephemeral schema per test.
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn fixture() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_listbind1086")
        .join("lbind")
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture())
        .await
        .expect("install lbind");
    rt
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// The red case of the issue: calling a list exactly as its own block documents it, but without
/// the context bind. Before the fix this returned `Ok` with an empty page (the lie); it must be
/// a LOUD error that names the missing parameter and the query.
#[tokio::test]
async fn missing_context_bind_is_a_loud_error_not_an_empty_page() {
    let rt = hub().await;
    let err = rt
        .execute_query("lbind.items.list", &Params::new(), &ctx())
        .await
        .expect_err("an absent :cart_id must fail loudly, not answer total: 0");
    match err {
        RuntimeError::MissingRequiredParam { query, param } => {
            assert_eq!(param, "cart_id", "the error names the missing parameter");
            assert_eq!(query, "lbind.items.list", "the error names the query");
        }
        other => panic!("expected MissingRequiredParam, got {other:?}"),
    }
}

/// No regression: the same list WITH its bind returns exactly its scope (rows, total, filters).
#[tokio::test]
async fn with_the_bind_the_list_returns_exactly_that_scope() {
    let rt = hub().await;
    let rows = rt
        .execute_query(
            "lbind.items.list",
            &params(json!({ "cart_id": "cart-a" })),
            &ctx(),
        )
        .await
        .expect("with the bind, the list works as always");
    assert_eq!(rows.len(), 3, "cart-a has three items: {rows:?}");
    assert!(rows.iter().all(|r| r["cart_id"] == json!("cart-a")));
}

/// The optional half: a bind the module wrapped in `COALESCE(:p, default)` is a declared
/// default, not an accident — absent must keep meaning "default scope" (services#44 idiom).
#[tokio::test]
async fn coalesce_wrapped_bind_stays_optional_with_its_default_scope() {
    let rt = hub().await;

    // Absent → default scope (only non-archived carts), and NO error.
    let active = rt
        .execute_query("lbind.carts.list", &Params::new(), &ctx())
        .await
        .expect("a COALESCE-guarded bind absent is the declared default, not a failure");
    assert_eq!(
        active.len(),
        2,
        "default scope hides the archived cart: {active:?}"
    );

    // Present → the declared wider scope.
    let all = rt
        .execute_query(
            "lbind.carts.list",
            &params(json!({ "include_archived": 1 })),
            &ctx(),
        )
        .await
        .expect("the optional bind accepts a value");
    assert_eq!(all.len(), 3, "include_archived=1 widens the scope: {all:?}");
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
