// hub#1160, hub#1196: the drawer reads an amount the way every money field of the Hub reads it — the platform's
// `MoneyInput` and its `parseMoney` (`@erplora/ui/components`) — in the four windows that take one (each window's test
// runs the table of `__tests__/money-field.ts`) and in the list's amount filters (`lib/sessionFilters.ts`, through
// `filterCents` and `amountFilterErrors` of `base/frontend/lib/money.ts`; `SessionsPage.test.ts` runs the table of
// `base/frontend/__tests__/amount-filter.ts`). This guard keeps the drawer's own reader from coming back: nobody uses it.
import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['./**/*.{ts,vue}', '!./**/*.test.ts', '!./**/__tests__/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

describe('the drawer’s own amount reader (hub#1160, hub#1196)', () => {
  it('nobody uses it: no window, page or filter reads an amount with it nor has a money field of its own', () => {
    const readers = Object.entries(sources)
      .filter(([, source]) => /\b(readMoney|readAmount|moneyRefusal)\b|MoneyField\.vue/.test(source))
      .map(([file]) => file);
    expect(readers.sort()).toEqual([]);
  });
});
