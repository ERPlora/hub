// flow: hub-e2e-capture — FIX of the e2e harness (FIX-HUB-E2E-SHOT-BEFORE-RESIZE-UNCHECKED)
// A screenshot taken right after `setViewportSize` can come before the browser painted the page at its new size: the
// area the resize uncovered still holds the top of the page, so the capture repeats the topbar at its bottom (87 rows,
// 5 in 24 on the demo list with no wait, 2 in 24 after `settled` of service-helpers.ts, measured on main). Such a
// capture is evidence of a screen nobody saw. `repeatedTop` (helpers.ts) spots it; `capture` (helpers.ts) waits for
// a painted frame, takes the screenshot again while it repeats the top, and fails saying so if it never stops;
// `settled` (service-helpers.ts) waits for a painted frame too.
// FIX-HUB-E2E-CAPTURE-WITHOUT-WAIT-UNCHECKED: a spec that forgot to wait before `capture` got a frame of an overlay of
// Ionic still entering (WEBSITE-F07/F08 with their toast sliding in), and nothing said so. `capture` now waits itself
// until nothing finite moves (`untilStill`, endless spinners aside), or fails naming what still moves.
import { readFileSync, rmSync } from 'node:fs';

import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, createItem, listReady, login, repeatedTop, shot, shown, uniqueName } from './helpers';
import { settled } from './service-helpers';

const TASK = 'FIX-HUB-E2E-SHOT-BEFORE-RESIZE-UNCHECKED';
const WAIT_TASK = 'FIX-HUB-E2E-CAPTURE-WITHOUT-WAIT-UNCHECKED';

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

/** The finite animations running in the shadow root of the last `ion-toast` (its entrance), read on its own. */
const toastMoving = (page: Page) =>
  page.evaluate(() => {
    const toast = [...document.querySelectorAll('ion-toast')].at(-1);
    return (toast?.shadowRoot?.getAnimations() ?? []).filter(
      (animation) => animation.playState === 'running' && animation.effect?.getTiming().iterations !== Infinity,
    ).length;
  });

/** The box of the toast on screen (its `.toast-wrapper`, in its shadow root), in whole pixels inside the window. */
const toastBox = (page: Page) =>
  page.locator('ion-toast').last().evaluate((toast) => {
    const box = toast.shadowRoot?.querySelector('.toast-wrapper')?.getBoundingClientRect();
    if (!box) throw new Error('ion-toast without its .toast-wrapper');
    const left = Math.max(0, Math.floor(box.left));
    const top = Math.max(0, Math.floor(box.top));
    return {
      left,
      top,
      width: Math.min(innerWidth, Math.ceil(box.right)) - left,
      height: Math.min(innerHeight, Math.ceil(box.bottom)) - top,
    };
  });

/** How many pixels of `box` differ between the screenshots `a` and `b`, decoded in `page`'s browser. */
async function differingPixels(
  page: Page,
  a: Buffer,
  b: Buffer,
  box: { left: number; top: number; width: number; height: number },
): Promise<number> {
  return page.evaluate(
    async ({ first, second, area }) => {
      const pixels = async (base64: string) => {
        const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
        const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const context = new OffscreenCanvas(bitmap.width, bitmap.height).getContext('2d');
        if (!context) throw new Error('differingPixels: no 2d context to read the screenshot');
        context.drawImage(bitmap, 0, 0);
        return new Uint32Array(context.getImageData(area.left, area.top, area.width, area.height).data.buffer);
      };
      const [one, two] = await Promise.all([pixels(first), pixels(second)]);
      let differing = 0;
      for (let i = 0; i < one.length; i++) if (one[i] !== two[i]) differing++;
      return differing;
    },
    { first: a.toString('base64'), second: b.toString('base64'), area: box },
  );
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

test.describe('capture: never a screenshot while something finite moves on the page', () => {
  test('hub-e2e-capture: capture() right after a toast of Ionic shows up writes the toast at rest, at 390, 834 and 1440', async ({
    page,
    context,
  }) => {
    await login(page, A, '/demo/items');
    const item = await createItem(context, A, uniqueName('Capture toast'));
    // Animations at a fifth of their speed (Chrome's own control): the toast enters for longer than a screenshot takes,
    // so a capture that does not wait for it catches it still sliding in.
    const devtools = await context.newCDPSession(page);
    await devtools.send('Animation.enable');
    try {
      // «Save note» with the network down: the page's error toast (`toastError`), and nothing is saved.
      await page.route('**/api/demo/**', (route) => (route.request().method() === 'POST' ? route.abort('internetdisconnected') : route.continue()));
      for (const size of SIZES) {
        await page.setViewportSize({ width: size.width, height: size.height });
        await devtools.send('Animation.setPlaybackRate', { playbackRate: 1 });
        await page.goto(`/demo/items/${item.id}`);
        const detail = shown(page);
        await detail.locator('[data-testid=demo-note] textarea').fill(`Note at ${size.label}`);
        await expect(detail.getByTestId('demo-note-save')).toBeEnabled();
        await settled(page);
        await devtools.send('Animation.setPlaybackRate', { playbackRate: 0.2 });
        await detail.getByTestId('demo-note-save').click();
        await expect(page.locator('ion-toast').last()).toBeVisible();
        // No wait of the spec's own: capture() is the one that waits.
        const name = `${WAIT_TASK}-${size.label}`;
        const png = await capture(page, name);
        expect.soft(await toastMoving(page), `the toast still entering once capture() returned at ${size.label}`).toBe(0);
        await settled(page);
        const atRest = await capture(page, `${name}-at-rest`);
        const box = await toastBox(page);
        expect(box.width * box.height, `the toast's box at ${size.label}`).toBeGreaterThan(0);
        expect.soft(await differingPixels(page, png, atRest, box), `pixels of the toast in ${name}.png unlike the toast at rest`).toBe(0);
        expect(readFileSync(shot(name)).equals(png), `${name}.png is the capture returned`).toBe(true);
      }
    } finally {
      await devtools.send('Animation.setPlaybackRate', { playbackRate: 1 });
      await page.unroute('**/api/demo/**');
      const res = await api(context, A, 'POST', '/demo/items/delete', { id: item.id });
      expect(res.status).toBeLessThan(300);
    }
  });

  /** A page of its own, with an element `tag` (its own name, so a failure names it) animated as `timing` says. */
  const animated = async (page: Page, tag: string, timing: KeyframeAnimationOptions) => {
    await page.evaluate(
      ({ tag, timing }) => {
        const element = document.body.appendChild(document.createElement(tag));
        element.style.cssText = 'display: block; width: 80px; height: 80px; background: #1d4ed8';
        (window as unknown as Record<string, Animation>)[tag] = element.animate(
          [{ transform: 'translateX(0)' }, { transform: 'translateX(200px)' }],
          timing,
        );
      },
      { tag, timing },
    );
  };

  test('hub-e2e-capture: capture() waits for a finite animation to end before its screenshot', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.setContent('<!doctype html><body style="margin: 0"></body>');
    await animated(page, 'capture-probe', { duration: 1500 });
    await capture(page, `${WAIT_TASK}-finite`);
    expect(await page.evaluate(() => (window as unknown as Record<string, Animation>)['capture-probe'].playState)).toBe('finished');
  });

  test('hub-e2e-capture: capture() is not held by an endless animation (a spinner)', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.setContent('<!doctype html><body style="margin: 0"></body>');
    await animated(page, 'capture-spinner', { duration: 800, iterations: Infinity });
    const started = Date.now();
    const png = await capture(page, `${WAIT_TASK}-endless`);
    expect(Date.now() - started, 'ms capture() took beside a spinner').toBeLessThan(3_000);
    expect(readFileSync(shot(`${WAIT_TASK}-endless`)).equals(png)).toBe(true);
  });

  test('hub-e2e-capture: capture() fails naming what still moves once its wait runs out, and writes nothing', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.setContent('<!doctype html><body style="margin: 0"></body>');
    await animated(page, 'capture-stuck', { duration: 600_000 });
    const name = `${WAIT_TASK}-stuck`;
    rmSync(shot(name), { force: true });
    const failure = await capture(page, name).then(
      () => 'capture() wrote a screenshot while capture-stuck moved',
      (error: unknown) => String(error),
    );
    expect(failure).toContain(`capture ${name}: still moving`);
    expect(failure).toContain('capture-stuck');
    expect(() => readFileSync(shot(name))).toThrow(/ENOENT/);
  });
});
