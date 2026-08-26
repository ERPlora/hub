//! **hub#1101** — uninstalling a module OTHER installed modules depend on cannot be a silent
//! `ok: true`.
//!
//! Installing resolves dependencies forward (ADR-0060): asking for `verifactu` drags in `invoice`,
//! `sales` and `inventory`. The inverse door had no gate at all. Removing `taxes` — declared in
//! `depends_on` by `sales`, `inventory`, `invoice` and `services` — answered `{"ok":true}`, the
//! till went on looking perfectly healthy with its «Charge · 2.00 €» button enabled, and the
//! cashier only found out at the moment of charging, when `sales.complete_sale` aborted on a read
//! that no longer had an owner.
//!
//! So the refusal has to happen at the door, and it has to NAME who depends on the module: «this
//! cannot be removed» is not actionable, «`sales`, `invoice` and `services` need it» is.
//!
//! The escape hatch is explicit and separate ([`Runtime::uninstall_forced`]): the owner who was
//! shown the list and confirmed anyway is not blocked by a gate meant for a caller that never saw
//! it (a script, the assistant, a flow, `curl`). What `force` must NEVER open is the fiscal side —
//! see the last test.
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::testutil::fresh_db;
use erplora_runtime::native::{NativeHandler, NativeHost, PendingObligation};
use erplora_runtime::{RuntimeError, Runtime};
use erplora_wasm_host::Output;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_dependents1101")
        .join(name)
}

/// `dbase` ← `dmid` ← `dtop`, plus `dloose` which depends on nobody.
async fn hub_with_chain() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    for m in ["dbase", "dmid", "dtop", "dloose"] {
        rt.install_from_dir(&fixture(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    rt
}

fn installed(rt: &Runtime) -> Vec<String> {
    let mut ids: Vec<String> = rt.modules().into_iter().map(|m| m.id).collect();
    ids.sort();
    ids
}

/// The refusal, with the dependents it names (sorted, so the assertions do not depend on registry
/// order).
fn dependents_named(err: RuntimeError) -> Vec<String> {
    match err {
        RuntimeError::HasDependents { mut dependents, .. } => {
            dependents.sort();
            dependents
        }
        other => panic!("expected the dependents gate to refuse, got {other:?}"),
    }
}

#[tokio::test]
async fn uninstalling_a_module_others_depend_on_is_refused_and_names_them() {
    let mut rt = hub_with_chain().await;

    let err = rt
        .uninstall("dbase")
        .await
        .expect_err("`dmid` needs `dbase`: this is the ok:true that killed the till");

    // Transitive on purpose: `dtop` does not declare `dbase`, but it stops working all the same.
    // Naming only the direct dependant would under-report exactly what the owner has to weigh.
    assert_eq!(dependents_named(err), vec!["dmid", "dtop"]);
    assert_eq!(
        installed(&rt),
        vec!["dbase", "dloose", "dmid", "dtop"],
        "a refused uninstall must not half-apply"
    );
}

#[tokio::test]
async fn the_refusal_leaves_the_module_registered_for_the_next_boot() {
    let mut rt = hub_with_chain().await;

    rt.uninstall("dbase").await.expect_err("refused");

    // The `hub_module` row is what the runtime reloads: a module removed from the registry but
    // still persisted comes back as installed-but-unknown on the next boot.
    let stranded = rt.installed_but_unregistered().await.expect("read state");
    assert!(
        !stranded.iter().any(|(id, _)| id == "dbase"),
        "`dbase` must stay a normal installed module, not a stranded row"
    );
}

#[tokio::test]
async fn a_module_nobody_depends_on_uninstalls_with_no_new_friction() {
    let mut rt = hub_with_chain().await;

    rt.uninstall("dloose")
        .await
        .expect("nothing declares `dloose`: the gate must not tax the normal case");
    assert_eq!(installed(&rt), vec!["dbase", "dmid", "dtop"]);
}

#[tokio::test]
async fn the_top_of_the_chain_is_never_blocked_by_what_it_itself_depends_on() {
    let mut rt = hub_with_chain().await;

    // `dtop` depends on `dmid`; nobody depends on `dtop`. The gate looks DOWNSTREAM only — reading
    // it the other way round would make a dependency chain impossible to dismantle at all.
    rt.uninstall("dtop").await.expect("nothing needs `dtop`");
    rt.uninstall("dmid")
        .await
        .expect("with `dtop` gone, nothing needs `dmid` either");
    rt.uninstall("dbase").await.expect("and now `dbase` is free");
    assert_eq!(installed(&rt), vec!["dloose"]);
}

#[tokio::test]
async fn force_is_the_owner_who_was_shown_the_list_and_said_yes() {
    let mut rt = hub_with_chain().await;

    rt.uninstall_forced("dbase")
        .await
        .expect("an explicit confirmation is a decision, not a mistake to block");
    assert_eq!(installed(&rt), vec!["dloose", "dmid", "dtop"]);
}

#[tokio::test]
async fn a_module_that_is_not_installed_still_reports_that_and_not_the_dependents_error() {
    let mut rt = hub_with_chain().await;

    let err = rt.uninstall("nope").await.expect_err("nothing to uninstall");
    assert!(
        matches!(err, RuntimeError::CommandNotFound(_)),
        "expected the usual not-installed error, got {err:?}"
    );
}

/// The engine of `dloose`, owing `count` units of work to an external authority (hub#314).
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
        unreachable!("the gate must not dispatch commands")
    }

    async fn pending_obligations(
        &self,
        _hub_id: &str,
        _host: &dyn NativeHost,
    ) -> Result<Option<PendingObligation>, RuntimeError> {
        Ok((self.count > 0).then(|| PendingObligation {
            count: self.count,
            code: "dloose.unsent_records".to_string(),
            message: format!("{} record(s) still unsent", self.count),
        }))
    }
}

#[tokio::test]
async fn force_does_not_open_the_retention_gate() {
    let mut rt = hub_with_chain().await;
    rt.register_native("dloose", Arc::new(OwingEngine { count: 4 }));

    // `force` is the answer to ONE question — «other apps need this, remove it anyway?» — and the
    // owner can answer it. Whether records still owed to a tax authority may be orphaned is not
    // that question and is not theirs (ADR-0202 guard R2), so the flag must not reach it.
    let err = rt
        .uninstall_forced("dloose")
        .await
        .expect_err("force must never be a way past the retention gate");
    assert!(
        matches!(err, RuntimeError::Domain { ref code, .. } if code == "dloose.unsent_records"),
        "expected the retention refusal, got {err:?}"
    );
    assert!(
        rt.modules().iter().any(|m| m.id == "dloose"),
        "the module must survive the refusal"
    );
}
