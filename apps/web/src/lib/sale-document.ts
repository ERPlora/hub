// **The ticket of a sale, as the sales module prints it** — the paper the shell hands the printer
// when a sale is charged (hub#1921).
//
// ## Why the shell does not compose the ticket itself
//
// It used to: a builder of its own (`receipt-document.ts`, deleted) composed the document from the
// raw `sales.get` / `sales.lines` rows. Those rows carry money in minor units, quantities in
// millionths and the payment method as a code, so an 11,90 € sale came out as «1000000x Acondicionador 300 ml 1190.00», «TOTAL 1190.00»,
// «Pago: Card» — while the ticket screen's print button, on the same sale, printed «1x … 11.90»,
// «TOTAL 11.90», «Pago: Tarjeta», with the shop's name and NIF. Two builders of one paper drift
// apart, and the customer holds the one nobody was looking at.
//
// The sales module owns the sale's meaning (units, the currency's scale, the payment label in the
// hub's language, the shop's identity, the fiscal number once it exists), and it already turns a
// sale into the structured document the ESC/POS renderer reads: its viewer, `erp-sales-document`,
// through `printableDocument()` — the call the ticket screen's print button makes. So this asks
// that viewer. One builder, so the automatic ticket and the reprint are the same paper by
// construction, and "regenerate, never store" (ADR-0265) keeps holding: the copy reprinted a month
// later is the copy the customer got.
//
// ## How
//
// The viewer loads its sale itself once it is in the document, so it is mounted inside a hidden
// host, asked for the document until it has loaded, and removed — removing it also ends the
// viewer's fiscal watch, which would otherwise keep querying for a minute. The contract used is
// the viewer's public one and nothing else: the `saleId` property and `printableDocument()`, which
// answers `undefined` while there is nothing to print.

/** The sales module's document viewer. */
export const SALE_DOCUMENT_TAG = 'erp-sales-document';

/** The sales module is not installed, or its bundle does not bring a viewer that can print. */
export const SALE_DOCUMENT_UNAVAILABLE = 'sale_document_unavailable';

/** The viewer never produced the document (its sale did not load in time). */
export const SALE_DOCUMENT_TIMEOUT = 'sale_document_timeout';

/** What the shell reads of the viewer: its public surface, no internals. */
interface SaleDocumentViewer extends HTMLElement {
  saleId?: string;
  printableDocument?: () => Record<string, unknown> | undefined;
}

export interface SaleDocumentOptions {
  /** Makes the sales bundle define its viewer on a device that never opened the till. */
  loadViewer: () => Promise<void>;
  /** The viewer's tag. Only tests change it (the custom element registry cannot forget one). */
  tag?: string;
  /** How long the viewer has to load its sale. */
  timeoutMs?: number;
  /** How often it is asked whether the document is ready. */
  pollMs?: number;
}

/**
 * The structured ticket of `saleId`, composed by the sales module's viewer.
 *
 * Rejects with {@link SALE_DOCUMENT_UNAVAILABLE} or {@link SALE_DOCUMENT_TIMEOUT} as the error
 * message: the caller warns the till instead of printing a half-built paper.
 */
export async function saleTicketDocument(
  saleId: string,
  { loadViewer, tag = SALE_DOCUMENT_TAG, timeoutMs = 15000, pollMs = 50 }: SaleDocumentOptions,
): Promise<Record<string, unknown>> {
  if (!customElements.get(tag)) await loadViewer();
  if (!customElements.get(tag)) throw new Error(SALE_DOCUMENT_UNAVAILABLE);

  const host = document.createElement('div');
  host.hidden = true;
  host.setAttribute('aria-hidden', 'true');
  const viewer = document.createElement(tag) as SaleDocumentViewer;
  if (typeof viewer.printableDocument !== 'function') throw new Error(SALE_DOCUMENT_UNAVAILABLE);
  viewer.saleId = saleId;
  host.appendChild(viewer);
  document.body.appendChild(host);
  try {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const doc = viewer.printableDocument();
      if (doc) return doc;
      if (Date.now() >= deadline) throw new Error(SALE_DOCUMENT_TIMEOUT);
      await new Promise((resolve) => setTimeout(resolve, pollMs));
    }
  } finally {
    host.remove();
  }
}
