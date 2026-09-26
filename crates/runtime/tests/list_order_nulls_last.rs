//! **Rows without a value came FIRST in a newest-first list** (hub#2099).
//!
//! The list engine emitted a bare `ORDER BY sub.<col> DESC`, and Postgres sorts `NULL` as the
//! largest value: in `DESC` every row without a date went to the top. The WhatsApp inbox showed it —
//! a conversation created empty (its first message bounced off the monthly cap) sat above the
//! conversations with activity this morning. Any «last X» list where a row has no X yet did the same.
//!
//! The contract pinned here is the one every inbox and listing in the market follows: **rows
//! without a value go last, in both directions**, without each module having to ask for it.
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;
use std::path::PathBuf;

const HUB: &str = "hub-2099";

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_nulls_order")
}

fn ctx() -> RequestContext {
    RequestContext::new(HUB, "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Three threads: one from this morning, one from April, and one never written to.
async fn inbox() -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.install_from_dir(&fixture())
        .await
        .expect("install the fixture");
    for (label, last) in [
        ("april", json!("2026-04-02T10:00:00Z")),
        ("empty", json!(null)),
        ("today", json!("2026-09-02T09:00:00Z")),
    ] {
        rt.execute_command(
            "nullsorder.threads.create",
            &params(json!({ "label": label, "last_message_at": last })),
            &ctx(),
        )
        .await
        .unwrap_or_else(|e| panic!("create thread {label}: {e}"));
    }
    rt
}

async fn labels(rt: &Runtime, p: serde_json::Value) -> Vec<String> {
    let page = rt
        .execute_query_page("nullsorder.threads.list", &params(p), &ctx())
        .await
        .unwrap();
    page.rows
        .iter()
        .map(|r| r["label"].as_str().unwrap().to_string())
        .collect()
}

/// 🔴 The manifest's `default_dir: desc` — the inbox as it opens.
#[tokio::test]
async fn default_desc_puts_rows_without_value_last() {
    let rt = inbox().await;
    let names = labels(&rt, json!({ "limit": 10 })).await;
    assert_eq!(names, ["today", "april", "empty"]);
}

/// 🔴 The user asks for `desc` explicitly (column header click).
#[tokio::test]
async fn explicit_desc_puts_rows_without_value_last() {
    let rt = inbox().await;
    let names = labels(
        &rt,
        json!({ "sort": "last_message_at", "dir": "desc", "limit": 10 }),
    )
    .await;
    assert_eq!(names, ["today", "april", "empty"]);
}

/// The first page of a newest-first list is the newest rows, never the empty one.
#[tokio::test]
async fn first_page_of_desc_does_not_start_with_the_empty_row() {
    let rt = inbox().await;
    let page = rt
        .execute_query_page("nullsorder.threads.list", &Params::new(), &ctx())
        .await
        .unwrap();
    assert_eq!(page.total, 3);
    let names: Vec<&str> = page
        .rows
        .iter()
        .map(|r| r["label"].as_str().unwrap())
        .collect();
    assert_eq!(names, ["today", "april"]);
}

/// `asc` keeps them last as well: the rule is «no value, at the end», whatever the direction.
#[tokio::test]
async fn asc_puts_rows_without_value_last() {
    let rt = inbox().await;
    let names = labels(
        &rt,
        json!({ "sort": "last_message_at", "dir": "asc", "limit": 10 }),
    )
    .await;
    assert_eq!(names, ["april", "today", "empty"]);
}
