//! Handlers WASM (Tier 2) del módulo `customers` — las operaciones **batch** del legacy:
//!
//! * `bulk_create` — alta de N clientes (cap 50, igual que CustomerService.bulk_create).
//!   Normaliza lifecycle "customer" → "active" (fiel a create_customer).
//! * `set_groups` — asigna los grupos de un cliente (M2M): emite un `_group_clear`
//!   + un `_group_add` por group_id (reemplaza la colección completa, como routes).
//! * `set_tags` — idem para etiquetas (`_tag_clear` + N `_tag_add`).
//!
//! Lógica pura (sin BD): recibe `{payload, context}`, devuelve **intenciones** (ops SQL
//! por nombre de command del mismo módulo + params) que el host valida y ejecuta en una
//! transacción. Los ids de filas nuevas salen de `context.new_ids` (autoridad del host).

use erplora_guest_sdk::{Operation, Output};
use serde_json::{json, Map, Value};

#[cfg(feature = "guest")]
use extism_pdk::*;

#[cfg(feature = "guest")]
#[plugin_fn]
pub fn bulk_create(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(bulk_create_pure(input.into_inner().into_value())))
}

#[cfg(feature = "guest")]
#[plugin_fn]
pub fn set_groups(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(set_membership(input.into_inner().into_value(), "group")))
}

#[cfg(feature = "guest")]
#[plugin_fn]
pub fn set_tags(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(set_membership(input.into_inner().into_value(), "tag")))
}

const MAX_BULK: usize = 50;

fn as_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        _ => String::new(),
    }
}

fn opt_str(item: &Value, key: &str) -> Value {
    match item.get(key) {
        Some(Value::Null) | None => Value::Null,
        Some(v) => Value::String(as_str(v)),
    }
}

fn str_or(item: &Value, key: &str, default: &str) -> String {
    let s = as_str(item.get(key).unwrap_or(&Value::Null));
    if s.is_empty() { default.to_string() } else { s }
}

fn payload_context(input: &Value) -> (Value, Vec<Value>) {
    let payload = input.get("payload").cloned().unwrap_or(Value::Null);
    let empty: Vec<Value> = Vec::new();
    let new_ids = input
        .get("context")
        .and_then(|c| c.get("new_ids"))
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or(empty);
    (payload, new_ids)
}

/// Normaliza el lifecycle: "customer" → "active" (fiel a create_customer del legacy).
fn norm_stage(item: &Value) -> String {
    let s = str_or(item, "lifecycle_stage", "active");
    if s == "customer" { "active".to_string() } else { s }
}

/// Lógica pura de `bulk_create`.
pub fn bulk_create_pure(input: Value) -> Output {
    let (payload, new_ids) = payload_context(&input);
    let empty: Vec<Value> = Vec::new();
    let items = payload.get("items").and_then(|v| v.as_array()).unwrap_or(&empty);

    let mut ops: Vec<Operation> = Vec::new();
    for (i, item) in items.iter().take(MAX_BULK).enumerate() {
        let id = new_ids.get(i).cloned().unwrap_or(Value::Null);
        let mut p = Map::new();
        p.insert("new_id".into(), id); // create.sql usa :new_id
        p.insert("name".into(), json!(as_str(item.get("name").unwrap_or(&Value::Null))));
        p.insert("email".into(), json!(str_or(item, "email", "")));
        p.insert("phone".into(), json!(str_or(item, "phone", "")));
        p.insert("tax_id".into(), json!(str_or(item, "tax_id", "")));
        p.insert("address".into(), json!(str_or(item, "address", "")));
        p.insert("city".into(), json!(str_or(item, "city", "")));
        p.insert("postal_code".into(), json!(str_or(item, "postal_code", "")));
        p.insert("country".into(), json!(str_or(item, "country", "")));
        p.insert("avatar".into(), json!(str_or(item, "avatar", "")));
        p.insert("notes".into(), json!(str_or(item, "notes", "")));
        p.insert("lifecycle_stage".into(), json!(norm_stage(item)));
        p.insert("source".into(), json!(str_or(item, "source", "import")));
        p.insert("company_name".into(), json!(str_or(item, "company_name", "")));
        p.insert("birthday".into(), opt_str(item, "birthday"));
        p.insert("anniversary".into(), opt_str(item, "anniversary"));
        p.insert("preferred_channel".into(), json!(str_or(item, "preferred_channel", "none")));
        p.insert("marketing_consent".into(), json!(item.get("marketing_consent").and_then(|v| v.as_bool()).unwrap_or(false) as i64));
        p.insert("consent_date".into(), opt_str(item, "consent_date"));
        ops.push(Operation::sql("customers.create", p));
    }
    Output { operations: ops, events: vec![] }
}

/// Lógica de set_groups / set_tags: clear + N adds (reemplazo de colección M2M).
/// `kind` = "group" | "tag". payload: { customer_id, ids: [..] }.
/// Sin la feature `guest` solo lo ejercitan los tests; el `allow` evita el warning
/// de no-usado en `cargo build` plano.
#[cfg_attr(all(not(feature = "guest"), not(test)), allow(dead_code))]
fn set_membership(input: Value, kind: &str) -> Output {
    let (payload, _ids) = payload_context(&input);
    let customer_id = payload.get("customer_id").cloned().unwrap_or(Value::Null);
    let empty: Vec<Value> = Vec::new();
    let ids = payload.get("ids").and_then(|v| v.as_array()).unwrap_or(&empty);

    let (clear_cmd, add_cmd, id_key) = match kind {
        "group" => ("customers._group_clear", "customers._group_add", "group_id"),
        _ => ("customers._tag_clear", "customers._tag_add", "tag_id"),
    };

    let mut ops: Vec<Operation> = Vec::new();
    // 1) limpiar la colección actual del cliente.
    let mut clear = Map::new();
    clear.insert("customer_id".into(), customer_id.clone());
    ops.push(Operation::sql(clear_cmd, clear));
    // 2) añadir cada id (INSERT OR IGNORE).
    for ref_id in ids {
        if ref_id.is_null() { continue; }
        let mut a = Map::new();
        a.insert("customer_id".into(), customer_id.clone());
        a.insert(id_key.into(), ref_id.clone());
        ops.push(Operation::sql(add_cmd, a));
    }
    Output { operations: ops, events: vec![] }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx(n: usize) -> Value {
        let ids: Vec<Value> = (0..n).map(|i| json!(format!("id-{i}"))).collect();
        json!({ "context": { "new_ids": ids } })
    }
    fn with(payload: Value, mut base: Value) -> Value {
        base["payload"] = payload;
        base
    }

    #[test]
    fn bulk_create_normalizes_stage_and_correlates_ids() {
        let payload = json!({ "items": [
            { "name": "Bar Manolo", "email": "m@bar.es", "lifecycle_stage": "customer" },
            { "name": "Ana", "phone": "600" }
        ]});
        let out = bulk_create_pure(with(payload, ctx(4)));
        assert_eq!(out.operations.len(), 2);
        assert_eq!(out.operations[0].command, "customers.create");
        assert_eq!(out.operations[0].params["new_id"], json!("id-0"));
        // "customer" → "active".
        assert_eq!(out.operations[0].params["lifecycle_stage"], json!("active"));
        assert_eq!(out.operations[0].params["source"], json!("import"));
        assert_eq!(out.operations[1].params["new_id"], json!("id-1"));
        // sin lifecycle → default "active".
        assert_eq!(out.operations[1].params["lifecycle_stage"], json!("active"));
    }

    #[test]
    fn bulk_create_caps_at_50() {
        let items: Vec<Value> = (0..80).map(|i| json!({ "name": format!("C{i}") })).collect();
        let out = bulk_create_pure(with(json!({ "items": items }), ctx(80)));
        assert_eq!(out.operations.len(), MAX_BULK);
    }

    #[test]
    fn set_groups_emits_clear_then_adds() {
        let payload = json!({ "customer_id": "c1", "ids": ["g1", "g2"] });
        let out = set_membership(with(payload, ctx(0)), "group");
        assert_eq!(out.operations.len(), 3);
        assert_eq!(out.operations[0].command, "customers._group_clear");
        assert_eq!(out.operations[0].params["customer_id"], json!("c1"));
        assert_eq!(out.operations[1].command, "customers._group_add");
        assert_eq!(out.operations[1].params["group_id"], json!("g1"));
        assert_eq!(out.operations[2].params["group_id"], json!("g2"));
    }

    #[test]
    fn set_tags_clear_only_when_empty() {
        let out = set_membership(with(json!({ "customer_id": "c1", "ids": [] }), ctx(0)), "tag");
        assert_eq!(out.operations.len(), 1);
        assert_eq!(out.operations[0].command, "customers._tag_clear");
    }
}
