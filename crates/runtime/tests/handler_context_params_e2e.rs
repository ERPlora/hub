//! hub#1022 / hub#1098 — the runtime hands every handler the hub's CLOCK and the caller's
//! LANGUAGE, so no module has to guess either again.
//!
//! Before these two, the WASM/native handler input carried fiscal identity
//! (`context.country_code`/`region_code`, ADR-0085) but not the timezone: a module scheduling
//! "tomorrow at 09:00" had to infer the business clock from... nothing. And the effective
//! language of whoever asked was resolved by each module that projected translated text by
//! re-implementing the precedence in SQL (taxes#38/#40 read `hub_user_pref` + `hub_settings`
//! themselves, duplicating the core's default and getting it wrong once already).
//!
//! Contract under test:
//!  - `context.timezone` (hub#1022): the IANA name the flows kernel already uses
//!    (`settings::timezone_of`): the declared `timezone` setting, else the one deduced from
//!    `country_code`/`region_code`. Never `null`.
//!  - `:timezone` (hub#1022): the same value as a system param, bindable in any command or
//!    query SQL.
//!  - `:caller_lang` (hub#1098): the effective language of the CALLER with the precedence the
//!    shell already uses (`bootHubLanguage`): the user's own override (`hub_user_pref.language`)
//!    → the hub's `language` setting → the core default `es`.
//!
//! The handler is NATIVE on purpose (same `payload`+`context` input contract as WASM — see
//! `handler_new_ids_e2e.rs`): it records what the host handed it into one row, and the test
//! reads the row back. One fixture query, `ctxp.echo`, mirrors the same params through the
//! plain-query path, which binds system params too.
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{native::NativeHandler, RequestContext, Runtime};
use erplora_wasm_host::{Operation, Output};
use serde_json::{json, Value as Json};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_ctxparams")
        .join("ctxp")
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Records everything the host handed the handler about the clock and the language into one
/// `ctxp_observation` row: `context.timezone` on one column, the `:timezone`/`:caller_lang`
/// system params (which ride the payload) on the others.
#[derive(Debug)]
struct RecordingHandler;

#[async_trait]
impl NativeHandler for RecordingHandler {
    async fn call(
        &self,
        _function: &str,
        input: &Json,
        _host: &dyn erplora_runtime::native::NativeHost,
    ) -> Result<Output, erplora_runtime::errors::RuntimeError> {
        let mut params = serde_json::Map::new();
        params.insert("id".into(), input["context"]["new_ids"][0].clone());
        params.insert("ctx_timezone".into(), input["context"]["timezone"].clone());
        params.insert(
            "param_timezone".into(),
            input["payload"]["timezone"].clone(),
        );
        params.insert(
            "caller_lang".into(),
            input["payload"]["caller_lang"].clone(),
        );
        Ok(Output::new().with_operation(Operation::sql("ctxp._insert", params)))
    }
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&fixture()).await.expect("install ctxp");
    rt.register_native("ctxp", Arc::new(RecordingHandler));
    rt
}

/// Runs `ctxp.record` and returns `(context.timezone, :timezone, :caller_lang)` as the handler
/// saw them, read back from the row its operation materialised.
async fn observed(rt: &Runtime, ctx: &RequestContext) -> (String, String, String) {
    rt.execute_command("ctxp.record", &Params::new(), ctx)
        .await
        .expect("ctxp.record runs");
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("h1"));
    let row = rt
        .db_for_test()
        .query(
            "SELECT ctx_timezone, param_timezone, caller_lang FROM ctxp_observation LIMIT 1",
            &p,
        )
        .await
        .expect("read the observation back")
        .rows
        .into_iter()
        .next()
        .expect("the handler materialised exactly one row");
    (
        row["ctx_timezone"].as_str().unwrap_or_default().to_string(),
        row["param_timezone"]
            .as_str()
            .unwrap_or_default()
            .to_string(),
        row["caller_lang"].as_str().unwrap_or_default().to_string(),
    )
}

async fn set_user_language(rt: &Runtime, user_id: &str, lang: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("h1"));
    p.insert("user_id".into(), json!(user_id));
    p.insert("language".into(), json!(lang));
    rt.db_for_test()
        .execute(
            "INSERT INTO hub_user_pref (hub_id, user_id, language, theme_mode, theme_palette, updated_at) \
             VALUES (:hub_id, :user_id, :language, '', '', '2026-01-01T00:00:00Z')",
            &p,
        )
        .await
        .expect("seed the user's language override");
}

// ── hub#1022: context.timezone / :timezone ────────────────────────────────────────────────

/// The DECLARED timezone setting reaches the handler through BOTH doors: `context.timezone`
/// and the `:timezone` system param.
#[tokio::test]
async fn handler_sees_the_declared_timezone_in_context_and_param() {
    let rt = runtime().await;
    let mut updates = serde_json::Map::new();
    updates.insert("timezone".into(), json!("Atlantic/Canary"));
    rt.set_settings(&updates, "u1").await.expect("set timezone");

    let (ctx_tz, param_tz, _) = observed(&rt, &admin()).await;
    assert_eq!(ctx_tz, "Atlantic/Canary", "context.timezone");
    assert_eq!(param_tz, "Atlantic/Canary", ":timezone");
}

/// No declared timezone → the DEDUCED one (`settings::timezone_of`, hub#731): a hub in
/// Portugal gets Europe/Lisbon from its `country_code`, without declaring anything.
#[tokio::test]
async fn timezone_is_deduced_from_the_country_when_not_declared() {
    let rt = runtime().await;
    let mut updates = serde_json::Map::new();
    updates.insert("country_code".into(), json!("PT"));
    rt.set_settings(&updates, "u1")
        .await
        .expect("set country_code=PT");

    let (ctx_tz, param_tz, _) = observed(&rt, &admin()).await;
    assert_eq!(ctx_tz, "Europe/Lisbon", "context.timezone is deduced");
    assert_eq!(param_tz, "Europe/Lisbon", ":timezone is deduced");
}

// ── hub#1098: :caller_lang ────────────────────────────────────────────────────────────────

/// The user's OWN language wins (the exact case of the issue: the user has it in `es` even
/// though the hub says `en`).
#[tokio::test]
async fn caller_lang_prefers_the_users_own_language() {
    let rt = runtime().await;
    let mut updates = serde_json::Map::new();
    updates.insert("language".into(), json!("en"));
    rt.set_settings(&updates, "u1")
        .await
        .expect("hub language = en");
    set_user_language(&rt, "u1", "es").await;

    let (_, _, lang) = observed(&rt, &admin()).await;
    assert_eq!(
        lang, "es",
        ":caller_lang is the user's override, not the hub's"
    );
}

/// No user override → the hub's setting; and with neither → the core default `es` (taxes#40:
/// the default is the core's, applied by the settings layer — never a module's guess).
#[tokio::test]
async fn caller_lang_falls_back_to_the_hub_then_the_core_default() {
    // Hub says `en`, user said nothing.
    let rt = runtime().await;
    let mut updates = serde_json::Map::new();
    updates.insert("language".into(), json!("en"));
    rt.set_settings(&updates, "u1")
        .await
        .expect("hub language = en");
    let (_, _, lang) = observed(&rt, &admin()).await;
    assert_eq!(
        lang, "en",
        "hub setting applies when the user has no override"
    );

    // Fresh hub: nobody said anything → the core default.
    let rt = runtime().await;
    let (_, _, lang) = observed(&rt, &admin()).await;
    assert_eq!(lang, "es", "the core default is es, not a module's guess");
}

// ── the plain-query path binds the same params ─────────────────────────────────────────────

/// `ctxp.echo` is a plain SELECT that binds `:timezone`/`:caller_lang`: the query path must
/// resolve them too, or every list a module projects (taxes#38's `categories_list`) would keep
/// re-implementing the resolution in SQL.
#[tokio::test]
async fn queries_bind_the_same_timezone_and_caller_lang() {
    let rt = runtime().await;
    let mut updates = serde_json::Map::new();
    updates.insert("timezone".into(), json!("Atlantic/Canary"));
    updates.insert("language".into(), json!("en"));
    rt.set_settings(&updates, "u1")
        .await
        .expect("set tz + language");
    set_user_language(&rt, "u1", "es").await;

    let rows = rt
        .execute_query("ctxp.echo", &Params::new(), &admin())
        .await
        .expect("ctxp.echo runs");
    let row = rows.first().expect("echo answers one row");
    assert_eq!(
        row["timezone"],
        json!("Atlantic/Canary"),
        ":timezone in a query"
    );
    assert_eq!(row["caller_lang"], json!("es"), ":caller_lang in a query");
}
