// What the money of every screen that paints it reads alike, whichever app's `formatMoney` paints it: the thousands
// grouped from four digits on, in Spanish too, and a dash for a missing amount. Each app's test passes its own
// `formatMoney` and `plain` (which makes the narrow no-break spaces Intl writes plain).
import { expect, it } from 'vitest';

type Money = { currency: string; decimals: number };

const EUR: Money = { currency: 'EUR', decimals: 2 };

export function itGroupsThousandsAndDashesAMissingAmount(
  formatMoney: (cents: number | null | undefined, locale: string, money?: Money) => string,
  plain: (text: string) => string,
): void {
  it('groups the thousands from four digits on, in Spanish too', () => {
    // Spanish CLDR only groups from five digits on (minimumGroupingDigits 2): «1234,56 €» beside
    // «12.345,67 €», and unlike Carts, Price lists and Payments, which paint «1.234,56 €».
    expect(plain(formatMoney(123456, 'es', EUR))).toBe('1.234,56 €');
    expect(plain(formatMoney(1234567, 'es', EUR))).toBe('12.345,67 €');
    expect(plain(formatMoney(-123456, 'es', EUR))).toBe('-1.234,56 €');
    expect(formatMoney(123456, 'en', EUR)).toBe('€1,234.56');
    expect(formatMoney(1234567, 'en', EUR)).toBe('€12,345.67');
  });

  it('a missing amount is a dash, never «NaN», and a broken language falls back to English', () => {
    expect(formatMoney(null, 'en', EUR)).toBe('—');
    expect(formatMoney(undefined, 'es', EUR)).toBe('—');
    expect(formatMoney(100, 'not a tag!', EUR)).toBe('€1.00');
  });
}
