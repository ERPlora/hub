// flow: e2e-overflow — FIX of the e2e harness (FIX-HUB-E2E-HORIZONTAL-SCROLL-CHECK-BLIND-TO-ION-CONTENT)
// Every «no horizontal scroll» check of the e2e goes through `horizontalOverflow(page)` (helpers.ts), which reads the
// document and every `ion-content` on screen. A spec that measures the document by hand (`documentElement.scrollWidth`
// against the window) is blind to a screen cut inside `ion-content`: Ionic pins the `body`, so the document never grows
// (60 files of the e2e did, and a 1600 px block on a page at 390 passed). No ratchet: no file but helpers.ts measures it.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The file of the one measure. */
const HELPERS = 'helpers.ts';

/** The ways of reading how wide the document is: its root's, its scrolling element's or its body's `scrollWidth`. */
const DOCUMENT_WIDTH = /\b(?:documentElement|scrollingElement|document\s*\.\s*body)\s*!?\s*\??\.\s*scrollWidth\b/g;

/** `file:line` of each line of `source` (the file `name`) that reads how wide the document is. */
function documentMeasures(name: string, source: string): string[] {
  return source.split('\n').flatMap((line, index) => (line.match(DOCUMENT_WIDTH) ? [`${name}:${index + 1}`] : []));
}

/** The files of the e2e (the specs and their helpers, not Vitest's own tests) that measure the document by hand. */
function handMeasures(): string[] {
  return readdirSync(E2E_DIR)
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts') && name !== HELPERS)
    .sort()
    .flatMap((name) => documentMeasures(name, readFileSync(join(E2E_DIR, name), 'utf8')));
}

describe('the e2e checks for a horizontal scroll go through horizontalOverflow() of helpers.ts', () => {
  it('no file of tests/e2e but helpers.ts measures the document by hand: the check is horizontalOverflow(page)', () => {
    expect(handMeasures()).toEqual([]);
  });

  it('helpers.ts has the one measure, and it reads the document and the scroll box of every ion-content', () => {
    const helpers = readFileSync(join(E2E_DIR, HELPERS), 'utf8');
    expect(helpers).toContain('export async function horizontalOverflow(page: Page): Promise<number>');
    expect(helpers).toContain('const boxes: Element[] = [document.documentElement];');
    expect(helpers).toContain("for (const content of document.querySelectorAll('ion-content'))");
    expect(helpers).toContain(`content.shadowRoot?.querySelector('[part~="scroll"]')`);
  });

  it('the count reads every way of measuring the document by hand, and the helper or an element’s own width as none', () => {
    const lines = [
      'page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)',
      'page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)',
      '      documentScrollWidth: document.documentElement.scrollWidth,',
      'return document.scrollingElement!.scrollWidth - innerWidth;',
      'return document.body.scrollWidth > innerWidth;',
    ];
    expect(lines.map((line) => documentMeasures('x.ts', line))).toEqual(lines.map(() => ['x.ts:1']));
    expect(documentMeasures('x.ts', 'expect.poll(() => horizontalOverflow(page)).toBeLessThanOrEqual(0);')).toEqual([]);
    expect(documentMeasures('x.ts', 'label.scrollWidth > label.clientWidth + 1')).toEqual([]);
    expect(documentMeasures('x.ts', 'const body = el.querySelector(".drawer-body"); body.scrollWidth > body.clientWidth')).toEqual([]);
  });
});
