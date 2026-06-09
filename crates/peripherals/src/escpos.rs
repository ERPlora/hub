//! Render ESC/POS: convierte un `document_type` + `data` (JSON del Hub) en bytes para enviar
//! por el socket TCP de la impresora.
//!
//! Porta:
//!   - los comandos crudos de `_RawNetworkPrinter` (`discovery.py`): align/bold/size/cut.
//!   - los renderizadores de documento de `printer.py` (`_print_receipt`, `_print_kitchen_order`,
//!     `_print_invoice`, `_print_delivery_note`, `_print_barcode_label`, `_print_cash_report`,
//!     `_print_generic`) y `test_print`.

use crate::Result;
use oem_cp::{Cp437, StrExt};
use serde::{Deserialize, Serialize};

/// Ancho de papel estándar en columnas (80mm ≈ 32 chars). Espejo del `padding = 32 - …` de Python.
pub const LINE_WIDTH: usize = 32;

/// Tipos de documento soportados (espejo del `if document_type == …` de `PrinterManager`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DocumentType {
    Receipt,
    KitchenOrder,
    Invoice,
    DeliveryNote,
    BarcodeLabel,
    CashSessionReport,
    Generic,
}

impl DocumentType {
    /// Mapea el string del protocolo; desconocido → `Generic` (igual que el `else` de Python).
    pub fn from_wire(s: &str) -> Self {
        match s {
            "receipt" => Self::Receipt,
            "kitchen_order" => Self::KitchenOrder,
            "invoice" => Self::Invoice,
            "delivery_note" => Self::DeliveryNote,
            "barcode_label" => Self::BarcodeLabel,
            "cash_session_report" => Self::CashSessionReport,
            _ => Self::Generic,
        }
    }
}

/// Alineación horizontal (ESC a n).
#[derive(Debug, Clone, Copy)]
pub enum Align {
    Left,
    Center,
    Right,
}

/// Constructor de un buffer ESC/POS. Cada método empuja bytes al buffer interno.
/// Porta `_RawNetworkPrinter.{set,text,cut,barcode}` (codificación cp437).
#[derive(Default)]
pub struct EscposBuilder {
    buf: Vec<u8>,
}

impl EscposBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    /// Estado de impresión: alineación + negrita + doble alto/ancho (`ESC a`, `ESC E`, `GS !`).
    /// Espejo exacto de `_RawNetworkPrinter.set`.
    pub fn set(&mut self, align: Align, bold: bool, double_h: bool, double_w: bool) -> &mut Self {
        // ESC a n  (align: left=0, center=1, right=2)
        let a = match align {
            Align::Left => 0u8,
            Align::Center => 1u8,
            Align::Right => 2u8,
        };
        self.buf.extend_from_slice(&[0x1b, 0x61, a]);
        // ESC E n  (bold)
        self.buf
            .extend_from_slice(&[0x1b, 0x45, if bold { 1 } else { 0 }]);
        // GS ! n  (n: |0x10 double_height, |0x20 double_width)
        let mut n = 0u8;
        if double_h {
            n |= 0x10;
        }
        if double_w {
            n |= 0x20;
        }
        self.buf.extend_from_slice(&[0x1d, 0x21, n]);
        self
    }

    /// Texto (cp437, reemplazando lo no representable por '?'). Porta `_RawNetworkPrinter.text`
    /// (`txt.encode('cp437', errors='replace')`).
    pub fn text(&mut self, txt: &str) -> &mut Self {
        for cp in txt.to_cp_lossy::<Cp437>() {
            self.buf.push(cp.0);
        }
        self
    }

    /// Corte de papel (`GS V`). Porta `_RawNetworkPrinter.cut`: `\n\n\n` + GS V 1.
    pub fn cut(&mut self) -> &mut Self {
        self.buf.extend_from_slice(b"\n\n\n");
        self.buf.extend_from_slice(&[0x1d, 0x56, 0x01]);
        self
    }

    /// Código de barras. Porta el fallback de `_RawNetworkPrinter.barcode`, que imprime
    /// `[code]\n` como texto en vez de un GS k real (el camino python-escpos EAN13 no existe
    /// en el fallback crudo, que es lo que portamos aquí).
    pub fn barcode(&mut self, code: &str) -> &mut Self {
        self.text(&format!("[{code}]\n"));
        self
    }

    /// Línea de total alineada a la derecha: `Etiqueta        12.50`. Porta `_print_total_line`.
    pub fn total_line(&mut self, label: &str, amount: f64) -> &mut Self {
        let amount_str = format!("{amount:.2}");
        let padding = (LINE_WIDTH as isize - label.len() as isize - amount_str.len() as isize).max(1)
            as usize;
        self.text(&format!("{label}{}{amount_str}\n", " ".repeat(padding)));
        self
    }

    /// Devuelve los bytes acumulados.
    pub fn finish(self) -> Vec<u8> {
        self.buf
    }
}

/// Render principal: documento → bytes ESC/POS listos para el socket.
/// Despacha por `DocumentType` igual que `PrinterManager.print_document`.
pub fn render_document(doc: DocumentType, data: &serde_json::Value) -> Result<Vec<u8>> {
    let mut b = EscposBuilder::new();
    match doc {
        // invoice == receipt (`_print_invoice` delega en `_print_receipt`).
        DocumentType::Receipt | DocumentType::Invoice => render_receipt(&mut b, data),
        DocumentType::KitchenOrder => render_kitchen_order(&mut b, data),
        DocumentType::DeliveryNote => render_delivery_note(&mut b, data),
        DocumentType::BarcodeLabel => render_barcode_label(&mut b, data),
        DocumentType::CashSessionReport => render_cash_report(&mut b, data),
        DocumentType::Generic => render_generic(&mut b, data),
    }
    Ok(b.finish())
}

/// Página de prueba. Porta `PrinterManager.test_print`.
pub fn render_test_page(printer_id: &str) -> Vec<u8> {
    let mut b = EscposBuilder::new();
    b.set(Align::Center, false, false, false);
    b.text("================================\n");
    b.set(Align::Center, true, true, false);
    b.text("ERPlora Bridge\n");
    b.set(Align::Center, false, false, false);
    b.text("--------------------------------\n");
    b.text("Test Print OK\n");
    b.text(&format!("{}\n", now_ymd_hms()));
    b.text("--------------------------------\n");
    b.text(&format!("Printer: {printer_id}\n"));
    b.text("================================\n");
    b.cut();
    b.finish()
}

// ─── Helpers de lectura de `data` (espejo de los `.get(...)` de Python) ──────

/// `%d/%m/%Y %H:%M` en hora local (como `datetime.now().strftime` de Python).
fn now_dmy_hm() -> String {
    chrono::Local::now().format("%d/%m/%Y %H:%M").to_string()
}

/// `%Y-%m-%d %H:%M:%S` en hora local (test page).
fn now_ymd_hms() -> String {
    chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
}

/// `%H:%M` en hora local (kitchen order).
fn now_hm() -> String {
    chrono::Local::now().format("%H:%M").to_string()
}

/// Lee un campo string; ausente/no-string → `default`.
fn str_field<'a>(data: &'a serde_json::Value, key: &str, default: &'a str) -> &'a str {
    data.get(key).and_then(|v| v.as_str()).unwrap_or(default)
}

/// `true` si el campo existe y es "truthy" como el `if data.get(x):` de Python
/// (string no vacío, número != 0, bool true).
fn is_truthy(data: &serde_json::Value, key: &str) -> bool {
    match data.get(key) {
        Some(serde_json::Value::String(s)) => !s.is_empty(),
        Some(serde_json::Value::Number(n)) => n.as_f64().map(|f| f != 0.0).unwrap_or(false),
        Some(serde_json::Value::Bool(b)) => *b,
        Some(serde_json::Value::Null) | None => false,
        Some(_) => true,
    }
}

/// Renderiza un valor JSON tal como lo haría `f"{value}"` de Python para el documento genérico.
fn json_to_display(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Bool(b) => {
            // Python imprime True/False con mayúscula inicial.
            if *b { "True".to_string() } else { "False".to_string() }
        }
        serde_json::Value::Null => "None".to_string(),
        other => other.to_string(),
    }
}

// ─── Renderizadores de documento (porta `printer.py`) ────────────────────────

/// Porta `_print_receipt`.
fn render_receipt(b: &mut EscposBuilder, data: &serde_json::Value) {
    b.set(Align::Center, true, false, false);
    let business_name = str_field(data, "business_name", "ERPlora");
    b.text(&format!("{business_name}\n"));

    if is_truthy(data, "business_address") {
        b.set(Align::Center, false, false, false);
        b.text(&format!("{}\n", str_field(data, "business_address", "")));
    }

    if is_truthy(data, "vat_number") {
        b.text(&format!("NIF: {}\n", str_field(data, "vat_number", "")));
    }

    if is_truthy(data, "phone") {
        b.text(&format!("Tel: {}\n", str_field(data, "phone", "")));
    }

    b.text("================================\n");

    b.set(Align::Left, false, false, false);
    let receipt_id = str_field(data, "receipt_id", "");
    b.text(&format!("Ticket: {receipt_id}\n"));
    b.text(&format!("Fecha: {}\n", now_dmy_hm()));

    if is_truthy(data, "cashier") {
        b.text(&format!("Cajero: {}\n", str_field(data, "cashier", "")));
    }

    if is_truthy(data, "customer_name") {
        b.text(&format!("Cliente: {}\n", str_field(data, "customer_name", "")));
    }

    b.text("--------------------------------\n");

    if let Some(items) = data.get("items").and_then(|v| v.as_array()) {
        for item in items {
            let name = str_field(item, "name", "");
            let qty = item.get("quantity").and_then(|v| v.as_f64()).unwrap_or(1.0);
            let total = item.get("total").and_then(|v| v.as_f64()).unwrap_or(0.0);

            b.set(Align::Left, false, false, false);
            let line = format!("{}x {name}", fmt_qty(item.get("quantity"), qty));
            let total_str = format!("{total:.2}");
            let padding = (LINE_WIDTH as isize - line.len() as isize - total_str.len() as isize)
                .max(1) as usize;
            b.text(&format!("{line}{}{total_str}\n", " ".repeat(padding)));

            if is_truthy(item, "notes") {
                b.set(Align::Left, false, false, false);
                b.text(&format!("  > {}\n", str_field(item, "notes", "")));
            }
        }
    }

    b.text("--------------------------------\n");

    if let Some(subtotal) = data.get("subtotal").and_then(|v| v.as_f64()) {
        b.total_line("Subtotal", subtotal);
    }

    if let Some(tax_amount) = data.get("tax_amount").and_then(|v| v.as_f64()) {
        let tax_label = str_field(data, "tax_label", "IVA");
        b.total_line(tax_label, tax_amount);
    }

    if let Some(discount) = data.get("discount").and_then(|v| v.as_f64()) {
        if discount > 0.0 {
            b.total_line("Descuento", -discount);
        }
    }

    b.text("================================\n");
    b.set(Align::Left, true, true, false);
    let total = data.get("total").and_then(|v| v.as_f64()).unwrap_or(0.0);
    b.total_line("TOTAL", total);
    b.set(Align::Left, false, false, false);
    b.text("================================\n");

    if is_truthy(data, "payment_method") {
        b.set(Align::Left, false, false, false);
        b.text(&format!("Pago: {}\n", str_field(data, "payment_method", "")));
    }

    if let Some(paid) = data.get("paid").and_then(|v| v.as_f64()) {
        b.total_line("Entregado", paid);
    }

    if let Some(change) = data.get("change").and_then(|v| v.as_f64()) {
        if change > 0.0 {
            b.total_line("Cambio", change);
        }
    }

    b.text("\n");
    if is_truthy(data, "receipt_header") {
        b.set(Align::Center, false, false, false);
        b.text(&format!("{}\n", str_field(data, "receipt_header", "")));
    }

    if is_truthy(data, "receipt_footer") {
        b.set(Align::Center, false, false, false);
        b.text(&format!("{}\n", str_field(data, "receipt_footer", "")));
    }

    b.set(Align::Center, false, false, false);
    b.text("\nGracias por su compra\n\n");

    b.cut();
}

/// Porta `_print_kitchen_order`.
fn render_kitchen_order(b: &mut EscposBuilder, data: &serde_json::Value) {
    b.set(Align::Center, true, true, true);
    b.text("COCINA\n");

    b.set(Align::Center, true, true, false);
    // order_number = data.get('receipt_id', data.get('order_number', ''))
    let order_number = data
        .get("receipt_id")
        .and_then(|v| v.as_str())
        .or_else(|| data.get("order_number").and_then(|v| v.as_str()))
        .unwrap_or("");
    b.text(&format!("#{order_number}\n"));

    b.set(Align::Center, false, false, false);
    b.text("================================\n");

    if is_truthy(data, "table") {
        b.set(Align::Left, true, true, false);
        b.text(&format!("Mesa: {}\n", str_field(data, "table", "")));
    }

    b.set(Align::Left, false, false, false);
    if is_truthy(data, "waiter") {
        b.text(&format!("Camarero: {}\n", str_field(data, "waiter", "")));
    }

    b.text(&format!("Hora: {}\n", now_hm()));
    b.text("--------------------------------\n");

    if let Some(items) = data.get("items").and_then(|v| v.as_array()) {
        for item in items {
            let qty = item.get("quantity").and_then(|v| v.as_f64()).unwrap_or(1.0);
            let name = str_field(item, "name", "");

            b.set(Align::Left, true, true, false);
            b.text(&format!("{}x {name}\n", fmt_qty(item.get("quantity"), qty)));

            if is_truthy(item, "notes") {
                b.set(Align::Left, false, false, false);
                b.text(&format!("   >> {}\n", str_field(item, "notes", "")));
            }
        }
    }

    b.text("================================\n");

    let priority = str_field(data, "priority", "NORMAL");
    if priority == "HIGH" {
        b.set(Align::Center, true, true, false);
        b.text("!! URGENTE !!\n");
    }

    b.text("\n");
    b.cut();
}

/// Porta `_print_delivery_note`.
fn render_delivery_note(b: &mut EscposBuilder, data: &serde_json::Value) {
    b.set(Align::Center, true, false, false);
    b.text("ALBARAN\n");
    b.text("================================\n");

    b.set(Align::Left, false, false, false);
    b.text(&format!("N: {}\n", str_field(data, "receipt_id", "")));
    b.text(&format!("Fecha: {}\n", now_dmy_hm()));

    if is_truthy(data, "customer_name") {
        b.text(&format!("Cliente: {}\n", str_field(data, "customer_name", "")));
    }
    if is_truthy(data, "delivery_address") {
        b.text(&format!("Dir: {}\n", str_field(data, "delivery_address", "")));
    }

    b.text("--------------------------------\n");

    if let Some(items) = data.get("items").and_then(|v| v.as_array()) {
        for item in items {
            let qty = item.get("quantity").and_then(|v| v.as_f64()).unwrap_or(1.0);
            let name = str_field(item, "name", "");
            b.text(&format!("{}x {name}\n", fmt_qty(item.get("quantity"), qty)));
        }
    }

    b.text("================================\n");
    b.text("\nFirma: _______________\n\n");
    b.cut();
}

/// Porta `_print_barcode_label`.
fn render_barcode_label(b: &mut EscposBuilder, data: &serde_json::Value) {
    b.set(Align::Center, true, false, false);
    b.text(&format!("{}\n", str_field(data, "product_name", "")));

    let barcode_value = str_field(data, "barcode", "");
    if !barcode_value.is_empty() {
        // El fallback crudo de Python siempre imprime [code] como texto.
        b.barcode(barcode_value);
    }

    if let Some(price) = data.get("price").and_then(|v| v.as_f64()) {
        b.set(Align::Center, true, true, false);
        b.text(&format!("{price:.2}\n"));
    }

    b.cut();
}

/// Porta `_print_cash_report`.
fn render_cash_report(b: &mut EscposBuilder, data: &serde_json::Value) {
    b.set(Align::Center, true, false, false);
    b.text("CIERRE DE CAJA\n");
    b.text("================================\n");

    b.set(Align::Left, false, false, false);
    b.text(&format!("Sesion: {}\n", str_field(data, "receipt_id", "")));
    b.text(&format!("Fecha: {}\n", now_dmy_hm()));

    if is_truthy(data, "cashier") {
        b.text(&format!("Cajero: {}\n", str_field(data, "cashier", "")));
    }

    b.text("--------------------------------\n");

    let opening = data.get("opening_balance").and_then(|v| v.as_f64()).unwrap_or(0.0);
    let closing = data.get("closing_balance").and_then(|v| v.as_f64()).unwrap_or(0.0);
    b.total_line("Apertura", opening);
    b.total_line("Cierre", closing);

    let diff = closing - opening;
    b.total_line("Diferencia", diff);

    b.text("--------------------------------\n");

    if let Some(transactions) = data.get("transactions").and_then(|v| v.as_array()) {
        for tx in transactions {
            // label = tx.get('label', tx.get('type', ''))
            let label = tx
                .get("label")
                .and_then(|v| v.as_str())
                .or_else(|| tx.get("type").and_then(|v| v.as_str()))
                .unwrap_or("");
            let amount = tx.get("amount").and_then(|v| v.as_f64()).unwrap_or(0.0);
            b.total_line(label, amount);
        }
    }

    b.text("================================\n\n");
    b.cut();
}

/// Porta `_print_generic`.
fn render_generic(b: &mut EscposBuilder, data: &serde_json::Value) {
    b.set(Align::Center, true, false, false);
    b.text(&format!("{}\n", str_field(data, "title", "Documento")));
    b.text("================================\n");

    b.set(Align::Left, false, false, false);
    if let Some(obj) = data.as_object() {
        for (key, value) in obj {
            if key == "title" || key == "receipt_id" {
                continue;
            }
            b.text(&format!("{key}: {}\n", json_to_display(value)));
        }
    }

    b.text("================================\n\n");
    b.cut();
}

/// Formatea la cantidad como lo hace `f"{qty}x …"` en Python: si el JSON trae un entero
/// (`2`) se imprime `2`, no `2.0`. Si trae decimal (`1.5`) se imprime `1.5`.
fn fmt_qty(raw: Option<&serde_json::Value>, fallback: f64) -> String {
    match raw {
        Some(serde_json::Value::Number(n)) => {
            if let Some(i) = n.as_i64() {
                i.to_string()
            } else if let Some(u) = n.as_u64() {
                u.to_string()
            } else {
                n.to_string()
            }
        }
        Some(serde_json::Value::String(s)) => s.clone(),
        _ => {
            // Sin valor → el default de Python es el entero 1.
            if fallback.fract() == 0.0 {
                format!("{}", fallback as i64)
            } else {
                fallback.to_string()
            }
        }
    }
}
