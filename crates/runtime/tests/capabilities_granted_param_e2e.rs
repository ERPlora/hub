//! hub#1425 — `:capabilities_granted`: a module can finally tell whether the owner GRANTED the
//! capabilities it declares, at the point of use, without reading a system table.
//!
//! The hole it closes (verifactu#62). The owner switches VeriFactu on in `/m/verifactu` →
//! Settings. `verifactu.config.save` is plain SQL, so it always succeeds: `capabilities::enforce`
//! (ADR-0079, default-deny) only runs in front of a NATIVE handler. With `certificate` ungranted
//! — the default of any hub whose modules did not arrive through the Apps consent dialog:
//! blueprint, API, import, where grants deliberately do not travel — the hub is left «VeriFactu
//! enabled» and unable to sign or file a single invoice, and the screen had no way to warn.
//!
//! The core already did its half (hub#1191/#1171/#1119): the `invoice.created` listener dies with
//! `module.capability_denied`, and `setup_status` does not call the module configured. What was
//! missing was the MODULE's half — at the point of use, on its own screen.
//!
//! Two properties are asserted here and nowhere else, because only the dispatcher can show them:
//!  · the value is per CALLING MODULE, not one flag for the hub (`nocap` reads 1 while `capg`
//!    reads 0, in the same hub, same instant);
//!  · it tracks the grant live — the same all-or-nothing `capabilities::enforce` applies, so a
//!    half-granted module still reads 0.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};

const ACTOR: &str = "hub_user:admin";

fn fixture(module: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_capgrant")
        .join(module)
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&fixture("capg"))
        .await
        .expect("install capg");
    rt.install_from_dir(&fixture("nocap"))
        .await
        .expect("install nocap");
    rt
}

async fn grant(rt: &Runtime, module: &str, capability: &str, on: bool) {
    erplora_runtime::capabilities::set_grant(
        rt.db(),
        rt.registry(),
        "h1",
        module,
        capability,
        on,
        ACTOR,
    )
    .await
    .expect("the administrator flips the switch");
}

/// What the module's own SELECT sees bound to `:capabilities_granted`.
async fn can_sign(rt: &Runtime, query: &str) -> i64 {
    let page = rt
        .execute_query(query, &Params::new(), &admin())
        .await
        .unwrap_or_else(|e| panic!("`{query}` runs: {e}"));
    page.first()
        .expect("one row")
        .get("can_sign")
        .and_then(|v| v.as_i64())
        .expect("`can_sign` comes back as 0/1")
}

#[tokio::test]
async fn a_module_reads_zero_until_every_capability_it_declares_is_granted() {
    let rt = runtime().await;

    // Default-deny (ADR-0079): nobody granted anything, so the screen can warn.
    assert_eq!(
        can_sign(&rt, "capg.config_get").await,
        0,
        "default-deny reads 0"
    );

    // Half of them is still 0 — the same all-or-nothing the gate applies. This is the case that
    // makes «re-deriving it in the module's own SQL» wrong: an OR would read 1 here and the
    // handler would still be denied.
    grant(&rt, "capg", "network", true).await;
    assert_eq!(
        can_sign(&rt, "capg.config_get").await,
        0,
        "half granted is not granted"
    );

    grant(&rt, "capg", "certificate", true).await;
    assert_eq!(
        can_sign(&rt, "capg.config_get").await,
        1,
        "all granted reads 1"
    );

    // Revoking is visible on the next call: nothing is cached past the grant.
    grant(&rt, "capg", "network", false).await;
    assert_eq!(
        can_sign(&rt, "capg.config_get").await,
        0,
        "a revoke reads 0 again"
    );
}

#[tokio::test]
async fn the_answer_is_per_calling_module_not_one_flag_for_the_hub() {
    let rt = runtime().await;

    // Same hub, same instant, two modules: the one that declares nothing has nothing to be
    // granted and reads 1, while its neighbour is still denied. Without this, `:capabilities_granted`
    // would be a hub-wide flag and every module would paint its neighbour's state.
    assert_eq!(can_sign(&rt, "nocap.config_get").await, 1);
    assert_eq!(can_sign(&rt, "capg.config_get").await, 0);

    // And granting `capg` does not change what `nocap` sees, nor the reverse.
    grant(&rt, "capg", "network", true).await;
    grant(&rt, "capg", "certificate", true).await;
    assert_eq!(can_sign(&rt, "capg.config_get").await, 1);
    assert_eq!(can_sign(&rt, "nocap.config_get").await, 1);
}

#[tokio::test]
async fn a_caller_cannot_grant_itself_by_putting_the_key_in_its_own_payload() {
    let rt = runtime().await;
    let mut forged = Params::new();
    forged.insert("capabilities_granted".into(), serde_json::json!(1));

    let page = rt
        .execute_query("capg.config_get", &forged, &admin())
        .await
        .expect("the query runs");
    assert_eq!(
        page[0]["can_sign"].as_i64(),
        Some(0),
        "the runtime overwrites the key AFTER cloning the payload, like `:hub_id`"
    );
}
