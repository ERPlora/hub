//! **verifactu#70** — a `range` filter (`f_<col>_from`/`f_<col>_to`) on an INSTANT column
//! (every such column in production is TEXT holding a full ISO-8601 instant — `verifactu_event
//! .timestamp`, `.next_attempt_at`, `.query_timestamp`) silently returned nothing for a
//! same-day query. The upper bound compared the column against a bare `YYYY-MM-DD` bound with
//! `<=`, and a bare date is a strict TEXT PREFIX of any instant string that shares its day:
//! lexicographically `'2026-01-15T23:30:00+00:00' <= '2026-01-15'` is FALSE (the longer string
//! sorts after its own prefix), so a row logged at 23:30 fell outside
//! `from=2026-01-15, to=2026-01-15` even though it happened that day.
//!
//! The lower bound was never the problem (`>=` against midnight already includes the whole day
//! forward); only the upper bound needs to move to the START of the NEXT day, compared with `<`.
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

/// The bug, pinned: `from` and `to` both `2026-01-15` must return BOTH rows logged that day
/// (08:00 and 23:30), and neither neighbour (23:00 the day before, 00:30 the day after).
#[tokio::test]
async fn range_filter_on_an_instant_column_includes_the_whole_same_day() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "rangefix.events.list",
            &params(&[
                ("f_happened_at_from", json!("2026-01-15")),
                ("f_happened_at_to", json!("2026-01-15")),
            ]),
            &ctx(),
        )
        .await
        .unwrap();

    let ids: Vec<&str> = page
        .rows
        .iter()
        .map(|r| r["id"].as_str().unwrap())
        .collect();
    assert_eq!(
        page.total, 2,
        "the 23:30 row must not be silently dropped by a same-day range: {ids:?}"
    );
    assert!(ids.contains(&"morning"), "{ids:?}");
    assert!(ids.contains(&"evening"), "{ids:?}");
    assert!(
        !ids.contains(&"day-before") && !ids.contains(&"day-after"),
        "the widened bound must stop at the day boundary, not leak into the neighbours: {ids:?}"
    );
}

/// A `to` bound that already carries a time (a caller that knows the exact instant it wants)
/// keeps meaning exactly that — the widening only kicks in for a BARE calendar date.
#[tokio::test]
async fn range_filter_with_an_explicit_time_bound_is_left_exact() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "rangefix.events.list",
            &params(&[
                ("f_happened_at_from", json!("2026-01-15T00:00:00+00:00")),
                ("f_happened_at_to", json!("2026-01-15T12:00:00+00:00")),
            ]),
            &ctx(),
        )
        .await
        .unwrap();

    let ids: Vec<&str> = page
        .rows
        .iter()
        .map(|r| r["id"].as_str().unwrap())
        .collect();
    assert_eq!(
        page.total, 1,
        "an explicit noon cutoff excludes the 23:30 row, unchanged by the fix: {ids:?}"
    );
    assert_eq!(ids, vec!["morning"]);
}

/// Regression guard: the fix must not touch the ALREADY-correct case — a `range` filter over a
/// bare calendar-date TEXT column (the `_date` columns of `verifactu`), where a same-day
/// `from`/`to` already worked via exact lexicographic comparison.
#[tokio::test]
async fn range_filter_on_a_bare_date_text_column_stays_exact() {
    let rt = hub().await;

    let page = rt
        .execute_query_page(
            "rangefix.events.list",
            &params(&[
                ("f_logged_on_from", json!("2026-01-15")),
                ("f_logged_on_to", json!("2026-01-15")),
            ]),
            &ctx(),
        )
        .await
        .unwrap();

    let ids: Vec<&str> = page
        .rows
        .iter()
        .map(|r| r["id"].as_str().unwrap())
        .collect();
    assert_eq!(page.total, 2, "{ids:?}");
    assert!(ids.contains(&"morning") && ids.contains(&"evening"), "{ids:?}");
}
