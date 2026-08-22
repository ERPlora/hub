//! **hub#1092** — the binder typed a parameter by its VALUE, so a field declared
//! `"type": "number"` reached the SAME prepared statement as `int8` (when the payload sent `10`)
//! or as `float8` (when it sent `10.5`). sqlx caches prepared statements per connection by SQL
//! text and does not re-Parse on a hit, and `int8` and `float8` are both 8 bytes on the wire — so
//! the server reads the bytes as the type fixed by whoever warmed the cache first:
//!
//!  * statement prepared as `int8`, a `10.5` arrives → the f64 bit pattern read as an integer
//!    (`≈4.6e18`) → in a narrow column with a CHECK this fails LOUDLY (`23514`), intermittently,
//!    by connection;
//!  * statement prepared as `float8`, a `10` arrives → the integer bits read as a denormal
//!    (`≈1.5e-323`) → passes any `>= 0` CHECK and is stored. SILENT data corruption.
//!
//! The fix: when the module's JSON Schema DECLARES the type, the runtime rewrites the JSON number
//! to the declared shape BEFORE binding (`number` → always float-shaped, `integer` → always
//! int-shaped), so the same slot always carries the same wire type no matter which payload warmed
//! the cache. The db layer still types by value when nothing is declared — it cannot know.
//!
//! Real Postgres, ephemeral schema per test. The fixture declares `FLOAT4` on purpose: the DDL
//! shim only rewrites the portable tokens, so the column is a true 4-byte float — the loud case.
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

fn fixture() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_ptype1092")
        .join("ptype")
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture())
        .await
        .expect("install ptype");
    rt
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn rates(rt: &Runtime, ctx: &RequestContext) -> Vec<Json> {
    rt.execute_query("ptype.rules.all", &Params::new(), ctx)
        .await
        .expect("ptype.rules.all")
        .iter()
        .map(|r| r["rate"].clone())
        .collect()
}

/// The LOUD half: `10` (int) warms the statement as `int8`, then `10.5` must still insert
/// correctly. Before the fix the f64 bytes were read as an integer, the value exploded to
/// `≈4.6e18`, and the CHECK rejected it with `23514` — a tax rule "sometimes" failed to create
/// depending on which payload had used that connection first.
#[tokio::test]
async fn integer_then_fraction_on_the_same_statement_both_store_exactly() {
    let rt = hub().await;
    let ctx = ctx();

    rt.execute_command("ptype.rules.create", &params(json!({ "rate": 10 })), &ctx)
        .await
        .expect("integer-shaped number must insert");
    rt.execute_command("ptype.rules.create", &params(json!({ "rate": 10.5 })), &ctx)
        .await
        .expect("fraction-shaped number must insert on the SAME prepared statement");

    let got = rates(&rt, &ctx).await;
    assert_eq!(got.len(), 2, "both rows must exist: {got:?}");
    assert_eq!(
        got[0].as_f64(),
        Some(10.5),
        "the fraction keeps its value: {got:?}"
    );
    assert_eq!(
        got[1].as_f64(),
        Some(10.0),
        "the integer keeps its value: {got:?}"
    );
}

/// The SILENT half, the one that corrupts: `10.5` warms the statement as `float8`, then `10`
/// arrives; the int64 bytes read as a denormal double (`≈1.5e-323`) which passes the
/// `rate >= 0` CHECK. Nothing errors — the row is simply WRONG. This is the services#55
/// measurement, reproduced end-to-end through the declarative engine.
#[tokio::test]
async fn fraction_then_integer_on_the_same_statement_does_not_corrupt() {
    let rt = hub().await;
    let ctx = ctx();

    rt.execute_command("ptype.rules.create", &params(json!({ "rate": 10.5 })), &ctx)
        .await
        .expect("fraction-shaped number must insert");
    rt.execute_command("ptype.rules.create", &params(json!({ "rate": 10 })), &ctx)
        .await
        .expect("integer-shaped number must insert on the SAME prepared statement");

    let got = rates(&rt, &ctx).await;
    assert_eq!(got.len(), 2, "both rows must exist: {got:?}");
    assert_eq!(
        got[0].as_f64(),
        Some(10.5),
        "the fraction keeps its value: {got:?}"
    );
    assert_eq!(
        got[1].as_f64(),
        Some(10.0),
        "the integer must NOT be stored as a denormal float read of its bytes: {got:?}"
    );
}

fn params(v: Json) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
