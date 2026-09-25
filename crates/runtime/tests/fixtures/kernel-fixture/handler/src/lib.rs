//! Tier 2 guest of the kernel conformance fixture (ERPlora/hub#1238).
//!
//! Deliberately minimal: it exercises the four halves of the host↔guest contract frozen in
//! `contracts/kernel/guest.snapshot`, and nothing else.
//!
//! 1. `Input` arrives as `{ payload, context }` and the guest reads ids ONLY from
//!    `context.new_ids` — the host is the sole authority of ids (ARQUITECTURA.md §5.3).
//! 2. `Output.operations` describes INTENTIONS by command name + params; the host validates each
//!    one against the module's own SQL commands and runs them in one transaction.
//! 3. `Output.events` names events the host enqueues in the outbox after the writes land.
//! 4. `Output.error` is the ONLY channel a business refusal travels on: the host turns it into
//!    `RuntimeError::Domain { code }`, which is what the browser can translate. The `Err` arm is
//!    reserved for a broken guest contract.
//!
//! 5. `context.principal` (`human` | `machine`, hub#2113) is echoed back in `Output.result`, so the
//!    suite proves the WASM path tells a guest WHO is calling (hub#2117).
//!
//! `escape_to` exists so the suite can prove the HOST refuses an operation naming a command the
//! module does not own — the guest is allowed to ask; the kernel is what says no.

use erplora_guest_sdk::{DomainError, Event, Operation, Output};
use serde_json::{json, Map, Value};

#[cfg(feature = "guest")]
use extism_pdk::*;

/// The pure half: `Input` value in, `Output` out. Compiled natively too, so it is unit-testable
/// without a wasm runtime.
pub fn handle_pure(input: Value) -> Output {
    let names: Vec<String> = input["payload"]["names"]
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();

    if names.is_empty() {
        let mut out = Output::new();
        out.error = Some(DomainError::new(
            "kfx.empty_batch",
            "a bulk insert needs at least one name",
        ));
        return out;
    }

    // Ids come from the host's batch and from nowhere else: the sandbox has no randomness, and
    // minting an id here would take the authority of ids away from the kernel.
    let new_ids: Vec<&str> = input["context"]["new_ids"]
        .as_array()
        .map(|ids| ids.iter().filter_map(Value::as_str).collect())
        .unwrap_or_default();

    // The command every operation names. Normally the module's own `kfx._insert_item`; the suite
    // overrides it to prove the host refuses a foreign one.
    let target = input["payload"]["escape_to"]
        .as_str()
        .unwrap_or("kfx._insert_item")
        .to_string();

    let mut out = Output::new();
    for (i, name) in names.iter().enumerate() {
        let Some(id) = new_ids.get(i) else {
            // More rows than the host offered ids for. Refuse: half a batch is worse than none.
            let mut refused = Output::new();
            refused.error = Some(DomainError::new(
                "kfx.empty_batch",
                "the host did not offer enough ids for this batch",
            ));
            return refused;
        };
        let mut params = Map::new();
        params.insert("id".to_string(), json!(id));
        params.insert("name".to_string(), json!(name));
        out = out.with_operation(Operation::sql(&target, params));
    }
    out = out.with_event(Event::new(
        "kfx.items.bulked",
        json!({ "count": names.len() }),
    ));
    out.with_result(json!({
        "count": names.len(),
        "principal": input["context"]["principal"],
    }))
}

#[cfg(feature = "guest")]
#[plugin_fn]
pub fn handle(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(handle_pure(input.into_inner().into_value())))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input(names: Value) -> Value {
        json!({
            "payload": { "names": names },
            "context": { "new_ids": ["id-1", "id-2", "id-3"] }
        })
    }

    #[test]
    fn one_operation_per_name_taking_ids_from_the_host() {
        let out = handle_pure(input(json!(["a", "b"])));
        assert_eq!(out.operations.len(), 2);
        assert_eq!(out.operations[0].command, "kfx._insert_item");
        assert_eq!(out.operations[0].params["id"], json!("id-1"));
        assert_eq!(out.events.len(), 1);
        assert!(out.error.is_none());
    }

    #[test]
    fn echoes_who_is_calling_from_the_host_context() {
        let mut value = input(json!(["a"]));
        value["context"]["principal"] = json!("machine");
        let out = handle_pure(value);
        assert_eq!(out.result.unwrap()["principal"], json!("machine"));
    }

    #[test]
    fn an_empty_batch_is_a_domain_refusal_not_a_broken_contract() {
        let out = handle_pure(input(json!([])));
        assert_eq!(out.error.unwrap().code, "kfx.empty_batch");
        assert!(out.operations.is_empty());
    }
}
