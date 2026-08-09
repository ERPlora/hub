//! **A hub moved between deployments: another installation's rows** — ADR-0273 D8, hub#558.
//!
//! `NumeroInstalacion = hub_id` (ADR-0202 invariant, already pinned by tests). A different
//! `hub_id` is a different installation, a different SIF and a **new chain** with
//! `PrimerRegistro=S`. So a profile stamped with somebody else's `system_id` must not carry on
//! filing as if nothing happened — carrying on is how two chains get mixed, and a record the tax
//! authority already accepted is neither re-sent nor deleted (ADR-0189).
//!
//! The refusal was already built (`fiscal.installation_mismatch`, hub#556) and the mode already
//! derived. What this covers is the pair that only shows up assembled: the **boot noticing** and
//! the **explicit way out**, driven through the real doors — `Runtime::refresh_fiscal_profile`
//! and `Runtime::execute_command`.
use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::fiscal_profile::{BlockedReason, FiscalMode};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

const HUB: &str = "hub-restored";
const ORIGIN: &str = "hub-where-these-rows-were-written";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_adopt558")
        .join(name)
}

fn admin_ctx() -> RequestContext {
    RequestContext::new(HUB, "u1", ["*".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn code_of(err: &RuntimeError) -> String {
    match err {
        RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

async fn set_setting(rt: &Runtime, key: &str, value: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("key".into(), json!(key));
    p.insert("value".into(), json!(value));
    p.insert("now".into(), json!("2026-08-09T10:00:00Z"));
    rt.db()
        .execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at) \
             VALUES (:hub_id, :key, :value, :now) \
             ON CONFLICT (hub_id, key) DO UPDATE SET value = EXCLUDED.value",
            &p,
        )
        .await
        .unwrap();
}

/// A Spanish hub filing for real, with a provider of its regime mounted — and a profile whose rows
/// say they were written by a **different** installation, which is what a restore into a new
/// deployment leaves behind.
async fn hub_restored_elsewhere() -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    set_setting(&rt, "country_code", "ES").await;
    set_setting(&rt, "business_tax_id", "B12345678").await;
    set_setting(&rt, "business_legal_name", "Bar Pepe SL").await;
    rt.install_from_dir(&fixture("fsale")).await.expect("install fsale");
    rt.install_from_dir(&fixture("fprov")).await.expect("install fprov");
    // The trigger events are LEARNT from the healthy provider, so this has to run while it is
    // mounted — same order as a real boot.
    rt.refresh_fiscal_profile().await.unwrap();

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("origin".into(), json!(ORIGIN));
    rt.db()
        .execute(
            "UPDATE _hub_fiscal_profile \
             SET status = 'ACTIVE', environment = 'production', taxpayer_id = 'B12345678', \
                 activated_at = '2026-08-01T09:00:00Z', system_id = :origin \
             WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
    rt
}

/// 🔴 **The whole case, end to end.** The boot notices and flags it, the till stops being able to
/// open a fiscal chain, and the only way forward is somebody adopting the installation on purpose.
#[tokio::test]
async fn a_restored_hub_is_blocked_until_somebody_adopts_the_installation() {
    let rt = hub_restored_elsewhere().await;

    // 1 · The boot notices: derived BLOCKED, and the row flagged for a human.
    let mode = rt.refresh_fiscal_profile().await.unwrap();
    assert_eq!(
        mode,
        FiscalMode::Blocked(BlockedReason::InstallationMismatch)
    );
    assert!(
        rt.fiscal_profile().await.unwrap().unwrap().needs_review,
        "the core does not decide this by itself: it asks for a human (ADR-0249)"
    );

    // 2 · The sale that would open a fiscal chain is refused — with its own code, so the screen
    //     can say *which* problem this is.
    let ctx = admin_ctx();
    let err = rt
        .execute_command(
            "fsale.sales.complete",
            &params(json!({ "total": "1000" })),
            &ctx,
        )
        .await
        .expect_err("this chain is not ours to continue");
    assert_eq!(code_of(&err), "fiscal.installation_mismatch");

    // 3 · The way out is EXPLICIT, and never something the boot did on its own.
    let adopted = rt
        .fiscal_adopt_installation("hub_user:1")
        .await
        .expect("somebody takes the installation over on purpose");
    assert_eq!(adopted.adopted_from, ORIGIN, "where these rows came from");
    assert_eq!(adopted.adopted_by, "hub_user:1");

    // 4 · And the hub files again, under its own `hub_id` — which IS its `NumeroInstalacion`, so
    //     what it opens is a chain of its own.
    assert_eq!(rt.fiscal_mode().await.unwrap(), FiscalMode::Active);
    rt.execute_command(
        "fsale.sales.complete",
        &params(json!({ "total": "1000" })),
        &ctx,
    )
    .await
    .expect("after adopting, the till works");
}

/// **Restarting is not adopting.** However many times the hub boots, nobody takes the foreign
/// installation over — that is the property the whole design hangs from.
#[tokio::test]
async fn restarting_never_adopts_the_installation() {
    let rt = hub_restored_elsewhere().await;

    for _ in 0..3 {
        rt.refresh_fiscal_profile().await.unwrap();
    }

    let profile = rt.fiscal_profile().await.unwrap().unwrap();
    assert_eq!(profile.system_id, ORIGIN, "nobody adopted anything");
    assert_eq!(profile.adopted_at, "", "and nothing pretends they did");
    assert_eq!(
        rt.fiscal_mode().await.unwrap(),
        FiscalMode::Blocked(BlockedReason::InstallationMismatch)
    );
}
