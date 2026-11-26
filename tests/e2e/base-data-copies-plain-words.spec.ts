// Settings › Data › Reset › «Copies of the data» tells the owner what a copy is in plain words, with no database
// jargon, in English and in Spanish, and the text fits its card at the three sizes.
// flow: BASE-F37
import { expect, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, hostPage, saveSessionForTheSweep, signedInSpanish, testid } from './helpers';

const SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1280, height: 720 },
] as const;

const RESET = '/settings?data=reset#data';
const JARGON = /postgres|pg_restore|pg_dump|sql/i;

async function introFits(page: Page, kept: string, name: string): Promise<void> {
  const intro = testid(page, 'dumps-intro');
  await expect(intro).toContainText(kept);
  expect(await intro.innerText()).not.toMatch(JARGON);
  const [text, card] = await Promise.all([intro.boundingBox(), testid(page, 'dumps-card').boundingBox()]);
  expect(text && card).toBeTruthy();
  if (!text || !card) return;
  expect(text.x).toBeGreaterThanOrEqual(card.x);
  expect(text.x + text.width).toBeLessThanOrEqual(card.x + card.width + 0.5);
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  await expect(testid(page, 'dumps-loading')).toHaveCount(0);
  await testid(page, 'dumps-card').scrollIntoViewIfNeeded();
  await capture(page, name);
}

for (const viewport of SIZES) {
  const size = `${viewport.width}×${viewport.height}`;

  test(`«Copies of the data» in plain words in English at ${size}`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: RESET });
    try {
      await introFits(page, 'keeps it for 90 days', `BASE-F37-copies-intro-en-${viewport.width}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });

  test(`«Copies of the data» in plain words in Spanish at ${size}`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, viewport, RESET);
    try {
      await introFits(page, 'la guarda 90 días', `BASE-F37-copies-intro-es-${viewport.width}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });
}
