// How the modifier screens paint a supplement and a group's rule, in the page language (Intl) and in the
// business's currency (its country's, with the decimals the server counts it in): a supplement carries its
// sign («+1,00 zł», «-0,50 €») and 0 is «Free»; until the business answers it is a figure without a symbol,
// never a euro by default. The rule reads as the old screen's Choice column did, «Optional» or
// «Required (min. N)», plus « · max. N» and « · repeats».
import { describe, expect, it } from 'vitest';

import { choiceRule, decimalMark, formatDelta, formatMoney, type Money, moneyDecimals } from './format';

const EN: Record<string, string> = {
  'modifier.rule.optional': 'Optional',
  'modifier.rule.required': 'Required (min. {min})',
  'modifier.rule.max': 'max. {max}',
  'modifier.rule.repeat': 'repeats',
};
const t = (key: string, named?: Record<string, unknown>) =>
  EN[key].replace(/\{(\w+)\}/g, (_, name: string) => String(named?.[name] ?? ''));

const EUR: Money = { currency: 'EUR', decimals: 2 };
const PLN: Money = { currency: 'PLN', decimals: 2 };
const JPY: Money = { currency: 'JPY', decimals: 0 };
const spaced = (text: string) => text.replace(/\s/g, ' ');

describe('format', () => {
  it('paints minor units in the business’s currency, in the page language', () => {
    expect(spaced(formatMoney(150, 'es', EUR))).toBe('1,50 €');
    expect(formatMoney(150, 'en', EUR)).toBe('€1.50');
    expect(spaced(formatMoney(150, 'es', PLN))).toBe('1,50 zł');
    expect(spaced(formatMoney(150, 'en', PLN))).toBe('zł 1.50');
  });

  it('with the decimals the server counts, never the browser’s: 150 yen is ¥150', () => {
    expect(formatMoney(150, 'en', JPY)).toBe('¥150');
    expect(formatDelta(150, 'en', 'Free', JPY)).toBe('+¥150');
  });

  it('until the business answers, a figure without a symbol: never a euro by default', () => {
    expect(formatMoney(150, 'es')).toBe('1,50');
    expect(formatMoney(150, 'en')).toBe('1.50');
    expect(formatDelta(-50, 'es', 'Gratis')).toBe('-0,50');
    expect(formatDelta(100, 'en', 'Free')).toBe('+1.00');
  });

  it('a supplement carries its sign in any currency, and 0 is free', () => {
    expect(spaced(formatDelta(100, 'es', 'Gratis', EUR))).toBe('+1,00 €');
    expect(spaced(formatDelta(-50, 'es', 'Gratis', EUR))).toBe('-0,50 €');
    expect(formatDelta(250, 'en', 'Free', EUR)).toBe('+€2.50');
    expect(spaced(formatDelta(100, 'es', 'Gratis', PLN))).toBe('+1,00 zł');
    expect(spaced(formatDelta(-50, 'es', 'Gratis', PLN))).toBe('-0,50 zł');
    expect(formatDelta(0, 'es', 'Gratis', PLN)).toBe('Gratis');
    expect(formatDelta(0, 'en', 'Free')).toBe('Free');
  });

  it('the decimals of an amount: the currency’s, two while it is unknown', () => {
    expect([moneyDecimals(JPY), moneyDecimals(PLN), moneyDecimals()]).toEqual([0, 2, 2]);
  });

  it('knows the decimal mark of each language', () => {
    expect([decimalMark('es'), decimalMark('en')]).toEqual([',', '.']);
  });

  it('reads a group rule as the old Choice column', () => {
    expect(choiceRule({ min_choices: 0, max_choices: 0, allow_repeat: false }, t)).toBe('Optional');
    expect(choiceRule({ min_choices: 1, max_choices: 1, allow_repeat: false }, t)).toBe('Required (min. 1) · max. 1');
    expect(choiceRule({ min_choices: 0, max_choices: 3, allow_repeat: true }, t)).toBe('Optional · max. 3 · repeats');
  });
});
