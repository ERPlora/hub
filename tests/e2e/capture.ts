// The evidence a spec leaves under `.artifacts/`: its screenshots, taken once the page is still and painted at its
// size, and its measurements for the report.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, type Page } from '@playwright/test';

import { horizontalOverflow, shown } from './screen';
import { painted, untilStill } from './settled';

const HERE = dirname(fileURLToPath(import.meta.url));
export const ARTIFACTS = join(HERE, '.artifacts');
const METRICS = join(ARTIFACTS, 'metrics');

/** Path of a screenshot under `.artifacts/` (created on demand). */
export function shot(name: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  return join(ARTIFACTS, `${name}.png`);
}

/** The fewest rows `repeatedTop` counts as a stripe. */
const STRIPE_MIN_ROWS = 8;

/**
 * How many rows at the bottom of `png`, a screenshot of `page`, repeat the first rows of the image: 0 when none. It is
 * what a capture taken before the browser painted the page at its new size shows (the area the resize uncovered,
 * filled with the top of the page): evidence of a screen nobody saw. A stripe whose rows are each one flat colour (a
 * background at both ends, a hairline across it) does not count, nor one that is the same row over and over, whatever
 * its colours across: a background crossed by a border (the assistant's panel, all the screen on a phone, with its left
 * border; a card's veil over it). The top of the page a capture before the paint repeats is its topbar, rows unlike
 * each other. Decoded in `page`'s browser: the e2e has no image library. Ported from erplora.com's e2e (`repeatedTop`
 * of its tests/e2e/panel/fixtures.ts).
 */
export async function repeatedTop(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(
    async ({ base64, minRows }) => {
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const { width, height } = bitmap;
      const context = new OffscreenCanvas(width, height).getContext('2d');
      if (!context) throw new Error('repeatedTop: no 2d context to read the screenshot');
      context.drawImage(bitmap, 0, 0);
      const pixels = new Uint32Array(context.getImageData(0, 0, width, height).data.buffer);
      const sameRow = (a: number, b: number) => {
        for (let x = 0; x < width; x++) if (pixels[a * width + x] !== pixels[b * width + x]) return false;
        return true;
      };
      const flatRow = (row: number) => {
        for (let x = 1; x < width; x++) if (pixels[row * width + x] !== pixels[row * width]) return false;
        return true;
      };
      for (let rows = Math.floor(height / 2); rows >= minRows; rows--) {
        let repeated = true;
        let flat = true;
        let uniform = true;
        for (let row = 0; row < rows && repeated; row++) {
          repeated = sameRow(height - rows + row, row);
          flat &&= flatRow(row);
          uniform &&= sameRow(row, 0);
        }
        if (repeated && !flat && !uniform) return rows;
      }
      return 0;
    },
    { base64: png.toString('base64'), minRows: STRIPE_MIN_ROWS },
  );
}

/** How many screenshots `capture` takes at most while each one repeats the top of the page at its bottom. */
const CAPTURE_TRIES = 10;

/**
 * The screenshot of `page` as painted at its size, still, written as `.artifacts/<name>.png` and returned: every capture
 * of the e2e goes through here (`raw-screenshots.test.ts` keeps it so). It waits until nothing finite moves
 * (`untilStill`: an overlay of Ionic entering, endless spinners aside; one that still moves after its wait fails the
 * spec naming it, and nothing is written) and for a painted frame, and a screenshot that still repeats the top of the
 * page at its bottom (`repeatedTop`) is taken again, a frame later, up to `CAPTURE_TRIES` times; if every one does, it
 * fails saying so and writes nothing. What is on screen (data, a dialog) is the spec's to wait for before.
 */
export async function capture(page: Page, name: string, options: CaptureOptions = {}): Promise<Buffer> {
  let rows = 0;
  for (let tries = 0; tries < CAPTURE_TRIES; tries++) {
    await untilStill(page, `capture ${name}: still moving`);
    await painted(page);
    const png = await page.screenshot(options);
    rows = await repeatedTop(page, png);
    if (rows === 0) {
      writeFileSync(shot(name), png);
      return png;
    }
  }
  throw new Error(
    `capture ${name}: every screenshot repeats the top ${rows} rows of the page at its bottom (${CAPTURE_TRIES} tries): ` +
      'the browser never painted the page at its size',
  );
}

/** What `capture` hands to `page.screenshot`: everything but the path, which is `shot(name)`. */
export type CaptureOptions = Omit<NonNullable<Parameters<Page['screenshot']>[0]>, 'path'>;

/** Writes the measurements of a check to `.artifacts/metrics/<key>.json` for the report. */
export function record(key: string, data: unknown): void {
  mkdirSync(METRICS, { recursive: true });
  writeFileSync(join(METRICS, `${key}.json`), `${JSON.stringify(data, null, 2)}\n`);
}

/** The capture once the screen settled and nothing scrolls sideways. */
export async function settledCapture(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/** The page still, with nothing past its right edge at the size `label`, then captured as `name`. */
export async function capturedFitting(page: Page, name: string, label: string): Promise<void> {
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
  await capture(page, name);
}
