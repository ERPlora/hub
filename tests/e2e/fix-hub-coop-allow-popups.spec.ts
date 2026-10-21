// The Hub's pages keep the windows they open (FIX-HUB-COOP-ALLOW-POPUPS, asked by WHATSAPP_INBOX-F01/F02): Meta's
// window to connect a WhatsApp number, and erplora.com's return page after it, post back to the page that opened
// them. With Django's default Cross-Origin-Opener-Policy, `same-origin`, a window on another origin lost its opener
// and nothing came back. The page answers `same-origin-allow-popups` (never `unsafe-none`), opens a window on
// another origin that sends no policy of its own (this stack's Vite: no third party) and that window sees its opener
// and posts to it; the page receives the message and still holds the window. The page in three sizes
// (FIX-HUB-COOP-ALLOW-POPUPS-390|834|1440).
// flow: ninguno — FIX base (COOP del Hub; la piden WHATSAPP_INBOX-F01/F02, de otro carril)
import { expect, test } from '@playwright/test';

import { A, login, shot, topbarApps } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';

interface Posted {
  origin: string;
  data: unknown;
}

const PROBE = { type: 'erplora.coop.probe' };

test('a window the Hub opens on another origin keeps it as its opener and posts back to it', async ({ page, context }) => {
  await login(page, A);
  const response = await page.goto('/demo/items');
  expect(response?.headers()['cross-origin-opener-policy']).toBe('same-origin-allow-popups');
  await topbarApps(page).waitFor({ state: 'attached' });

  await page.evaluate(() => {
    const w = window as unknown as { __posted: Posted[] };
    w.__posted = [];
    window.addEventListener('message', (event) => w.__posted.push({ origin: event.origin, data: event.data }));
  });
  // Any new page, not only a popup Playwright ties to this one: a window cut from its opener is still caught.
  const opened = context.waitForEvent('page');
  await page.evaluate((url) => {
    (window as unknown as { __window: Window | null }).__window = window.open(url, 'coop-probe', 'popup,width=480,height=640');
  }, STACK.viteClient);
  const other = await opened;
  await other.waitForLoadState();
  const otherOrigin = new URL(STACK.viteClient).origin;
  expect(new URL(other.url()).origin).toBe(otherOrigin);
  expect(otherOrigin).not.toBe(A);

  expect(await other.evaluate(() => window.opener !== null)).toBe(true);
  await other.evaluate(({ hub, probe }) => (window.opener as Window).postMessage(probe, hub), { hub: A, probe: PROBE });
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __posted: Posted[] }).__posted))
    .toEqual([{ origin: otherOrigin, data: PROBE }]);
  expect(await page.evaluate(() => (window as unknown as { __window: Window | null }).__window?.closed)).toBe(false);
  await other.close();

  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await settled(page);
    // Two frames after the resize: right after 834×1112 → 1440×900 the capture still held the taller frame (the
    // shell's top bar again below 813 px).
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
    await noHorizontalScroll(page, `FIX-HUB-COOP-ALLOW-POPUPS ${viewport.label}`);
    await page.screenshot({ path: shot(`FIX-HUB-COOP-ALLOW-POPUPS-${viewport.label}`) });
  }
});
