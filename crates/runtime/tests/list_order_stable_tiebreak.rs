//! **A row jumped when you touched it, and paging repeated or lost rows** (hub#2352).
//!
//! The list engine emitted `ORDER BY sub.<col> <dir> NULLS LAST` and nothing else. When many rows
//! share the value they are sorted by (a status, a priority, an empty due date), Postgres hands the
//! ties back in whatever order it scanned them — and an `UPDATE` rewrites the row at the end of the
//! heap. So starting or editing a task moved it to the bottom of its group although the column the
//! list is sorted by never changed; and with `LIMIT/OFFSET` over an order that is not total, two
//! consecutive pages could share a row or skip one. The same paging feeds the whole-set reads of a
//! command (`reads`, `guard_query`), where a repeated or missing row is a wrong answer, not a glitch.
//!
//! The contract pinned here is the one Odoo (`id` appended to every `_order`) and every cursor-paged
//! API follow: **the row id breaks every tie**, in the direction the list is sorted, so the order is
//! total and does not depend on where the database keeps the row.
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;
use std::path::PathBuf;

const HUB: &str = "hub-2352";

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_list_tiebreak")
}

fn ctx() -> RequestContext {
    RequestContext::new(HUB, "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Six open tasks (`t1`…`t6`, created in that order) and one done task, `t7`.
async fn board() -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.install_from_dir(&fixture())
        .await
        .expect("install the fixture");
    for n in 1..=7 {
        let status = if n == 7 { "done" } else { "open" };
        rt.execute_command(
            "tiebreak.tasks.create",
            &params(
                json!({ "id": format!("t{n}"), "title": format!("Task {n}"), "status": status }),
            ),
            &ctx(),
        )
        .await
        .unwrap_or_else(|e| panic!("create t{n}: {e}"));
    }
    rt
}

/// Edits a column the list is NOT sorted by — the row's place must not change.
async fn touch(rt: &Runtime, id: &str) {
    rt.execute_command(
        "tiebreak.tasks.touch",
        &params(json!({ "id": id, "note": "started" })),
        &ctx(),
    )
    .await
    .unwrap_or_else(|e| panic!("touch {id}: {e}"));
}

async fn ids(rt: &Runtime, query: &str, p: serde_json::Value, key: &str) -> Vec<String> {
    let page = rt
        .execute_query_page(query, &params(p), &ctx())
        .await
        .unwrap_or_else(|e| panic!("{query}: {e}"));
    page.rows
        .iter()
        .map(|r| r[key].as_str().unwrap().to_string())
        .collect()
}

/// 🔴 The symptom of tasks#45: start the first task of a tied group and it drops to the bottom.
#[tokio::test]
async fn a_touched_row_keeps_its_place_among_ties() {
    let rt = board().await;
    touch(&rt, "t1").await;
    let order = ids(
        &rt,
        "tiebreak.tasks.list",
        json!({ "sort": "status", "dir": "asc", "limit": 20 }),
        "id",
    )
    .await;
    assert_eq!(order, ["t7", "t1", "t2", "t3", "t4", "t5", "t6"]);
}

/// 🔴 Walking the pages of a tied list shows every row exactly once, in the order of the whole list.
#[tokio::test]
async fn paging_through_ties_returns_every_row_exactly_once() {
    let rt = board().await;
    touch(&rt, "t1").await;
    touch(&rt, "t4").await;
    let mut walked = Vec::new();
    for offset in [0, 3, 6] {
        walked.extend(
            ids(
                &rt,
                "tiebreak.tasks.list",
                json!({ "sort": "status", "dir": "asc", "limit": 3, "offset": offset }),
                "id",
            )
            .await,
        );
    }
    assert_eq!(walked, ["t7", "t1", "t2", "t3", "t4", "t5", "t6"]);
}

/// 🔴 The whole-set read a command's `reads`/`guard_query` uses pages through the same engine
/// (`page_size: 3` here): a repeated row there is a guard that counts one thing twice.
#[tokio::test]
async fn a_whole_set_read_over_ties_sees_every_row_once() {
    let rt = board().await;
    touch(&rt, "t2").await;
    touch(&rt, "t5").await;
    let rows = rt
        .execute_query("tiebreak.tasks.list", &Params::new(), &ctx())
        .await
        .unwrap();
    let order: Vec<&str> = rows.iter().map(|r| r["id"].as_str().unwrap()).collect();
    assert_eq!(order, ["t7", "t1", "t2", "t3", "t4", "t5", "t6"]);
}

/// 🔴 Flipping the direction flips the WHOLE list, ties included — the tie is broken the way the
/// list is sorted, so `desc` is exactly `asc` read backwards.
#[tokio::test]
async fn desc_breaks_ties_in_the_same_direction() {
    let rt = board().await;
    touch(&rt, "t6").await;
    let order = ids(
        &rt,
        "tiebreak.tasks.list",
        json!({ "sort": "status", "dir": "desc", "limit": 20 }),
        "id",
    )
    .await;
    assert_eq!(order, ["t6", "t5", "t4", "t3", "t2", "t1", "t7"]);
}

/// The chosen column still decides first: the tiebreak only orders rows that tie on it.
#[tokio::test]
async fn the_chosen_column_still_decides_before_the_tiebreak() {
    let rt = board().await;
    let order = ids(
        &rt,
        "tiebreak.tasks.list",
        json!({ "sort": "title", "dir": "desc", "limit": 20 }),
        "id",
    )
    .await;
    assert_eq!(order, ["t7", "t6", "t5", "t4", "t3", "t2", "t1"]);
}

/// A list whose SELECT has no `id` column (a report, an aggregate) still answers: the engine does
/// not invent a column the query does not project.
#[tokio::test]
async fn a_list_without_an_id_column_still_answers() {
    let rt = board().await;
    let titles = ids(
        &rt,
        "tiebreak.labels.list",
        json!({ "sort": "status", "dir": "asc", "limit": 20 }),
        "title",
    )
    .await;
    assert_eq!(titles.len(), 7);
    assert_eq!(titles[0], "Task 7");
}
