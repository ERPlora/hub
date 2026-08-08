// The ticket is BUILT FROM THE SALE, and it is built in one place (hub#501).
//
// Ioan's decision (2026-08-08): the ticket is **regenerated from the data**, never stored. Nothing
// keeps a rendered copy — what is kept as immutable evidence is the fiscal XML (and, if wanted, the
// invoice PDF), because that is what a legal obligation backs. A screen ticket needs none of that.
//
// Two things follow, and this file pins both:
//
//  1. **The content's source of truth is the sale row**, not whatever a screen happened to be
//     showing. A till that composed its own totals would be a till that decides what the ticket
//     says — including the amounts.
//  2. **There is exactly one builder.** First print, re-print and the ticket opened from the sales
//     list all call this, or they drift and the copy the customer gets stops matching the copy the
//     owner sees.
import { describe, expect, it } from 'vitest';

import { buildReceiptDocument } from './receipt-document';

const settings = { receipt_header: 'Bar Manolo', receipt_footer: 'Gracias' };

const sale = {
  id: 42,
  sale_number: 'T-0042',
  customer_name: 'Ana Soto',
  subtotal: 10,
  tax_amount: 2.1,
  discount_amount: 1,
  total: 11.1,
  payment_method_name: 'Efectivo',
  amount_tendered: 20,
  change_due: 8.9,
};

const lines = [
  { name: 'Cafe', quantity: 2, total: 2.4, notes: 'sin azucar' },
  { product_name: 'Tostada', quantity: 1, line_total: 3.5 },
];

describe('receipt document — regenerated from the sale', () => {
  it('reads every amount from the sale row and never invents one', () => {
    const doc = buildReceiptDocument(settings, sale, lines);

    expect(doc.subtotal).toBe(10);
    expect(doc.tax_amount).toBe(2.1);
    expect(doc.discount).toBe(1);
    expect(doc.total).toBe(11.1);
    expect(doc.paid).toBe(20);
    expect(doc.change).toBe(8.9);
  });

  it('carries the lines with the two names the sales module uses for them', () => {
    const doc = buildReceiptDocument(settings, sale, lines);

    expect(doc.items).toEqual([
      { name: 'Cafe', quantity: 2, total: 2.4, notes: 'sin azucar' },
      { name: 'Tostada', quantity: 1, total: 3.5, notes: undefined },
    ]);
  });

  it('identifies the ticket by its sale number, falling back to the id', () => {
    expect(buildReceiptDocument(settings, sale, lines).receipt_id).toBe('T-0042');
    expect(buildReceiptDocument(settings, { id: 42 }, []).receipt_id).toBe('42');
  });

  // **The property the "regenerate, never store" decision rests on.** The same sale produces the
  // same document, so re-printing a ticket from the sales list a month later gives what the customer
  // got — without anybody having kept a copy of it. If this were not deterministic, not storing the
  // render would mean losing it.
  it('gives the same document every time it is built from the same sale', () => {
    expect(buildReceiptDocument(settings, sale, lines)).toEqual(
      buildReceiptDocument(settings, sale, lines),
    );
  });

  // A sale with nothing optional filled in still yields a printable document: a ticket that throws
  // is a sale that cannot be closed, and printing must never be able to do that.
  it('builds a printable document from the bare minimum a sale can be', () => {
    const doc = buildReceiptDocument({}, { id: 1 }, []);

    expect(doc.business_name).toBe('ERPlora');
    expect(doc.items).toEqual([]);
    expect(doc.total).toBe(0);
    expect(doc.customer_name).toBeUndefined();
  });

  // The header/footer are the owner's settings, not the sale's: two different sources, and the one
  // that is configuration must not be able to overwrite the one that is a fact about the sale.
  it('takes the header and footer from the printing settings', () => {
    const doc = buildReceiptDocument(settings, sale, lines);

    expect(doc.business_name).toBe('Bar Manolo');
    expect(doc.receipt_footer).toBe('Gracias');
  });
});
