// flow: hub-e2e-capture — FIX of the e2e harness (FIX-HUB-E2E-SHOT-BEFORE-RESIZE-UNCHECKED)
// A screenshot taken right after `setViewportSize` can come before the browser painted the page at its new size: the
// area the resize uncovered still holds the top of the page, so the capture repeats the topbar at its bottom (87 rows,
// 5 in 24 on the demo list with no wait, 2 in 24 after `settled` of service-helpers.ts, measured on main). Such a
// capture is evidence of a screen nobody saw. `repeatedTop` (helpers.ts) spots it; `capture` (helpers.ts) waits for
// a painted frame, takes the screenshot again while it repeats the top, and fails saying so if it never stops;
// `settled` (service-helpers.ts) waits for a painted frame too.
import { readFileSync, rmSync } from 'node:fs';

import { expect, type Page, test } from '@playwright/test';

import { A, capture, listReady, login, repeatedTop, shot } from './helpers';
import { settled } from './service-helpers';

const TASK = 'FIX-HUB-E2E-SHOT-BEFORE-RESIZE-UNCHECKED';

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** Rounds through the three sizes: one in about twelve captures came out striped on main, so 36 of them. */
const ROUNDS = 12;

/**
 * A PNG of `width`×`height` drawn in `page`'s browser: a horizontal gradient (no row of it is one flat colour) on
 * white, or white only. With `stripe`, its first `stripe` rows are painted again at its bottom, as a capture taken
 * before the page was painted at its size.
 */
async function picture(page: Page, options: { width: number; height: number; stripe?: number; flat?: boolean }): Promise<Buffer> {
  const base64 = await page.evaluate(async ({ width, height, stripe, flat }) => {
    const canvas = new OffscreenCanvas(width, height);
    const context = canvas.getContext('2d');
    if (!context) throw new Error('picture: no 2d context');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, width, height);
    if (!flat) {
      const gradient = context.createLinearGradient(0, 0, width, 0);
      gradient.addColorStop(0, '#1d4ed8');
      gradient.addColorStop(1, '#f97316');
      context.fillStyle = gradient;
      context.fillRect(0, 0, width, 40);
      context.fillStyle = '#16a34a';
      context.fillRect(10, 50, width / 3, 20);
    }
    if (stripe) context.drawImage(canvas, 0, 0, width, stripe, 0, height - stripe, width, stripe);
    const blob = await canvas.convertToBlob({ type: 'image/png' });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = '';
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
  }, options);
  return Buffer.from(base64, 'base64');
}

test.describe('repeatedTop: the stripe of a capture taken before the page was painted', () => {
  test('counts the rows of the top painted again at the bottom', async ({ page }) => {
    expect(await repeatedTop(page, await picture(page, { width: 390, height: 844, stripe: 87 }))).toBe(87);
    expect(await repeatedTop(page, await picture(page, { width: 1440, height: 900, stripe: 120 }))).toBe(120);
  });

  test('finds none in a capture painted at its size, nor in a page of one flat colour', async ({ page }) => {
    expect(await repeatedTop(page, await picture(page, { width: 390, height: 844 }))).toBe(0);
    expect(await repeatedTop(page, await picture(page, { width: 390, height: 844, flat: true }))).toBe(0);
    // A background of one colour at both ends is no stripe, even as tall as one.
    expect(await repeatedTop(page, await picture(page, { width: 390, height: 844, flat: true, stripe: 87 }))).toBe(0);
  });

  test('a stripe under 8 rows is no stripe: one line of the same colour at both ends is common', async ({ page }) => {
    expect(await repeatedTop(page, await picture(page, { width: 390, height: 844, stripe: 7 }))).toBe(0);
  });
});

test.describe('capture: the screenshot of the page as painted at its size', () => {
  test('right after each resize it never keeps a capture that repeats the top of the page at its bottom', async ({ page }) => {
    await login(page, A, '/demo/items');
    await listReady(page);
    const striped: string[] = [];
    for (let round = 0; round < ROUNDS; round++) {
      for (const size of SIZES) {
        await page.setViewportSize({ width: size.width, height: size.height });
        const name = `${TASK}-${size.label}`;
        const png = await capture(page, name);
        const rows = await repeatedTop(page, png);
        if (rows) striped.push(`round ${round} at ${size.label}: ${rows} rows`);
        // What lands on disk is the capture it returned.
        expect(readFileSync(shot(name)).equals(png), `${name}.png is the capture returned`).toBe(true);
      }
    }
    expect(striped).toEqual([]);
  });

  test('fails saying so when every capture repeats the top, and writes nothing', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    // A page whose top and bottom are the same band: what a capture of the page before it is painted looks like.
    await page.setContent(`<!doctype html><style>
      body { margin: 0; height: 844px; position: relative; }
      .band { position: absolute; left: 0; right: 0; height: 50px; background: linear-gradient(90deg, #1d4ed8 50%, #f97316 50%); }
    </style><div class="band" style="top: 0"></div><div class="band" style="bottom: 0"></div>`);
    const name = `${TASK}-always-striped`;
    rmSync(shot(name), { force: true });
    await expect(capture(page, name)).rejects.toThrow(
      `capture ${name}: every screenshot repeats the top 50 rows of the page at its bottom`,
    );
    expect(() => readFileSync(shot(name))).toThrow(/ENOENT/);
  });
});

test('settled: a screenshot right after each resize and settled() is the page as painted', async ({ page }) => {
  await login(page, A, '/demo/items');
  await listReady(page);
  const striped: string[] = [];
  for (let round = 0; round < ROUNDS; round++) {
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await settled(page);
      const rows = await repeatedTop(page, await page.screenshot());
      if (rows) striped.push(`round ${round} at ${size.label}: ${rows} rows`);
    }
  }
  expect(striped).toEqual([]);
});
