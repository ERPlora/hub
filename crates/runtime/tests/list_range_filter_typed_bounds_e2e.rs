//! **hub#1542** — a `range` filter (`f_<col>_from`/`f_<col>_to`) whose bounds arrive as TEXT
//! over a NUMERIC column failed the whole request with the generic `db` error instead of
//! filtering.
//!
//! The screen never hit it (`ok-data-table`'s `onRangeInput` emits `Number(raw)`), but every
//! other caller of a list does: a flow, an assistant tool or any integration sends what it has
//! at hand, which is a string. The engine bound it as TEXT and Postgres refused
//! `bigint >= text` (`42883`), so the page came back `{"ok":false,"error":{"code":"db"}}`.
//!
//! The fix cannot be "if the bound parses as a number, bind a number": the published catalogue
//! declares `range` over TEXT columns too (`customers.list.f_tax_id`,
//! `invoice.list.f_customer_tax_id`, `cash_register.counts.list.f_count_type`,
//! `services.packages.list.f_discount_type`) and an all-digit tax id filters correctly TODAY.
//! Guessing from the value would trade this bug for that regression — the only thing that knows
//! is the COLUMN, so the bound is handed to Postgres untyped and the server resolves it against
//! the column it is compared with.
//!
//! Real Postgres, ephemeral schema per test — see `crates/db/src/testutil.rs`.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_rangefilter70")
        .join("rangefix")
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture())
        .await
        .expect("install rangefix");
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

async fn ids_for(pairs: &[(&str, serde_json::Value)]) -> Vec<String> {
    let rt = hub().await;
    let page = rt
        .execute_query_page("rangefix.events.list", &params(pairs), &ctx())
        .await
        .unwrap_or_else(|e| panic!("the range filter must not fail the request: {e}"));
    page.rows
        .iter()
        .map(|r| r["id"].as_str().unwrap().to_string())
        .collect()
}

/// The bug, pinned. Bounds `"10"`/`"20"` as STRINGS over an INTEGER column must answer exactly
/// the rows a caller sending the numbers gets — and the `100` row proves the comparison stayed
/// NUMERIC: lexicographically `'100' <= '20'` is TRUE, so a fix that compared both sides as
/// text would leak it in.
#[tokio::test]
async fn string_bounds_on_a_numeric_column_filter_by_number() {
    let ids = ids_for(&[
        ("f_priority_from", json!("10")),
        ("f_priority_to", json!("20")),
    ])
    .await;

    assert_eq!(
        ids,
        vec!["evening".to_string(), "morning".to_string()],
        "string bounds must select the same rows as numeric ones, ordered by the default sort"
    );
}

/// The same bounds as NUMBERS — the path the screen already uses. It worked before the fix and
/// has to keep answering exactly the same rows.
#[tokio::test]
async fn numeric_bounds_on_a_numeric_column_are_unchanged() {
    let ids = ids_for(&[
        ("f_priority_from", json!(10)),
        ("f_priority_to", json!(20)),
    ])
    .await;

    assert_eq!(ids, vec!["evening".to_string(), "morning".to_string()]);
}

/// The regression the obvious fix would have caused: a `range` over a TEXT column whose bounds
/// are ALL DIGITS (`customers.list.f_tax_id` — a tax id without a control letter) compares as
/// TEXT and keeps doing so. `'B12345678'` sorts ABOVE `'99999999'` (the database collation puts
/// letters after digits), so it falls outside the range even though it "starts with a bigger
/// number".
#[tokio::test]
async fn all_digit_bounds_on_a_text_column_keep_comparing_as_text() {
    let ids = ids_for(&[
        ("f_tax_id_from", json!("12345678")),
        ("f_tax_id_to", json!("99999999")),
    ])
    .await;

    assert_eq!(
        ids,
        vec!["day-after".to_string(), "morning".to_string()],
        "an all-digit bound over a TEXT column must not be turned into a number"
    );
}

/// A bound the column cannot make sense of still FAILS — the engine does not widen the door to
/// "compare anything with anything". What changes is that it says WHICH bound it could not read
/// and what the column expects, instead of the generic `db` error the caller got before.
#[tokio::test]
async fn an_unreadable_bound_names_the_bound_instead_of_failing_generically() {
    let rt = hub().await;

    let err = rt
        .execute_query_page(
            "rangefix.events.list",
            &params(&[("f_priority_from", json!("abc"))]),
            &ctx(),
        )
        .await
        .expect_err("a bound that is not a number cannot filter a numeric column");

    assert_eq!(
        erplora_runtime::error_registry::error_code_of(&err),
        "invalid_filter_bound",
        "the caller has to be able to tell a bad bound from a database outage: {err}"
    );
    let msg = err.to_string();
    assert!(
        msg.contains("f_priority_from"),
        "the message must name the bound it could not read: {msg}"
    );
    assert!(
        msg.contains("abc"),
        "the message must quote the value it could not read: {msg}"
    );
}

/// `nan` and `inf` are the bounds that would slip past a plain "does it parse as a number?"
/// check, and Postgres accepts BOTH as `NUMERIC` — so they never fail, they LIE. `col >= NaN` is
/// false for every row and `col <= NaN` is true for every row, so the page comes back empty (or
/// whole) as if the filter had run, which is the one answer a list must never give.
#[tokio::test]
async fn a_bound_that_is_not_a_position_on_the_number_line_is_refused_too() {
    let rt = hub().await;

    for bound in ["nan", "inf", "1e400"] {
        let err = rt
            .execute_query_page(
                "rangefix.events.list",
                &params(&[("f_priority_to", json!(bound))]),
                &ctx(),
            )
            .await
            .err()
            .unwrap_or_else(|| panic!("`{bound}` is not a position a range can end at"));

        assert_eq!(
            erplora_runtime::error_registry::error_code_of(&err),
            "invalid_filter_bound",
            "`{bound}` must be refused, not silently answered: {err}"
        );
    }
}
