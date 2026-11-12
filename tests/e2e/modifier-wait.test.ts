// flow: modifier-e2e-wait — the Modifiers specs' wait
// Before a capture or a measurement, the Modifiers specs (modifier-*.spec.ts) wait with the harness's one wait,
// `untilStill(page)` (helpers.ts), which asks every open shadow root too. A wait of their own that asks the document
// alone for its animations is blind to Ionic's overlays (`modifier-settled.spec.ts` shows the till's options sheet
// passing for still), and swapping one back would leave every spec green: this keeps them out of the Modifiers files,
// and no fixed sleep (`waitForTimeout(`) takes their place. own-animation-waits.test.ts holds the same rule for every
// spec of the e2e.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The Modifiers specs and their helpers (`modifier-*.ts`), not Vitest's own tests. */
const modifierFiles = (): string[] => readdirSync(E2E_DIR).filter((name) => /^modifier-.*\.ts$/.test(name) && !name.endsWith('.test.ts'));

const read = (name: string): string => readFileSync(join(E2E_DIR, name), 'utf8');

/** The lines of `source` that ask for animations themselves (`getAnimations(`) instead of waiting with `untilStill`. */
function ownAnimationWaits(source: string): string[] {
  return source.split('\n').filter((line) => /\bgetAnimations\(/.test(line));
}

/** The lines of `source` that sleep a fixed time (`waitForTimeout(`). */
function sleeps(source: string): string[] {
  return source.split('\n').filter((line) => /\.waitForTimeout\(/.test(line));
}

describe('the Modifiers specs wait with untilStill() of helpers.ts', () => {
  it('there are Modifiers specs to look at', () => {
    expect(modifierFiles()).toEqual(expect.arrayContaining(['modifier-groups.spec.ts', 'modifier-settled.spec.ts', 'modifier-till.spec.ts']));
  });

  it('no Modifiers spec or helper asks for animations itself: the wait is untilStill(page)', () => {
    const own = modifierFiles().flatMap((name) => ownAnimationWaits(read(name)).map((line) => `${name}: ${line.trim()}`));
    expect(own).toEqual([]);
  });

  it('no Modifiers spec or helper sleeps a fixed time', () => {
    const slept = modifierFiles().flatMap((name) => sleeps(read(name)).map((line) => `${name}: ${line.trim()}`));
    expect(slept).toEqual([]);
  });

  it('the checks read the wait the Modifiers specs had, a fixed sleep, and untilStill() as neither', () => {
    const blind = "    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));";
    expect(ownAnimationWaits(blind)).toEqual([blind]);
    expect(sleeps('    await page.waitForTimeout(400);')).toEqual(['    await page.waitForTimeout(400);']);
    expect(ownAnimationWaits('    await untilStill(page);')).toEqual([]);
    expect(sleeps('    await untilStill(page);')).toEqual([]);
  });
});
