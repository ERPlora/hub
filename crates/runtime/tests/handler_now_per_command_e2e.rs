//! hub#2166 — a handler command sees ONE `:now`, shared by every operation it returns.
//!
//! The declarative path binds `system_params` once per command, so every `sql[]` statement of
//! the command shares the same `:now`. The handler path (WASM and native) minted a fresh `:now`
//! for EACH operation, plus two more for the handler's own `payload.now` and `context.now`. The
//! pattern that broke (appointments#196): operation 1 stamps `updated_at = :now`, operation 2
//! writes the history row anchored on `WHERE updated_at = :now` → 0 rows, no error, and the
//! history silently loses the change.
//!
//! Contract under test:
//!  - operation 2 finds the row operation 1 stamped, through `:now`;
//!  - the handler's `context.now` and `payload.now` are that same instant, so a handler that
//!    computes with the clock it was given agrees with what its operations write;
//!  - the command's declared event carries that same `now` in its payload;
//!  - two separate commands still get two different instants (the clock is per command, not
//!    frozen).
//!
//! The handler is NATIVE on purpose: it shares `persist_handler_output` with WASM (same trick as
//! `handler_new_ids_e2e.rs`) without compiling a `.wasm` in tests.
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{native::NativeHandler, RequestContext, Runtime};
use erplora_wasm_host::{Operation, Output};
use serde_json::{json, Value as Json};

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_now_per_command")
        .join("npc")
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Two SEPARATE operations: `_stamp` sets `updated_at = :now`, `_trail` inserts a history row
/// only where `updated_at = :now` — the appointments#196 shape. It also forwards the clock the
/// handler itself was given (`context.now`, `payload.now`) so the test can compare them.
#[derive(Debug)]
struct TwoStepHandler;

#[async_trait]
impl NativeHandler for TwoStepHandler {
    async fn call(
        &self,
        _function: &str,
        input: &Json,
        _host: &dyn erplora_runtime::native::NativeHost,
    ) -> Result<Output, erplora_runtime::errors::RuntimeError> {
        let id = input["payload"]["id"].clone();

        let mut stamp = serde_json::Map::new();
        stamp.insert("id".into(), id.clone());

        let mut trail = serde_json::Map::new();
        trail.insert("id".into(), id);
        trail.insert("handler_now".into(), input["context"]["now"].clone());
        trail.insert("payload_now".into(), input["payload"]["now"].clone());

        Ok(Output::new()
            .with_operation(Operation::sql("npc._stamp", stamp))
            .with_operation(Operation::sql("npc._trail", trail)))
    }
}

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.expect("install npc");
    rt.register_native("npc", Arc::new(TwoStepHandler));
    rt
}

async fn touch(rt: &Runtime, id: &str) {
    let params: Params = json!({ "id": id }).as_object().cloned().unwrap_or_default();
    rt.execute_command("npc.touch", &params, &admin())
        .await
        .expect("npc.touch runs");
}

async fn trail_rows(rt: &Runtime) -> Vec<Json> {
    rt.db_for_test()
        .query(
            "SELECT item_id, stamped_at, handler_now, payload_now FROM npc_trail ORDER BY item_id",
            &Params::new(),
        )
        .await
        .expect("read npc_trail")
        .rows
}

/// The regression: the second operation anchors on the `:now` the first one wrote.
#[tokio::test]
async fn a_second_operation_finds_the_row_the_first_stamped_with_now() {
    let rt = runtime().await;
    touch(&rt, "a1").await;

    let rows = trail_rows(&rt).await;
    assert_eq!(
        rows.len(),
        1,
        "the history row anchored on `updated_at = :now` must be written — every operation of \
         one command sees the same `:now` (hub#2166), got {rows:?}"
    );
}

/// The handler's own clock is the command's clock: `context.now` and `payload.now` equal the
/// `:now` its operations bind.
#[tokio::test]
async fn the_handler_context_and_payload_now_are_the_operations_now() {
    let rt = runtime().await;
    touch(&rt, "a1").await;

    let rows = trail_rows(&rt).await;
    let row = rows.first().expect("the history row exists");
    assert_eq!(
        row["handler_now"], row["stamped_at"],
        "context.now must be the command's :now"
    );
    assert_eq!(
        row["payload_now"], row["stamped_at"],
        "payload.now must be the command's :now"
    );
}

/// The declared event travels with the command's `now`, not a third instant of its own.
#[tokio::test]
async fn the_declared_event_carries_the_operations_now() {
    let rt = runtime().await;
    touch(&rt, "a1").await;

    let stamped = trail_rows(&rt).await.first().expect("the history row exists")["stamped_at"]
        .clone();
    let events = rt
        .db_for_test()
        .query(
            "SELECT payload FROM _event_outbox WHERE event_name = 'npc.touched'",
            &Params::new(),
        )
        .await
        .expect("read _event_outbox")
        .rows;
    assert_eq!(events.len(), 1, "the declared event is enqueued: {events:?}");
    let payload: Json = match &events[0]["payload"] {
        Json::String(text) => serde_json::from_str(text).expect("payload is JSON"),
        other => other.clone(),
    };
    assert_eq!(
        payload["now"], stamped,
        "the declared event's payload.now must be the command's :now"
    );
}

/// The clock is minted per command, not frozen: two commands stamp two different instants.
#[tokio::test]
async fn two_commands_get_two_different_instants() {
    let rt = runtime().await;
    touch(&rt, "a1").await;
    touch(&rt, "a2").await;

    let rows = trail_rows(&rt).await;
    assert_eq!(rows.len(), 2, "both commands write their history: {rows:?}");
    assert_ne!(
        rows[0]["stamped_at"], rows[1]["stamped_at"],
        "each command mints its own :now"
    );
}
