//! **hub#2383** — a PLAIN query (no `list` block) asked WITHOUT the parameter its SQL needs
//! answered "there is nothing" instead of saying what was missing.
//!
//! `appointments.appointments.get` asked with `{}` bound `:appointment_id` as NULL, matched zero
//! rows and answered `[]` — the same empty ticket as sales#316, reached by forgetting the id
//! instead of misspelling it. hub#1086 closed this for the LIST engine (`missing_required_param`)
//! and hub#1913 closed the misspelt half for plain queries (`unknown_filter`); this is the gap left.
//!
//! What a plain query REQUIRES is read from what the module wrote, never guessed:
//!
//!  * a bind its SQL references is required…
//!  * …unless the SQL handles the NULL itself on at least one occurrence — inside the first
//!    argument of `COALESCE(…)` (the `appointments.appointments.list` idiom) or tested with
//!    `IS [NOT] NULL` — or the query's JSON Schema declares it as an optional property (the
//!    `tasks.tasks.my` shape, whose screen sends `due_horizon: null` on purpose);
//!  * the kernel's system params and the engine's paging pair (`limit`/`offset`) never are.
//!
//! Command `reads` (ADR-0069) are NOT gated by this: their params are a mapping the module author
//! declared (`payload.staff_id` resolves to null when the payload has none, by design) and the
//! handler owns the "not found" decision — `appointments.availability.slots` asks
//! `staff.availability.day_at` as a REQUIRED read with an optional `staff_id`, and refusing it would
//! abort every "any professional" availability check.
//!
//! Real Postgres, ephemeral schema per test.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_plainbind2383")
        .join("pbind")
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture())
        .await
        .expect("install pbind");
    rt
}

fn ctx(hub_id: &str) -> RequestContext {
    RequestContext::new(hub_id, "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn ids(rows: &[serde_json::Value]) -> Vec<&str> {
    rows.iter().filter_map(|r| r["id"].as_str()).collect()
}

fn assert_missing(err: RuntimeError, query: &str, param: &str) {
    match err {
        RuntimeError::MissingRequiredParam { query: q, param: p } => {
            assert_eq!(p, param, "the error names the missing parameter");
            assert_eq!(q, query, "the error names the query");
        }
        other => panic!("expected MissingRequiredParam, got {other:?}"),
    }
}

/// The acceptance case, in the exact shape of the issue: a single-record read asked without the
/// id. It used to answer `[]`; now it names the parameter it needs.
#[tokio::test]
async fn a_plain_read_asked_without_its_bind_names_the_missing_param() {
    let rt = hub().await;
    let err = rt
        .execute_query("pbind.items.get", &Params::new(), &ctx("h1"))
        .await
        .expect_err("an absent :item_id must fail loudly, not answer []");
    assert_missing(err, "pbind.items.get", "item_id");
}

/// `null` is the same omission written down: the SDK serialises `undefined` fields away, but a
/// screen that sends `{ item_id: null }` forgot the id just the same.
#[tokio::test]
async fn an_explicit_null_is_the_same_omission() {
    let rt = hub().await;
    let err = rt
        .execute_query(
            "pbind.items.get",
            &params(json!({ "item_id": null })),
            &ctx("h1"),
        )
        .await
        .expect_err("a null :item_id must fail loudly, not answer []");
    assert_missing(err, "pbind.items.get", "item_id");
}

/// The paged door is the same door: a flow's `query` step reads a plain query through
/// `execute_query_page`, and it refuses the same omission instead of answering an empty page.
#[tokio::test]
async fn the_paged_door_refuses_the_same_omission() {
    let rt = hub().await;
    let err = rt
        .execute_query_page("pbind.items.get", &Params::new(), &ctx("h1"))
        .await
        .expect_err("an absent :item_id must not come back as an empty page");
    assert_missing(err, "pbind.items.get", "item_id");
}

/// No regression, and tenancy: with the bind the read answers its record, and only in its hub.
#[tokio::test]
async fn with_the_bind_the_read_answers_its_record_and_only_in_its_hub() {
    let rt = hub().await;
    let mine = rt
        .execute_query(
            "pbind.items.get",
            &params(json!({ "item_id": "i1" })),
            &ctx("h1"),
        )
        .await
        .expect("with the bind the read works as always");
    assert_eq!(ids(&mine), vec!["i1"]);

    let foreign = rt
        .execute_query(
            "pbind.items.get",
            &params(json!({ "item_id": "i3" })),
            &ctx("h1"),
        )
        .await
        .expect("another hub's id is simply not found");
    assert!(foreign.is_empty(), "h1 never sees h2's row: {foreign:?}");
}

/// The module wrapped one occurrence in COALESCE: absent means "every status" (the
/// `appointments.appointments.list` idiom), exactly as before.
#[tokio::test]
async fn a_bind_the_sql_coalesces_stays_optional() {
    let rt = hub().await;
    let all = rt
        .execute_query("pbind.items.by_status", &Params::new(), &ctx("h1"))
        .await
        .expect("a COALESCE-handled bind absent is the module's declared default");
    assert_eq!(ids(&all), vec!["i1", "i2"]);

    let open = rt
        .execute_query(
            "pbind.items.by_status",
            &params(json!({ "status": "open" })),
            &ctx("h1"),
        )
        .await
        .expect("the optional bind still filters");
    assert_eq!(ids(&open), vec!["i1"]);
}

/// The module tested the bind with IS NULL: absent means "any tag", exactly as before.
#[tokio::test]
async fn a_bind_the_sql_tests_for_null_stays_optional() {
    let rt = hub().await;
    let all = rt
        .execute_query("pbind.items.tagged", &Params::new(), &ctx("h1"))
        .await
        .expect("an IS NULL-handled bind absent is the module's declared default");
    assert_eq!(ids(&all), vec!["i1", "i2"]);
}

/// The JSON Schema declares the bind optional (the `tasks.tasks.my` shape): absent or null is the
/// module's own contract, not an accident.
#[tokio::test]
async fn a_bind_the_schema_declares_optional_stays_optional() {
    let rt = hub().await;
    for p in [
        json!({ "apply_horizon": 0, "due_horizon": null }),
        json!({ "apply_horizon": 0 }),
    ] {
        let rows = rt
            .execute_query("pbind.items.due", &params(p.clone()), &ctx("h1"))
            .await
            .unwrap_or_else(|e| panic!("{p}: a schema-optional bind must not be refused: {e:?}"));
        assert_eq!(ids(&rows), vec!["i1", "i2"], "{p}");
    }
}

/// Kernel context and the paging pair are never the caller's to send: a query that binds only
/// `:hub_id` and `:limit` answers with `{}`.
#[tokio::test]
async fn system_params_and_the_paging_pair_are_never_required() {
    let rt = hub().await;
    let rows = rt
        .execute_query("pbind.items.all", &Params::new(), &ctx("h1"))
        .await
        .expect("nothing for the caller to send");
    assert_eq!(ids(&rows), vec!["i1", "i2"]);
}

/// A command's preloaded `reads` keep the author's mapping: a REQUIRED read whose param comes from
/// an optional payload field is preloaded as `[]` and the command runs — the handler decides what
/// "not found" means (`appointments.availability.slots` without a professional).
#[tokio::test]
async fn a_command_read_with_an_absent_mapped_param_still_preloads() {
    let package = kernel_fixture::broken_copy("read-optional-param-2383", |m| {
        m["queries"]["kfx.items.one"] = json!({
            "permission": "kfx.read",
            "sql": "queries/item_one.sql"
        });
        m["commands"]["kfx.items.bulk"]["reads"] = json!([{
            "query": "kfx.items.one",
            "params": { "item_id": "payload.item_id" },
            "required": true
        }]);
    });
    std::fs::write(
        package.path().join("queries").join("item_one.sql"),
        "SELECT id, name FROM kfx_item WHERE hub_id = :hub_id AND id = :item_id\n",
    )
    .expect("write the read's SQL");

    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(package.path())
        .await
        .expect("install the fixture with the extra read");

    let out = rt
        .execute_command(
            "kfx.items.bulk",
            &params(json!({ "names": ["a"] })),
            &kernel_fixture::admin(),
        )
        .await
        .expect("a required read with an absent optional param is preloaded, never aborts");
    assert_eq!(out["operations"], json!(1));
}

/// The same read when the author's mapping also carries a page size: a numeric `limit` sends
/// `queries::execute` down its single-trip branch, and that branch still reads as the command's
/// own read — the absent `item_id` binds NULL and the command runs.
#[tokio::test]
async fn a_command_read_with_a_mapped_limit_still_preloads() {
    let package = kernel_fixture::broken_copy("read-optional-param-limit-2383", |m| {
        m["queries"]["kfx.items.one"] = json!({
            "permission": "kfx.read",
            "sql": "queries/item_one.sql"
        });
        m["commands"]["kfx.items.bulk"]["reads"] = json!([{
            "query": "kfx.items.one",
            "params": { "item_id": "payload.item_id", "limit": "payload.take" },
            "required": true
        }]);
    });
    std::fs::write(
        package.path().join("queries").join("item_one.sql"),
        "SELECT id, name FROM kfx_item WHERE hub_id = :hub_id AND id = :item_id\n",
    )
    .expect("write the read's SQL");

    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(package.path())
        .await
        .expect("install the fixture with the extra read");

    let out = rt
        .execute_command(
            "kfx.items.bulk",
            &params(json!({ "names": ["a"], "take": 5 })),
            &kernel_fixture::admin(),
        )
        .await
        .expect("a required read with a page size and an absent optional param still preloads");
    assert_eq!(out["operations"], json!(1));
}
