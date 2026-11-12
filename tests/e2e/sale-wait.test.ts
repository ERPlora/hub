// flow: sale-e2e-wait — the Sales specs' wait
// Before a capture or a measurement, the Sales specs (sale-*.spec.ts) and their helpers wait with the harness's one
// wait, `untilStill(page)` (helpers.ts), which asks every open shadow root too. A wait of their own that asks the
// document alone for its animations is blind to Ionic's overlays (`sale-settled.spec.ts` shows the till's «sold out»
// toast passing for still), and so is a fixed sleep; swapping one back would leave every spec green: this keeps them
// out of the Sales files. own-animation-waits.test.ts holds the same rule for every spec of the e2e.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The fixed sleeps a Sales file keeps on purpose, by file: the dictation's recording time before «Stop» waits for no animation. */
const SLEEPS: Record<string, number> = { 'sale-speak.spec.ts': 1 };

/** The Sales specs and their helpers (`sale-*.ts`), not Vitest's own tests. */
const saleFiles = (): string[] => readdirSync(E2E_DIR).filter((name) => /^sale-.*\.ts$/.test(name) && !name.endsWith('.test.ts'));

const read = (name: string): string => readFileSync(join(E2E_DIR, name), 'utf8');

/** The lines of `source` that ask for animations themselves (`getAnimations(`) instead of waiting with `untilStill`. */
function ownAnimationWaits(source: string): string[] {
  return source.split('\n').filter((line) => /\bgetAnimations\(/.test(line));
}

/** How many fixed sleeps (`waitForTimeout(`) `source` has. */
function sleeps(source: string): number {
  return source.match(/\.waitForTimeout\(/g)?.length ?? 0;
}

describe('the Sales specs wait with untilStill() of helpers.ts', () => {
  it('there are Sales specs and helpers to look at', () => {
    expect(saleFiles()).toEqual(expect.arrayContaining(['sale-helpers.ts', 'sale-settled.spec.ts', 'sale-till-flows.spec.ts']));
  });

  it('no Sales spec or helper asks for animations itself: the wait is untilStill(page)', () => {
    const own = saleFiles().flatMap((name) => ownAnimationWaits(read(name)).map((line) => `${name}: ${line.trim()}`));
    expect(own).toEqual([]);
  });

  it('no Sales spec or helper sleeps a fixed time but the ones listed', () => {
    const over = saleFiles()
      .map((name) => [name, sleeps(read(name))] as const)
      .filter(([name, count]) => count > (SLEEPS[name] ?? 0))
      .map(([name, count]) => `${name}: ${count} waitForTimeout( calls, ${SLEEPS[name] ?? 0} allowed`);
    expect(over).toEqual([]);
  });

  it('the listed sleeps are still there: one that goes leaves the list', () => {
    const stale = Object.entries(SLEEPS)
      .filter(([name, count]) => sleeps(read(name)) !== count)
      .map(([name, count]) => `${name}: ${sleeps(read(name))} waitForTimeout( calls, the list says ${count}`);
    expect(stale).toEqual([]);
  });

  it('the checks read the waits the Sales specs had, and untilStill() as none', () => {
    const blind = "    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));";
    expect(ownAnimationWaits(blind)).toEqual([blind]);
    expect(sleeps('    await page.waitForTimeout(400);')).toBe(1);
    expect(ownAnimationWaits('    await untilStill(page);')).toEqual([]);
    expect(sleeps('    await untilStill(page);')).toBe(0);
  });
});
