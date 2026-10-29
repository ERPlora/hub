// flow: combo-e2e-wait — FIX of the Menus specs' wait (FIX-HUB-COMBO-E2E-WAIT-BLIND-TO-SHADOW-ROOTS)
// Before a capture or a measurement, the Menus specs (combo-*.spec.ts) wait with the harness's one wait,
// `untilStill(page)` (helpers.ts), which asks every open shadow root too, and `painted(page)` for a frame. Their own
// wait asked the document alone for its animations, blind to Ionic's overlays (`combo-settled.spec.ts` shows it let
// the till's menu sheet pass for still), or only waited two frames. Swapping one back would leave every spec green:
// this keeps them from coming back in the Menus files, and no fixed sleep (`waitForTimeout(`) takes their place. The
// same rule for every spec of the e2e is FIX-HUB-E2E-OWN-ANIMATION-WAIT-UNGUARDED's (hub:base).
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The Menus specs and their helpers (`combo-*.ts`), not Vitest's own tests. */
const comboFiles = (): string[] => readdirSync(E2E_DIR).filter((name) => /^combo-.*\.ts$/.test(name) && !name.endsWith('.test.ts'));

const read = (name: string): string => readFileSync(join(E2E_DIR, name), 'utf8');

/** The lines of `source` that ask for animations themselves (`getAnimations(`) instead of waiting with `untilStill`. */
function ownAnimationWaits(source: string): string[] {
  return source.split('\n').filter((line) => /\bgetAnimations\(/.test(line));
}

/** The lines of `source` that wait for frames themselves (`requestAnimationFrame(`) instead of with `painted`. */
function ownFrameWaits(source: string): string[] {
  return source.split('\n').filter((line) => /\brequestAnimationFrame\(/.test(line));
}

/** The lines of `source` that sleep a fixed time (`waitForTimeout(`). */
function sleeps(source: string): string[] {
  return source.split('\n').filter((line) => /\.waitForTimeout\(/.test(line));
}

describe('the Menus specs wait with untilStill() of helpers.ts', () => {
  it('there are Menus specs to look at', () => {
    expect(comboFiles()).toEqual(
      expect.arrayContaining(['combo-business-currency.spec.ts', 'combo-menus.spec.ts', 'combo-settled.spec.ts', 'combo-till.spec.ts']),
    );
  });

  it('no Menus spec or helper asks for animations itself: the wait is untilStill(page)', () => {
    const own = comboFiles().flatMap((name) => ownAnimationWaits(read(name)).map((line) => `${name}: ${line.trim()}`));
    expect(own).toEqual([]);
  });

  it('no Menus spec or helper waits for frames itself: the wait is painted(page)', () => {
    const own = comboFiles().flatMap((name) => ownFrameWaits(read(name)).map((line) => `${name}: ${line.trim()}`));
    expect(own).toEqual([]);
  });

  it('no Menus spec or helper sleeps a fixed time', () => {
    const slept = comboFiles().flatMap((name) => sleeps(read(name)).map((line) => `${name}: ${line.trim()}`));
    expect(slept).toEqual([]);
  });

  it('the checks read the waits the Menus specs had, a fixed sleep, and untilStill() and painted() as none', () => {
    const blind = "    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));";
    const frames = '    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));';
    expect(ownAnimationWaits(blind)).toEqual([blind]);
    expect(ownFrameWaits(frames)).toEqual([frames]);
    expect(sleeps('    await page.waitForTimeout(400);')).toEqual(['    await page.waitForTimeout(400);']);
    for (const wait of ['    await untilStill(page);', '    await painted(page);']) {
      expect(ownAnimationWaits(wait)).toEqual([]);
      expect(ownFrameWaits(wait)).toEqual([]);
      expect(sleeps(wait)).toEqual([]);
    }
  });
});
