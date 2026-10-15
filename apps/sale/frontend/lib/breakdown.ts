// How one row of a sale's breakdown reads on paper (the ticket, the pre-bill). The breakdown has one row
// per fiscal key and component — tax, regime, qualification, exemption cause and rate —, the very rows
// Invoicing declares: a subject key is «<tax> <rate>», an exempt one names its cause («Exempt (E1)»), a
// not-subject one says so and a reverse charge carries its mark. A row kept before the key existed reads
// as subject VAT.
import type { BreakdownOut } from '../operations';
import { formatPercent } from './format';

export interface TaxRowWords {
  locale: string;
  /** The short name of a tax («VAT»), or the label its rule gave it. */
  taxName: (label: string) => string;
  /** How a qualification reads: exempt, not_subject, subject_reverse. */
  qualification: (kind: 'exempt' | 'not_subject' | 'subject_reverse') => string;
}

export function taxRow(row: BreakdownOut, words: TaxRowWords): { key: string; label: string } {
  const qualification = row.qualification ?? 'subject';
  const reason = row.exempt_reason ?? '';
  const key = [row.tax_type ?? row.label, row.regime ?? '01', qualification, reason, row.label, row.rate_pct].join('|');
  const rated = `${words.taxName(row.label)} ${formatPercent(row.rate_pct, words.locale)}`;
  if (qualification === 'exempt') {
    const exempt = words.qualification('exempt');
    return { key, label: reason ? `${exempt} (${reason})` : exempt };
  }
  if (qualification.startsWith('not_subject')) return { key, label: words.qualification('not_subject') };
  if (qualification === 'subject_reverse') return { key, label: `${rated} · ${words.qualification('subject_reverse')}` };
  return { key, label: rated };
}
