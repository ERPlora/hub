//! hub#661 (ADR-0283 K7) — `schemas/flow.schema.json` and the runtime must be the SAME contract.
//!
//! The flow document is **frozen**: the core gains this last family of primitives and stops, so
//! whatever is written down now is what the module `flows`, its editor and every template will
//! speak against for as long as the product exists. That contract is written twice on purpose —
//! once in Rust (`flows::def`, what the hub judges against at save time) and once in JSON Schema
//! (what the editor and the toolkit judge against at authoring time) — because loading a JSON
//! Schema at runtime to validate a row is work a till should not do.
//!
//! Two lists that must agree, with nothing checking them, is exactly how hub#521 happened: the
//! module schema forbade `navigation[].actions` while the runtime had parsed it since ADR-0048.
//! This file is the seam. Change one side without the other and it goes red, naming the value.
use std::collections::BTreeSet;

use erplora_runtime::flows::approvals::{ExpiryPolicy, RejectPolicy};
use erplora_runtime::flows::def::{
    AiOutputKind, AiPolicy, ErrorPolicy, Op, PastDuePolicy, QueryResult, StepKind, TriggerKind,
    DEFAULT_APPROVAL_TTL_SECONDS, DEFAULT_MAX_ITERS, MAX_APPROVAL_TTL_SECONDS, MAX_CORRELATE_PAIRS,
    MAX_DELAY_HORIZON, MAX_ITERS_CAP, MAX_OPTION_ROWS, MAX_QUERY_ROWS, MAX_WAIT_HOOKS,
    SCHEMA_VERSION,
};
use erplora_runtime::host_notify::Channel;

fn schema() -> serde_json::Value {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../schemas/flow.schema.json")
        .canonicalize()
        .expect("schemas/flow.schema.json ships with the hub");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

/// The values of an `enum` at a JSON Pointer.
fn enum_at(schema: &serde_json::Value, pointer: &str) -> BTreeSet<String> {
    schema
        .pointer(pointer)
        .unwrap_or_else(|| panic!("the schema has nothing at {pointer}"))
        .get("enum")
        .and_then(|e| e.as_array())
        .unwrap_or_else(|| panic!("the schema declares no enum at {pointer}"))
        .iter()
        .filter_map(|v| v.as_str().map(|s| s.to_string()))
        .collect()
}

fn keys_at(schema: &serde_json::Value, pointer: &str) -> BTreeSet<String> {
    schema
        .pointer(pointer)
        .unwrap_or_else(|| panic!("the schema has nothing at {pointer}"))
        .as_object()
        .unwrap_or_else(|| panic!("{pointer} is not an object"))
        .keys()
        .cloned()
        .collect()
}

#[test]
fn the_step_kinds_are_the_same_on_both_sides() {
    let declared = enum_at(&schema(), "/$defs/step/properties/kind");
    let known: BTreeSet<String> = StepKind::ALL
        .iter()
        .map(|k| k.as_str().to_string())
        .collect();
    assert_eq!(
        declared, known,
        "the vocabulary is frozen: a kind in one list and not the other is a document the editor \
         accepts and the hub refuses, or worse, the other way round"
    );
}

/// The `http` step's keys (hub#662). The runtime refuses a key it does not know — that is hub#521's
/// lesson written into this contract — so a key the editor offers and the runtime rejects is a
/// document that saves in one place and is refused in the other.
#[test]
fn the_keys_of_an_http_step_are_declared_on_both_sides() {
    let declared = keys_at(&schema(), "/$defs/step/properties");
    for key in ["method", "url", "headers", "body", "timeout"] {
        assert!(
            declared.contains(key),
            "`{key}` is accepted by `flows::def` for an http step and missing from the schema"
        );
    }
    // And the runtime really does accept exactly these.
    let accepted = erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
        "schema_version": 1,
        "steps": [{
            "id": "call", "kind": "http", "method": "POST",
            "url": "https://api.example.com/v1/x",
            "headers": { "Authorization": "Bearer {{secret.K}}" },
            "body": { "a": 1 },
            "timeout": 20
        }]
    }));
    assert!(accepted.is_ok(), "{accepted:?}");
}

/// hub#954 — the `query` step. Three halves have to agree, and each for its own reason:
///
/// - the **keys**, because the runtime refuses one it does not know;
/// - the **`result` vocabulary**, because `rows` is the value everybody will reach for and it is
///   deliberately absent from v1 (the mapping language cannot index an array), so a schema that
///   offered it would have an editor saving a mapping the kernel resolves to nothing;
/// - the **ceiling**, because the runtime REFUSES above it instead of clamping, and a schema that
///   allowed more would move that refusal from the editor to a background tick at 3 AM.
#[test]
fn the_query_step_is_declared_with_the_same_ceiling_and_the_same_result_shapes() {
    let schema = schema();
    let declared = keys_at(&schema, "/$defs/step/properties");
    for key in ["query", "params", "result", "limit", "options"] {
        assert!(
            declared.contains(key),
            "the schema must declare `{key}` of a `query` step; it has {declared:?}"
        );
    }

    assert_eq!(
        enum_at(&schema, "/$defs/step/properties/result"),
        QueryResult::ALL
            .iter()
            .map(|r| r.as_str().to_string())
            .collect::<BTreeSet<String>>(),
        "`rows` is not in v1 on either side: `resolve_path` cannot walk `steps.x.rows.0.total`, \
         and a mapping the kernel resolves to nothing is a lie the editor would help write. \
         `options` (hub#1641) is what it is missing FOR, and it is on both sides or on neither"
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/result/default"),
        Some(&serde_json::json!(QueryResult::First.as_str()))
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/limit/maximum"),
        Some(&serde_json::json!(MAX_QUERY_ROWS)),
        "the runtime refuses above the ceiling; a schema that allowed more would move that \
         refusal off the screen where it was typed"
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/limit/minimum"),
        Some(&serde_json::json!(1))
    );

    // And the runtime really does accept exactly these keys, and really does refuse a bigger read.
    let step = |extra: serde_json::Value| {
        let mut base = serde_json::json!({
            "id": "week", "kind": "query", "query": "sales.summary",
            "params": { "from": "input.from" }
        });
        let map = base.as_object_mut().unwrap();
        for (k, v) in extra.as_object().unwrap() {
            map.insert(k.clone(), v.clone());
        }
        erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
            "schema_version": 1, "steps": [base]
        }))
    };
    assert!(step(serde_json::json!({ "result": "first", "limit": 50 })).is_ok());
    assert!(step(serde_json::json!({ "result": "count" })).is_ok());
    assert!(step(serde_json::json!({ "result": "rows" })).is_err());
    assert!(step(serde_json::json!({ "limit": MAX_QUERY_ROWS + 1 })).is_err());
}

/// hub#1641 — `result: "options"` and its `options` block. The halves that have to agree are the
/// two the runtime refuses on, and BOTH of them are conditional on `result`, so the schema says
/// them with an `if`/`then` instead of a flat `required`:
///
/// - `options` is **required** with that result and **refused** without it — a schema that let
///   either through would have the editor saving a document the hub rejects at save;
/// - the **row ceiling drops to [`MAX_OPTION_ROWS`]**, because these rows have one destination and
///   Meta holds ten. A schema that still allowed 200 would move that refusal off the screen.
#[test]
fn a_read_that_publishes_options_is_declared_the_same_on_both_sides() {
    let schema = schema();
    let conditional = schema
        .pointer("/$defs/step/allOf/0")
        .expect("the schema states what `result: \"options\"` requires");
    assert_eq!(
        conditional.pointer("/if/properties/result/const"),
        Some(&serde_json::json!(QueryResult::Options.as_str()))
    );
    assert_eq!(
        conditional.pointer("/then/required"),
        Some(&serde_json::json!(["options"])),
        "a read that publishes options carries the columns they are made of"
    );
    assert_eq!(
        conditional.pointer("/then/properties/limit/maximum"),
        Some(&serde_json::json!(MAX_OPTION_ROWS)),
        "the runtime caps an options read at what a tappable message can carry"
    );
    assert_eq!(
        conditional.pointer("/else/not/required"),
        Some(&serde_json::json!(["options"])),
        "a mapping nothing reads is refused by the runtime, so the editor must not offer it"
    );
    assert_eq!(
        keys_at(&schema, "/$defs/step/properties/options/properties"),
        BTreeSet::from([
            "id".to_string(),
            "title".to_string(),
            "description".to_string(),
        ]),
        "the three a tappable row has, and no fourth"
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/options/required"),
        Some(&serde_json::json!(["id", "title"])),
        "`description` is the optional second line; the other two are what Meta cannot send \
         a row without"
    );

    // And the runtime really does refuse each half the schema promises it refuses.
    let step = |extra: serde_json::Value| {
        let mut base = serde_json::json!({
            "id": "free", "kind": "query", "query": "appointments.free_slots"
        });
        let map = base.as_object_mut().unwrap();
        for (k, v) in extra.as_object().unwrap() {
            map.insert(k.clone(), v.clone());
        }
        erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
            "schema_version": 1, "steps": [base]
        }))
    };
    let shape = serde_json::json!({ "id": "slot_id", "title": "label" });
    assert!(step(serde_json::json!({ "result": "options", "options": shape })).is_ok());
    assert!(step(serde_json::json!({ "result": "options" })).is_err());
    assert!(step(serde_json::json!({ "options": shape })).is_err());
    assert!(step(serde_json::json!({
        "result": "options", "options": shape, "limit": MAX_OPTION_ROWS + 1
    }))
    .is_err());
    assert!(step(serde_json::json!({
        "result": "options", "options": shape, "limit": MAX_OPTION_ROWS
    }))
    .is_ok());
}

/// hub#951 — the extended `delay`. Four halves have to agree, and each for its own reason:
///
/// - the **keys**, because the runtime refuses one it does not know;
/// - the **`past_due_policy` vocabulary** and its default, because it is what a document says
///   should happen when the instant already went by, and the default is deliberately NOT the
///   market's (`skip`, not Salesforce's «run it now»);
/// - the **horizon**, because the runtime REFUSES above it instead of clamping — a schema that
///   allowed a year would move that refusal from the editor to a row asleep for a year;
/// - the **hook shape**, because `correlate` is the half that makes a cancellation about ONE
///   appointment, and an editor that let it be omitted would help write a flow that cancels
///   everybody's reminder.
#[test]
fn the_extended_delay_is_declared_with_the_same_horizon_the_runtime_refuses_above() {
    let schema = schema();
    let declared = keys_at(&schema, "/$defs/step/properties");
    for key in [
        "seconds",
        "until",
        "offset_seconds",
        "max_wait",
        "past_due_policy",
        "cancel_on",
        "reschedule_on",
    ] {
        assert!(
            declared.contains(key),
            "the schema must declare `{key}` of a `delay` step; it has {declared:?}"
        );
    }

    assert_eq!(
        enum_at(&schema, "/$defs/step/properties/past_due_policy"),
        PastDuePolicy::ALL
            .iter()
            .map(|p| p.as_str().to_string())
            .collect::<BTreeSet<String>>()
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/past_due_policy/default"),
        Some(&serde_json::json!(PastDuePolicy::Skip.as_str())),
        "the restrictive default is the contract: a reminder whose hour went by is not sent"
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/max_wait/maximum"),
        Some(&serde_json::json!(MAX_DELAY_HORIZON))
    );
    for list in ["cancel_on", "reschedule_on"] {
        assert_eq!(
            schema.pointer(&format!("/$defs/step/properties/{list}/maxItems")),
            Some(&serde_json::json!(MAX_WAIT_HOOKS)),
            "`{list}` is matched on the hot path of every event delivered in the hub"
        );
        assert_eq!(
            schema.pointer(&format!("/$defs/step/properties/{list}/items/$ref")),
            Some(&serde_json::json!("#/$defs/wait_hook"))
        );
    }
    assert_eq!(
        schema.pointer("/$defs/wait_hook/required"),
        Some(&serde_json::json!(["event", "correlate"])),
        "an uncorrelated hook cancels every armed wait in the hub, so it is required on both sides"
    );
    assert_eq!(
        schema.pointer("/$defs/wait_hook/properties/correlate/maxProperties"),
        Some(&serde_json::json!(MAX_CORRELATE_PAIRS))
    );

    // And the runtime really does accept exactly these, and really does refuse past the horizon.
    let delay = |extra: serde_json::Value| {
        let mut base = serde_json::json!({ "id": "w", "kind": "delay", "until": "input.at" });
        let map = base.as_object_mut().unwrap();
        for (k, v) in extra.as_object().unwrap() {
            map.insert(k.clone(), v.clone());
        }
        erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
            "schema_version": 1, "steps": [base]
        }))
    };
    assert!(delay(serde_json::json!({
        "offset_seconds": -86400, "max_wait": 604800, "past_due_policy": "skip",
        "cancel_on": [{ "event": "a.cancelled", "correlate": { "event.id": "input.id" } }],
        "reschedule_on": [{ "event": "a.moved", "correlate": { "event.id": "input.id" },
                            "until": "event.at" }]
    }))
    .is_ok());
    assert!(delay(serde_json::json!({ "max_wait": MAX_DELAY_HORIZON + 1 })).is_err());
    assert!(delay(serde_json::json!({ "past_due_policy": "run_anyway" })).is_err());
    assert!(delay(serde_json::json!({ "cancel_on": [{ "event": "a.b" }] })).is_err());
}

/// hub#950 — the `approval` step, the eighth kind. Three halves have to agree:
///
/// - the **keys**, because the runtime refuses one it does not know;
/// - the **two policy vocabularies**, because they are what a document says should happen when the
///   answer is «no» or when there is no answer at all — a schema offering a value the hub degrades
///   to something else would have an editor promising a branch the kernel will not take;
/// - the **ceiling on `expires_in`**, because the runtime REFUSES above it instead of clamping, and
///   a schema that allowed a year would move that refusal from the editor to a sweep at 3 AM.
#[test]
fn the_approval_step_is_declared_with_the_same_policies_and_the_same_ceiling() {
    let schema = schema();
    let declared = keys_at(&schema, "/$defs/step/properties");
    for key in [
        "title",
        "summary",
        "assignee",
        "expires_in",
        "on_expire",
        "on_reject",
    ] {
        assert!(
            declared.contains(key),
            "the schema must declare `{key}` of an `approval` step; it has {declared:?}"
        );
    }

    assert_eq!(
        enum_at(&schema, "/$defs/step/properties/on_expire"),
        ExpiryPolicy::ALL
            .iter()
            .map(|p| p.as_str().to_string())
            .collect::<BTreeSet<String>>()
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/on_expire/default"),
        Some(&serde_json::json!(ExpiryPolicy::Reject.as_str())),
        "silence is read as a refusal, because the steps after an approval assumed it was granted"
    );
    assert_eq!(
        enum_at(&schema, "/$defs/step/properties/on_reject"),
        RejectPolicy::ALL
            .iter()
            .map(|p| p.as_str().to_string())
            .collect::<BTreeSet<String>>()
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/on_reject/default"),
        Some(&serde_json::json!(RejectPolicy::Cancel.as_str()))
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/expires_in/maximum"),
        Some(&serde_json::json!(MAX_APPROVAL_TTL_SECONDS))
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/expires_in/default"),
        Some(&serde_json::json!(DEFAULT_APPROVAL_TTL_SECONDS))
    );

    // The assignee is a ROLE and there is no shape in which a person can be named — the same
    // closed-object property that makes a `notify` recipient impossible to write by hand.
    assert_eq!(
        keys_at(&schema, "/$defs/assignee/properties"),
        BTreeSet::from(["role".to_string()])
    );
    assert_eq!(
        schema
            .pointer("/$defs/assignee/additionalProperties")
            .and_then(|v| v.as_bool()),
        Some(false),
        "an extra key in `assignee` is refused on both sides: that object is the only way a \
         question names who may answer it, and it must not grow one that reads like a user id"
    );

    // And the runtime really does accept exactly these, and really does refuse a longer wait.
    let step = |extra: serde_json::Value| {
        let mut base = serde_json::json!({
            "id": "approve", "kind": "approval", "title": "¿Aprobamos {{input.what}}?"
        });
        let map = base.as_object_mut().unwrap();
        for (k, v) in extra.as_object().unwrap() {
            map.insert(k.clone(), v.clone());
        }
        erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
            "schema_version": 1, "steps": [base]
        }))
    };
    assert!(step(serde_json::json!({
        "summary": "Importe {{input.total}} €",
        "assignee": { "role": "manager" },
        "expires_in": MAX_APPROVAL_TTL_SECONDS,
        "on_expire": "continue",
        "on_reject": "continue"
    }))
    .is_ok());
    assert!(step(serde_json::json!({ "expires_in": MAX_APPROVAL_TTL_SECONDS + 1 })).is_err());
    assert!(step(serde_json::json!({ "assignee": { "user": "hub_user:7" } })).is_err());
}

#[test]
fn the_trigger_kinds_are_the_same_four_on_both_sides() {
    let declared = enum_at(&schema(), "/$defs/trigger/properties/kind");
    let known: BTreeSet<String> = TriggerKind::ALL
        .iter()
        .map(|k| k.as_str().to_string())
        .collect();
    assert_eq!(declared, known);
}

#[test]
fn the_condition_operators_are_the_same_set_on_both_sides() {
    let declared = keys_at(
        &schema(),
        "/$defs/condition/additionalProperties/properties",
    );
    let known: BTreeSet<String> = Op::ALL.iter().map(|o| o.as_str().to_string()).collect();
    assert_eq!(
        declared, known,
        "an operator the schema allows and the runtime does not know is a filter that saves in the \
         editor and is refused by the hub"
    );
    // And the schema must forbid everything else, or the editor would happily accept `greater_than`
    // and the refusal would only arrive from the hub.
    assert_eq!(
        schema()
            .pointer("/$defs/condition/additionalProperties/additionalProperties")
            .and_then(|v| v.as_bool()),
        Some(false),
        "the operator set is closed on the schema side too"
    );
}

#[test]
fn the_document_declares_the_version_this_hub_speaks_and_requires_it() {
    let schema = schema();
    assert_eq!(
        schema.pointer("/properties/schema_version/const").unwrap(),
        &serde_json::json!(SCHEMA_VERSION),
        "the schema pins the version the runtime implements"
    );
    let required: BTreeSet<String> = schema["required"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|v| v.as_str().map(|s| s.to_string()))
        .collect();
    assert!(
        required.contains("schema_version"),
        "`schema_version` is required from day one: an unversioned document is one nobody can \
         refuse later"
    );
    assert!(
        required.contains("steps"),
        "a flow with no steps does nothing, and the runtime refuses it"
    );
    assert_eq!(
        schema["additionalProperties"].as_bool(),
        Some(false),
        "unknown top-level keys are refused, not dropped (hub#521)"
    );
}

/// hub#665 — the `ai` step is the newest half of the frozen document, so it is the half most
/// likely to drift. The policy vocabulary is exactly two values and the DEFAULT is the restrictive
/// one; a schema that defaulted to `auto` (or accepted a third value) would have an editor happily
/// saving a flow that writes to the business database unattended.
#[test]
fn the_ai_policies_are_the_same_two_on_both_sides_and_default_to_manual() {
    let schema = schema();
    let declared = enum_at(&schema, "/$defs/step/properties/policy");
    let known: BTreeSet<String> = AiPolicy::ALL
        .iter()
        .map(|p| p.as_str().to_string())
        .collect();
    assert_eq!(declared, known);
    assert_eq!(
        schema.pointer("/$defs/step/properties/policy/default"),
        Some(&serde_json::json!(AiPolicy::Manual.as_str())),
        "the permissive option is the one nobody writes down and everybody assumes (ADR-0283 D3)"
    );
}

/// **The shapes a turn may leave behind, on both sides** (hub#1639). The editor writes `output`
/// against this enum and the hub judges it against [`AiOutputKind`]; a schema that accepted a
/// fourth shape would have an editor saving a document the hub then refuses at the till, which is
/// hub#521 with the sides swapped.
#[test]
fn the_ai_output_shapes_are_the_same_on_both_sides() {
    let schema = schema();
    let declared = enum_at(
        &schema,
        "/$defs/step/properties/output/additionalProperties/properties/type",
    );
    let known: BTreeSet<String> = AiOutputKind::ALL
        .iter()
        .map(|k| k.as_str().to_string())
        .collect();
    assert_eq!(declared, known);
    // Both halves of a field are required on both sides: a field with no `describe` is a field
    // the model fills with whatever it likes, and the editor must refuse it where it is typed.
    let required: BTreeSet<String> = schema
        .pointer("/$defs/step/properties/output/additionalProperties/required")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| panic!("`output` fields declare what they require"))
        .iter()
        .filter_map(|v| v.as_str().map(str::to_string))
        .collect();
    assert_eq!(
        required,
        BTreeSet::from(["describe".to_string(), "type".to_string()])
    );
}

/// The loop bound is money — every turn is a metered call through the SaaS proxy — so the number
/// the editor enforces and the number the hub enforces have to be the same number.
#[test]
fn the_agent_loop_bounds_are_the_same_on_both_sides() {
    let schema = schema();
    assert_eq!(
        schema.pointer("/$defs/step/properties/max_iters/default"),
        Some(&serde_json::json!(DEFAULT_MAX_ITERS))
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/max_iters/maximum"),
        Some(&serde_json::json!(MAX_ITERS_CAP)),
        "the runtime REFUSES above the cap; a schema that allowed more would move the refusal \
         from the editor to a background tick at 3 AM"
    );
}

/// hub#821 — the `notify` step. Two halves have to agree, and each for its own reason:
///
/// - the **channels**, because the runtime refuses one it cannot send on (`sms`) and a schema that
///   offered it would move that refusal from the editor to a background tick;
/// - the **shape of `to`**, which is the whole security property of the step. It is an object of
///   `{query, params, field}` and NOTHING else. A schema that allowed a string there would have an
///   editor happily saving «send it to `{{input.email}}`» — the address out of the event payload,
///   which is precisely what a recipient grant exists to make impossible.
#[test]
fn the_notify_channels_and_the_shape_of_a_recipient_are_the_same_on_both_sides() {
    let schema = schema();
    let declared = enum_at(&schema, "/$defs/step/properties/channel");
    let deliverable: BTreeSet<String> = Channel::DELIVERABLE
        .iter()
        .map(|c| c.as_str().to_string())
        .collect();
    assert_eq!(
        declared, deliverable,
        "a channel in one list and not the other is either a step the editor refuses and the hub \
         runs, or one it saves and the hub dead-letters"
    );

    let recipient = keys_at(&schema, "/$defs/recipient/properties");
    assert_eq!(
        recipient,
        BTreeSet::from([
            "field".to_string(),
            "params".to_string(),
            "query".to_string()
        ])
    );
    assert_eq!(
        schema
            .pointer("/$defs/recipient/additionalProperties")
            .and_then(|v| v.as_bool()),
        Some(false),
        "an extra key in `to` is refused on both sides: that object is the only way a flow names \
         anybody, and it must not grow one that reads like an address"
    );
    let required: BTreeSet<String> = schema["$defs"]["recipient"]["required"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|v| v.as_str().map(|s| s.to_string()))
        .collect();
    assert_eq!(
        required,
        BTreeSet::from(["field".to_string(), "query".to_string()]),
        "a recipient is one field of one query; neither half is optional"
    );

    // And the runtime really does accept exactly this document, and really does refuse a `to` that
    // is an address.
    let step = |to: serde_json::Value| {
        erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
            "schema_version": 1,
            "steps": [{
                "id": "remind", "kind": "notify", "channel": "whatsapp", "to": to,
                "template": "reminder", "vars": { "text": "hola" }
            }]
        }))
    };
    assert!(step(serde_json::json!({
        "query": "crm.customer.get",
        "params": { "id": "input.customer_id" },
        "field": "phone"
    }))
    .is_ok());
    assert!(step(serde_json::json!("{{input.phone}}")).is_err());
}

/// Every key the runtime parses for an `ai` step must be declared, or the editor would flag as
/// unknown something the hub reads — the mirror image of hub#521, and just as confusing.
#[test]
fn every_key_of_the_ai_step_is_declared_in_the_schema() {
    let declared = keys_at(&schema(), "/$defs/step/properties");
    for key in ["channel", "to", "template", "vars", "interactive"] {
        assert!(
            declared.contains(key),
            "the schema must declare `{key}` of a `notify` step; it has {declared:?}"
        );
    }
    for key in ["prompt", "tools", "policy", "max_iters", "output"] {
        assert!(
            declared.contains(key),
            "the schema must declare `{key}` of an `ai` step; it has {declared:?}"
        );
    }
    // …and the `tools` block is closed on both sides: `queries` and `commands`, nothing else.
    let tools = keys_at(&schema(), "/$defs/step/properties/tools/properties");
    assert_eq!(
        tools,
        BTreeSet::from(["commands".to_string(), "queries".to_string()])
    );
    assert_eq!(
        schema()
            .pointer("/$defs/step/properties/tools/additionalProperties")
            .and_then(|v| v.as_bool()),
        Some(false)
    );
}

/// **What a FAILURE costs the run** (hub#1635), on both sides. `on_error` is the third policy of
/// this contract and the one with the widest reach: `on_expire`/`on_reject` belong to the two kinds
/// that wait for a person, and this one belongs to every kind that can fail.
///
/// The vocabulary matters more here than anywhere else, because of the value that is deliberately
/// NOT in it. A schema that offered `retry` would have an editor promising the hub will re-run a
/// business command on its own — which is how a sale gets charged twice (ADR-0283 §1) — and the
/// runtime would degrade it to `stop` in silence.
#[test]
fn the_failure_policy_is_the_same_closed_vocabulary_on_both_sides() {
    let schema = schema();
    assert!(
        keys_at(&schema, "/$defs/step/properties").contains("on_error"),
        "the schema must declare `on_error`: the runtime accepts it on every kind that can fail"
    );
    assert_eq!(
        enum_at(&schema, "/$defs/step/properties/on_error"),
        ErrorPolicy::ALL
            .iter()
            .map(|p| p.as_str().to_string())
            .collect::<BTreeSet<String>>()
    );
    assert!(
        !enum_at(&schema, "/$defs/step/properties/on_error").contains("retry"),
        "`retry` is not a policy this kernel has, and a schema offering it would promise a branch \
         the runtime would silently degrade to `stop`"
    );
    assert_eq!(
        schema.pointer("/$defs/step/properties/on_error/default"),
        Some(&serde_json::json!(ErrorPolicy::Stop.as_str())),
        "a document that says nothing still stops: the steps written after a write assumed it \
         happened"
    );

    // And the runtime really does accept it exactly where the schema's description says it does.
    let step = |kind: &str, extra: serde_json::Value| {
        let mut base = serde_json::json!({ "id": "s", "kind": kind, "on_error": "continue" });
        let map = base.as_object_mut().unwrap();
        for (k, v) in extra.as_object().unwrap() {
            map.insert(k.clone(), v.clone());
        }
        erplora_runtime::flows::FlowDefinition::parse(&serde_json::json!({
            "schema_version": 1, "steps": [base]
        }))
    };
    assert!(step("command", serde_json::json!({ "command": "crm.note.add" })).is_ok());
    assert!(step("query", serde_json::json!({ "query": "crm.note.list" })).is_ok());
    assert!(step("delay", serde_json::json!({ "seconds": 60 })).is_ok());
    assert!(
        step(
            "http",
            serde_json::json!({ "url": "https://example.com/x" })
        )
        .is_ok(),
        "the two kinds that fail OUTSIDE the tick obey the same policy, or it would cover the \
         cheap half of the kernel and miss the one somebody is waiting on"
    );
    assert!(step("ai", serde_json::json!({ "prompt": "book it" })).is_ok());
    assert!(step(
        "notify",
        serde_json::json!({
            "channel": "email", "template": "t",
            "to": { "query": "crm.customer.get", "field": "email" }
        })
    )
    .is_ok());

    // …and refuses it where a failure cannot happen. A `condition` that does not match is the flow
    // working as written, and an `approval` answers with `on_reject`/`on_expire`.
    assert!(step(
        "condition",
        serde_json::json!({ "when": { "input.x": { "eq": 1 } } })
    )
    .is_err());
    assert!(step("approval", serde_json::json!({ "title": "¿Seguimos?" })).is_err());
}
