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
use erplora_db::testutil::{fresh_db, TestDb};
use erplora_db::DatabaseAdapter;
use erplora_runtime::native::{NativeHandler, NativeHost, PendingObligation};
use erplora_runtime::{Runtime, RuntimeError};
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
    rt.uninstall("dbase")
        .await
        .expect("and now `dbase` is free");
    assert_eq!(installed(&rt), vec!["dloose"]);
}

#[tokio::test]
async fn force_is_the_owner_who_was_shown_the_list_and_said_yes() {
    let mut rt = hub_with_chain().await;

    let mut also = rt
        .uninstall_forced("dbase")
        .await
        .expect("an explicit confirmation is a decision, not a mistake to block");
    also.sort();

    // hub#2545: the list the owner confirmed is the list of what goes WITH it (Odoo, Business
    // Central). Leaving `dmid` and `dtop` installed without `dbase` is what kept them «Active» on
    // a dependency that no longer exists and brought `dbase` back on the next boot.
    assert_eq!(also, vec!["dmid", "dtop"], "the answer names what went with it");
    assert_eq!(installed(&rt), vec!["dloose"]);
}

#[tokio::test]
async fn after_a_forced_uninstall_the_next_boot_has_nothing_to_bring_back() {
    let tdb = TestDb::new().await;
    let mut rt = Runtime::with_hub_id(Box::new(tdb.adapter().await), "h2545");
    rt.ensure_system_tables().await.unwrap();
    for m in ["dbase", "dmid", "dtop", "dloose"] {
        rt.install_from_dir(&fixture(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    rt.uninstall_forced("dbase").await.expect("confirmed");

    // The next boot over the same data, with the download cache emptied (every cloud redeploy).
    // Whatever `hub_module` still says is installed but cannot be registered is re-downloaded, and
    // the install plan drags in its missing dependencies: a surviving `dmid` row is exactly how the
    // removed `dbase` came back on its own (hub#2545).
    let mut rebooted = Runtime::with_hub_id(Box::new(tdb.adapter().await), "h2545");
    rebooted.ensure_system_tables().await.unwrap();
    let empty_cache = std::env::temp_dir().join(format!("erplora-2545-{}", std::process::id()));
    rebooted
        .rehydrate_installed(&empty_cache)
        .await
        .expect("rehydrate");
    let to_redownload = rebooted.installed_but_unregistered().await.expect("read");
    assert!(
        to_redownload.iter().all(|(id, _)| id == "dloose"),
        "nothing that depended on the removed app may be brought back at boot, got {to_redownload:?}"
    );
}

#[tokio::test]
async fn the_dependents_that_went_with_it_are_named_the_farthest_first() {
    let mut rt = hub_with_chain().await;

    // `dtop` needs `dmid`, which needs `dbase`: the answer (and the live frames the server sends
    // from it) lists them in the order they left, so `dtop` is never announced after the app it
    // stood on.
    let also = rt.uninstall_forced("dbase").await.expect("confirmed");
    assert_eq!(also, vec!["dtop", "dmid"]);
}

#[tokio::test]
async fn a_forced_uninstall_that_fails_halfway_leaves_no_app_without_its_dependency() {
    let tdb = TestDb::new().await;
    let db = tdb.adapter().await;
    let mut rt = Runtime::with_hub_id(Box::new(tdb.adapter().await), "h2545");
    rt.ensure_system_tables().await.unwrap();
    for m in ["dbase", "dmid", "dtop", "dloose"] {
        rt.install_from_dir(&fixture(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    // Removing `dmid`'s row fails, the way a lock or a lost connection would.
    db.execute_batch(
        "CREATE FUNCTION refuse_dmid_delete() RETURNS trigger LANGUAGE plpgsql AS $$ \
            BEGIN IF OLD.module_id = 'dmid' THEN RAISE EXCEPTION 'simulated failure'; END IF; \
            RETURN OLD; END $$; \
         CREATE TRIGGER refuse_dmid BEFORE DELETE ON hub_module FOR EACH ROW \
            EXECUTE FUNCTION refuse_dmid_delete();",
    )
    .await
    .unwrap();

    let before = db.query("SELECT module_id, hub_id FROM hub_module ORDER BY module_id", &Default::default()).await.unwrap().rows;
    eprintln!("DEBUG before={before:?}");
    let r = rt.uninstall_forced("dbase").await;
    eprintln!("DEBUG result={r:?}");
    assert!(r.is_err(), "the failure must surface");

    // The farthest go first, so whatever survives still has what it needs: `dmid` stays with
    // `dbase` under it. Removing `dbase` first would leave `dmid` in `hub_module` on a dependency
    // that no longer exists — exactly what dragged a removed app back in at boot (hub#2545).
    let rows = db
        .query(
            "SELECT module_id FROM hub_module ORDER BY module_id",
            &Default::default(),
        )
        .await
        .unwrap()
        .rows;
    let left: Vec<&str> = rows
        .iter()
        .filter_map(|r| r["module_id"].as_str())
        .collect();
    assert_eq!(left, vec!["dbase", "dloose", "dmid"]);
}

#[tokio::test]
async fn force_does_not_take_a_dependent_that_still_owes_records() {
    let mut rt = hub_with_chain().await;
    rt.register_native("dtop", Arc::new(OwingEngine { module: "dtop", count: 2 }));

    // Removing `dbase` now takes `dtop` with it, so `dtop`'s engine is asked too: the same rule as
    // switching off a chain (HUB-F28). Asking only the app the owner clicked was the back door
    // that let records owed to the AEAT be orphaned through their dependency (hub#2545).
    let err = rt
        .uninstall_forced("dbase")
        .await
        .expect_err("a dependent that owes records holds the whole chain");
    assert!(
        matches!(err, RuntimeError::Domain { ref code, .. } if code == "dtop.unsent_records"),
        "expected the retention refusal of the dependent, got {err:?}"
    );
    assert_eq!(
        installed(&rt),
        vec!["dbase", "dloose", "dmid", "dtop"],
        "a refused uninstall must not half-apply"
    );
}

#[tokio::test]
async fn a_module_that_is_not_installed_still_reports_that_and_not_the_dependents_error() {
    let mut rt = hub_with_chain().await;

    let err = rt
        .uninstall("nope")
        .await
        .expect_err("nothing to uninstall");
    assert!(
        matches!(err, RuntimeError::CommandNotFound(_)),
        "expected the usual not-installed error, got {err:?}"
    );
}

/// The engine of `module`, owing `count` units of work to an external authority (hub#314).
#[derive(Debug)]
struct OwingEngine {
    module: &'static str,
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
            oldest_pending_at: None,
            code: format!("{}.unsent_records", self.module),
            message: format!("{} record(s) still unsent", self.count),
        }))
    }
}

#[tokio::test]
async fn force_does_not_open_the_retention_gate() {
    let mut rt = hub_with_chain().await;
    rt.register_native("dloose", Arc::new(OwingEngine { module: "dloose", count: 4 }));

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
