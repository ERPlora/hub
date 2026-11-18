// flow: kitchen-e2e-wait — the Kitchen specs' wait
// Before a capture or a measurement, the Kitchen specs (kitchen-*.spec.ts) and their helpers wait with the harness's
// one wait, `untilStill(page)` (helpers.ts), which asks every open shadow root too. A wait of their own that asks the
// document alone for its animations is blind to Ionic's overlays (`kitchen-settled.spec.ts` shows the till's «Order
// tickets» sheet passing for still while it slides in), and swapping one back would leave every spec green: this
// keeps them out of the Kitchen files. own-animation-waits.test.ts holds the same rule for every spec of the e2e;
// printing-kitchen.spec.ts is the Printing app's.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The Kitchen specs and their helpers (`kitchen-*.ts`), not Vitest's own tests. */
const kitchenFiles = (): string[] => readdirSync(E2E_DIR).filter((name) => /^kitchen-.*\.ts$/.test(name) && !name.endsWith('.test.ts'));

const read = (name: string): string => readFileSync(join(E2E_DIR, name), 'utf8');

/** The lines of `source` that ask for animations themselves (`getAnimations(`) instead of waiting with `untilStill`. */
function ownAnimationWaits(source: string): string[] {
  return source.split('\n').filter((line) => /\bgetAnimations\(/.test(line));
}

/** The lines of `source` that sleep a fixed time (`waitForTimeout(`). */
function sleeps(source: string): string[] {
  return source.split('\n').filter((line) => /\.waitForTimeout\(/.test(line));
}

/** Each offending line of the Kitchen files by `find`, as `<file>: <line>`. */
const offending = (find: (source: string) => string[]): string[] =>
  kitchenFiles().flatMap((name) => find(read(name)).map((line) => `${name}: ${line.trim()}`));

describe('the Kitchen specs wait with untilStill() of helpers.ts', () => {
  it('there are Kitchen specs to look at, and not the Printing app’s', () => {
    expect(kitchenFiles()).toEqual(expect.arrayContaining(['kitchen-menu-options.spec.ts', 'kitchen-pos.spec.ts', 'kitchen-display.spec.ts']));
    expect(kitchenFiles()).not.toContain('printing-kitchen.spec.ts');
  });

  it('no Kitchen spec or helper asks for animations itself: the wait is untilStill(page)', () => {
    expect(offending(ownAnimationWaits)).toEqual([]);
  });

  it('no Kitchen spec or helper sleeps a fixed time', () => {
    expect(offending(sleeps)).toEqual([]);
  });

  it('the checks read the waits the Kitchen specs had, and untilStill() as none', () => {
    const blind = "  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));";
    expect(ownAnimationWaits(blind)).toEqual([blind]);
    expect(sleeps('    await page.waitForTimeout(400);')).toEqual(['    await page.waitForTimeout(400);']);
    expect(ownAnimationWaits('    await untilStill(page);')).toEqual([]);
    expect(sleeps('    await untilStill(page);')).toEqual([]);
  });
});
