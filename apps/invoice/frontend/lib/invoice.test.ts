// What the invoice screens say about a document, the same in the list, the detail and the paper: its
// type and status in words, the tone of its status, its breakdown as printed rows («VAT 21%»,
// «Equivalence surcharge 5.2%», «Exempt (E1)»…), the note of a rectifying invoice in the reader's
// language, and whether a full invoice lacks the customer's tax ID.
import { describe, expect, it } from 'vitest';

import type { BreakdownOut, InvoiceOut } from '../operations';
import {
  documentNote,
  isSimplified,
  missingTaxId,
  rateHeader,
  SOURCE_CODES,
  STATUS_CODES,
  statusTone,
  taxRows,
  TYPE_CODES,
} from './invoice';
import { plain } from './format';

const t = (key: string, named?: Record<string, unknown>) =>
  named ? `${key}${JSON.stringify(named)}` : key;

const entry = (over: Partial<BreakdownOut>): BreakdownOut => ({
  tax: 'vat',
  regime: '01',
  qualification: 'subject',
  exempt_reason: '',
  rate: '21.00',
  surcharge_rate: '0.00',
  base: 1000,
  quota: 210,
  surcharge_quota: 0,
  ...over,
});

describe('rateHeader', () => {
  it('names the rate by the tax its lines are declared with: VAT, IGIC or IPSI', () => {
    expect(rateHeader(['vat', 'vat'], t)).toBe('invoice.taxPct.vat');
    expect(rateHeader(['igic'], t)).toBe('invoice.taxPct.igic');
    expect(rateHeader(['ipsi'], t)).toBe('invoice.taxPct.ipsi');
  });

  it('is a plain «Tax %» when the tax is not known yet, is not one or is mixed', () => {
    expect(rateHeader([], t)).toBe('invoice.taxPct.any');
    expect(rateHeader(['vat', 'igic'], t)).toBe('invoice.taxPct.any');
    expect(rateHeader(['sales_tax'], t)).toBe('invoice.taxPct.any');
  });
});

describe('the closed lists the server knows', () => {
  it('names every type, status and source', () => {
    expect(TYPE_CODES).toEqual(['F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5']);
    expect(STATUS_CODES).toEqual(['issued', 'paid', 'cancelled']);
    expect(SOURCE_CODES).toEqual(['sale', 'manual', 'substitution', 'rectification', 'refund', 'void']);
  });
});

describe('statusTone', () => {
  it('issued in progress, paid done, cancelled blocked', () => {
    expect([statusTone('issued'), statusTone('paid'), statusTone('cancelled')]).toEqual(['info', 'success', 'danger']);
  });
});

describe('isSimplified and missingTaxId', () => {
  it('a ticket and its rectification identify no customer; a full one without tax ID is warned', () => {
    expect([isSimplified('F2'), isSimplified('R5'), isSimplified('F1'), isSimplified('R1')]).toEqual([true, true, false, false]);
    expect(missingTaxId({ invoice_type: 'F1', customer_tax_id: ' ' })).toBe(true);
    expect(missingTaxId({ invoice_type: 'R1', customer_tax_id: '' })).toBe(true);
    expect(missingTaxId({ invoice_type: 'F2', customer_tax_id: '' })).toBe(false);
    expect(missingTaxId({ invoice_type: 'F1', customer_tax_id: 'B12345674' })).toBe(false);
  });
});

describe('taxRows', () => {
  it('a subject key reads its tax and rate; a surcharge is a row of its own over the same base', () => {
    const rows = taxRows([entry({ surcharge_rate: '5.20', surcharge_quota: 52 })], t, 'en');
    expect(rows).toEqual([
      { label: 'invoice.taxes.vat 21%', base: 1000, amount: 210 },
      { label: 'invoice.taxes.surcharge 5.2%', base: 1000, amount: 52 },
    ]);
  });

  it('exempt with or without its cause, not subject, reverse charge; IGIC by its own name', () => {
    const rows = taxRows(
      [
        entry({ qualification: 'exempt', exempt_reason: 'E1', rate: '0.00', quota: 0 }),
        entry({ qualification: 'exempt', exempt_reason: '', rate: '0.00', quota: 0 }),
        entry({ qualification: 'not_subject', rate: '0.00', quota: 0 }),
        entry({ qualification: 'subject_reverse', rate: '0.00', quota: 0 }),
        entry({ tax: 'igic', rate: '7.00', quota: 70 }),
      ],
      t,
      'es',
    );
    expect(rows.map((row) => plain(row.label))).toEqual([
      'invoice.taxes.exemptCause{"cause":"E1"}',
      'invoice.taxes.exempt',
      'invoice.taxes.notSubject',
      'invoice.taxes.reverseCharge',
      'IGIC 7 %',
    ]);
  });
});

describe('documentNote', () => {
  const doc = (over: Partial<InvoiceOut>) => ({ rectifies: null, description: '', notes: '', ...over }) as InvoiceOut;

  it('a rectifying invoice names what it rectifies and why, in the reader’s language', () => {
    const rect = doc({ rectifies: { id: 'o', number: 'FACT-2026-000001' } as InvoiceOut['rectifies'], description: 'Wrong price' });
    expect(documentNote(rect, t)).toBe('invoice.detail.rectifiesNote{"number":"FACT-2026-000001","reason":"Wrong price"}');
    expect(documentNote({ ...rect, description: ' ' }, t)).toBe('invoice.detail.rectifiesNoteNoReason{"number":"FACT-2026-000001"}');
  });

  it('any other document says its own notes', () => {
    expect(documentNote(doc({ notes: 'Thanks' }), t)).toBe('Thanks');
  });
});
