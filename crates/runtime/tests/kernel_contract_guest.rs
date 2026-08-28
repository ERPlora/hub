//! `contracts/kernel/guest.snapshot` ≡ the WASM guest contract — ERPlora/hub#1235.
//!
//! Regression test for ERPlora/hub#1235. A Tier-2 module ships a compiled `.wasm`: it talks to the
//! hub through exactly two JSON shapes (`Input`, `Output`) and runs under three limits. Renaming a
//! field of `Output` breaks every published handler at once and no `cargo build` anywhere would
//! say so, because the guests are already binaries.
//!
//! Everything here is derived by SERIALISING real values, never by copying a list of names: what
//! the file records is what actually crosses the host↔guest wire, `#[serde(transparent)]`,
//! `skip_serializing_if` and renames included.
//!
//! Update: `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_guest`.

use erplora_guest_sdk::{DomainError, Event, Input, Operation, Output};
use erplora_wasm_host::WasmLimits;
use serde_json::{json, Map, Value};

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;

#[test]
fn guest_snapshot_matches_the_sdk_hub1235() {
    kernel_snapshot::assert_snapshot("guest.snapshot", &generate());
}

/// `Input` is transparent: whatever the host sends arrives verbatim. Asserted rather than
/// described, because "the guest gets the JSON as it is" is the whole input half of the contract.
#[test]
fn guest_input_is_the_json_verbatim_hub1235() {
    let payload = json!({ "sale_id": "s1", "lines": [1, 2] });
    assert_eq!(
        serde_json::to_value(Input::new(payload.clone())).expect("serializar Input"),
        payload,
        "`Input` dejó de ser transparente: el guest ya no recibe el JSON tal cual"
    );
}

fn generate() -> String {
    let mut out = String::from(
        "# Contrato del guest WASM — generado desde `crates/guest-sdk` y `crates/wasm-host`,\n\
         # NO editar a mano. Un `.wasm` ya publicado no se recompila: renombrar un campo de aquí\n\
         # rompe a la vez a todos los handlers Tier 2 que hay instalados.\n\
         # `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_guest`\n\
         # Contrato del kernel: ADR «El Hub se CIERRA como KERNEL».\n",
    );

    out.push_str("\n[input]\n");
    out.push_str("<transparent>  # `Input` envuelve el JSON del host sin añadir ni un campo\n");

    // Un `Output` con TODOS sus campos presentes: los opcionales llevan `skip_serializing_if`, así
    // que un `Output::default()` no los enseñaría y el contrato saldría corto.
    let full = Output::new()
        .with_operation(Operation::sql("module.command", Map::new()))
        .with_event(Event::new("module.something_happened", json!({})))
        .with_error(DomainError::new("module.code", "message"))
        .with_result(Value::Null);
    let serialised = serde_json::to_value(&full).expect("serializar Output");

    out.push_str("\n[output]\n");
    for key in keys_of(&serialised, "Output") {
        out.push_str(&format!("{key}\n"));
    }
    out.push_str("\n[output.operations[]]\n");
    for key in keys_of(&serialised["operations"][0], "Operation") {
        out.push_str(&format!("{key}\n"));
    }
    out.push_str("\n[output.events[]]\n");
    for key in keys_of(&serialised["events"][0], "Event") {
        out.push_str(&format!("{key}\n"));
    }
    out.push_str("\n[output.error]\n");
    for key in keys_of(&serialised["error"], "DomainError") {
        out.push_str(&format!("{key}\n"));
    }

    // Los topes con los que corre CUALQUIER handler. Son los defaults del binario: lo que aplica a
    // un hub que no ha tocado `HUB_WASM_*`, que son todos.
    let limits = WasmLimits::default();
    out.push_str("\n[wasm_limits]\n");
    out.push_str(&format!("memory_max_mb = {}\n", limits.memory_max_mb));
    out.push_str(&format!("fuel = {}\n", limits.fuel));
    out.push_str(&format!("timeout_ms = {}\n", limits.timeout_ms));

    // Cero host functions es una DECISIÓN (ADR-0009): el guest no llama al host, devuelve
    // intenciones que el host valida. Si algún día aparece una, esta línea es la que cambia.
    out.push_str("\n[host_functions]\n");
    out.push_str(
        "(ninguna)  # el guest no llama al host: devuelve intenciones que el host valida\n",
    );
    out
}

/// Field names of a serialised value, in the order `serde_json` writes them (alphabetical).
fn keys_of(value: &Value, what: &str) -> Vec<String> {
    let object = value
        .as_object()
        .unwrap_or_else(|| panic!("`{what}` ya no serializa como objeto JSON: {value}"));
    assert!(!object.is_empty(), "`{what}` serializa sin un solo campo");
    object.keys().cloned().collect()
}
