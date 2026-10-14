// How a department's VAT reads, in its row and among the choices of its picker (the old screen's
// «Display name · 4%»): the category's name and the rate the server says it charges today, in the
// page's language. No rate today: the name alone. No name: the key it was named by.
import { formatPercent } from '../../lib/format';

export function taxLabel(name: string, rate: string | null, locale: string, key = ''): string {
  const shown = name.trim() || key;
  return rate === null ? shown : `${shown} · ${formatPercent(rate, locale)}`;
}
