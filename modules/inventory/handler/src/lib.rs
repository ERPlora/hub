//! Handlers WASM (Tier 2) del módulo `inventory` — las dos operaciones **batch**:
//!
//! * `bulk_create` — alta de N productos (cap 100, igual que el legacy
//!   `ProductService.bulk_create_products`). Genera SKU `PROD-{n:03d}` cuando la
//!   línea no trae sku (continúa la numeración con `existing_count` que el host
//!   pasa en el payload).
//! * `receive_stock` — recepción de mercancía: incrementa stock de productos
//!   existentes por línea (cap 200, `ProductService.receive_stock`). El casado
//!   por sku no se puede hacer en el guest (no toca BD), así que el host/SDK
//!   resuelve sku→product_id antes; el handler emite una op por línea con id.
//!
//! Lógica pura (sin BD): recibe `{payload, context}`, devuelve **intenciones**
//! (ops SQL por nombre de command del mismo módulo + params) que el host valida
//! y ejecuta en una transacción. Los ids de filas nuevas salen de
//! `context.new_ids` (el host es la autoridad de ids; el guest los reparte).

use erplora_guest_sdk::{Operation, Output};
use serde_json::{json, Map, Value};

#[cfg(feature = "guest")]
use extism_pdk::*;

/// Alta batch de productos. Exporta `bulk_create`.
#[cfg(feature = "guest")]
#[plugin_fn]
pub fn bulk_create(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(bulk_create_pure(input.into_inner().into_value())))
}

/// Recepción de stock batch. Exporta `receive_stock`.
#[cfg(feature = "guest")]
#[plugin_fn]
pub fn receive_stock(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(receive_stock_pure(input.into_inner().into_value())))
}

/// Listener WASM de `sale.completed`: descuenta stock por línea. Exporta `decrease_on_sale`.
#[cfg(feature = "guest")]
#[plugin_fn]
pub fn decrease_on_sale(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(decrease_on_sale_pure(input.into_inner().into_value())))
}

const MAX_BULK: usize = 100;
const MAX_RECEIVE: usize = 200;

fn as_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        _ => String::new(),
    }
}

fn as_i64(v: &Value, default: i64) -> i64 {
    match v {
        // Cae a f64 si el número viene como float (p.ej. quantity 3.0 del evento
        // sale.completed): as_i64() de serde devuelve None para floats no enteros.
        Value::Number(n) => n
            .as_i64()
            .or_else(|| n.as_f64().map(|f| f as i64))
            .unwrap_or(default),
        Value::String(s) => s.trim().parse::<i64>().ok().or_else(|| s.trim().parse::<f64>().ok().map(|f| f as i64)).unwrap_or(default),
        _ => default,
    }
}

fn opt_str(item: &Value, key: &str) -> Value {
    match item.get(key) {
        Some(Value::Null) | None => Value::Null,
        Some(v) => Value::String(as_str(v)),
    }
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

/// Lógica pura de `bulk_create`.
pub fn bulk_create_pure(input: Value) -> Output {
    let (payload, new_ids) = payload_context(&input);
    let empty: Vec<Value> = Vec::new();
    let products = payload.get("products").and_then(|v| v.as_array()).unwrap_or(&empty);
    // Contador de productos existentes para continuar la secuencia PROD-NNN.
    let existing = payload.get("existing_count").map(|v| as_i64(v, 0)).unwrap_or(0);

    let mut ops: Vec<Operation> = Vec::new();
    for (i, item) in products.iter().take(MAX_BULK).enumerate() {
        let sku = {
            let s = as_str(item.get("sku").unwrap_or(&Value::Null));
            if s.is_empty() {
                format!("PROD-{:03}", existing + i as i64 + 1)
            } else {
                s
            }
        };
        let product_id = new_ids.get(i).cloned().unwrap_or(Value::Null);
        let ptype = {
            let t = as_str(item.get("product_type").unwrap_or(&Value::Null));
            if t.is_empty() { "physical".to_string() } else { t }
        };
        let mut p = Map::new();
        p.insert("product_id".into(), product_id);
        p.insert("name".into(), json!(as_str(item.get("name").unwrap_or(&Value::Null))));
        p.insert("sku".into(), json!(sku));
        p.insert("ean13".into(), opt_str(item, "ean13"));
        p.insert("description".into(), json!(as_str(item.get("description").unwrap_or(&Value::Null))));
        p.insert("product_type".into(), json!(ptype));
        p.insert("price".into(), item.get("price").cloned().unwrap_or(json!(0)));
        p.insert("cost".into(), item.get("cost").cloned().unwrap_or(json!(0)));
        p.insert("stock".into(), item.get("stock").cloned().unwrap_or(json!(0)));
        p.insert("low_stock_threshold".into(), item.get("low_stock_threshold").cloned().unwrap_or(json!(10)));
        p.insert("tax_class_id".into(), opt_str(item, "tax_class_id"));
        p.insert("image".into(), json!(as_str(item.get("image").unwrap_or(&Value::Null))));
        ops.push(Operation::sql("inventory._insert_product", p));
    }
    Output { operations: ops, events: vec![] }
}

/// Lógica pura de `receive_stock`. Cada línea debe traer `product_id` (resuelto
/// por el SDK/host desde sku si hiciera falta) y `qty` > 0; `unit_cost` opcional.
pub fn receive_stock_pure(input: Value) -> Output {
    let (payload, _ids) = payload_context(&input);
    let empty: Vec<Value> = Vec::new();
    let items = payload.get("items").and_then(|v| v.as_array()).unwrap_or(&empty);

    let mut ops: Vec<Operation> = Vec::new();
    for item in items.iter().take(MAX_RECEIVE) {
        let qty = as_i64(item.get("qty").unwrap_or(&Value::Null), 0);
        let product_id = item.get("product_id").cloned().unwrap_or(Value::Null);
        if qty <= 0 || product_id.is_null() {
            continue; // líneas inválidas se omiten (el legacy las reporta; aquí se saltan)
        }
        let mut p = Map::new();
        p.insert("product_id".into(), product_id);
        p.insert("qty".into(), json!(qty));
        p.insert("unit_cost".into(), item.get("unit_cost").cloned().unwrap_or(Value::Null));
        ops.push(Operation::sql("inventory._receive_line", p));
    }
    Output { operations: ops, events: vec![] }
}

/// Lógica pura del listener de `sale.completed`: por cada línea con product_id
/// que NO sea servicio, emite una op `inventory.stock.decrease` (product_id, qty).
/// El payload del evento (lo emite sales) trae `items: [{product_id, quantity, is_service}]`.
/// Fiel a inventory.events._on_sale_completed (saltaba servicios y product_id None).
pub fn decrease_on_sale_pure(input: Value) -> Output {
    let (payload, _ids) = payload_context(&input);
    let empty: Vec<Value> = Vec::new();
    let items = payload.get("items").and_then(|v| v.as_array()).unwrap_or(&empty);
    let mut ops: Vec<Operation> = Vec::new();
    for it in items {
        let is_service = match it.get("is_service") {
            Some(Value::Bool(b)) => *b,
            Some(Value::Number(n)) => n.as_i64().unwrap_or(0) != 0,
            Some(Value::String(st)) => matches!(st.as_str(), "1" | "true" | "True"),
            _ => false,
        };
        let product_id = it.get("product_id").cloned().unwrap_or(Value::Null);
        if is_service || product_id.is_null() {
            continue;
        }
        let qty = it.get("quantity").map(|v| as_i64(v, 0)).unwrap_or(0);
        if qty <= 0 {
            continue;
        }
        let mut p = Map::new();
        p.insert("product_id".into(), product_id);
        p.insert("qty".into(), json!(qty));
        ops.push(Operation::sql("inventory.stock.decrease", p));
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

    fn merge(payload: Value, mut base: Value) -> Value {
        base["payload"] = payload;
        base
    }

    #[test]
    fn bulk_create_generates_skus_and_correlates_ids() {
        let payload = json!({
            "existing_count": 5,
            "products": [
                { "name": "Café", "price": 4.5 },
                { "name": "Té", "sku": "TE-1", "price": 3.0, "stock": 20 }
            ]
        });
        let out = bulk_create_pure(merge(payload, ctx(4)));
        assert_eq!(out.operations.len(), 2);
        assert_eq!(out.operations[0].command, "inventory._insert_product");
        // SKU autogenerado continúa desde existing_count (5 → PROD-006).
        assert_eq!(out.operations[0].params["sku"], json!("PROD-006"));
        assert_eq!(out.operations[0].params["product_id"], json!("id-0"));
        // SKU explícito se respeta.
        assert_eq!(out.operations[1].params["sku"], json!("TE-1"));
        assert_eq!(out.operations[1].params["product_id"], json!("id-1"));
        assert_eq!(out.operations[1].params["stock"], json!(20));
    }

    #[test]
    fn bulk_create_caps_at_100() {
        let products: Vec<Value> = (0..150).map(|i| json!({ "name": format!("P{i}"), "price": 1 })).collect();
        let out = bulk_create_pure(merge(json!({ "products": products }), ctx(150)));
        assert_eq!(out.operations.len(), MAX_BULK);
    }

    #[test]
    fn receive_stock_skips_invalid_lines() {
        let payload = json!({
            "items": [
                { "product_id": "p1", "qty": 10, "unit_cost": 2.5 },
                { "product_id": "p2", "qty": 0 },          // qty inválida → omitida
                { "qty": 5 },                               // sin product_id → omitida
                { "product_id": "p3", "qty": 3 }
            ]
        });
        let out = receive_stock_pure(merge(payload, ctx(0)));
        assert_eq!(out.operations.len(), 2);
        assert_eq!(out.operations[0].command, "inventory._receive_line");
        assert_eq!(out.operations[0].params["product_id"], json!("p1"));
        assert_eq!(out.operations[0].params["qty"], json!(10));
        assert_eq!(out.operations[0].params["unit_cost"], json!(2.5));
        assert_eq!(out.operations[1].params["product_id"], json!("p3"));
        assert_eq!(out.operations[1].params["unit_cost"], Value::Null);
    }

    #[test]
    fn decrease_on_sale_skips_services_and_nulls() {
        let payload = json!({ "items": [
            { "product_id": "p1", "quantity": 3, "is_service": false },
            { "product_id": "p2", "quantity": 1, "is_service": true },   // servicio → omitido
            { "product_id": null, "quantity": 5 },                        // sin id → omitido
            { "product_id": "p3", "quantity": 2 }
        ]});
        let out = decrease_on_sale_pure(json!({ "payload": payload, "context": { "new_ids": [] } }));
        assert_eq!(out.operations.len(), 2);
        assert_eq!(out.operations[0].command, "inventory.stock.decrease");
        assert_eq!(out.operations[0].params["product_id"], json!("p1"));
        assert_eq!(out.operations[0].params["qty"], json!(3));
        assert_eq!(out.operations[1].params["product_id"], json!("p3"));
    }
}
