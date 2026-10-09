//! A `range` filter (`f_<col>_from`/`f_<col>_to`) places its bounds against the REAL type of the
//! column, whichever way round the caller wrote them — **hub#1542** (TEXT bound over a NUMERIC
//! column) and its mirror **hub#1566** (NUMBER bound over a column that is not numeric). Either
//! diagonal used to fail the whole request with the generic `db` error instead of filtering.
//!
//! What follows is hub#1542; hub#1566 picks up further down, and the last block covers the third
//! state both share: the column type could not be resolved at all.
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
    let ids = ids_for(&[("f_priority_from", json!(10)), ("f_priority_to", json!(20))]).await;

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

/// A TEXT column swallows the very same bound without complaint — proof that the refusal
/// comes from the COLUMN's type and not from a value-shape guess made by the engine. Under
/// the database collation `'B12345678'` sorts above `'abc'`, so the honest answer is one row.
#[tokio::test]
async fn the_same_unreadable_bound_is_a_legitimate_text_bound() {
    let ids = ids_for(&[("f_tax_id_from", json!("abc"))]).await;
    assert_eq!(
        ids,
        vec!["evening".to_string()],
        "'B12345678' is the only tax id the collation puts at or above 'abc'"
    );
}

// ── hub#1566 — the MIRROR: the bound arrives as a NUMBER over a TEXT column ──────────────────
//
// hub#1542 above covers TEXT bound over NUMERIC column. The other diagonal was still bound as
// written: a `Json::Number` over a TEXT column reached Postgres as `bigint` and it refused
// `text >= bigint` (`42883`), so the whole page came back with the generic `db` error — the same
// one a database outage gives, so whoever integrates cannot tell whether to fix their call or
// wait. It is what a flow, an assistant tool or any integration sends when the value it has at
// hand is already a number; `ok-data-table` itself emits `Number(raw)` for a `range` control
// (`onRangeInput`), so any screen that ever declares one over a TEXT column lands here too.

/// The bug, pinned. The very same window as
/// [`all_digit_bounds_on_a_text_column_keep_comparing_as_text`], written as NUMBERS: it has to
/// answer exactly the same rows instead of failing the request.
#[tokio::test]
async fn numeric_bounds_on_a_text_column_answer_the_same_rows_as_text_bounds() {
    let ids = ids_for(&[
        ("f_tax_id_from", json!(12345678)),
        ("f_tax_id_to", json!(99999999)),
    ])
    .await;

    assert_eq!(
        ids,
        vec!["day-after".to_string(), "morning".to_string()],
        "a numeric bound over a TEXT column must select the same rows as the same bound written \
         as text"
    );
}

/// And it lands where TEXT puts it, not where the number line would. `2` compared as a number
/// selects the three ids above two — and chokes on `'B12345678'`, which is not a number at all;
/// compared as the text `'2'` it selects only the two the collation sorts after it, because
/// every all-digit id in the fixture starts with a `0` or a `1`. The two answers are disjoint on
/// purpose: a fix that cast the COLUMN instead of the bound cannot pass this.
#[tokio::test]
async fn a_numeric_bound_lands_where_text_puts_it_not_on_the_number_line() {
    let ids = ids_for(&[("f_tax_id_from", json!(2))]).await;

    assert_eq!(
        ids,
        vec!["day-after".to_string(), "evening".to_string()],
        "'2' sorts above '00000001' and '12345678' as text; a numeric comparison would answer \
         the opposite rows"
    );
}

/// A numeric bound is not a bare date, so the `to` end is NOT widened to the next day
/// (verifactu#70 only ever applied to a `YYYY-MM-DD` string). Closed at `'12345678'`, the row
/// with that exact tax id is IN — and nothing beyond it leaks in from a widening that must not
/// happen.
#[tokio::test]
async fn a_numeric_to_bound_is_closed_and_never_widened_to_a_next_day() {
    let ids = ids_for(&[("f_tax_id_to", json!(12345678))]).await;

    assert_eq!(
        ids,
        vec!["day-before".to_string(), "morning".to_string()],
        "`<=` on the number written as text: '00000001' and '12345678' are at or below it"
    );
}

// ── El tercer estado: el servidor NO pudo decir de qué tipo es la columna ────────────────────
//
// Contra Postgres real el tipo siempre se resuelve, así que la degradación —el `describe` falla,
// o el adaptador no sabe responderlo— no aparece en ninguna de las pruebas de arriba. Y es justo
// el estado que las dos conversiones no pueden confundir con «la columna NO es numérica»: no
// saber tiene que dejar el extremo exactamente como venía. Este doble es un hub REAL al que sólo
// se le ha cegado esa pregunta.

/// A real Postgres hub whose `column_kinds` always fails — the degradation path, and nothing
/// else. Everything a query needs still runs against the real database.
struct BlindToColumnKinds(erplora_db::PgAdapter);

#[async_trait::async_trait]
impl erplora_db::DatabaseAdapter for BlindToColumnKinds {
    async fn execute(
        &self,
        sql: &str,
        params: &Params,
    ) -> Result<erplora_db::CommandResult, erplora_db::DbError> {
        self.0.execute(sql, params).await
    }

    async fn execute_tx(
        &self,
        ops: &[(String, Params)],
    ) -> Result<erplora_db::CommandResult, erplora_db::DbError> {
        self.0.execute_tx(ops).await
    }

    async fn execute_tx_gated(
        &self,
        ops: &[(String, Params)],
        gates: &[erplora_db::RowGate],
        conditions: &[erplora_db::OpCondition],
    ) -> Result<erplora_db::TxGatedOutcome, erplora_db::DbError> {
        self.0.execute_tx_gated(ops, gates, conditions).await
    }

    async fn query(
        &self,
        sql: &str,
        params: &Params,
    ) -> Result<erplora_db::QueryResult, erplora_db::DbError> {
        self.0.query(sql, params).await
    }

    async fn execute_batch(&self, sql: &str) -> Result<(), erplora_db::DbError> {
        self.0.execute_batch(sql).await
    }

    async fn column_kinds(
        &self,
        _sql: &str,
    ) -> Result<std::collections::BTreeMap<String, erplora_db::ColumnKind>, erplora_db::DbError>
    {
        // A REAL `DbError`, asked of the real database — the crate does not re-export `sqlx`, and
        // an error built by hand would be a different shape from the one production degrades on.
        self.0.column_kinds("SELECT ! FROM nowhere").await
    }
}

async fn blind_hub() -> Runtime {
    let mut rt = Runtime::new(Box::new(BlindToColumnKinds(fresh_db().await)));
    rt.install_from_dir(&fixture())
        .await
        .expect("install rangefix");
    rt
}

/// The control for the two tests below: the double really is blind. Without this, a change that
/// made `column_kinds` succeed would turn both of them into a second copy of the happy path —
/// green, and proving nothing.
#[tokio::test]
async fn the_double_really_cannot_resolve_a_column_type() {
    let db = BlindToColumnKinds(fresh_db().await);
    let err = erplora_db::DatabaseAdapter::column_kinds(&db, "SELECT 1 AS n")
        .await
        .expect_err("the double must fail the question the engine asks");
    assert!(
        !format!("{err}").is_empty(),
        "the failure has to carry something to log"
    );
}

/// A NUMERIC bound over a NUMERIC column keeps working when the type could not be resolved. It
/// is the answer that the "unknown = not numeric" shortcut would break: writing this bound as
/// text would compare `integer >= text` and bring back hub#1542's failure through the back door,
/// precisely when the engine has the least information.
#[tokio::test]
async fn without_column_types_a_numeric_bound_is_still_bound_as_a_number() {
    let rt = blind_hub().await;

    let page = rt
        .execute_query_page(
            "rangefix.events.list",
            &params(&[("f_priority_from", json!(10)), ("f_priority_to", json!(20))]),
            &ctx(),
        )
        .await
        .unwrap_or_else(|e| panic!("not knowing the column type must not break the list: {e}"));

    let ids: Vec<String> = page
        .rows
        .iter()
        .map(|r| r["id"].as_str().unwrap().to_string())
        .collect();
    assert_eq!(ids, vec!["evening".to_string(), "morning".to_string()]);
}

/// And the bound the engine cannot place is left exactly as the caller wrote it: a TEXT bound
/// over the same numeric column fails as it did before hub#1542 — loudly — instead of being
/// converted on a guess.
#[tokio::test]
async fn without_column_types_a_text_bound_is_not_converted_on_a_guess() {
    let rt = blind_hub().await;

    let err = rt
        .execute_query_page(
            "rangefix.events.list",
            &params(&[("f_priority_from", json!("10"))]),
            &ctx(),
        )
        .await
        .expect_err("without the column type there is no conversion to make");

    assert_eq!(
        erplora_runtime::error_registry::error_code_of(&err),
        "db",
        "degrading has to give yesterday's answer, not a new one: {err}"
    );
}
