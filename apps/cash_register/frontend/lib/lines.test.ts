// How a line of a shift reads: its type and payment method in the reader's language and its concept —
// a sale is named by its document («Ticket 20261014-0007», «Invoice …»), a void «Void of …» and a refund
// «Refund of …»; a line written by hand shows what was typed. A factory payment method (Sales keeps
// «Cash» and «Card» in English) is translated; one the owner named is shown as she named it.
import { describe, expect, it } from 'vitest';

import { conceptOf, methodOf } from './lines';

const t = (key: string, named?: Record<string, unknown>) => (named ? `${key}(${Object.values(named).join(',')})` : key);

describe('conceptOf', () => {
  it('names a sale by its document, a void and a refund by theirs, and keeps a written concept', () => {
    const sale = { type: 'sale', description: '', sale_number: '20261014-0007', document_type: 'ticket' } as const;
    expect(conceptOf(sale, t)).toBe('cash_register.concept.ticket(20261014-0007)');
    expect(conceptOf({ ...sale, document_type: 'invoice' }, t)).toBe('cash_register.concept.invoice(20261014-0007)');
    expect(conceptOf({ ...sale, type: 'void' }, t)).toBe('cash_register.concept.voidOf(cash_register.concept.ticket(20261014-0007))');
    expect(conceptOf({ ...sale, type: 'refund' }, t)).toBe('cash_register.concept.refundOf(cash_register.concept.ticket(20261014-0007))');
    expect(conceptOf({ ...sale, sale_number: '' }, t)).toBe('cash_register.concept.saleUnnumbered');
    expect(conceptOf({ type: 'out', description: 'Bread supplier', sale_number: '', document_type: '' }, t)).toBe('Bread supplier');
  });
});

describe('methodOf', () => {
  it('translates the factory methods and a line written by hand, and keeps an owner’s name', () => {
    expect(methodOf({ method_type: 'cash', method_name: 'Cash' }, t)).toBe('cash_register.methods.cash');
    expect(methodOf({ method_type: 'card', method_name: 'Card' }, t)).toBe('cash_register.methods.card');
    expect(methodOf({ method_type: 'cash', method_name: '' }, t)).toBe('cash_register.methods.cash');
    expect(methodOf({ method_type: 'other', method_name: 'Bizum' }, t)).toBe('Bizum');
  });
});
