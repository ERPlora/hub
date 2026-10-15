// The drawer's settings in Chrome (CASH_REGISTER-F01, F02; apps/cash_register/WORKBOOK.md): the owner turns
// the blind count on and saves it (the server says so), adds a drawer and deactivates it; the employee reads
// the settings blocked, without «Save». Screenshots of the settings in the three viewports. The settings
// are put back and the drawer deleted after it.
import { expect, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shown } from './helpers';
import { dialog, fill } from './inventory-helpers';
import { shots, stamp } from './sale-helpers';

const RUN = stamp();
const DRAWER = `e2e Bar ${RUN}`;
let before: Record<string, unknown> | undefined;

test.afterAll(() => {
  psql(`delete from cash_register_register where name like 'e2e %'`);
  // The settings as they were: no row at all (the factory values) or the saved blind count.
  if (before && before.updated_at === null) psql('delete from cash_register_settings');
  else if (before) psql(`update cash_register_settings set require_blind_count = ${before.require_blind_count ? 'true' : 'false'}`);
});

async function settingsReady(page: import('@playwright/test').Page): Promise<void> {
  await shown(page).locator('[data-testid=cash-register-settings-heading]').waitFor({ state: 'visible' });
}

test('CASH_REGISTER-F01: the owner turns the blind count on and saves it', async ({ page, context }) => {
  await login(page, A, '/cash_register/settings');
  before = (await api<Record<string, unknown>>(context, A, 'GET', '/cash_register/settings')).data;
  await settingsReady(page);
  await shots(page, 'cash-register-settings', settingsReady);
  const toggle = shown(page).locator('[data-testid=cash-register-setting-require_blind_count]');
  await toggle.click();
  const save = shown(page).locator('[data-testid=cash-register-settings-save]');
  await expect(save).not.toHaveAttribute('aria-disabled', 'true');
  await save.click();
  await expect.poll(async () => (await api<{ require_blind_count: boolean }>(context, A, 'GET', '/cash_register/settings')).data.require_blind_count).toBe(
    !before?.require_blind_count,
  );
  await expect(save).toHaveAttribute('aria-disabled', 'true');
});

test('CASH_REGISTER-F02: the owner adds a drawer and deactivates it', async ({ page, context }) => {
  await login(page, A, '/cash_register/settings');
  await settingsReady(page);
  await shown(page).locator('[data-testid=cash-register-registers-add]').click();
  const modal = dialog(page, 'cash-register-register');
  await expect(modal).toBeVisible();
  await fill(modal, 'cash-register-register-name', DRAWER);
  await modal.locator('[data-testid=cash-register-register-submit]').click();
  await expect(modal).toBeHidden();
  const row = shown(page).locator('[data-testid=cash-register-registers-row]').filter({ hasText: DRAWER });
  await expect(row).toContainText(/Yes|Sí/);
  const listed = await api<{ rows: { id: string; name: string }[] }>(context, A, 'GET', `/cash_register/registers?search=${encodeURIComponent(RUN)}`);
  const drawer = listed.data.rows.find((r) => r.name === DRAWER)!;
  await shown(page).locator(`[data-testid=cash-register-registers-row-${drawer.id}-toggle]`).first().click();
  await expect(row).toContainText(/No/);
});

test('CASH_REGISTER-F01: the employee reads the settings blocked', async ({ page }) => {
  await login(page, A, '/cash_register/settings', EMPLOYEE);
  await settingsReady(page);
  await expect(shown(page).locator('[data-testid=cash-register-settings-read-only]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=cash-register-settings-save]')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=cash-register-setting-require_blind_count]')).toBeDisabled();
});
