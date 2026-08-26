//! ADR-0398 (hub#1177): a module DECLARES the domain error codes it provides in
//! `module.json → errors`. With the block present the runtime is strict — an undeclared
//! `Output.error` code is a broken guest contract (`Wasm`), never a `Domain` the UI would
//! translate — and the installer refuses an `expect_rows.error` outside the catalog. Without the
//! block (the 14 published modules that emit codes today) nothing changes.
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{native::NativeHandler, RequestContext, Runtime, RuntimeError};
use erplora_wasm_host::Output;
use serde_json::{json, Value as Json};

fn fixture(variant: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_errors1177")
        .join(variant)
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Rejects with whatever code the payload names — the test drives which code is emitted.
#[derive(Debug)]
struct RejectingHandler;

#[async_trait]
impl NativeHandler for RejectingHandler {
    async fn call(
        &self,
        _function: &str,
        input: &Json,
        _host: &dyn erplora_runtime::native::NativeHost,
    ) -> Result<Output, RuntimeError> {
        let code = input["payload"]["code"]
            .as_str()
            .expect("the test names the code");
        let mut output = Output::new();
        output.error = Some(erplora_wasm_host::guest_sdk::DomainError::new(
            code,
            "refused by the test",
        ));
        Ok(output)
    }
}

async fn runtime(variant: &str) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture(variant))
        .await
        .unwrap_or_else(|e| panic!("install {variant}: {e}"));
    rt.register_native("e1177", Arc::new(RejectingHandler));
    rt
}

async fn reject(rt: &Runtime, code: &str) -> RuntimeError {
    let params: Params = json!({ "code": code }).as_object().cloned().unwrap();
    rt.execute_command("e1177.reject", &params, &admin())
        .await
        .expect_err("the handler always rejects")
}

#[tokio::test]
async fn declared_code_still_travels_as_a_domain_error() {
    let rt = runtime("declared").await;
    match reject(&rt, "e1177.refused").await {
        RuntimeError::Domain { code, .. } => assert_eq!(code, "e1177.refused"),
        other => panic!("expected Domain, got {other:?}"),
    }
}

#[tokio::test]
async fn deprecated_code_is_still_a_domain_error() {
    let rt = runtime("declared").await;
    assert!(matches!(
        reject(&rt, "e1177.old").await,
        RuntimeError::Domain { .. }
    ));
}

#[tokio::test]
async fn undeclared_code_with_catalog_present_is_a_broken_guest_contract() {
    let rt = runtime("declared").await;
    match reject(&rt, "e1177.not_in_catalog").await {
        RuntimeError::Wasm(msg) => assert!(
            msg.contains("e1177.not_in_catalog") && msg.contains("errors"),
            "the message names the code and the catalog: {msg}"
        ),
        other => panic!("expected Wasm (unexpected), got {other:?}"),
    }
}

#[tokio::test]
async fn without_catalog_any_own_namespace_code_is_a_domain_error_as_before() {
    let rt = runtime("lenient").await;
    assert!(matches!(
        reject(&rt, "e1177.whatever").await,
        RuntimeError::Domain { .. }
    ));
}

#[tokio::test]
async fn install_refuses_expect_rows_error_outside_the_catalog() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let err = rt
        .install_from_dir(&fixture("undeclared_expect"))
        .await
        .expect_err("expect_rows.error must be declared when the catalog exists");
    let msg = err.to_string();
    assert!(
        msg.contains("e1177.missing") && msg.contains("e1177.close"),
        "the refusal names the command and the code: {msg}"
    );
}

#[tokio::test]
async fn module_info_exposes_the_declared_catalog() {
    let rt = runtime("declared").await;
    let info = rt
        .modules()
        .into_iter()
        .find(|m| m.id == "e1177")
        .expect("installed");
    let codes: Vec<&str> = info.errors.iter().map(|e| e.code.as_str()).collect();
    assert_eq!(codes, vec!["e1177.old", "e1177.refused"], "sorted, stable");
    assert_eq!(
        info.errors
            .iter()
            .find(|e| e.code == "e1177.old")
            .unwrap()
            .deprecated
            .as_deref(),
        Some("1.0.0")
    );
    assert!(info
        .errors
        .iter()
        .find(|e| e.code == "e1177.refused")
        .unwrap()
        .deprecated
        .is_none());
}
