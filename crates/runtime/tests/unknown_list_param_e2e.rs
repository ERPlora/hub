//! **hub#1173** — a filter a list query does NOT declare was ignored in silence: `200 ok` and the
//! WHOLE list back. The caller — a module, the assistant, an integration, a flow — believes it
//! filtered and works on 280 rows thinking it holds 12, and the answer is indistinguishable from a
//! filter that ran and matched nothing (only `total` tells them apart, and nobody reads `total`).
//!
//! Measured in production (hub `qa-pm149-…`, core v1.1.9): `inventory.products.list` with
//! `category_id` answered the entire catalogue; `tables.sessions.list` with `status: "active"`
//! answered the closed session too.
//!
//! # Why refusing, and not warning
//!
//! Sweep of the 27 module repos on `origin/main` (25/08/2026): 73 list queries, and exactly TWO
//! call sites in the whole catalogue send a parameter outside their query's vocabulary — and both
//! of them are this bug, live:
//!
//!   - `payments`: `erp-payments-list.ts` asks `payments.methods.list` for `{active_only: 1}`.
//!     `:active_only` exists only in a COMMENT of `queries/methods_list.sql`; the cashier is shown
//!     the payment methods the owner deactivated.
//!   - `sales`: `erp-pos-touch.ts` asks `services.services.list` for `{page_size: 500}` — the very
//!     param the SDK documents as "not a runtime parameter" in the module's OWN comment.
//!
//! So there is no legitimate caller a refusal would break: the only two casualties are two silent
//! bugs, and making them loud is the point. Both are fixed in their own repos alongside this.
//!
//! The asymmetry this closes is the trap named in the issue: command payloads are validated
//! strictly (`invalid_payload: Additional properties are not allowed`), query params were not.
//!
//! Real Postgres, ephemeral schema per test.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, RuntimeError, Runtime};
use serde_json::json;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_listbind1086")
        .join("lbind")
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.expect("install lbind");
    rt
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

fn params(pairs: &[(&str, serde_json::Value)]) -> Params {
    let mut p = Params::new();
    for (k, v) in pairs {
        p.insert((*k).into(), v.clone());
    }
    p
}

/// The acceptance case: a param the query never declared no longer buys a full page. This is the
/// shape the assistant, a flow or an integration writes — `{"status": "active"}` instead of
/// `{"f_status": "active"}` — and the one the QA of the issue sent by hand.
#[tokio::test]
async fn an_undeclared_param_is_refused_instead_of_ignored() {
    let rt = hub().await;

    let err = rt
        .execute_query_page(
            "lbind.items.list",
            &params(&[("cart_id", json!("cart-a")), ("category_id", json!("x"))]),
            &ctx(),
        )
        .await
        .expect_err("an undeclared filter must not answer the whole list");

    match err {
        RuntimeError::UnknownFilter { query, param, accepted } => {
            assert_eq!(query, "lbind.items.list");
            assert_eq!(param, "category_id", "the refusal names the offending param");
            assert!(
                accepted.iter().any(|a| a == "f_name"),
                "and lists what IS accepted, so the caller can fix it: {accepted:?}"
            );
        }
        other => panic!("expected the stable unknown-filter refusal, got {other:?}"),
    }
}

/// The OTHER half, pinned as it stands today: `f_*` is the engine's own namespace, and an
/// undeclared column inside it is still DROPPED, not refused.
///
/// Deliberate and measured, not an oversight. The SDK flattens `filters` to `f_<col>` whatever the
/// manifest says, so a column a screen's table declares `filterable` while its manifest declares no
/// filter for it arrives here correctly prefixed. That case EXISTS: the sweep of the 27 module
/// repos (`origin/main`, 25/08/2026) finds 5 such components, `inventory`'s product table among
/// them (`name`/`sku` are `search` columns, not `filters`). Refusing them here would turn "the
/// filter does nothing" into "the table breaks", which is not fixing it — what fixes it is
/// declaring the missing filter in those manifests (hub#1182 carries the measured list). Only then
/// can this door cover `f_*` too.
#[tokio::test]
async fn an_undeclared_column_inside_the_engine_prefix_is_still_dropped() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "lbind.items.list",
            &params(&[("cart_id", json!("cart-a")), ("f_price", json!(5))]),
            &ctx(),
        )
        .await
        .expect("`f_*` is the engine namespace: an unmatched filter is dropped, as it always was");
    assert_eq!(
        page.total, 3,
        "the documented hole, pinned: the page is the unfiltered scope (hub#1182): {:?}",
        page.rows
    );
}

/// Positive control — without it the two tests above pass for the wrong reason (everything
/// refused). A DECLARED filter still filters, and still returns the right rows.
#[tokio::test]
async fn a_declared_filter_still_filters() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "lbind.items.list",
            &params(&[("cart_id", json!("cart-a")), ("f_name", json!("croissant"))]),
            &ctx(),
        )
        .await
        .expect("the declared `name` LIKE filter must run");
    assert_eq!(page.total, 1, "one item matches: {:?}", page.rows);
}

/// Compat, pinned: the engine's own vocabulary and the binds the base SQL references pass through
/// untouched. `:cart_id` is a context bind the module's SQL names (hub#1086) — never a filter, and
/// refusing it would break every sub-list in the catalogue.
#[tokio::test]
async fn the_engine_vocabulary_and_the_sql_binds_still_pass() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "lbind.items.list",
            &params(&[
                ("cart_id", json!("cart-a")),
                ("limit", json!(2)),
                ("offset", json!(0)),
                ("search", json!("c")),
                ("sort", json!("name")),
                ("dir", json!("asc")),
            ]),
            &ctx(),
        )
        .await
        .expect("limit/offset/search/sort/dir + the SQL's own bind are the vocabulary");
    assert_eq!(page.limit, 2, "the `limit` the caller asked for is the one it gets");
    assert_eq!(page.rows.len(), 2, "one page of it: {:?}", page.rows);
    assert_eq!(
        page.total, 3,
        "search ran: coffee, croissant and orange juice carry a `c`; the sandwich of cart-b does \
         not count, the context bind scoped it out: {:?}",
        page.rows
    );
}

/// Compat, pinned: an optional bind the module guarded with COALESCE itself (the services#44
/// idiom) is part of its query's vocabulary — it is declared in the SQL, which is where a list
/// query declares its context binds.
#[tokio::test]
async fn a_coalesce_guarded_optional_bind_is_still_accepted() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "lbind.carts.list",
            &params(&[("include_archived", json!("1"))]),
            &ctx(),
        )
        .await
        .expect("`:include_archived` is referenced by the base SQL: it is vocabulary, not a filter");
    assert_eq!(page.total, 3, "archived cart included: {:?}", page.rows);
}

/// The FOURTH place a query declares something passable: its own JSON Schema. A property the
/// module wrote in `schemas/*.json` is a deliberate declaration — not the typo this guard exists
/// to catch — so it is vocabulary even when it is neither a filter nor a bind of the base SQL.
///
/// Zero queries in the published catalogue need it today (`customers.purchases` is the only list
/// with a schema, and its one property IS an SQL bind). It is here so the guard cannot surprise
/// the author who uses the door the manifest already offers.
#[tokio::test]
async fn a_param_the_query_schema_declares_is_vocabulary() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "lbind.items.scoped",
            &params(&[("cart_id", json!("cart-a")), ("audit_tag", json!("who-asked"))]),
            &ctx(),
        )
        .await
        .expect("`audit_tag` is declared in the query's own JSON Schema: it is vocabulary");
    assert_eq!(page.total, 3, "the scope still applies: {:?}", page.rows);
}

/// And the guard still bites on that same query: declaring a schema does not open the door to
/// everything — only to what the schema actually names.
#[tokio::test]
async fn a_query_with_a_schema_still_refuses_what_it_never_declared() {
    let rt = hub().await;

    let err = rt
        .execute_query_page(
            "lbind.items.scoped",
            &params(&[("cart_id", json!("cart-a")), ("category_id", json!("x"))]),
            &ctx(),
        )
        .await
        .expect_err("a schema that declares `audit_tag` does not declare `category_id`");
    match err {
        RuntimeError::UnknownFilter { param, .. } => assert_eq!(param, "category_id"),
        other => panic!("expected the stable unknown-filter refusal, got {other:?}"),
    }
}
