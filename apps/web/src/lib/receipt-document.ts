// **The ticket, built from the sale** — the one place a sale becomes the structured document the
// printer renders (hub#501).
//
// ## Who builds the document, and with what authority
//
// The document travels structured now, so somebody has to compose it. The authority is **the sale
// row in the hub's database**, never the screen that asked for the print: a till that composed its
// own totals would be a till that decides what the ticket says, amounts included. So the input here
// is what `sales.get` / `sales.lines` return, read fresh, and the caller's job is to fetch that —
// never to pass along what it happened to have on screen. (`print-on-sale.ts` already worked this
// way and says so: "los datos autoritativos de la venta; el payload del evento es un resumen, no la
// fuente". This makes it the rule instead of a habit of one caller.)
//
// ## Why it is extracted, and why nothing stores the result
//
// Ioan's decision (2026-08-08): **the ticket is regenerated from the data and never stored.** The
// sale is already in the database with everything the ticket needs; keeping the render as well
// would be a derived copy, and a stored derived copy is one that drifts. What does get kept as
// immutable evidence is the **fiscal XML** — and, if wanted, the invoice PDF — because there the
// point is that the bytes are the bytes that were, backed by a legal obligation. A screen ticket
// has no such obligation.
//
// That decision only works if building is **deterministic and lives in one place**: re-printing a
// ticket, or opening it from the sales list a month later, has to produce what the customer got
// without anybody having kept a copy. With the builder private to the auto-print path, the second
// caller would inevitably grow a second, slightly different version — and then the copy the
// customer holds and the copy the owner reads would disagree, which is the worst possible way for
// this to fail.
//
// The shape is the one `escpos::render_document` reads for `DocumentType::Receipt`
// (`crates/peripherals/src/escpos.rs`).

/** The `printing` module's settings that show up on the paper. */
export interface ReceiptSettings {
  receipt_header?: string;
  receipt_footer?: string;
}

/** A sale line, under either of the two names the sales module uses. */
export interface SaleLine {
  name?: string;
  product_name?: string;
  quantity?: number;
  total?: number;
  line_total?: number;
  is_service?: number | boolean;
  notes?: string;
}

/** The document, in the shape the ESC/POS receipt renderer reads. */
export interface ReceiptDocument extends Record<string, unknown> {
  business_name: string;
  receipt_id: string;
  customer_name?: string;
  items: { name: string; quantity: number; total: number; notes?: string }[];
  subtotal: number;
  tax_amount: number;
  discount?: number;
  total: number;
  payment_method: string;
  paid?: number;
  change?: number;
  receipt_footer?: string;
}

function num(v: unknown): number {
  return typeof v === 'number' ? v : Number(v ?? 0) || 0;
}

/**
 * Composes the receipt document for a sale.
 *
 * Pure on purpose — no clock, no fetch, no randomness — so the same sale gives the same document
 * every time. That is exactly the property "regenerate, never store" depends on.
 */
export function buildReceiptDocument(
  settings: ReceiptSettings,
  sale: Record<string, unknown>,
  lines: SaleLine[],
): ReceiptDocument {
  return {
    business_name: settings.receipt_header || 'ERPlora',
    receipt_id: String(sale.sale_number ?? sale.id ?? ''),
    customer_name: (sale.customer_name as string) || undefined,
    items: (lines ?? []).map((l) => ({
      name: l.name ?? l.product_name ?? '',
      quantity: num(l.quantity ?? 1),
      total: num(l.total ?? l.line_total),
      notes: l.notes,
    })),
    subtotal: num(sale.subtotal),
    tax_amount: num(sale.tax_amount),
    // Absent and zero are different facts: a sale with no discount must not print a "Descuento 0"
    // line, so the field is left out rather than defaulted.
    discount: sale.discount_amount != null ? num(sale.discount_amount) : undefined,
    total: num(sale.total),
    payment_method: String(sale.payment_method_name ?? sale.payment_method ?? ''),
    paid: sale.amount_tendered != null ? num(sale.amount_tendered) : undefined,
    change: sale.change_due != null ? num(sale.change_due) : undefined,
    receipt_footer: settings.receipt_footer || undefined,
  };
}
