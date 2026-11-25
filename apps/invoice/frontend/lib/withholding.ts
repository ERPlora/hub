// The IRPF withholding on the invoice screens (INVOICE-F03, F17, F18): the rates a manual invoice offers and what an
// invoice says of its own, the same on its page and on the paper.
import type { WithholdingOut, WithholdingRate } from '../invoice-withholding';
import { formatPercent } from './format';

type Translate = (key: string, named?: Record<string, unknown>) => string;

export const WITHHOLDING_RATES: readonly WithholdingRate[] = [15, 7, 1, 19];

/** What is withheld, with its rate, as it is taken from the total; none when nothing is. */
export function withholdingOf(
  invoice: Pick<WithholdingOut, 'withholding_rate' | 'withholding_amount'>,
  t: Translate,
  locale: string,
): { label: string; amount: number } | null {
  if (!invoice.withholding_rate) return null;
  return {
    label: t('invoice.withholding.of', { rate: formatPercent(invoice.withholding_rate, locale) }),
    amount: 0 - invoice.withholding_amount,
  };
}
