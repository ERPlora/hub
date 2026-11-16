// A save of the time clock's Settings that fails with no connection says so in red right above «Save»; the field
// typed back to what is saved and «Save» again sends nothing and says only «Settings saved.»: the failed save's red
// notice goes with it, until the next refusal (hub#894; apps/attendance/WORKBOOK.md ATTENDANCE-F04 «Si falla»). The
// Hub and its SaaS are the real ones; the connection is cut at the edge (the save's request aborted, as with no
// network), so nothing is saved and nothing needs undoing.
// flow: ATTENDANCE-F04
import { expect, type Page, test } from '@playwright/test';

import { A, capture, login, shown } from './helpers';
import { noHorizontalScroll, VIEWPORTS } from './schedule-helpers';

const KEY = 'FIX-HUB-894-ATTENDANCE-SETTINGS-SAVE-UNCHANGED-CLEARS-REFUSAL';
const SAVE = '/api/attendance/settings';

/** Every «Save» sent from now on is lost on its way, as with no connection; returns how many were sent. */
async function cutTheConnection(page: Page): Promise<() => number> {
  let sent = 0;
  await page.route(`**${SAVE}`, async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    sent += 1;
    return route.abort('internetdisconnected');
  });
  return () => sent;
}

test('ATTENDANCE-F04 — after a failed save, «Save» with nothing changed says only «Settings saved.» and the red notice goes', async ({ page }) => {
  await login(page, A, '/attendance/settings');
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  const sent = await cutTheConnection(page);
  for (const vp of VIEWPORTS) {
    const where = `${vp.width}x${vp.height}`;
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/attendance/settings`);
    const view = shown(page);
    await expect(view.locator('[data-testid=attendance-settings-form]'), where).toBeVisible();
    const hours = view.locator('[data-testid=attendance-settings-auto_close_after_hours] input');
    const failed = view.locator('[data-testid=attendance-settings-save-error]');
    const saved = view.locator('[data-testid=attendance-settings-saved]');
    const save = view.locator('[data-testid=attendance-settings-save]');
    await expect(hours, where).not.toHaveValue('');
    const kept = await hours.inputValue();
    const before = sent();

    await hours.fill(kept === '24' ? '23' : String(Number(kept) + 1));
    await save.click();
    await expect(failed, `${where}: the failed save is said`).toBeVisible();
    await expect(saved, where).toHaveCount(0);

    await hours.fill(kept);
    await expect(failed, `${where}: a refusal that names no field stays while typing`).toBeVisible();
    await save.click();
    await expect(saved, `${where}: what is on screen is what is saved`).toBeVisible();
    await expect(failed, `${where}: the failed save's notice goes with it`).toHaveCount(0);
    expect(sent() - before, `${where}: the second «Save» sends nothing`).toBe(1);
    await noHorizontalScroll(page, where);
    await capture(page, `${KEY}-${where}`);
  }
});
