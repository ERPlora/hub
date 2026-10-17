// Sales & POS back office in Chrome (SALE-F34, F35, F36; apps/sale/WORKBOOK.md): the owner of hub `a`
// adds, edits and deletes a quick note and a department (its VAT chosen with the server-search picker,
// its rate painted from the server), and saves the till settings; an employee sees the same lists with
// no «+» nor row actions and the settings refused. Screenshots of each page in the three viewports.
// What this file creates is deleted after it (`afterAll`), and the settings it touched are restored.
import { expect, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, api, hostPage, login, psql, shot, shown } from './helpers';

const CLEANUP = ["delete from sale_quicknote where text like 'e2e %'", "delete from sale_department where name like 'e2e %'"].join('; ');

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

let headerBefore: string | null = null;

test.afterAll(() => {
  psql(CLEANUP);
  if (headerBefore !== null) {
    const quoted = headerBefore.replace(/'/g, "''");
    psql(`update sale_settings set receipt_header = '${quoted}'`);
  }
});

/** Types into an Ionic input the way a person does. */
async function type(page: Page, testid: string, text: string): Promise<void> {
  const input = page.locator(`[data-testid=${testid}] input`);
  await input.fill(text);
}

async function listReady(page: Page, testid: string): Promise<void> {
  await shown(page).locator(`[data-testid=${testid}-row], [data-testid=${testid}-empty]`).first().waitFor({ state: 'visible' });
}

async function shots(page: Page, name: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await page.screenshot({ path: shot(`${name}-${viewport.label}`) });
  }
}

test('SALE-F36: the owner prepares a quick note, changes it and deletes it', async ({ page }) => {
  await login(page, A, '/sale/quick-notes');
  await listReady(page, 'sale-quick-notes');
  await expect(shown(page).locator('[data-testid=sale-quick-notes-intro]')).toBeVisible();

  await shown(page).locator('[data-testid=sale-quick-notes-add]').click();
  const form = page.locator('ion-modal[data-testid=sale-quick-note-form]');
  await expect(form).toBeVisible();
  await type(page, 'sale-quick-note-form-text', 'e2e no salt');
  await type(page, 'sale-quick-note-form-order', '5');
  await form.locator('[data-testid=sale-quick-note-form-submit]').click();
  await expect(form).toBeHidden();
  const row = shown(page).locator('[data-testid=sale-quick-notes-row]').filter({ hasText: 'e2e no salt' });
  await expect(row).toBeVisible();

  const id = await row.getAttribute('data-id');
  await shown(page).locator(`[data-testid=sale-quick-notes-row-${id}-edit]`).first().click();
  await expect(form).toBeVisible();
  await type(page, 'sale-quick-note-form-text', 'e2e very rare');
  await form.locator('[data-testid=sale-quick-note-form-submit]').click();
  await expect(shown(page).locator('[data-testid=sale-quick-notes-row]').filter({ hasText: 'e2e very rare' })).toBeVisible();
  await shots(page, 'sale-quick-notes', (p) => listReady(p, 'sale-quick-notes'));
  await page.setViewportSize({ width: 1280, height: 860 });

  await shown(page).locator(`[data-testid=sale-quick-notes-row-${id}-delete]`).first().click();
  const confirm = page.locator('ion-modal').filter({ hasText: /Delete quick note|Eliminar nota rápida/ }).last();
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(confirm).toBeHidden();
  await expect(shown(page).locator(`[data-testid=sale-quick-notes-row][data-id="${id}"]`)).toHaveCount(0);
});

test('SALE-F35: the owner adds a department at a VAT found on the server and sees its rate', async ({ page }) => {
  await login(page, A, '/sale/departments');
  await listReady(page, 'sale-departments');

  await shown(page).locator('[data-testid=sale-departments-add]').click();
  const form = page.locator('ion-modal[data-testid=sale-department-form]');
  await expect(form).toBeVisible();
  await type(page, 'sale-department-form-name', 'e2e Fruit');
  await form.locator('[data-testid=sale-department-form-tax]').click();
  const picker = page.locator('[data-testid=sale-department-form-tax-modal]');
  await expect(picker).toBeVisible();
  await picker.locator('[data-testid=sale-department-form-tax-search] input').fill('super');
  await picker.locator('[data-testid=sale-department-form-tax-option][data-value="product.super_reduced"]').click();
  await form.locator('[data-testid=sale-department-form-submit]').click();
  await expect(form).toBeHidden();
  const row = shown(page).locator('[data-testid=sale-departments-row]').filter({ hasText: 'e2e Fruit' });
  await expect(row).toBeVisible();
  // The rate comes from the server (tax's rule in force today for Spain): 4 %.
  await expect(row).toContainText(/4\s?%/);
  await shots(page, 'sale-departments', (p) => listReady(p, 'sale-departments'));
});

test('SALE-F34: the owner saves the till settings', async ({ page, context }) => {
  await login(page, A, '/sale/settings');
  const before = await api<{ receipt_header: string }>(context, A, 'GET', '/sale/settings');
  headerBefore = before.data?.receipt_header ?? '';
  const form = shown(page).locator('[data-testid=sale-settings-form]');
  await expect(form).toBeVisible();
  await expect(shown(page).locator('[data-testid=sale-settings-heading]')).toBeVisible();
  const header = form.locator('ion-textarea textarea').first();
  await header.fill('e2e Bar Manolo\nC/ Mayor 1');
  await shown(page).locator('[data-testid=sale-settings-save]').click();
  await expect.poll(async () => (await api<{ receipt_header: string }>(context, A, 'GET', '/sale/settings')).data.receipt_header).toBe(
    'e2e Bar Manolo\nC/ Mayor 1',
  );
  await shots(page, 'sale-settings', async (p) => {
    await shown(p).locator('[data-testid=sale-settings-form]').waitFor();
  });
});

test('the employee reads the quick notes and departments without managing them, and no settings', async ({ browser }) => {
  psql(
    "insert into sale_quicknote (id, text, sort_order, is_deleted, created_at, updated_at, created_by) values (gen_random_uuid(), 'e2e read only', 1, false, now(), now(), 'e2e')",
  );
  const { context, page } = await hostPage(browser, A, { next: '/sale/quick-notes', credentials: EMPLOYEE });
  try {
    await listReady(page, 'sale-quick-notes');
    await expect(shown(page).locator('[data-testid=sale-quick-notes-row]').filter({ hasText: 'e2e read only' })).toBeVisible();
    await expect(shown(page).locator('[data-testid=sale-quick-notes-add]')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid^=sale-quick-notes-row-][data-testid$=-edit]')).toHaveCount(0);
    await page.screenshot({ path: shot('sale-quick-notes-employee') });

    await page.goto(`${A}/sale/departments`);
    await listReady(page, 'sale-departments');
    await expect(shown(page).locator('[data-testid=sale-departments-add]')).toHaveCount(0);

    await page.goto(`${A}/sale/settings`);
    // The business's values, blocked, with the old «You do not have permission to change these settings…».
    const readOnly = shown(page).locator('[data-testid=sale-settings-read-only]');
    await readOnly.scrollIntoViewIfNeeded();
    await expect(readOnly).toBeVisible();
    await expect(readOnly).toContainText(/permission|permiso/);
    await expect(shown(page).locator('[data-testid=sale-settings-save]')).toHaveCount(0);
    await page.screenshot({ path: shot('sale-settings-employee') });
  } finally {
    await context.close();
  }
});
