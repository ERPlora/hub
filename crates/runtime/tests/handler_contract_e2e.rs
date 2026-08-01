//! Contrato conjunto hub#70 + hub#139: reads autoritativas, result y errores de dominio.

use std::path::PathBuf;
use std::sync::Arc;

use erplora_db::{testutil::fresh_db, Params};
use erplora_guest_sdk::{DomainError, Event, Operation, Output};
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::{json, Value};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_handler_contract")
}

fn params(value: Value) -> Params {
    value.as_object().cloned().unwrap_or_default()
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "user-1", ["*".to_string()])
}

#[derive(Debug)]
struct ContractHandler;

#[async_trait::async_trait]
impl NativeHandler for ContractHandler {
    async fn call(
        &self,
        function: &str,
        input: &Value,
        _host: &dyn NativeHost,
    ) -> Result<Output, RuntimeError> {
        assert_eq!(
            function, "handle",
            "las reads fallidas cortan antes de llamar al handler"
        );
        let mode = input["payload"]["mode"].as_str().unwrap_or("echo_read");
        let authoritative = input["context"]["reads"]["contract.authoritative"].clone();
        let output = match mode {
            "null" => Output::new(),
            "list" => Output::new().with_result(json!([1, 2, 3])),
            "result_and_effects" => Output::new()
                .with_operation(Operation::sql(
                    "contract._insert",
                    params(json!({ "id": "row-1", "value": "persisted" })),
                ))
                .with_event(Event::new("contract.completed", json!({ "id": "row-1" })))
                .with_result(json!({ "created": "row-1" })),
            "domain_error" => Output::new()
                .with_operation(Operation::sql(
                    "contract._insert",
                    params(json!({ "id": "must-not-exist", "value": "rollback" })),
                ))
                .with_event(Event::new("contract.completed", json!({})))
                .with_error(DomainError::new("contract.rejected", "Operación rechazada")),
            "invalid_domain_error" => {
                Output::new().with_error(DomainError::new("inventory.not_owned", "namespace ajeno"))
            }
            "too_large" => Output::new().with_result(json!("x".repeat(1_100_000))),
            _ => Output::new().with_result(authoritative),
        };
        Ok(output)
    }
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "h1");
    runtime.ensure_system_tables().await.unwrap();
    runtime.install_from_dir(&fixture()).await.unwrap();
    runtime.register_native("contract", Arc::new(ContractHandler));
    runtime
}

#[tokio::test]
async fn required_read_is_server_owned_hub_scoped_and_needs_no_rows_from_caller() {
    let runtime = runtime().await;
    let out = runtime
        .execute_command("contract.handle", &Params::new(), &ctx("h2"))
        .await
        .unwrap();
    assert_eq!(out["result"][0]["hub_id"], json!("h2"));
    assert_eq!(out["result"][0]["source"], json!("server-owned"));
}

#[tokio::test]
async fn result_preserves_null_list_and_result_together_with_operations_and_events() {
    let runtime = runtime().await;
    let null = runtime
        .execute_command(
            "contract.handle",
            &params(json!({ "mode": "null" })),
            &ctx("h1"),
        )
        .await
        .unwrap();
    assert_eq!(null["result"], Value::Null);

    let list = runtime
        .execute_command(
            "contract.handle",
            &params(json!({ "mode": "list" })),
            &ctx("h1"),
        )
        .await
        .unwrap();
    assert_eq!(list["result"], json!([1, 2, 3]));

    let mixed = runtime
        .execute_command(
            "contract.handle",
            &params(json!({ "mode": "result_and_effects" })),
            &ctx("h1"),
        )
        .await
        .unwrap();
    assert_eq!(mixed["result"], json!({ "created": "row-1" }));
    assert_eq!(mixed["operations"], json!(1));
    let rows = runtime
        .execute_query("contract.rows", &Params::new(), &ctx("h1"))
        .await
        .unwrap();
    assert_eq!(rows.len(), 1);
}

#[tokio::test]
async fn domain_error_aborts_all_effects_and_keeps_a_stable_code() {
    let runtime = runtime().await;
    let error = runtime
        .execute_command(
            "contract.handle",
            &params(json!({ "mode": "domain_error" })),
            &ctx("h1"),
        )
        .await
        .unwrap_err();
    assert!(matches!(
        error,
        RuntimeError::Domain { ref code, ref message }
            if code == "contract.rejected" && message == "Operación rechazada"
    ));
    let rows = runtime
        .execute_query("contract.rows", &Params::new(), &ctx("h1"))
        .await
        .unwrap();
    assert!(
        rows.is_empty(),
        "error + operation nunca puede persistir la operación"
    );
}

#[tokio::test]
async fn invalid_or_oversized_output_is_rejected_before_persisting() {
    let runtime = runtime().await;
    let invalid = runtime
        .execute_command(
            "contract.handle",
            &params(json!({ "mode": "invalid_domain_error" })),
            &ctx("h1"),
        )
        .await
        .unwrap_err();
    assert!(matches!(invalid, RuntimeError::Wasm(_)));

    let too_large = runtime
        .execute_command(
            "contract.handle",
            &params(json!({ "mode": "too_large" })),
            &ctx("h1"),
        )
        .await
        .unwrap_err();
    assert!(matches!(
        too_large,
        RuntimeError::HandlerResultTooLarge { .. }
    ));
}

#[tokio::test]
async fn required_read_failure_and_size_limit_abort_before_invoking_handler() {
    let runtime = runtime().await;
    let missing = runtime
        .execute_command("contract.required_missing", &Params::new(), &ctx("h1"))
        .await
        .unwrap_err();
    assert!(matches!(missing, RuntimeError::RequiredReadFailed { .. }));

    let too_large = runtime
        .execute_command("contract.required_too_large", &Params::new(), &ctx("h1"))
        .await
        .unwrap_err();
    assert!(matches!(too_large, RuntimeError::ReadTooLarge { .. }));
}
