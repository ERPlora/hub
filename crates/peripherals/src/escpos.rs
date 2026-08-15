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
    /// **The bill taken to the table before charging** (ADR-0141, hub#748). Deliberately a document
    /// of its own and not a `Receipt`: it is the same list of lines, but it must NOT carry a series
    /// number, a payment method or a VeriFactu QR — the numbering is consumed on payment and there
    /// is no billing record yet — and it must carry the printed notice that it is not an invoice.
    /// Handing a customer paper that passes for an invoice is a legal problem, not a cosmetic one.
    Prebill,
    Generic,
}

impl DocumentType {
    /// Maps the protocol string, **refusing what it does not know** (hub#501). The only door.
    ///
    /// It used to have a lenient twin (`from_wire`, unknown → `Generic`, mirroring Python's
    /// `else`), and that leniency is the most expensive kind of failure: a `Kitchen` or a `kitchn`
    /// rendered as `Generic` — a nameless dump of key/value pairs — so the kitchen got a piece of
    /// paper that was not an order and **nobody found out until the plate was missing**. A ticket
    /// that fails loudly is cheaper than one that fails quietly, so the caller gets a `None` it has
    /// to deal with. The twin's only caller was the standalone Bridge, deleted by hub#340; hub#578
    /// removed the door with it, so no route can degrade to `Generic` in silence any more.
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
            "prebill" => Self::Prebill,
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
    /// (`txt.encode('cp437', errors='replace')`), con la transliteración de [`to_printable`]
    /// delante: sin ella la puntuación tipográfica de un texto traducido llega al papel como `?`.
    pub fn text(&mut self, txt: &str) -> &mut Self {
        for cp in to_printable(txt).to_cp_lossy::<Cp437>() {
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
    // **A bill with no lines is refused, not cut blank.** Every renderer reads by key, so a
    // document in the SCREEN's shape (`business.name`, `lines[]` — what `ok-receipt` paints) finds
    // nothing it wants and prints «ERPlora», no lines and TOTAL 0.00 without erroring. Paper that
    // comes out WRONG is worse than paper that does not come out: nobody re-checks a bill that
    // printed. It is checked for the bill and not for every document because the others have
    // legitimately item-less shapes (a label, a cash report), and a guard that fires on a correct
    // document is a guard somebody deletes.
    if doc == DocumentType::Prebill
        && !data
            .get("items")
            .and_then(|v| v.as_array())
            .is_some_and(|items| !items.is_empty())
    {
        return Err(crate::PeripheralError::InvalidPayload(
            "a bill has `items` to charge for; this document has none (is it the screen's shape, \
             with `lines`?)"
                .to_string(),
        ));
    }
    let mut b = EscposBuilder::new();
    match doc {
        // invoice == receipt (`_print_invoice` delega en `_print_receipt`).
        DocumentType::Receipt | DocumentType::Invoice => render_receipt(&mut b, data),
        // NOT an arm of `render_receipt` with a flag: what the bill must not print is precisely
        // what a receipt exists to print, so sharing the body would put the fiscal furniture one
        // forgotten `if` away from the paper the waiter hands over.
        DocumentType::Prebill => render_prebill(&mut b, data),
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

    // **El SEGUNDO QR: «pide tu factura»** (hub#963). No sustituye al de arriba y por eso son dos
    // campos: el de VeriFactu apunta a la Sede de la AEAT (`ValidarQR`) y sirve para COTEJAR; este
    // apunta a este hub y sirve para PEDIR. Ágora imprime «CREAR FACTURA», Cuiner imprime
    // localizador + QR — y los dos lo ponen al pie, junto al fiscal, sobre el mismo papel.
    //
    // El **localizador en texto** va debajo y no es decorativo: es la única vía cuando la cámara no
    // enfoca, el móvil no tiene batería o el tique se fotocopia. Por eso el alfabeto Crockford del
    // core evita `I`, `L`, `O` y `U` — se teclea de un papel térmico, no se lee de una pantalla.
    if is_truthy(data, "claim_qr_data") {
        b.set(Align::Center, false, false, false);
        if is_truthy(data, "claim_note") {
            b.text(&format!("{}\n", str_field(data, "claim_note", "")));
        }
        b.qr(str_field(data, "claim_qr_data", ""));
        if is_truthy(data, "claim_locator") {
            b.text(&format!("{}\n", str_field(data, "claim_locator", "")));
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

/// **The bill taken to the table before charging** (ADR-0141, hub#748).
///
/// The waiter's most frequent piece of paper: it comes out once before every payment, so more often
/// than the fiscal ticket. It is the same list of lines as a receipt and, on purpose, **not the
/// same document**:
///
/// - **no series number** — the numbering is consumed by `complete_sale`, not before;
/// - **no VeriFactu QR** — there is no billing record to point at yet;
/// - **no payment method, amount tendered or change** — nothing has been charged;
/// - **a printed notice** that this is not an invoice.
///
/// Those four are dropped **here**, not trusted to the producer: a caller that hands over its
/// receipt document by mistake gets a bill, never a paper that passes for an invoice. Handing a
/// customer one of those is a legal problem, not a cosmetic one.
///
/// The Spanish literals are the ones this whole file prints (`COCINA`, `TOTAL`, `Fecha`): the paper
/// is composed at the device, which has no translator, so what the producer wants said in the
/// customer's language it sends — that is what `notice` is for.
fn render_prebill(b: &mut EscposBuilder, data: &serde_json::Value) {
    // The title is the first thing anyone reads and the cheapest way to tell this paper from a
    // ticket at a glance — the same job `COCINA` does for the kitchen order.
    b.set(Align::Center, true, true, false);
    b.text("CUENTA\n");

    b.set(Align::Center, true, false, false);
    b.text(&format!("{}\n", str_field(data, "business_name", "ERPlora")));

    if is_truthy(data, "business_address") {
        b.set(Align::Center, false, false, false);
        b.text(&format!("{}\n", str_field(data, "business_address", "")));
    }

    b.text("================================\n");

    b.set(Align::Left, false, false, false);
    // What identifies a bill is the table, not a number: it is how the waiter knows which of the
    // six he is holding.
    if is_truthy(data, "customer_name") {
        b.text(&format!("Mesa/Cliente: {}\n", str_field(data, "customer_name", "")));
    }
    b.text(&format!("Fecha: {}\n", now_dmy_hm()));
    b.text("--------------------------------\n");

    if let Some(items) = data.get("items").and_then(|v| v.as_array()) {
        for item in items {
            let name = str_field(item, "name", "");
            let qty = item.get("quantity").and_then(|v| v.as_f64()).unwrap_or(1.0);
            let total = item.get("total").and_then(|v| v.as_f64()).unwrap_or(0.0);
            b.set(Align::Left, false, false, false);
            b.total_line(&format!("{}x {name}", fmt_qty(item.get("quantity"), qty)), total);
            if is_truthy(item, "notes") {
                b.text(&format!("  > {}\n", str_field(item, "notes", "")));
            }
        }
    }

    b.text("--------------------------------\n");

    if let Some(subtotal) = data.get("subtotal").and_then(|v| v.as_f64()) {
        b.total_line("Subtotal", subtotal);
    }
    if let Some(tax_amount) = data.get("tax_amount").and_then(|v| v.as_f64()) {
        b.total_line(str_field(data, "tax_label", "IVA"), tax_amount);
    }
    if let Some(discount) = data.get("discount").and_then(|v| v.as_f64()) {
        if discount > 0.0 {
            b.total_line("Descuento", -discount);
        }
    }

    b.text("================================\n");
    b.set(Align::Left, true, true, false);
    b.total_line("TOTAL", data.get("total").and_then(|v| v.as_f64()).unwrap_or(0.0));
    b.set(Align::Left, false, false, false);
    b.text("================================\n\n");

    // The notice is what makes this paper legal, so it has a default: a producer that forgets to
    // send it must not be able to print something that passes for an invoice.
    b.set(Align::Center, false, false, false);
    let notice = match data.get("notice").and_then(|v| v.as_str()) {
        Some(text) if !text.trim().is_empty() => text,
        _ => "Cuenta - no es una factura. El tiquet fiscal se entrega al cobrar.",
    };
    for line in wrap_to_width(notice, LINE_WIDTH) {
        b.text(&format!("{line}\n"));
    }

    b.text("\n");
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

    /// **The wire vocabulary, pinned from this side.** The hub's queue keeps the same eight names
    /// (`erplora_runtime::print_queue::DOCUMENT_TYPES`) and refuses anything else at the door; the
    /// two lists are duplicated on purpose (the hub server has no business linking the hardware
    /// crate), so each side pins its own or they drift — and a name the queue accepts becomes a
    /// job the printer refuses, one layer too late to tell the producer.
    #[test]
    fn the_wire_vocabulary_is_exactly_these_eight() {
        let vocabulary = [
            ("receipt", DocumentType::Receipt),
            ("kitchen_order", DocumentType::KitchenOrder),
            ("invoice", DocumentType::Invoice),
            ("delivery_note", DocumentType::DeliveryNote),
            ("barcode_label", DocumentType::BarcodeLabel),
            ("cash_session_report", DocumentType::CashSessionReport),
            ("prebill", DocumentType::Prebill),
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

    /// **A document type nobody knows is refused, not printed as `Generic`.** A typo used to reach
    /// the paper as a nameless key/value dump, and the kitchen only noticed when the plate did not
    /// arrive. `parse` is now the ONLY way in — the lenient `from_wire` that degraded to `Generic`
    /// went with its last caller, the standalone Bridge (hub#340 / hub#578).
    #[test]
    fn an_unknown_document_type_is_refused_instead_of_degraded() {
        for unknown in ["Kitchen", "kitchn", "", "html", "KITCHEN_ORDER"] {
            assert_eq!(
                DocumentType::parse(unknown),
                None,
                "`{unknown}` is not a document this printer renders"
            );
        }
    }

    /// **`generic` is a document you ASK for, never one you fall back into.** The distinction is
    /// the whole point of removing the lenient door: the type still exists, and a producer may
    /// legitimately name it, but nothing maps an unknown string onto it any more.
    #[test]
    fn generic_is_only_reachable_by_naming_it() {
        assert_eq!(DocumentType::parse("generic"), Some(DocumentType::Generic));
        for typo in ["Generic", "generi", "gener1c", "unknown"] {
            assert_eq!(
                DocumentType::parse(typo),
                None,
                "`{typo}` must not slide into `Generic`"
            );
        }
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

    /// Sanity of the builder every renderer is written on: a QR plus a cut must produce Epson's QR
    /// stamp (`GS ( k`) and the cut (`GS V 1`). Without it, a renderer can look right and still
    /// hand the printer bytes it does not understand.
    #[test]
    fn builder_qr_and_cut_smoke() {
        let mut b = EscposBuilder::new();
        b.set(Align::Center, false, false, false).qr("https://erplora.com/v/abc").cut();
        let out = b.finish();
        assert!(out.windows(3).any(|w| w == [0x1d, 0x28, 0x6b]), "debe contener GS ( k (QR)");
        assert!(out.windows(3).any(|w| w == [0x1d, 0x56, 0x01]), "debe contener GS V 1 (corte)");
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

    /// **The bill the waiter takes to the table is a document this printer knows** (hub#748).
    ///
    /// It is the most frequently printed paper of a restaurant service — it comes out before every
    /// payment, so more often than the fiscal ticket — and until now `prebill` was not in the
    /// vocabulary at all, so the only door refused it and no printer could produce it.
    ///
    /// Named through `parse` and not the variant on purpose: this is the string the hub's queue
    /// stores and the drain frame carries, so the test pins the **wire**, which is the contract.
    #[test]
    fn the_bill_taken_to_the_table_is_a_document_this_printer_knows() {
        assert!(
            DocumentType::parse("prebill").is_some(),
            "`prebill` is the bill taken to the table before charging; refusing it leaves the \
             waiter with nothing to carry"
        );
    }

    /// How many QR symbols reached the paper. One symbol is FIVE `GS ( k` commands (set model,
    /// module size, error correction, store data, print), so counting the raw prefix would answer
    /// five when the honest answer is one.
    fn qr_symbols(bytes: &[u8]) -> usize {
        bytes
            .windows(3)
            .filter(|w| *w == [0x1d, 0x28, 0x6b])
            .count()
            / 5
    }

    /// **Two QRs, not one** (hub#963). The VeriFactu one points at the AEAT's `ValidarQR` and is
    /// for CHECKING; the second points at this hub and is for ASKING — «pide tu factura». They are
    /// two fields on purpose: printing one over the other would either strip the fiscal proof from
    /// the ticket or leave the customer with nothing to scan.
    #[test]
    fn a_ticket_can_carry_both_the_fiscal_qr_and_the_invoice_request_qr() {
        let doc = json!({
            "business_name": "Bar Manolo",
            "receipt_id": "T-42",
            "items": [{ "name": "Cafe", "quantity": 1, "total": 1.2 }],
            "total": 1.2,
            "qr_data": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B1&numserie=T-42",
            "claim_note": "Pide tu factura",
            "claim_qr_data": "https://bar.erplora.com/p/ABCD1234ABCD1234",
            "claim_locator": "ABCD1234ABCD1234",
        });
        let bytes = render_document(DocumentType::parse("receipt").unwrap(), &doc)
            .expect("a well-formed ticket renders");
        let text = String::from_utf8_lossy(&bytes);

        assert_eq!(qr_symbols(&bytes), 2, "both QRs must reach the paper");
        assert!(
            text.contains("ValidarQR"),
            "the fiscal QR still points at the AEAT"
        );
        assert!(
            text.contains("/p/ABCD1234ABCD1234"),
            "and the second one at this hub"
        );
        assert!(
            text.contains("Pide tu factura"),
            "with a caption, or nobody knows what the second code is for"
        );
        assert!(
            text.contains("ABCD1234ABCD1234\n"),
            "and the locator in PLAIN TEXT below it: the camera is not always an option"
        );
    }

    /// A ticket with no claim prints exactly what it printed before. The second QR is opt-in, so
    /// no hub that has not adopted this grows a blank line or a stray caption.
    #[test]
    fn a_ticket_without_a_claim_is_unchanged() {
        let doc = json!({
            "receipt_id": "T-43",
            "items": [{ "name": "Cafe", "quantity": 1, "total": 1.2 }],
            "total": 1.2,
            "qr_data": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B1",
        });
        let bytes = render_document(DocumentType::parse("receipt").unwrap(), &doc).unwrap();
        assert_eq!(qr_symbols(&bytes), 1, "only the fiscal QR");
    }

    /// **The bill still carries no QR of either kind.** The pre-bill drops the fiscal one because
    /// there is no billing record yet — and for exactly the same reason there is no invoice to
    /// request: a claim on a sale that has not been charged would point at nothing.
    #[test]
    fn the_bill_carries_neither_qr() {
        let doc = json!({
            "items": [{ "name": "Cafe", "quantity": 1, "total": 1.2 }],
            "total": 1.2,
            "qr_data": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B1",
            "claim_qr_data": "https://bar.erplora.com/p/ABCD1234ABCD1234",
            "claim_locator": "ABCD1234ABCD1234",
        });
        let bytes = render_document(DocumentType::parse("prebill").unwrap(), &doc).unwrap();
        assert!(
            !bytes.windows(3).any(|w| w == [0x1d, 0x28, 0x6b]),
            "a bill carries no QR at all"
        );
        assert!(
            !String::from_utf8_lossy(&bytes).contains("ABCD1234ABCD1234"),
            "nor the locator in text"
        );
    }

    /// **The bill is NOT a ticket, and the paper has to say so** (ADR-0141).
    ///
    /// A bill with a series number, a payment method or a VeriFactu QR is a piece of paper that
    /// looks like an invoice without being one, which is a legal problem rather than a cosmetic
    /// one: the numbering is consumed when charging, not before, and there is no billing record
    /// yet. So the renderer must print the lines and the total — the waiter has to be able to
    /// collect — and must **not** print any of the fiscal furniture, whatever the producer sends.
    #[test]
    fn the_bill_prints_its_lines_but_none_of_the_fiscal_furniture() {
        let doc = json!({
            "business_name": "Bar Manolo",
            "customer_name": "Mesa 4",
            "items": [
                { "name": "Cafe", "quantity": 2, "total": 2.4 },
                { "name": "Tostada", "quantity": 1, "total": 3.5 },
            ],
            "total": 5.9,
            "notice": "Cuenta - no es una factura. El tiquet fiscal se entrega al cobrar.",
            // Sent on purpose: even if a producer hands over fiscal fields, a bill must not print
            // them. Dropping them here is cheaper than trusting every caller to omit them.
            "receipt_id": "T-42",
            "payment_method": "Efectivo",
            "qr_data": "https://prevalidacion.aeat.es/verifactu",
        });
        let bytes = render_document(
            DocumentType::parse("prebill").expect("`prebill` is a document this printer knows"),
            &doc,
        )
        .expect("a well-formed bill renders");
        let text = String::from_utf8_lossy(&bytes);

        assert!(text.contains("Bar Manolo"), "the business name is on the paper");
        assert!(text.contains("Mesa 4"), "the table is on the paper: it is what identifies the bill");
        assert!(text.contains("2x Cafe"), "the lines are on the paper");
        assert!(text.contains("TOTAL"), "the total is on the paper — it is what gets collected");
        assert!(
            text.contains("no es una factura"),
            "the notice is PRINTED: paper that looks like an invoice without being one is a legal \
             problem, not a cosmetic one"
        );

        assert!(!text.contains("T-42"), "a bill carries no series number: numbering is consumed on payment");
        assert!(!text.contains("Efectivo"), "a bill carries no payment method: nothing has been charged yet");
        assert!(
            !bytes.windows(3).any(|w| w == [0x1d, 0x28, 0x6b]),
            "a bill carries no VeriFactu QR: there is no billing record to point at yet"
        );
        assert_eq!(
            &bytes[bytes.len() - 3..],
            &[0x1d, 0x56, 0x01],
            "and the paper is cut, or the bill comes out attached to the next one"
        );
    }

    /// **A bill with no notice still says it is not an invoice.** The producer sends the translated
    /// text (`ui.prebillNotice`), but the guarantee cannot depend on every producer remembering:
    /// what is at stake is handing a customer a paper that passes for an invoice.
    #[test]
    fn a_bill_without_a_notice_still_says_it_is_not_an_invoice() {
        let bytes = render_document(
            DocumentType::parse("prebill").expect("`prebill` is a document this printer knows"),
            &json!({ "items": [{ "name": "Cafe", "quantity": 1, "total": 1.2 }], "total": 1.2 }),
        )
        .expect("a bill with no notice still renders");
        let text = String::from_utf8_lossy(&bytes);
        assert!(
            text.contains("no es una factura"),
            "the notice has a default: a producer that forgets it must not be able to print a \
             paper that passes for an invoice"
        );
    }

    /// **A bill with no lines is REFUSED, not cut blank.**
    ///
    /// This is the guard that stops the producer's mistake from becoming paper. The renderer reads
    /// by key, so a document in the SCREEN's shape (`business.name`, `lines[]` — what `ok-receipt`
    /// paints) finds none of the fields it wants, takes every default and hands the customer
    /// «ERPlora», no lines and TOTAL 0.00. Paper that comes out WRONG is worse than paper that does
    /// not come out: nobody checks a bill that printed.
    ///
    /// It matters beyond a typo. The module that produces the bill is installed at its **published**
    /// version, so between the hub taking this change and the module being republished, the old
    /// producer is what runs — and it sends exactly that shape (ERPlora/sales#78). Failing loudly
    /// puts the reason in `_print_queue.last_error` instead of in the customer's hand.
    #[test]
    fn a_bill_with_no_lines_is_refused_instead_of_cut_blank() {
        // The shape `<ok-receipt>` paints on screen: right document, wrong keys.
        let screen_shape = json!({
            "business": { "name": "Bar Manolo" },
            "lines": [{ "name": "Cafe", "qty": 2, "total": 2.4 }],
            "total": 2.4,
        });
        let err = render_document(
            DocumentType::parse("prebill").expect("`prebill` is a document this printer knows"),
            &screen_shape,
        )
        .expect_err("a bill with no lines the renderer can read is not a bill");
        assert!(
            matches!(err, crate::PeripheralError::InvalidPayload(_)),
            "the refusal says the document is wrong, not the printer: {err}"
        );
    }

    /// **Typographic punctuation reaches the paper as punctuation, not as `?`.**
    ///
    /// The printer speaks cp437 and the encoder replaces what it cannot represent with `?`, so the
    /// translated notice — «Cuenta — no es una factura» with a real em dash — came out as
    /// «Cuenta ? no es una factura». The text is written by translators in a text editor, so the
    /// dashes and curly quotes are not a mistake anybody is going to stop making; the encoder is
    /// the place that has to cope.
    #[test]
    fn typographic_punctuation_reaches_the_paper_as_punctuation() {
        let mut b = EscposBuilder::new();
        b.text("Cuenta — no es una factura: “Bar Manolo’s”…\n");
        let text = String::from_utf8_lossy(&b.finish()).to_string();
        assert!(
            !text.contains('?'),
            "nothing on the paper turned into a question mark, got: {text}"
        );
        assert!(text.contains("Cuenta - no es una factura"), "the em dash prints as a dash: {text}");
        assert!(text.contains("\"Bar Manolo's\""), "quotes print as quotes: {text}");
        assert!(text.contains("..."), "the ellipsis prints as three dots: {text}");
    }
}

/// **Typographic punctuation → what a cp437 printer can actually produce.**
///
/// The encoder replaces whatever cp437 cannot represent with `?`, so the translated bill notice
/// («Cuenta — no es una factura», with the em dash a translator naturally types) reached the paper
/// as «Cuenta ? no es una factura». Curly quotes, ellipses and non-breaking spaces do the same, and
/// they come from people writing in a text editor — not a habit anybody is going to stop having, so
/// this is the layer that copes. Accented Spanish needs none of this: cp437 has it.
fn to_printable(txt: &str) -> String {
    let mut out = String::with_capacity(txt.len());
    for c in txt.chars() {
        match c {
            // Hyphen..horizontal bar (en/em dash included) and the minus sign.
            '\u{2010}'..='\u{2015}' | '\u{2212}' => out.push('-'),
            '\u{2018}'..='\u{201B}' | '\u{2032}' => out.push('\''),
            '\u{201C}'..='\u{201F}' | '\u{2033}' => out.push('"'),
            '\u{2026}' => out.push_str("..."),
            // Every space that is not the plain one; a printer column does not care which it was.
            '\u{00A0}' | '\u{2007}' | '\u{2009}' | '\u{202F}' => out.push(' '),
            // cp437 predates the euro. A footer saying `EUR` beats one saying `?`.
            '\u{20AC}' => out.push_str("EUR"),
            other => out.push(other),
        }
    }
    out
}

/// Parte un texto en líneas de como mucho `width` columnas, **por palabras**.
///
/// La impresora corta por columna sin mirar dónde: sin esto, el aviso de la cuenta salía partido a
/// mitad de palabra. Una palabra más larga que el ancho se deja tal cual — partirla la haría
/// ilegible y es preferible que la impresora la doble.
fn wrap_to_width(txt: &str, width: usize) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    let mut current = String::new();
    for word in txt.split_whitespace() {
        if current.is_empty() {
            current.push_str(word);
        } else if current.chars().count() + 1 + word.chars().count() <= width {
            current.push(' ');
            current.push_str(word);
        } else {
            lines.push(std::mem::take(&mut current));
            current.push_str(word);
        }
    }
    if !current.is_empty() {
        lines.push(current);
    }
    lines
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
