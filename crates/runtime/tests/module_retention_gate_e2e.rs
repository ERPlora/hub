//! **hub#314 (ADR-0202 phase 1, guard R2)** — a module that still owes work to an external
//! authority cannot be disabled or uninstalled.
//!
//! `uninstall` used to delete the `hub_module` row without looking at the queue: the VeriFactu
//! records left `pending`/`retry`/`error`/`rejected` became literal orphans — nobody drains them
//! afterwards, so the invoices stay outside the AEAT chain (VeriFactu FAQ §5). Deactivating was
//! the same hole through a quieter door, including the CASCADE: turning off `invoice` drags
//! `verifactu` down with it (ADR-0128), so the gate has to cover the whole fall set or the
//! guard is one click away from being bypassed.
//!
//! These tests drive the REAL path (`Runtime::deactivate` / `Runtime::uninstall`) with a native
//! engine that reports what it owes, so they hold for `verifactu` and for any future first-party
//! engine with the same duty. Postgres real, ephemeral schema per test.
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::testutil::fresh_db;
use erplora_runtime::native::{NativeHandler, NativeHost, PendingObligation};
use erplora_runtime::{ModuleStatus, RuntimeError, Runtime};
use erplora_wasm_host::Output;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_retention314")
        .join(name)
}

/// Native engine of `rowing` that owes `count` units of work to an external authority.
#[derive(Debug)]
struct OwingEngine {
    count: u64,
}

#[async_trait]
impl NativeHandler for OwingEngine {
    async fn call(
        &self,
        _function: &str,
        _input: &serde_json::Value,
        _host: &dyn NativeHost,
    ) -> Result<Output, RuntimeError> {
        unreachable!("the retention gate must not dispatch commands")
    }

    async fn pending_obligations(
        &self,
        _hub_id: &str,
        _host: &dyn NativeHost,
    ) -> Result<Option<PendingObligation>, RuntimeError> {
        Ok((self.count > 0).then(|| PendingObligation {
            count: self.count,
            code: "rowing.unsent_records".to_string(),
            message: format!("{} record(s) still unsent", self.count),
        }))
    }
}

/// `rbase` ← `rowing` (rowing depends on rbase), with rowing's native engine owing `count`.
async fn hub_owing(count: u64) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("rbase")).await.expect("rbase");
    rt.install_from_dir(&fixture("rowing")).await.expect("rowing");
    rt.register_native("rowing", Arc::new(OwingEngine { count }));
    rt
}

fn status_of(rt: &Runtime, id: &str) -> ModuleStatus {
    rt.modules()
        .into_iter()
        .find(|m| m.id == id)
        .map(|m| m.status)
        .unwrap_or_else(|| panic!("`{id}` should still be installed"))
}

fn assert_says_how_many(err: RuntimeError, expected: &str) {
    match err {
        RuntimeError::Domain { code, message } => {
            assert_eq!(
                code, "rowing.unsent_records",
                "the stable namespaced code is what the UI translates (hub#139)"
            );
            assert!(
                message.contains(expected),
                "the refusal must say how many are left, got `{message}`"
            );
        }
        other => panic!("expected a translatable domain rejection, got {other:?}"),
    }
}

#[tokio::test]
async fn deactivating_a_module_with_unsent_records_is_refused_and_changes_nothing() {
    let mut rt = hub_owing(2).await;

    let err = rt
        .deactivate("rowing")
        .await
        .expect_err("2 unsent records must keep the module switched on");
    assert_says_how_many(err, "2");
    assert_eq!(
        status_of(&rt, "rowing"),
        ModuleStatus::Active,
        "a refused deactivation must not half-apply"
    );
}

#[tokio::test]
async fn uninstalling_a_module_with_unsent_records_is_refused_and_keeps_it_installed() {
    let mut rt = hub_owing(7).await;

    let err = rt
        .uninstall("rowing")
        .await
        .expect_err("7 unsent records must keep the module installed");
    assert_says_how_many(err, "7");
    assert_eq!(
        status_of(&rt, "rowing"),
        ModuleStatus::Active,
        "the module and its capabilities must survive the refusal"
    );
    // The persisted row is the thing that used to disappear: check the state the runtime reloads.
    let persisted = rt.installed_but_unregistered().await.expect("read state");
    assert!(
        !persisted.iter().any(|(id, _)| id == "rowing"),
        "rowing must remain registered, not stranded as an installed-but-unknown module"
    );
}

#[tokio::test]
async fn the_cascade_cannot_be_used_to_disable_a_module_that_still_owes_records() {
    let mut rt = hub_owing(3).await;

    // `rowing` depends on `rbase`, so turning off `rbase` would drag `rowing` down (ADR-0128).
    let err = rt
        .deactivate("rbase")
        .await
        .expect_err("the cascade is not a back door around the retention gate");
    assert_says_how_many(err, "3");
    assert_eq!(
        status_of(&rt, "rbase"),
        ModuleStatus::Active,
        "the dependency stays on too: nothing of the refused cascade is applied"
    );
    assert_eq!(status_of(&rt, "rowing"), ModuleStatus::Active);
}

#[tokio::test]
async fn once_everything_is_handed_over_the_module_can_be_disabled_and_removed() {
    let mut rt = hub_owing(0).await;

    rt.deactivate("rowing")
        .await
        .expect("with nothing owed the module switches off as always");
    assert_eq!(status_of(&rt, "rowing"), ModuleStatus::Inactive);

    rt.activate("rowing").await.expect("back on");
    rt.uninstall("rowing")
        .await
        .expect("with nothing owed the module uninstalls as always");
    assert!(
        !rt.modules().iter().any(|m| m.id == "rowing"),
        "the gate must not turn into a permanent lock"
    );
}
