// flow: staff-business-currency (FIX-HUB-STAFF-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/staff/WORKBOOK.md «Personal»,
// «Comisiones», STAFF-F01, F02 and F21)
// Staff paints and reads money in the business's currency: its country's, as erplora.com registered it
// (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: a
// professional's «Rate/h» reads in złoty in the directory and in their record (the field ends in «zł»), and
// Commissions reads what was sold and earned in złoty, with no «€», in 390, 834 and 1440 (captures
// `FIX-HUB-STAFF-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`, `…-form-<width>` and `…-commissions-<width>`); a rate
// typed as «13,75» is saved as 1375 groszy. Back in Spain, the same screens read in euros (`…-es-1440`). What the run
// creates is deleted after it and `a`'s registration put back, also when a test fails.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, hostPage, login, psql, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { settled } from './service-helpers';

const KEY = 'FIX-HUB-STAFF-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const STAMP = `SCUR${Date.now().toString(36)}`;
/** 12,50 as a till in Poland writes it: «12,50 zł», «zł 12.50». */
const ZLOTY = /zł\s?12[.,]50|12[.,]50\s?zł/;
const ZLOTY_TYPED = /zł\s?13[.,]75|13[.,]75\s?zł/;
const ZERO_ZLOTY = /zł\s?0[.,]00|0[.,]00\s?zł/;
const EUROS = /€\s?12[.,]50|12[.,]50\s?€/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let ana: { id: string; full_name: string };

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanUp(): void {
  psql(`delete from staff_member where first_name like 'SCUR%'`);
}

const memberRow = (page: Page): Locator => shown(page).locator(`[data-testid=staff-members-row][data-id="${ana.id}"]`);
const commissionRow = (page: Page): Locator => shown(page).locator(`[data-testid=staff-commissions-row][data-id="${ana.id}"]`);
const form = (page: Page): Locator => page.locator('ion-modal[data-testid=staff-member-form]');

async function openMembers(page: Page): Promise<void> {
  await page.goto('/staff/members');
  await shown(page).locator('[data-testid=staff-members-search] input').fill(STAMP);
  await expect(memberRow(page)).toBeVisible();
}

async function openRecord(page: Page): Promise<Locator> {
  await memberRow(page).getByText(ana.full_name).first().click();
  await expect(form(page)).toBeVisible();
  const rate = form(page).locator('[data-testid=staff-member-form-hourly_rate] input');
  await expect(rate).not.toHaveValue('');
  return rate;
}

async function openCommissions(page: Page): Promise<void> {
  await page.goto('/staff/commissions');
  await shown(page).locator('[data-testid=staff-commissions-search] input').fill(STAMP);
  await expect(commissionRow(page)).toBeVisible();
}

const noHorizontalScroll = (page: Page, size: string) =>
  expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${size}` })
    .toBeLessThanOrEqual(0);

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  cleanUp();
  const owner = await hostPage(browser, A, { next: '/staff/members' });
  const created = await api<{ id: string; full_name: string }>(owner.context, A, 'POST', '/staff/members', {
    first_name: `${STAMP} Ana`,
    last_name: 'Nowak',
    hourly_rate: 1250,
    commission_rate: '10',
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  ana = created.data;
  await owner.context.close();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanUp();
});

test(`${KEY}: staff-business-currency a business in Poland reads the rate and the commissions in złoty in 390, 834 and 1440`, async ({
  page,
  context,
}) => {
  await registerBusinessIn(original, 'PL');
  await login(page, A, '/staff/members');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openMembers(page);
    await expect(memberRow(page), size.name).toContainText(ZLOTY);
    await expect(memberRow(page), size.name).not.toContainText('€');
    await settled(page);
    await noHorizontalScroll(page, size.name);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });

    // The record: the rate as the person types it, the field ending in «zł».
    const rate = await openRecord(page);
    await expect(rate).toHaveValue(/^12[.,]50$/);
    await expect(form(page).locator('[data-testid=staff-member-form-hourly_rate-currency]')).toHaveText('zł');
    await expect(form(page)).not.toContainText('€');
    await rate.scrollIntoViewIfNeeded();
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-form-${size.name}`) });
    await form(page).locator('[data-testid=staff-member-form-cancel]').click();
    await expect(form(page)).toBeHidden();

    // Commissions: what Ana sold and earned today, and the totals, in złoty.
    await openCommissions(page);
    await expect(commissionRow(page), size.name).toContainText(ZERO_ZLOTY);
    await expect(shown(page).locator('[data-testid=staff-commissions-total-sold]'), size.name).toContainText('zł');
    await expect(shown(page).locator('[data-testid=staff-commissions-total-commission]'), size.name).toContainText('zł');
    await expect(shown(page).locator('[data-testid=staff-commissions-total-sold]'), size.name).not.toContainText('€');
    await expect(commissionRow(page), size.name).not.toContainText('€');
    await settled(page);
    await noHorizontalScroll(page, size.name);
    await page.screenshot({ path: shot(`${KEY}-commissions-${size.name}`) });
  }

  // A rate typed in złoty is read in złoty: «13,75» is 1375 groszy.
  await page.setViewportSize({ width: 1440, height: 900 });
  await openMembers(page);
  const rate = await openRecord(page);
  await rate.fill('13,75');
  await form(page).locator('[data-testid=staff-member-form-submit]').click();
  await expect(form(page)).toBeHidden();
  await expect(memberRow(page)).toContainText(ZLOTY_TYPED);
  expect(psql(`select hourly_rate from staff_member where id = '${ana.id}'`)).toBe('1375');
  psql(`update staff_member set hourly_rate = 1250 where id = '${ana.id}'`);
});

test(`${KEY}: staff-business-currency back in Spain the rate and the commissions are in euros`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/staff/members');
  await openMembers(page);
  await expect(memberRow(page)).toContainText(EUROS);
  await expect(memberRow(page)).not.toContainText('zł');
  await settled(page);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
  await openRecord(page);
  await expect(form(page).locator('[data-testid=staff-member-form-hourly_rate-currency]')).toHaveText('€');
  await form(page).locator('[data-testid=staff-member-form-cancel]').click();
  await expect(form(page)).toBeHidden();
  await openCommissions(page);
  await expect(shown(page).locator('[data-testid=staff-commissions-total-sold]')).toContainText('€');
  await expect(commissionRow(page)).not.toContainText('zł');
});
