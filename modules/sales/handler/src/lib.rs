//! Handler WASM (Tier 2) del módulo `sales` — completar una venta.
//! Portado de old_modules/m_sales (SaleItem.calculate_line_totals,
//! Sale.calculate_totals, calculate_change). Lógica pura, sin BD: recibe
//! `{payload, context}`, calcula líneas/IVA/totales y devuelve **intenciones**
//! (ops SQL del mismo módulo) que el host valida y ejecuta en una transacción,
//! más el evento `sale.completed` (lo consumen inventory, customers, cash_register).
//!
//! Ids: el host pasa `context.new_ids` (autoridad de ids); new_ids[0]=venta,
//! new_ids[1..]=líneas. Número atómico YYYYMMDD-NNNN: _bump_counter (upsert) +
//! _insert_sale leyendo el contador con subquery en la misma transacción.

use erplora_guest_sdk::{Event, Operation, Output};
use serde_json::{json, Map, Value};

#[cfg(feature = "guest")]
use extism_pdk::*;

#[cfg(feature = "guest")]
#[plugin_fn]
pub fn complete_sale(input: Json<erplora_guest_sdk::Input>) -> FnResult<Json<Output>> {
    Ok(Json(complete_sale_pure(input.into_inner().into_value())))
}

/// Redondeo a 2 decimales half-even (igual que Decimal.quantize de Python).
fn round2(x: f64) -> f64 {
    let scaled = x * 100.0;
    let floor = scaled.floor();
    let diff = scaled - floor;
    let rounded = if (diff - 0.5).abs() < 1e-9 {
        if (floor as i64) % 2 == 0 { floor } else { floor + 1.0 }
    } else {
        scaled.round()
    };
    rounded / 100.0
}

fn as_f64(v: &Value, d: f64) -> f64 {
    match v {
        Value::Number(n) => n.as_f64().unwrap_or(d),
        Value::String(s) => s.trim().parse::<f64>().unwrap_or(d),
        _ => d,
    }
}
fn as_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        _ => String::new(),
    }
}
fn as_bool(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_i64().unwrap_or(0) != 0,
        Value::String(s) => matches!(s.as_str(), "1" | "true" | "True" | "yes"),
        _ => false,
    }
}
fn str_or(p: &Value, k: &str, d: &str) -> String {
    let s = as_str(p.get(k).unwrap_or(&Value::Null));
    if s.is_empty() { d.to_string() } else { s }
}
fn num(x: f64) -> Value { json!(round2(x)) }

struct LineTotals { net: f64, tax: f64, line: f64 }

fn calc_line(unit_price: f64, qty: f64, disc_pct: f64, tax_rate: f64, tax_incl: bool) -> LineTotals {
    let discounted = unit_price - unit_price * (disc_pct / 100.0);
    if tax_incl {
        let divisor = 1.0 + tax_rate / 100.0;
        let net = round2((discounted / divisor) * qty);
        let line = round2(discounted * qty);
        LineTotals { net, tax: round2(line - net), line }
    } else {
        let net = round2(discounted * qty);
        let tax = round2(net * (tax_rate / 100.0));
        LineTotals { net, tax, line: round2(net + tax) }
    }
}

fn day_from_now(now: &str) -> String {
    let date = now.split('T').next().unwrap_or("");
    let digits: String = date.chars().filter(|c| c.is_ascii_digit()).collect();
    if digits.len() >= 8 { digits[..8].to_string() } else { "00000000".to_string() }
}

/// Lógica pura: `{payload, context}` → Output (intenciones).
pub fn complete_sale_pure(input: Value) -> Output {
    let payload = input.get("payload").cloned().unwrap_or(Value::Null);
    let context = input.get("context").cloned().unwrap_or(Value::Null);
    let empty: Vec<Value> = Vec::new();
    let new_ids = context.get("new_ids").and_then(|v| v.as_array()).unwrap_or(&empty);
    let now = context.get("now").map(as_str).unwrap_or_default();
    let day = day_from_now(&now);
    let sale_id = new_ids.first().map(as_str).unwrap_or_default();

    let tax_incl = payload.get("tax_included").map(as_bool).unwrap_or(true);
    let sale_disc = payload.get("discount_percent").map(|v| as_f64(v, 0.0)).unwrap_or(0.0);
    let items = payload.get("items").and_then(|v| v.as_array()).unwrap_or(&empty);

    let mut subtotal = 0.0;
    let mut tax_total = 0.0;
    let mut gross = 0.0;
    let mut breakdown: Vec<(String, f64, f64)> = Vec::new();
    let mut ops: Vec<Operation> = Vec::new();

    let mut bump = Map::new();
    bump.insert("day".into(), json!(day));
    ops.push(Operation::sql("sales._bump_counter", bump));

    let header_idx = ops.len();
    ops.push(Operation::sql("sales._insert_sale", Map::new())); // placeholder

    for (i, item) in items.iter().enumerate() {
        let unit_price = as_f64(item.get("price").unwrap_or(&Value::Null), 0.0);
        let qty = item.get("quantity").map(|v| as_f64(v, 1.0)).unwrap_or(1.0);
        let line_disc = item.get("discount").map(|v| as_f64(v, 0.0)).unwrap_or(0.0);
        let tax_rate = item.get("tax_rate").map(|v| as_f64(v, 0.0)).unwrap_or(0.0);
        let t = calc_line(unit_price, qty, line_disc, tax_rate, tax_incl);
        subtotal += t.net; tax_total += t.tax; gross += t.line;

        let rate_key = format!("{:.2}", tax_rate);
        if let Some(e) = breakdown.iter_mut().find(|(k, _, _)| *k == rate_key) {
            e.1 += t.net; e.2 += t.tax;
        } else {
            breakdown.push((rate_key, t.net, t.tax));
        }

        let line_id = new_ids.get(i + 1).map(as_str).unwrap_or_default();
        let mut p = Map::new();
        p.insert("line_id".into(), json!(line_id));
        p.insert("sale_id".into(), json!(sale_id));
        p.insert("product_id".into(), item.get("product_id").cloned().unwrap_or(Value::Null));
        p.insert("product_name".into(), json!(as_str(item.get("product_name").unwrap_or(&Value::Null))));
        p.insert("product_sku".into(), json!(str_or(item, "product_sku", "")));
        p.insert("is_service".into(), json!(item.get("is_service").map(as_bool).unwrap_or(false) as i64));
        p.insert("quantity".into(), json!(qty));
        p.insert("unit_price".into(), num(unit_price));
        p.insert("discount_percent".into(), num(line_disc));
        p.insert("tax_rate".into(), num(tax_rate));
        p.insert("tax_class_name".into(), json!(str_or(item, "tax_class_name", "")));
        p.insert("net_amount".into(), num(t.net));
        p.insert("tax_amount".into(), num(t.tax));
        p.insert("line_total".into(), num(t.line));
        ops.push(Operation::sql("sales._insert_line", p));
    }

    let discount_amount = if sale_disc > 0.0 { round2(gross * (sale_disc / 100.0)) } else { 0.0 };
    let total = round2(gross - discount_amount);
    let tendered = payload.get("amount_tendered").map(|v| as_f64(v, 0.0)).unwrap_or(0.0);
    let change = if tendered - total > 0.0 { round2(tendered - total) } else { 0.0 };

    let mut tb = Map::new();
    for (k, base, tax) in &breakdown {
        tb.insert(k.clone(), json!({ "base": round2(*base), "tax": round2(*tax) }));
    }
    let tax_breakdown_json = Value::Object(tb).to_string();

    let mut h = Map::new();
    h.insert("sale_id".into(), json!(sale_id));
    h.insert("day".into(), json!(day));
    h.insert("status".into(), json!(str_or(&payload, "status", "completed")));
    h.insert("subtotal".into(), num(subtotal));
    h.insert("tax_amount".into(), num(tax_total));
    h.insert("discount_amount".into(), num(discount_amount));
    h.insert("discount_percent".into(), num(sale_disc));
    h.insert("total".into(), num(total));
    h.insert("tax_breakdown".into(), json!(tax_breakdown_json));
    h.insert("payment_method_id".into(), payload.get("payment_method_id").cloned().unwrap_or(Value::Null));
    h.insert("payment_method_name".into(), json!(str_or(&payload, "payment_method_name", "")));
    h.insert("amount_tendered".into(), num(tendered));
    h.insert("change_due".into(), num(change));
    h.insert("customer_id".into(), payload.get("customer_id").cloned().unwrap_or(Value::Null));
    h.insert("customer_name".into(), json!(str_or(&payload, "customer_name", "")));
    h.insert("notes".into(), json!(str_or(&payload, "notes", "")));
    h.insert("channel".into(), json!(str_or(&payload, "channel", "")));
    h.insert("source_module".into(), json!(str_or(&payload, "source_module", "pos")));
    h.insert("table_id".into(), payload.get("table_id").cloned().unwrap_or(Value::Null));
    ops[header_idx] = Operation::sql("sales._insert_sale", h);

    // Líneas compactas para listeners cross-módulo (inventory descuenta stock por
    // product_id+quantity, saltando servicios). El payload del evento ES lo que
    // recibe el listener; por eso viaja la lista, no solo los totales.
    let event_items: Vec<Value> = items
        .iter()
        .map(|it| json!({
            "product_id": it.get("product_id").cloned().unwrap_or(Value::Null),
            "product_name": as_str(it.get("product_name").unwrap_or(&Value::Null)),
            "quantity": it.get("quantity").map(|v| as_f64(v, 1.0)).unwrap_or(1.0),
            "unit_price": as_f64(it.get("price").unwrap_or(&Value::Null), 0.0),
            "tax_rate": it.get("tax_rate").map(|v| as_f64(v, 0.0)).unwrap_or(0.0),
            "is_service": it.get("is_service").map(as_bool).unwrap_or(false),
        }))
        .collect();

    let event = Event::new("sale.completed", json!({
        "sender": "sales",
        "sale_id": sale_id,
        "total": round2(total),
        "subtotal": round2(subtotal),
        "tax_amount": round2(tax_total),
        "items_count": items.len(),
        "items": event_items,
        "customer_id": payload.get("customer_id").cloned().unwrap_or(Value::Null),
        "customer_name": str_or(&payload, "customer_name", ""),
    }));

    Output { operations: ops, events: vec![event] }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input(items: Value, ids: usize, tendered: f64) -> Value {
        let new_ids: Vec<Value> = (0..ids).map(|i| json!(format!("id-{i}"))).collect();
        json!({
            "payload": { "items": items, "tax_included": true, "amount_tendered": tendered, "customer_name": "Bar Manolo" },
            "context": { "hub_id": "h1", "current_user_id": "u1", "now": "2026-05-31T10:00:00+00:00", "new_ids": new_ids }
        })
    }

    #[test]
    fn round2_half_even() {
        assert_eq!(round2(0.125), 0.12);
        assert_eq!(round2(100.0 / 1.21), 82.64);
    }

    #[test]
    fn line_tax_inclusive() {
        let t = calc_line(121.0, 1.0, 0.0, 21.0, true);
        assert_eq!(t.net, 100.0); assert_eq!(t.tax, 21.0); assert_eq!(t.line, 121.0);
    }
    #[test]
    fn line_tax_exclusive() {
        let t = calc_line(100.0, 1.0, 0.0, 21.0, false);
        assert_eq!(t.net, 100.0); assert_eq!(t.tax, 21.0); assert_eq!(t.line, 121.0);
    }
    #[test]
    fn line_discount_inclusive() {
        let t = calc_line(110.0, 2.0, 10.0, 21.0, true);
        assert_eq!(t.line, 198.0); assert_eq!(t.net, 163.64); assert_eq!(t.tax, 34.36);
    }

    #[test]
    fn emits_counter_sale_lines_event() {
        let items = json!([
            { "product_name": "Café", "price": 1.21, "quantity": 2, "tax_rate": 21.0 },
            { "product_name": "Agua", "price": 1.10, "quantity": 1, "tax_rate": 10.0 }
        ]);
        let out = complete_sale_pure(input(items, 8, 20.0));
        assert_eq!(out.operations.len(), 4); // counter + sale + 2 líneas
        assert_eq!(out.operations[0].command, "sales._bump_counter");
        assert_eq!(out.operations[1].command, "sales._insert_sale");
        assert_eq!(out.operations[2].command, "sales._insert_line");
        assert_eq!(out.operations[1].params["sale_id"], json!("id-0"));
        assert_eq!(out.operations[2].params["sale_id"], json!("id-0"));
        assert_eq!(out.operations[2].params["line_id"], json!("id-1"));
        assert_eq!(out.events[0].name, "sale.completed");
        assert_eq!(out.events[0].payload["items_count"], json!(2));
    }

    #[test]
    fn totals_and_change() {
        let items = json!([{ "product_name": "X", "price": 121.0, "quantity": 1, "tax_rate": 21.0 }]);
        let out = complete_sale_pure(input(items, 4, 200.0));
        let s = &out.operations[1].params;
        assert_eq!(s["subtotal"], json!(100.0));
        assert_eq!(s["tax_amount"], json!(21.0));
        assert_eq!(s["total"], json!(121.0));
        assert_eq!(s["change_due"], json!(79.0));
    }
}
