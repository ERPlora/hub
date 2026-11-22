// flow: BASE-F05 (base/WORKBOOK.md)
// «My apps» lists the apps a person's role opens and no other. In `a`, with Sales & POS, Cash register, Taxes,
// Schedules and Payments on, the employee has Sales & POS and Cash register, and not the three that set the business
// up (the till still reads the taxes); the owner has all five. The topbar's sheet at the three sizes, captured.
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import {
  A,
  capture,
  type Credentials,
  EMPLOYEE,
  hostPage,
  OWNER,
  THREE_SIZES,
  turnOffTurnedOn,
  turnOnMissing,
  untilStill,
} from './helpers';
import { openApps } from './topbar';

const FLOOR = ['Sales & POS', 'Cash register'];
const SETUP = ['Taxes', 'Schedules', 'Payments'];
const turnedOn: string[] = [];

test.describe.configure({ mode: 'serial' });

async function ownerContext(browser: Browser) {
  return (await hostPage(browser, A, { next: '/' })).context;
}

test.beforeAll(async ({ browser }) => {
  const context = await ownerContext(browser);
  await turnOnMissing(context, A, ['tax', 'customer', 'sale', 'cash_register', 'schedule', 'payment'], turnedOn);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const context = await ownerContext(browser);
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

/** The topbar's «My apps» sheet, open, and the names of its apps. */
async function myApps(page: Page): Promise<{ sheet: Locator; names: string[] }> {
  const sheet = await openApps(page);
  await untilStill(page);
  const names = await sheet
    .locator('[data-testid=apps-launcher-app]')
    .evaluateAll((buttons) => buttons.map((button) => button.getAttribute('title') ?? ''));
  return { sheet, names };
}

async function closeMyApps(sheet: Locator): Promise<void> {
  await sheet.locator('[data-testid=apps-launcher-close]').click();
  await expect(sheet).toBeHidden();
}

async function signedIn(browser: Browser, credentials: Credentials) {
  return hostPage(browser, A, { next: '/', credentials });
}

test('an employee has in «My apps» the apps of the floor and none of those that set the business up', async ({ browser }) => {
  const { context, page } = await signedIn(browser, EMPLOYEE);
  // The employee's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const { label, width, height } of THREE_SIZES) {
    await page.setViewportSize({ width, height });
    const { sheet, names } = await myApps(page);
    expect(names).toEqual(expect.arrayContaining(FLOOR));
    for (const name of SETUP) expect(names, `${name} at ${label}`).not.toContain(name);
    await capture(page, `BASE-F05-my-apps-employee-${label}`, { fullPage: true });
    await closeMyApps(sheet);
  }
  await context.close();
});

test('the owner has every app on in «My apps»', async ({ browser }) => {
  const { context, page } = await signedIn(browser, OWNER);
  const { names } = await myApps(page);
  expect(names).toEqual(expect.arrayContaining([...FLOOR, ...SETUP]));
  await context.close();
});
