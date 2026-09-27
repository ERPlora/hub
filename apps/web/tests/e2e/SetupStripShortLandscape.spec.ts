// Regression test for ERPlora/hub#2272 — on a phone held sideways, the blocking strip («You cannot
// issue invoices yet») ate a third of the screen.
//
// The strip sits between the topbar and the scroller of EVERY shell screen, the till included, and
// it cannot be dismissed. Laid out in full (heading + the consequence + one row per thing missing)
// it measured ~113 px of the 375 px a 667×375 landscape phone has, and the till's open ticket was
// left with ~120 px: the total and «Charge» fitted, no line of the ticket did.
//
// On a SHORT screen (≤ 500 px tall) the strip folds to one row — the heading and a way to open
// what is missing — like the setup banners of Shopify and Square on a phone. The detail (and its
// «Set up» buttons) opens on tap, in place. Everywhere else the strip is exactly what it was: the
// three viewports of the UI contract are checked here too, so the fold cannot leak into them.
//
// This bench boots a hub with no business identity, so the strip is up on every screen but Home
// (Home paints the whole checklist and the strip stands down there). Spanish on purpose: its copy
// is the longest the row has to hold.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession, VIEWPORTS } from './shell-visual-helpers';

test.use({ locale: 'es-ES' });

/** Phones on their side: the one of the report (667×375) and the lowest there is (568×320). */
const SHORT_LANDSCAPE = [
  { width: 667, height: 375 },
  { width: 568, height: 320 },
] as const;

/** One row of the strip: a small button plus the band's own padding, and nothing below it. */
const ONE_ROW_MAX_PX = 56;

async function openStrip(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await loggedInSession(page);
  await page.goto('/settings');
  const strip = page.getByTestId('setup-strip');
  await expect(strip).toBeVisible();
  await expect(strip.getByText('Todavía no puedes facturar')).toBeVisible();
  return strip;
}

async function heightOf(page: Page, testId: string): Promise<number> {
  const box = await page.getByTestId(testId).boundingBox();
  if (!box) throw new Error(`${testId} has no box`);
  return Math.round(box.height);
}

test.describe('Blocking strip on a short landscape phone (hub#2272)', () => {
  for (const viewport of SHORT_LANDSCAPE) {
    test(`${viewport.width}×${viewport.height}: folds to one row and opens what is missing on tap`, async ({
      page,
    }) => {
      const strip = await openStrip(page, viewport);

      // Folded: the heading and the way in, on one row. What is missing is not painted yet.
      const toggle = page.getByTestId('setup-strip-toggle');
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await expect(toggle).toContainText('Ver qué falta');
      await expect(strip.locator('.setup-strip-body')).toBeHidden();
      await expect(strip.locator('.setup-strip-item').first()).toBeHidden();
      expect(await heightOf(page, 'setup-strip'), 'the folded strip is one row').toBeLessThanOrEqual(ONE_ROW_MAX_PX);

      // The toggle is on the SAME row as the heading, and inside the screen.
      const heading = await strip.getByText('Todavía no puedes facturar').boundingBox();
      const button = await toggle.boundingBox();
      if (!heading || !button) throw new Error('heading or toggle has no box');
      expect(button.y, 'the toggle does not drop below the heading').toBeLessThan(heading.y + heading.height);
      expect(button.x + button.width).toBeLessThanOrEqual(viewport.width);

      // Tap: the detail opens in place, with its way in for each thing missing.
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      await expect(toggle).toContainText('Ocultar');
      await expect(strip.locator('.setup-strip-body')).toBeVisible();
      await expect(strip.locator('.setup-strip-item').first()).toBeVisible();
      await expect(strip.locator('[data-testid^="setup-strip-action-"]').first()).toBeVisible();

      // And it folds back.
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await expect(strip.locator('.setup-strip-body')).toBeHidden();
      expect(await heightOf(page, 'setup-strip')).toBeLessThanOrEqual(ONE_ROW_MAX_PX);
    });
  }

  for (const viewport of VIEWPORTS) {
    test(`${viewport.width}×${viewport.height}: stays the full strip, with no fold`, async ({ page }) => {
      const strip = await openStrip(page, viewport);
      await expect(page.getByTestId('setup-strip-toggle')).toHaveCount(0);
      await expect(strip.locator('.setup-strip-body')).toBeVisible();
      await expect(strip.locator('.setup-strip-item').first()).toBeVisible();
      await expect(strip.locator('[data-testid^="setup-strip-action-"]').first()).toBeVisible();
    });
  }
});
