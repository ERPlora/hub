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

/// 🔴 Proof the guard catches the positive at RUN time too: a handler returning a code outside the
/// catalogue is a broken guest contract (`Wasm`, naming the code), never a `Domain` the UI would try
/// to translate — while the same handler returning a declared code travels as `Domain`.
///
/// Driven through a native handler on a copy of the fixture: `Output.error` shares the exact code
/// path with the WASM guest (`commands::persist_handler_output`), and this lets the test choose the
/// code without recompiling a guest for every case.
#[tokio::test]
async fn a_handler_code_outside_the_catalogue_is_a_broken_contract_not_a_domain_error_hub1238() {
    use std::sync::Arc;

    use async_trait::async_trait;
    use erplora_runtime::native::{NativeHandler, NativeHost};
    use erplora_wasm_host::{guest_sdk::DomainError, Output};

    /// Refuses with whatever code the payload names — the test drives the code.
    #[derive(Debug)]
    struct RefusingHandler;

    #[async_trait]
    impl NativeHandler for RefusingHandler {
        async fn call(
            &self,
            _function: &str,
            input: &serde_json::Value,
            _host: &dyn NativeHost,
        ) -> Result<Output, RuntimeError> {
            let code = input["payload"]["code"]
                .as_str()
                .expect("the test names the code");
            let mut out = Output::new();
            out.error = Some(DomainError::new(code, "refused by the test handler"));
            Ok(out)
        }
    }

    let native = broken_copy("native-refusal", |m| {
        m["commands"]["kfx.items.bulk"]["handler"] =
            json!({ "type": "native", "function": "refuse" });
    });

    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(native.path())
        .await
        .expect("install the native variant");
    rt.register_native(MODULE_ID, Arc::new(RefusingHandler));

    let mut declared = Params::new();
    declared.insert("code".into(), json!("kfx.not_found"));
    match rt
        .execute_command("kfx.items.bulk", &declared, &admin())
        .await
        .expect_err("the handler refuses")
    {
        RuntimeError::Domain { code, .. } => assert_eq!(code, "kfx.not_found"),
        other => panic!("a declared code is a Domain refusal, got {other:?}"),
    }

    let mut smuggled = Params::new();
    smuggled.insert("code".into(), json!("kfx.smuggled"));
    match rt
        .execute_command("kfx.items.bulk", &smuggled, &admin())
        .await
        .expect_err("the code is outside `errors`")
    {
        RuntimeError::Wasm(detail) => assert!(
            detail.contains("kfx.smuggled") && detail.contains(MODULE_ID),
            "the broken contract names the module and the code: {detail}"
        ),
        other => panic!("an undeclared code is a broken guest contract, got {other:?}"),
    }
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
