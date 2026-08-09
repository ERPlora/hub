//! **Cessation of activity reaches the dispatcher** — ADR-0273 D2, hub#557.
//!
//! The refusal itself was already built and unit-tested (`enforce_fiscal_capacity`, hub#556). What
//! only shows up assembled is that the *transition* actually gets there: a hub that ceases stops
//! issuing on the real path — `Runtime::execute_command` — while `Runtime::execute_query` keeps
//! answering, which is where "✅ consult · ✅ export · ✅ accounting" comes from.
//!
//! The fixture module is deliberately a plain one, with no relationship to any fiscal regime: the
//! default-deny has to hold for whatever is installed, without the core naming anybody.
use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_w140")
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

async fn hub_with_a_module() -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture_dir()).await.expect("install w140");
    rt
}

fn code_of(err: &RuntimeError) -> String {
    match err {
        RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

/// 🔴 **The whole point of `CLOSED`, end to end.** The business ceased: it does not issue any more,
/// but its books are still there to be read and exported.
#[tokio::test]
async fn a_hub_that_ceased_stops_writing_but_still_answers_queries() {
    let rt = hub_with_a_module().await;
    let ctx = admin_ctx();
    rt.execute_command(
        "w140.items.create",
        &params(json!({ "name": "before closing" })),
        &ctx,
    )
    .await
    .expect("while it is open the hub works normally");

    rt.fiscal_close("hub_user:1").await.expect("cease activity");

    let err = rt
        .execute_command(
            "w140.items.create",
            &params(json!({ "name": "after closing" })),
            &ctx,
        )
        .await
        .expect_err("a ceased hub does not issue any more");
    assert_eq!(code_of(&err), "fiscal.hub_closed");

    let rows = rt
        .execute_query("w140.items.list", &Params::new(), &ctx)
        .await
        .expect("consulting and exporting stay open");
    assert_eq!(rows.len(), 1, "what it invoiced before is still readable");
}
