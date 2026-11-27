// System › «Usage and plan» on a phone (BASE-F40). A value that is a sentence («Measured every night: …») used to take
// the whole width of a row of «For your information» and leave its name 0 px wide, one letter per line. The browser
// lays it out (tests/e2e/base-system-usage-phone-rows.spec.ts); this keeps the sheet that decides it.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const SFC = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'SystemUsage.vue'), 'utf8');
const SHEET = /<style scoped>([\s\S]*)<\/style>/.exec(SFC)?.[1] ?? '';
const WIDER = '@media (min-width: 768px) {';

/** The sheet split in what a phone reads and what the tablet and the desk add on top. */
function split(sheet: string): { phone: string; wider: string } {
  const start = sheet.indexOf(WIDER);
  if (start < 0) return { phone: sheet, wider: '' };
  let depth = 0;
  for (let at = start + WIDER.length - 1; at < sheet.length; at++) {
    if (sheet[at] === '{') depth++;
    if (sheet[at] === '}' && --depth === 0) {
      return { phone: sheet.slice(0, start) + sheet.slice(at + 1), wider: sheet.slice(start + WIDER.length, at) };
    }
  }
  return { phone: sheet.slice(0, start), wider: sheet.slice(start + WIDER.length) };
}

const selectors = (css: string): string[] => [...css.matchAll(/([^{}]+)\{[^{}]*\}/g)].map((rule) => rule[1].trim());
const declarations = (css: string, selector: string): string =>
  [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].find((rule) => rule[1].trim() === selector)?.[2] ?? '';

describe('SystemUsage on a phone', () => {
  const { phone, wider } = split(SHEET);

  it('reads the sheet and its tablet part', () => {
    expect(selectors(phone)).toContain('.system-usage-row');
    expect(wider).toContain('.system-usage-row');
  });

  it('lays a row of «For your information» out as a row of «What you use»: the value under the whole name', () => {
    expect(selectors(phone).filter((selector) => selector.includes('system-usage-row--info'))).toEqual([]);
  });

  it('keeps, from the tablet up, the name in its column and the value beside it', () => {
    expect(declarations(wider, '.system-usage-row--info')).toMatch(/grid-template-columns:\s*10rem minmax\(0, 1fr\)/);
    expect(declarations(wider, '.system-usage-amount')).toMatch(/grid-column:\s*2;/);
  });
});
