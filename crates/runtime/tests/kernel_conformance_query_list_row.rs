//! KCS · query / list engine / row contract.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! Three promises in one file, because they are one promise from a module's point of view: when a
//! module declares a `list` block it gets paging, sorting, search and filters for free; and every
//! row it writes is stamped by the KERNEL — `hub_id`, `current_user_id` and `now` come from the
//! request context and are NOT settable by whoever called. That last one is the tenancy boundary:
//! if a payload could name its own `hub_id`, every other guard in the hub would be decoration.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use kernel_fixture::{admin, ctx_with, install_fixture};
use serde_json::json;

async fn create(rt: &Runtime, ctx: &RequestContext, name: &str) -> serde_json::Value {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    rt.execute_command("kfx.item.create", &p, ctx)
        .await
        .unwrap_or_else(|e| panic!("create {name}: {e}"))
}

async fn seed(rt: &Runtime, names: &[&str]) {
    for name in names {
        create(rt, &admin(), name).await;
    }
}

fn names(rows: &[serde_json::Value]) -> Vec<String> {
    rows.iter()
        .map(|r| r["name"].as_str().unwrap().to_string())
        .collect()
}

/// A `list` block turns one SELECT into a paged read: the declared `page_size` is the default
/// window, and `total` counts the whole set behind it.
#[tokio::test]
async fn the_list_block_pages_sorts_and_reports_the_total_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;
    seed(&rt, &["c", "a", "b"]).await;

    let page = rt
        .execute_query_page("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("first page");
    assert_eq!(
        page.limit, 2,
        "the module's declared page_size is the window"
    );
    assert_eq!(
        page.total, 3,
        "the total counts the whole set, not the page"
    );
    assert_eq!(names(&page.rows), vec!["a", "b"], "default_sort name asc");

    let mut second = Params::new();
    second.insert("offset".into(), json!(2));
    let page = rt
        .execute_query_page("kfx.items.list", &second, &admin())
        .await
        .expect("second page");
    assert_eq!(names(&page.rows), vec!["c"]);

    let mut desc = Params::new();
    desc.insert("dir".into(), json!("desc"));
    let page = rt
        .execute_query_page("kfx.items.list", &desc, &admin())
        .await
        .expect("descending");
    assert_eq!(names(&page.rows), vec!["c", "b"]);
}

/// `execute_query` (no explicit `limit`) walks the WHOLE set, not one page — a `reads` block or a
/// guard that only saw the first page would have a hole in it.
#[tokio::test]
async fn a_whole_set_read_crosses_the_page_boundary_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;
    seed(&rt, &["a", "b", "c", "d", "e"]).await;

    let rows = rt
        .execute_query("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("whole set");
    assert_eq!(names(&rows), vec!["a", "b", "c", "d", "e"]);
}

/// Search and the declared `like` filter both narrow the set without the module writing a WHERE.
#[tokio::test]
async fn declared_search_and_filters_narrow_the_set_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;
    seed(&rt, &["apple", "apricot", "banana"]).await;

    let mut search = Params::new();
    search.insert("search".into(), json!("ap"));
    let rows = rt
        .execute_query("kfx.items.list", &search, &admin())
        .await
        .expect("search");
    assert_eq!(names(&rows), vec!["apple", "apricot"]);

    let mut filter = Params::new();
    filter.insert("f_name".into(), json!("ban"));
    let rows = rt
        .execute_query("kfx.items.list", &filter, &admin())
        .await
        .expect("filter");
    assert_eq!(names(&rows), vec!["banana"]);
}

/// 🔴 Proof the guard catches the positive: a param outside the query's vocabulary is refused
/// NAMING it, instead of buying a full page (hub#1173). An ignored filter is a caller working on
/// the whole table while believing it holds the twelve rows it asked for.
///
/// The engine's own `f_*` namespace is the documented exception and is pinned by
/// `unknown_list_param_e2e.rs`; hub#1182 carries closing it.
#[tokio::test]
async fn an_undeclared_param_is_refused_naming_it_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;
    seed(&rt, &["a", "b"]).await;

    let mut params = Params::new();
    params.insert("created_by".into(), json!("someone"));
    match rt
        .execute_query_page("kfx.items.list", &params, &admin())
        .await
        .expect_err("the query declares no `created_by` anything")
    {
        RuntimeError::UnknownFilter {
            query,
            param,
            accepted,
        } => {
            assert_eq!(query, "kfx.items.list");
            assert_eq!(param, "created_by", "the refusal names the offending param");
            assert!(
                accepted.iter().any(|a| a == "f_name"),
                "and lists what IS accepted, so the caller can fix it: {accepted:?}"
            );
        }
        other => panic!("expected the stable unknown-filter refusal, got {other:?}"),
    }
}

/// 🔑 THE ROW CONTRACT. `hub_id`, `current_user_id` and `now` are stamped by the kernel from the
/// request context; a payload that names them is overwritten, not honoured.
#[tokio::test]
async fn the_kernel_stamps_the_row_and_the_payload_cannot_forge_it_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let ctx = RequestContext::new("hub-of-record", "cashier-7", ["*".to_string()]);
    let mut payload = Params::new();
    payload.insert("name".into(), json!("a"));
    // What an attacker would send: somebody else's tenant and somebody else's name on the audit.
    payload.insert("hub_id".into(), json!("hub-of-the-victim"));
    payload.insert("current_user_id".into(), json!("the-owner"));
    rt.execute_command("kfx.item.create", &payload, &ctx)
        .await
        .expect("create");

    let row = rt
        .db_for_test()
        .query(
            "SELECT hub_id, created_by, created_at FROM kfx_item",
            &Params::new(),
        )
        .await
        .expect("read back")
        .rows
        .remove(0);
    assert_eq!(
        row["hub_id"],
        json!("hub-of-record"),
        "the tenant comes from the context, never from the payload"
    );
    assert_eq!(
        row["created_by"],
        json!("cashier-7"),
        "the audit names who actually called"
    );
    assert!(
        row["created_at"].as_str().is_some_and(|s| !s.is_empty()),
        "the kernel stamped `now`"
    );
}

/// Soft delete: the archived row leaves the module's list and stays in the table. The kernel does
/// not delete rows on a module's behalf — it gives it `:now` and the row keeps its history.
#[tokio::test]
async fn a_soft_deleted_row_leaves_the_list_and_stays_in_the_table_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;
    seed(&rt, &["a", "b"]).await;

    let id = rt
        .db_for_test()
        .query("SELECT id FROM kfx_item WHERE name = 'a'", &Params::new())
        .await
        .expect("read id")
        .rows
        .remove(0)["id"]
        .as_str()
        .unwrap()
        .to_string();

    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    rt.execute_command("kfx.item.archive", &p, &admin())
        .await
        .expect("archive");

    let rows = rt
        .execute_query("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("list");
    assert_eq!(
        names(&rows),
        vec!["b"],
        "the archived row is out of the list"
    );
    assert_eq!(
        rt.db_for_test()
            .query("SELECT id FROM kfx_item", &Params::new())
            .await
            .unwrap()
            .rows
            .len(),
        2,
        "and still in the table"
    );
}

/// A query is gated by its declared permission, flat — queries never offer elevation.
#[tokio::test]
async fn a_query_refuses_flat_without_its_permission_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let err = rt
        .execute_query("kfx.items.list", &Params::new(), &ctx_with(&["kfx.write"]))
        .await
        .expect_err("kfx.read is required");
    match err {
        RuntimeError::PermissionDenied(permission) => assert_eq!(permission, "kfx.read"),
        other => panic!("a query denies flat, it never offers a PIN dialog: {other:?}"),
    }
}
