// Money on the customer screens (WORKBOOK «Reglas que no se rompen»: money travels in minor units; the
// screen paints in the business's currency, flow customer-business-currency, or in the one a record kept). An amount is
// written with the platform's `formatMoney`, and what is typed in «Spent» is read by the platform (hub#1196,
// `customerFilters.test.ts`). The decimals are the server's (`currency_decimals`), never the browser's Intl; while the
// business has not answered, an amount is a dash, never the euro by default.
import { describe, expect, it } from 'vitest';

import { type Money, recordMoney } from './money';

/** The business's money, when the record has none of its own. */
const PLN: Money = { currency: 'PLN', decimals: 2 };

describe('recordMoney', () => {
  it('is the record’s own currency with its decimals: a record is never rewritten', () => {
    expect(recordMoney({ currency: 'EUR', currency_decimals: 2 }, PLN)).toEqual({ currency: 'EUR', decimals: 2 });
    expect(recordMoney({ currency: 'JPY', currency_decimals: 0 }, PLN)).toEqual({ currency: 'JPY', decimals: 0 });
  });

  it('is the business’s when the record has no currency of its own', () => {
    expect(recordMoney({ currency: '', currency_decimals: null }, PLN)).toEqual(PLN);
    expect(recordMoney({ currency: '', currency_decimals: null })).toBeUndefined();
    expect(recordMoney({ currency: 7, currency_decimals: null }, PLN)).toEqual(PLN);
  });
});
