// hub#1160: the drawer reads an amount the way every money field of the Hub reads it — the platform's `MoneyInput` and
// its `parseMoney` (`@erplora/ui/components`) — in the four windows that take one (each window's test runs the table
// of `__tests__/money-field.ts`). This guard keeps the drawer's own reader out of its windows and pages: it only reads
// the list's amount filters (`lib/sessionFilters.ts`), until hub#1196 takes those to the platform's reader too.
import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['./**/*.{ts,vue}', '!./**/*.test.ts', '!./**/__tests__/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

describe('the drawer’s own amount reader (hub#1160)', () => {
  it('no window reads an amount with it nor has a money field of its own: only the list’s filters still use it', () => {
    const readers = Object.entries(sources)
      .filter(([, source]) => /\b(readMoney|readAmount|moneyRefusal)\b|MoneyField\.vue/.test(source))
      .map(([file]) => file);
    expect(readers.sort()).toEqual(['./lib/money.ts', './lib/sessionFilters.ts']);
  });
});
