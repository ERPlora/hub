// `taxRow(row, words)`: how one row of a sale's breakdown reads on the paper (the ticket, the pre-bill).
// One row per fiscal key and component, as Invoicing declares it: a subject key is «<tax> <rate>», an
// exempt one names its cause («Exempt (E1)»), a not-subject one says so, a reverse charge carries its
// mark; two keys at the same rate never share a row (their `key` differs).
import { describe, expect, it } from 'vitest';

import type { BreakdownOut } from '../operations';
import { taxRow } from './breakdown';
import { plain } from './format';

const row = (over: Partial<BreakdownOut> = {}): BreakdownOut => ({
  rate_pct: '10.00',
  label: 'vat',
  tax_type: 'vat',
  regime: '01',
  qualification: 'subject',
  exempt_reason: '',
  base: 1000,
  tax: 100,
  ...over,
});

const WORDS: Record<string, string> = {
  vat: 'IVA',
  surcharge: 'RE',
  exempt: 'Exento',
  not_subject: 'No sujeto',
  subject_reverse: 'ISP',
};
const words = {
  locale: 'es',
  taxName: (label: string) => WORDS[label] ?? label,
  qualification: (kind: string) => WORDS[kind] ?? kind,
};

describe('taxRow', () => {
  it('a subject key reads «<tax> <rate>», a tax without short name keeps its own', () => {
    expect(plain(taxRow(row(), words).label)).toBe('IVA 10 %');
    expect(plain(taxRow(row({ label: 'surcharge', tax_type: 'surcharge', rate_pct: '5.20' }), words).label)).toBe('RE 5,2 %');
    expect(plain(taxRow(row({ label: 'Tasa turística', rate_pct: '7.00' }), words).label)).toBe('Tasa turística 7 %');
  });

  it('an exempt key names its cause; a not-subject one says so; a reverse charge carries its mark', () => {
    expect(taxRow(row({ qualification: 'exempt', exempt_reason: 'E1', rate_pct: '0.00' }), words).label).toBe('Exento (E1)');
    expect(taxRow(row({ qualification: 'exempt', rate_pct: '0.00' }), words).label).toBe('Exento');
    expect(taxRow(row({ qualification: 'not_subject_location', rate_pct: '0.00' }), words).label).toBe('No sujeto');
    expect(plain(taxRow(row({ qualification: 'subject_reverse', rate_pct: '21.00' }), words).label)).toBe('IVA 21 % · ISP');
  });

  it('two keys at the same rate are two rows', () => {
    const subject = taxRow(row({ rate_pct: '0.00' }), words);
    const exempt = taxRow(row({ rate_pct: '0.00', qualification: 'exempt', exempt_reason: 'E1' }), words);
    expect(subject.key).not.toBe(exempt.key);
  });

  it('a row kept before the key existed reads as subject VAT', () => {
    const old = { rate_pct: '21.00', label: 'vat', base: 100, tax: 21 } as BreakdownOut;
    expect(plain(taxRow(old, words).label)).toBe('IVA 21 %');
  });
});
