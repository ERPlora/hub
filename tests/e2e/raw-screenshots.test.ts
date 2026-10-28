// flow: hub-e2e-capture — FIX of the e2e harness (FIX-HUB-E2E-SHOT-BEFORE-RESIZE-UNCHECKED)
// Every capture of the e2e goes through `capture` (helpers.ts), which refuses a screenshot taken before the page was
// painted at its size (`repeatedTop`). A raw `.screenshot(` takes it as it comes: on the demo list, 5 in 24 captures
// right after `setViewportSize` repeated the topbar at their bottom. This keeps them from coming back as a ratchet:
// `raw-screenshots.json` holds, for each file that still had raw calls when `capture` arrived, how many; a file can
// only lose them (and then its count goes down, or its line away), never gain them, and a new file has none.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The raw calls `capture` itself makes, and the one of the spec that measures `settled` alone, on purpose. */
const ALLOWED: Record<string, number> = { 'helpers.ts': 1, 'helpers-capture.spec.ts': 1 };

/** What is left of the raw calls of before `capture`, by file: it only goes down. */
const RATCHET = JSON.parse(readFileSync(join(E2E_DIR, 'raw-screenshots.json'), 'utf8')) as Record<string, number>;

/** The raw screenshot calls in `source`: a page's or a locator's `.screenshot(`. */
function rawScreenshots(source: string): number {
  return source.match(/\.screenshot\(/g)?.length ?? 0;
}

/** Each file of the e2e with raw calls and how many: the specs and their helpers, not Vitest's own tests. */
function rawCallsByFile(): Record<string, number> {
  const found: Record<string, number> = {};
  for (const name of readdirSync(E2E_DIR)) {
    if (!name.endsWith('.ts') || name.endsWith('.test.ts')) continue;
    const calls = rawScreenshots(readFileSync(join(E2E_DIR, name), 'utf8'));
    if (calls > 0) found[name] = calls;
  }
  return found;
}

describe('the e2e captures go through capture() of helpers.ts', () => {
  it('no file takes more raw screenshots than the ratchet lists: a new capture is capture(page, name)', () => {
    const over = Object.entries(rawCallsByFile())
      .filter(([name, calls]) => calls > (ALLOWED[name] ?? RATCHET[name] ?? 0))
      .map(([name, calls]) => `${name}: ${calls} raw .screenshot( calls, ${ALLOWED[name] ?? RATCHET[name] ?? 0} allowed`);
    expect(over).toEqual([]);
  });

  it('the ratchet only goes down: a file with fewer raw calls lowers its count in raw-screenshots.json', () => {
    const found = rawCallsByFile();
    const stale = Object.entries(RATCHET)
      .filter(([name, calls]) => (found[name] ?? 0) !== calls)
      .map(([name, calls]) => `${name}: ${found[name] ?? 0} raw calls, the ratchet says ${calls}`);
    expect(stale).toEqual([]);
  });

  it('the ratchet lists only files with raw calls left, none of the allowed ones, in order', () => {
    const names = Object.keys(RATCHET);
    expect(Object.entries(RATCHET).filter(([, calls]) => !(calls > 0))).toEqual([]);
    expect(names.filter((name) => name in ALLOWED)).toEqual([]);
    expect(names).toEqual([...names].sort());
  });

  it('the count reads a page’s and a locator’s screenshot as raw calls, and capture() as none', () => {
    expect(rawScreenshots("    await page.screenshot({ path: shot(`APP-SALE-${flow}-${viewport.label}`) });")).toBe(1);
    expect(rawScreenshots("await row.screenshot({ path: shot('x') }); const png = await page.screenshot();")).toBe(2);
    expect(rawScreenshots("    await capture(page, `APP-SALE-${flow}-${viewport.label}`);")).toBe(0);
  });
});
