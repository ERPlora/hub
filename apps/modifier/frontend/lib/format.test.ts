// How the modifier screens paint a supplement and a group's rule, in the page language (Intl): a
// supplement carries its sign («+1,00 €», «-0,50 €») and 0 is «Free»; the rule reads as the old
// screen's Choice column did, «Optional» or «Required (min. N)», plus « · max. N» and « · repeats».
import { describe, expect, it } from 'vitest';

import { choiceRule, decimalMark, formatDelta, formatMoney } from './format';

const EN: Record<string, string> = {
  'modifier.rule.optional': 'Optional',
  'modifier.rule.required': 'Required (min. {min})',
  'modifier.rule.max': 'max. {max}',
  'modifier.rule.repeat': 'repeats',
};
const t = (key: string, named?: Record<string, unknown>) =>
  EN[key].replace(/\{(\w+)\}/g, (_, name: string) => String(named?.[name] ?? ''));

describe('format', () => {
  it('paints whole cents as euros in the page language', () => {
    expect(formatMoney(150, 'es').replace(/\s/g, ' ')).toBe('1,50 €');
    expect(formatMoney(150, 'en')).toBe('€1.50');
  });

  it('a supplement carries its sign, and 0 is free', () => {
    expect(formatDelta(100, 'es', 'Gratis').replace(/\s/g, ' ')).toBe('+1,00 €');
    expect(formatDelta(-50, 'es', 'Gratis').replace(/\s/g, ' ')).toBe('-0,50 €');
    expect(formatDelta(0, 'es', 'Gratis')).toBe('Gratis');
    expect(formatDelta(250, 'en', 'Free')).toBe('+€2.50');
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
