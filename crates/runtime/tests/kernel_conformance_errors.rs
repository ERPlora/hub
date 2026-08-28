//! KCS · errors — the catalogue of domain codes (ADR-0398 / ADR-0412).
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! The kernel emits CODES, never prose: the browser translates a code, it cannot translate a
//! sentence the runtime made up. A module that declares `errors` is in strict mode — a code the
//! catalogue does not list is a broken contract, refused at install (`expect_rows.error`) or
//! surfaced as `Wasm` rather than as a `Domain` the UI would try to translate.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{Runtime, RuntimeError};
use kernel_fixture::{admin, broken_copy, install_fixture, MODULE_ID};
use serde_json::json;

/// The catalogue reaches `/api/modules` through `ModuleInfo`, sorted and with its `deprecated`
/// marks — consumers read this instead of guessing from prose.
#[tokio::test]
async fn the_declared_catalogue_is_served_sorted_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let info = rt
        .modules()
        .into_iter()
        .find(|m| m.id == MODULE_ID)
        .expect("installed");
    let codes: Vec<&str> = info.errors.iter().map(|e| e.code.as_str()).collect();
    assert_eq!(
        codes,
        vec!["kfx.empty_batch", "kfx.not_found", "kfx.retired"]
    );
    assert_eq!(
        info.errors
            .iter()
            .find(|e| e.code == "kfx.retired")
            .unwrap()
            .deprecated
            .as_deref(),
        Some("1.1.0"),
        "a retired code stays in the catalogue, marked"
    );
    assert!(info
        .errors
        .iter()
        .find(|e| e.code == "kfx.not_found")
        .unwrap()
        .deprecated
        .is_none());
}

/// A declared code travels to the caller as a `Domain` error carrying the code itself.
#[tokio::test]
async fn a_declared_code_reaches_the_caller_as_a_code_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("id".into(), json!("no-such-item"));
    match rt
        .execute_command("kfx.item.archive", &p, &admin())
        .await
        .expect_err("nothing matched")
    {
        RuntimeError::Domain { code, message } => {
            assert_eq!(code, "kfx.not_found");
            assert!(
                !message.is_empty(),
                "the message is a developer hint; the CODE is the contract"
            );
        }
        other => panic!("expected Domain, got {other:?}"),
    }
}

/// 🔴 Proof the guard catches the positive: an `expect_rows.error` outside the catalogue is refused
/// AT INSTALL, naming both the command and the code — the module never reaches a customer's hub
/// able to emit a code nothing can translate.
#[tokio::test]
async fn install_refuses_an_expect_rows_code_outside_the_catalogue_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let broken = broken_copy("undeclared-code", |m| {
        m["commands"]["kfx.item.archive"]["expect_rows"]["error"] = json!("kfx.missing_code");
    });

    let err = rt
        .install_from_dir(broken.path())
        .await
        .expect_err("the code is not in `errors`")
        .to_string();
    assert!(
        err.contains("kfx.missing_code") && err.contains("kfx.item.archive"),
        "the refusal names the command and the code: {err}"
    );
}

/// …and the same manifest WITH the code declared installs: the guard is about the catalogue, not
/// about the shape of the clause.
#[tokio::test]
async fn the_same_code_declared_installs_fine_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let broken = broken_copy("declared-code", |m| {
        m["commands"]["kfx.item.archive"]["expect_rows"]["error"] = json!("kfx.missing_code");
        m["errors"]["kfx.missing_code"] = json!({});
    });

    rt.install_from_dir(broken.path())
        .await
        .expect("declaring the code is all it took");
}
