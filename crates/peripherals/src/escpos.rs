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
    /// Maps the protocol string; unknown → `Generic` (same as Python's `else`).
    ///
    /// ⚠️ **Lenient on purpose, and only for the retired standalone Bridge** (`apps/bridge`), whose
    /// wire this behaviour came from. Anything new must use [`DocumentType::parse`]: see why there.
    pub fn from_wire(s: &str) -> Self {
        Self::parse(s).unwrap_or(Self::Generic)
    }

    /// Maps the protocol string, **refusing what it does not know** (hub#501).
    ///
    /// This is the strict half of [`from_wire`], and it exists because the lenient one hides the
    /// most expensive kind of failure: a `Kitchen` or a `kitchn` used to render as `Generic` — a
    /// nameless dump of key/value pairs — so the kitchen got a piece of paper that was not an order
    /// and **nobody found out until the plate was missing**. A ticket that fails loudly is cheaper
    /// than one that fails quietly, so the caller gets a `None` it has to deal with.
    ///
    /// It is deliberately the same vocabulary the hub's queue accepts
    /// (`erplora_runtime::print_queue::DOCUMENT_TYPES`) — two guards, two layers, different
    /// messages, so neither can be deleted with the suite still green.
    pub fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "receipt" => Self::Receipt,
            "kitchen_order" => Self::KitchenOrder,
            "invoice" => Self::Invoice,
            "delivery_note" => Self::DeliveryNote,
            "barcode_label" => Self::BarcodeLabel,
            "cash_session_report" => Self::CashSessionReport,
            "generic" => Self::Generic,
            _ => return None,
        })
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

    /// Código de barras **nativo** (`GS k`, función B). Sustituye al antiguo fallback de texto
    /// `[code]` del Bridge Python (bridge#1):
    ///   - 12-13 dígitos → **EAN13** (m=67).
    ///   - resto → **CODE128** (m=73) en code set B (prefijo `{B`); lo no-ASCII-imprimible → `?`.
    ///
    /// Configura altura (`GS h`), ancho de módulo (`GS w`) y HRI debajo (`GS H 2`, fuente A
    /// `GS f 0`) antes de emitir el símbolo. Si el código está vacío o excede el límite del
    /// comando (255 bytes) cae al fallback de texto `[code]` para no enviar bytes inválidos.
    pub fn barcode(&mut self, code: &str) -> &mut Self {
        if code.is_empty() || code.len() > 250 {
            self.text(&format!("[{code}]\n"));
            return self;
        }

        // GS h n — altura del símbolo (puntos).
        self.buf.extend_from_slice(&[0x1d, 0x68, 80]);
        // GS w n — ancho de módulo.
        self.buf.extend_from_slice(&[0x1d, 0x77, 2]);
        // GS H n — HRI debajo del símbolo (2).
        self.buf.extend_from_slice(&[0x1d, 0x48, 2]);
        // GS f n — fuente A para el HRI.
        self.buf.extend_from_slice(&[0x1d, 0x66, 0]);

        let all_digits = code.chars().all(|c| c.is_ascii_digit());
        if all_digits && (code.len() == 12 || code.len() == 13) {
            // EAN13, función B: GS k 67 n d1..dn (con 12 dígitos la impresora calcula el checksum).
            self.buf.extend_from_slice(&[0x1d, 0x6b, 67, code.len() as u8]);
            self.buf.extend_from_slice(code.as_bytes());
        } else {
            // CODE128, función B: GS k 73 n {B d1..dk (code set B cubre ASCII 32-127).
            let mut payload: Vec<u8> = Vec::with_capacity(code.len() + 2);
            payload.extend_from_slice(b"{B");
            payload.extend(code.bytes().map(|b| if (0x20..0x7f).contains(&b) { b } else { b'?' }));
            self.buf.extend_from_slice(&[0x1d, 0x6b, 73, payload.len() as u8]);
            self.buf.extend_from_slice(&payload);
        }
        self.buf.push(b'\n');
        self
    }

    /// Código QR **nativo** (`GS ( k`, modelo 2) — bridge#1. Secuencia estándar Epson:
    /// fn 165 (modelo 2) → fn 167 (tamaño de módulo) → fn 169 (corrección de errores M) →
    /// fn 180 (almacenar datos) → fn 181 (imprimir). Datos vacíos o > límite del comando
    /// (~7 KB) → no-op.
    pub fn qr(&mut self, data: &str) -> &mut Self {
        let bytes = data.as_bytes();
        if bytes.is_empty() || bytes.len() > 7080 {
            return self;
        }

        // GS ( k 4 0 49 65 50 0 — fn 165: seleccionar modelo 2.
        self.buf.extend_from_slice(&[0x1d, 0x28, 0x6b, 4, 0, 49, 65, 50, 0]);
        // GS ( k 3 0 49 67 n — fn 167: tamaño de módulo (puntos).
        self.buf.extend_from_slice(&[0x1d, 0x28, 0x6b, 3, 0, 49, 67, 4]);
        // GS ( k 3 0 49 69 n — fn 169: nivel de corrección M (49).
        self.buf.extend_from_slice(&[0x1d, 0x28, 0x6b, 3, 0, 49, 69, 49]);
        // GS ( k pL pH 49 80 48 d1..dk — fn 180: almacenar los datos (len = k + 3).
        let len = bytes.len() + 3;
        self.buf.extend_from_slice(&[
            0x1d,
            0x28,
            0x6b,
            (len & 0xff) as u8,
            (len >> 8) as u8,
            49,
            80,
            48,
        ]);
        self.buf.extend_from_slice(bytes);
        // GS ( k 3 0 49 81 48 — fn 181: imprimir el símbolo almacenado.
        self.buf.extend_from_slice(&[0x1d, 0x28, 0x6b, 3, 0, 49, 81, 48]);
        self.buf.push(b'\n');
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

/// Main render: document → ESC/POS bytes ready for the socket.
/// Dispatches on `DocumentType` like `PrinterManager.print_document`.
///
/// **A `data` that is not an object is refused** (hub#501). Every renderer below reads its fields
/// by key (`data.get("items")`, `data.get("total")`); handed an array, a string or a `null` it finds
/// none of them, takes every default and cuts a **blank ticket** without erroring. That is a silent
/// failure at the very end of the chain — the one place where nobody is watching — so it stops here
/// and the print host reports it instead.
pub fn render_document(doc: DocumentType, data: &serde_json::Value) -> Result<Vec<u8>> {
    if !data.is_object() {
        return Err(crate::PeripheralError::InvalidPayload(format!(
            "a document is a JSON object of fields to print, not {}",
            match data {
                serde_json::Value::Null => "null",
                serde_json::Value::Bool(_) => "a boolean",
                serde_json::Value::Number(_) => "a number",
                serde_json::Value::String(_) => "a string",
                _ => "an array",
            }
        )));
    }
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

    // QR opcional del ticket (p.ej. VeriFactu / enlace a factura): campo `qr_data` del payload.
    if is_truthy(data, "qr_data") {
        b.set(Align::Center, false, false, false);
        b.qr(str_field(data, "qr_data", ""));
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
        // GS k nativo (EAN13/CODE128) con HRI debajo; ya no es el fallback de texto [code].
        b.set(Align::Center, false, false, false);
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// **The wire vocabulary, pinned from this side.** The hub's queue keeps the same seven names
    /// (`erplora_runtime::print_queue::DOCUMENT_TYPES`) and refuses anything else at the door; the
    /// two lists are duplicated on purpose (the hub server has no business linking the hardware
    /// crate), so each side pins its own or they drift and the printer starts degrading real
    /// documents to `Generic` in silence.
    #[test]
    fn the_wire_vocabulary_is_exactly_these_seven() {
        let vocabulary = [
            ("receipt", DocumentType::Receipt),
            ("kitchen_order", DocumentType::KitchenOrder),
            ("invoice", DocumentType::Invoice),
            ("delivery_note", DocumentType::DeliveryNote),
            ("barcode_label", DocumentType::BarcodeLabel),
            ("cash_session_report", DocumentType::CashSessionReport),
            ("generic", DocumentType::Generic),
        ];
        for (wire, expected) in vocabulary {
            assert_eq!(DocumentType::parse(wire), Some(expected), "`{wire}`");
            // The serde spelling is the same one: the queue stores this string and the frame
            // carries it, so a rename here would break the wire without touching this list.
            assert_eq!(
                serde_json::to_value(expected).unwrap(),
                json!(wire),
                "`{wire}` must serialise as itself"
            );
        }
    }

    /// **A document type nobody knows is refused, not printed as `Generic`.** This is the guard the
    /// lenient `from_wire` never had: a typo used to reach the paper as a nameless key/value dump,
    /// and the kitchen only noticed when the plate did not arrive.
    #[test]
    fn an_unknown_document_type_is_refused_instead_of_degraded() {
        for unknown in ["Kitchen", "kitchn", "", "html", "KITCHEN_ORDER"] {
            assert_eq!(
                DocumentType::parse(unknown),
                None,
                "`{unknown}` is not a document this printer renders"
            );
        }
        // And the lenient door is still lenient, deliberately: `apps/bridge` (🪦 standalone) speaks
        // that wire and is not being changed. If both behaved the same, one of them would be dead
        // code nobody would miss.
        assert_eq!(DocumentType::from_wire("kitchn"), DocumentType::Generic);
    }

    /// **A `data` that is not an object is refused before it becomes blank paper.** Every renderer
    /// reads by key, so an array or a string produces a ticket with nothing on it — and a cut.
    #[test]
    fn a_document_that_is_not_an_object_is_refused() {
        for bad in [json!(null), json!("<p>ticket</p>"), json!([1, 2]), json!(7)] {
            let err = render_document(DocumentType::Receipt, &bad)
                .expect_err("{bad} is not a document");
            assert!(
                matches!(err, crate::PeripheralError::InvalidPayload(_)),
                "the refusal says the payload is wrong, not that the printer is: {err}"
            );
        }
    }

    /// The guard above rejects **shape**, never content: a real ticket still renders, and what comes
    /// out carries what was asked for. Without this, refusing everything would pass the test above.
    #[test]
    fn a_real_receipt_still_renders_its_lines_and_total() {
        let bytes = render_document(
            DocumentType::Receipt,
            &json!({
                "business_name": "Bar Manolo",
                "receipt_id": "T-42",
                "items": [{ "name": "Cafe", "quantity": 2, "total": 2.4 }],
                "total": 2.4,
            }),
        )
        .expect("a well-formed receipt renders");
        let text = String::from_utf8_lossy(&bytes);
        assert!(text.contains("Bar Manolo"), "the business name is on the paper");
        assert!(text.contains("T-42"), "the ticket number is on the paper");
        assert!(text.contains("2x Cafe"), "the line is on the paper");
        assert!(text.contains("TOTAL"), "the total is on the paper");
        assert_eq!(
            &bytes[bytes.len() - 3..],
            &[0x1d, 0x56, 0x01],
            "and the paper is cut, or the next ticket comes out attached to this one"
        );
    }
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
