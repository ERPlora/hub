// Money of the customer screens: the server keeps minor units (WORKBOOK «Reglas que no se rompen»), a person
// reads and types them in the business's currency (`useBusinessMoney`, the platform's: its country's, with the
// decimals the server counts it in, never the browser's Intl, which gives the forint none). Until the business
// answers an amount is a dash, never the euro by default nor guessed decimals. A record that kept its own currency
// (a purchase) is painted in it. An amount is written with the platform's `formatMoney` (`@erplora/ui/components`);
// this is the one place the app says which money a record is in. What a person types in «Spent» is read by the
// platform, as every amount filter of the Hub (`filterCents`, `amountFilterErrors`; hub#1196).
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { amountFilterErrors, filterCents, useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The money of a record: the currency it kept, with the decimals the server says, else the business's. */
export function recordMoney(record: { currency?: unknown; currency_decimals?: number | null }, business?: Money): Money | undefined {
  const { currency, currency_decimals: decimals } = record;
  return typeof currency === 'string' && currency && typeof decimals === 'number' ? { currency, decimals } : business;
}
