// flow: MODIFIER-F04 (FIX-HUB-MODIFIER-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/modifier/WORKBOOK.md «Hoja del grupo»)
// Modifiers paints and reads a supplement in the business's currency: its country's, as erplora.com registered it
// (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: the
// group's sheet reads the supplement of an option of the run in złoty and no «€», in 390, 834 and 1440 (captures
// `FIX-HUB-MODIFIER-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`); «Add option» names the field «Supplement (PLN)»
// and «2,50» is saved as 250 minor units of złoty (read back through the API). Back in Spain the same supplement
// reads in euros and the field says EUR (`…-es-1440`). What the run creates is deleted after it and `a`'s
// registration put back, also when a test fails.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, hostPage, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { settled } from './service-helpers';

const KEY = 'FIX-HUB-MODIFIER-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const STAMP = Date.now().toString(36).toUpperCase();
const GROUP = `E2E MCUR Extras ${STAMP}`;
/** +1,50 as a till in Poland writes a supplement: «+1,50 zł», «+zł 1.50». */
const ZLOTY = /\+\s?zł\s?1[.,]50|\+1[.,]50\s?zł/;
const EUROS = /\+\s?€\s?1[.,]50|\+1[.,]50\s?€/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let groupId = '';

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanUp(): void {
  const groups = "select id from modifier_modifiergroup where name like 'E2E MCUR %'";
  psql(
    [
      `delete from modifier_modifierlink where group_id in (${groups})`,
      `delete from modifier_modifieroption where group_id in (${groups})`,
      "delete from modifier_modifiergroup where name like 'E2E MCUR %'",
    ].join('; '),
  );
}

const dialog = (page: Page, testid: string): Locator => page.locator(`ion-modal[data-testid=${testid}]`);
const sheet = (page: Page): Locator => dialog(page, 'modifier-sheet');
const cheese = (page: Page): Locator => sheet(page).locator('[data-testid^=modifier-sheet-options-row-]').filter({ hasText: 'Cheese' });

/** The run's group sheet, opened from Modifiers → its row (found by the run's stamp). */
async function openSheet(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/modifier/groups');
  await shown(page).locator('[data-testid=modifier-groups-row], [data-testid=modifier-groups-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=modifier-groups-search] input').fill(STAMP);
  await shown(page).locator(`[data-testid=modifier-groups-row][data-id="${groupId}"]`).locator('[role=cell]').first().click();
  await expect(sheet(page)).toBeVisible();
  await expect(cheese(page)).toBeVisible();
}

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  const owner = await hostPage(browser, A, { next: '/modifier/groups' });
  const group = await api<{ id: string }>(owner.context, A, 'POST', '/modifier/groups', { name: GROUP, max_choices: 3 });
  expect(group.status).toBe(201);
  groupId = group.data.id;
  const option = await api(owner.context, A, 'POST', '/modifier/options', { group_id: groupId, name: 'Cheese', price_delta: 150 });
  expect(option.status).toBe(201);
  await owner.context.close();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

test(`${KEY}: MODIFIER-F04 a business in Poland reads and types the supplements of a group in złoty in 390, 834 and 1440`, async ({
  page,
  context,
}) => {
  await registerBusinessIn(original, 'PL');
  await openSheet(page);
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(cheese(page), size.name).toContainText(ZLOTY);
    await expect(sheet(page).locator('[data-testid^=modifier-sheet-options-row-]').first(), size.name).not.toContainText('€');
    await settled(page);
    await expect
      .poll(() => horizontalOverflow(page), { message: `no horizontal scroll at ${size.name}` })
      .toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
  }

  // «Add option»: the field names the business's currency, and what is typed is złoty with its two decimals.
  await page.setViewportSize({ width: 1440, height: 900 });
  await sheet(page).locator('[data-testid=modifier-sheet-options-add]').click();
  const form = dialog(page, 'modifier-option-form');
  await expect(form).toBeVisible();
  const price = form.locator('[data-testid=modifier-option-form-price_delta]');
  await expect(price).toContainText('Supplement (PLN)');
  await expect(price).not.toContainText('€');
  await form.locator('[data-testid=modifier-option-form-name] input').fill('Bacon');
  const input = price.locator('input').first();
  await input.fill('2,50');
  await input.blur();
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-form-1440`) });
  await form.locator('[data-testid=modifier-option-form-submit]').click();
  await expect(form).toBeHidden();
  const options = await api<{ rows: { name: string; price_delta: number }[] }>(context, A, 'GET', `/modifier/options?group_id=${groupId}`);
  expect(options.status).toBe(200);
  expect(options.data.rows.map((row) => [row.name, row.price_delta]).sort()).toEqual([
    ['Bacon', 250],
    ['Cheese', 150],
  ]);
  await expect(sheet(page).locator('[data-testid^=modifier-sheet-options-row-]').filter({ hasText: 'Bacon' })).toContainText(
    /\+\s?zł\s?2[.,]50|\+2[.,]50\s?zł/,
  );
});

test(`${KEY}: MODIFIER-F04 back in Spain the supplements of a group are in euros`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await openSheet(page);
  await expect(cheese(page)).toContainText(EUROS);
  await expect(cheese(page)).not.toContainText('zł');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
  await sheet(page).locator('[data-testid=modifier-sheet-options-add]').click();
  const form = dialog(page, 'modifier-option-form');
  await expect(form).toBeVisible();
  await expect(form.locator('[data-testid=modifier-option-form-price_delta]')).toContainText('Supplement (EUR)');
});
