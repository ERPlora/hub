// What a manager holds in Customers, an employee does with a manager's PIN on the spot (BASE-F84; the old customers
// module's rule «what the manager has, another profile may do with a manager's approval (PIN)»): the employee asks to
// merge a duplicate card (CUSTOMER-F13) or to create a group (CUSTOMER-F27), «An approval is needed» opens over the
// screen, the owner approves it with their PIN on the employee's own device and it is done once. Screenshots of the
// dialog over the card in the three viewports. The owner's PIN exists only while this file runs, after the employee
// has entered (a PIN in hub `a` turns every browser's way in into the PIN pad: base-access.spec.ts), and the
// approvals it records go with it, as everything else this file creates (`afterAll`).
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  cardOf,
  cleanUp,
  createCard,
  e2eName,
  FLOW_VIEWPORTS,
  inputOf,
  rowNamed,
  searchList,
  spanishMobile,
} from './customer-helpers';
import { A, api, EMPLOYEE, login, OWNER, psql, shot, shown } from './helpers';

const OWNER_PIN = '2468';

test.describe.configure({ mode: 'serial' });

let owner: { context: BrowserContext; page: Page };
let employee: { context: BrowserContext; page: Page };

/** Every account of `email` in this hub's database: the cleanup leaves none of them with what this file made. */
const accountsOf = (email: string): string => `SELECT username FROM auth_user WHERE email = '${email}'`;

/** No PIN of the owner's left behind, in any of their accounts, and no approval of a Customers action. */
function forgetThePinAndTheApprovals(): void {
  psql(`UPDATE base_credential SET pin_hash = '', pin_set_at = NULL WHERE username IN (${accountsOf(OWNER.email)})`);
  psql(`DELETE FROM base_approval WHERE requested_by IN (${accountsOf(EMPLOYEE.email)}) AND operation LIKE 'customer.%'`);
}

test.beforeAll(async ({ browser }) => {
  // What a run that failed left: with the owner's PIN still set, the way in to hub `a` asks for a PIN.
  forgetThePinAndTheApprovals();
  const context = await browser.newContext({ baseURL: A });
  owner = { context, page: await context.newPage() };
  await login(owner.page, A, '/customer/customers');
  // The employee enters while nobody of the business has a PIN: the way in is erplora.com's, as every spec's.
  const shop = await browser.newContext({ baseURL: A });
  employee = { context: shop, page: await shop.newPage() };
  await login(employee.page, A, '/customer/customers', EMPLOYEE);
  // Only now the owner chooses a PIN («My profile»): who may approve, on the employee's device.
  const pin = await api<{ set: boolean }>(context, A, 'POST', '/me/pin', { pin: OWNER_PIN });
  expect(pin.status, JSON.stringify(pin.data)).toBe(200);
});

test.afterAll(async () => {
  forgetThePinAndTheApprovals();
  cleanUp();
  await employee?.context.close();
  await owner?.context.close();
});

/** «An approval is needed», over the screen that asked. */
const approval = (page: Page) => page.locator('ion-modal').filter({ has: page.getByTestId('approval-action') });

/** The owner approves on the employee's device: their face (when there is a choice) and their PIN. */
async function ownerApproves(page: Page): Promise<void> {
  const dialog = approval(page);
  const faces = dialog.getByTestId('pin-face');
  if (await faces.count()) await faces.first().click();
  for (const digit of OWNER_PIN) await dialog.getByTestId(`pinpad-key-${digit}`).click();
}

for (const viewport of FLOW_VIEWPORTS) {
  // flow: CUSTOMER-F13
  test(`CUSTOMER-F13 at ${viewport.label}: the employee merges a duplicate and the owner approves it with their PIN`, async () => {
    const { page } = employee;
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const stays = await createCard(owner.context, { name: e2eName('F13 Marta'), phone: spanishMobile() });
    const duplicate = await createCard(owner.context, { name: e2eName('F13 Marta R.'), phone: spanishMobile() });
    await page.goto(`${A}/customer/customers/${stays.id}`);
    await shown(page).locator('[data-testid=customer-detail-merge]').click();
    const panel = shown(page).locator('[data-testid=customer-merge]');
    await panel.locator('[data-testid=customer-picker-search] input').fill(duplicate.name);
    await panel.locator(`[data-testid=customer-picker-result-${duplicate.id}]`).click();
    await panel.locator('[data-testid=customer-merge-submit]').click();
    const dialog = approval(page);
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId('approval-action')).toHaveText(/^(Approving: Merge two customer cards|Se aprueba: Fusionar dos fichas de cliente)$/);
    // The PIN pad (or the faces to choose from) painted, the sheet's animation over: then the picture.
    await expect(dialog.locator('[data-testid=pin-face], [data-testid=pinpad-key-1]').first()).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`CLOSE-CUSTOMER-${viewport.label}`) });
    await ownerApproves(page);
    await expect(dialog).toBeHidden();
    await expect(page.locator('ion-toast').last()).toContainText(duplicate.name);
    expect((await cardOf(owner.context, duplicate.id)).status).toBe(404);
    expect((await cardOf(owner.context, stays.id)).status).toBe(200);
  });
}

// flow: CUSTOMER-F27
test('CUSTOMER-F27: the employee creates a group and the owner approves it with their PIN', async () => {
  const { page } = employee;
  await page.setViewportSize({ width: 1440, height: 900 });
  const name = e2eName('F27 Approved group');
  await page.goto(`${A}/customer/groups`);
  await shown(page).locator('[data-testid=customer-groups-add]').click();
  const form = page.locator('ion-modal[data-testid=customer-group-form]');
  await inputOf(form, 'customer-group-form-name').fill(name);
  await form.locator('[data-testid=customer-group-form-submit]').click();
  const dialog = approval(page);
  await expect(dialog.getByTestId('approval-action')).toHaveText(/^(Approving: Create a customer group|Se aprueba: Crear un grupo de clientes)$/);
  await ownerApproves(page);
  await expect(form).toBeHidden();
  await searchList(page, 'customer-groups', name);
  await expect(rowNamed(page, 'customer-groups', name)).toBeVisible();
});

// flow: CUSTOMER-F16
test('what only an administrator does is never offered to the employee: no «Erase personal data», no «Delete»', async () => {
  const { page } = employee;
  const card = await createCard(owner.context, { name: e2eName('F16 Not offered') });
  await page.goto(`${A}/customer/customers/${card.id}`);
  await expect(shown(page).locator('[data-testid=customer-detail-merge]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=customer-detail-erase]')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=customer-detail-delete]')).toHaveCount(0);
});
