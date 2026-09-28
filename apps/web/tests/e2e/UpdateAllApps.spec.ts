// hub#2331 — «Update all» in «My apps», in the real shell, at the three widths of the UI contract.
//
// The bench has no Cloud and no apps installed, so the three things this screen asks the runtime
// about the apps (the installed list, which ones have a new version, and the per-app update) are
// answered here; everything else — shell, Ionic, OutfitKit, the layout — is the real thing. What it
// measures: the offer and its button are on screen, the progress says which app is running, and
// the result — one line per app, the failed one with its reason and «Retry» — fits the window
// without pushing «My apps» off it.
import type { Page } from '@playwright/test';
import { test, expect } from '../bench-boot';
import { loggedInSession, VIEWPORTS } from './shell-visual-helpers';

const APPS = [
  { id: 'sales', name: 'Ventas', version: '1.0.0', status: 'active' },
  { id: 'inventory', name: 'Inventario', version: '1.2.0', status: 'active' },
  { id: 'kitchen', name: 'Cocina', version: '0.9.0', status: 'active' },
];
const SENTENCE = 'El marketplace no ha contestado a tiempo';

async function openMyAppsWithUpdates(page: Page): Promise<{ calls: () => string[] }> {
  const calls: string[] = [];
  await page.route(/\/api\/modules\?locale=/, (r) => r.fulfill({ json: { ok: true, data: APPS } }));
  await page.route(/\/api\/modules\/updates/, (r) =>
    r.fulfill({
      json: {
        ok: true,
        data: APPS.map((a) => ({
          module_id: a.id,
          installed: a.version,
          latest: '2.0.0',
          update_available: true,
          pinned: null,
        })),
      },
    }),
  );
  await page.route(/\/api\/modules\/[a-z_]+\/update$/, async (r) => {
    const id = /modules\/([a-z_]+)\/update/.exec(r.request().url())![1];
    calls.push(id);
    await new Promise((res) => setTimeout(res, 700));
    if (id === 'inventory') {
      await r.fulfill({ status: 502, json: { error: SENTENCE, code: 'update_failed' } });
      return;
    }
    const from = APPS.find((a) => a.id === id)!.version;
    await r.fulfill({ json: { ok: true, module_id: id, from, to: '2.0.0', updated: true } });
  });
  await loggedInSession(page);
  await page.goto('/apps#mine');
  return { calls: () => calls };
}

async function insideWindow(page: Page, testId: string, width: number, height: number): Promise<void> {
  const box = await page.getByTestId(testId).first().boundingBox();
  expect(box, `${testId} must be on screen`).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width, `${testId} inside the window`).toBeLessThanOrEqual(width + 0.5);
  expect(box!.y + box!.height, `${testId} inside the window`).toBeLessThanOrEqual(height + 0.5);
}

test.describe('«Actualizar todas» in «Mis apps» (hub#2331)', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`${width}px: offer, progress and per-app result, all on screen`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height });
      const update = await openMyAppsWithUpdates(page);

      const offer = page.getByTestId('apps-update-all');
      await expect(offer).toContainText('3 apps tienen una versión nueva.');
      const button = page.getByTestId('apps-update-all-button');
      await expect(button).toHaveText('Actualizar todas');
      await insideWindow(page, 'apps-update-all-button', width, height);
      await page.screenshot({ path: testInfo.outputPath(`offer-${width}.png`) });

      await button.click();
      await expect(offer).toContainText('Actualizando Ventas (1 de 3)…');
      await expect(offer.locator('ion-progress-bar')).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`progress-${width}.png`) });

      await expect(offer).toContainText('2 de 3 apps actualizadas.', { timeout: 15_000 });
      expect(update.calls()).toEqual(['sales', 'inventory', 'kitchen']);
      await expect(page.locator('[data-testid="apps-update-all-result"][data-id="inventory"]')).toContainText(SENTENCE);
      await expect(page.locator('[data-testid="apps-update-all-result"][data-id="sales"]')).toContainText('1.0.0 → 2.0.0');
      await insideWindow(page, 'apps-update-all-retry', width, height);
      await insideWindow(page, 'apps-update-all-finish', width, height);
      await expect(page.getByTestId('apps-update-all-finish')).toHaveText('Recargar ahora');
      // «My apps» is still there under the result, not pushed off the screen.
      const table = await page.locator('ok-data-table').first().boundingBox();
      expect(table!.height, 'the «My apps» list keeps room on screen').toBeGreaterThan(120);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, 'no sideways scroll').toBeLessThanOrEqual(0);
      await page.screenshot({ path: testInfo.outputPath(`result-${width}.png`) });

      // «Retry» asks for that app alone.
      await page.getByTestId('apps-update-all-retry').click();
      await expect.poll(update.calls).toEqual(['sales', 'inventory', 'kitchen', 'inventory']);
    });
  }
});
