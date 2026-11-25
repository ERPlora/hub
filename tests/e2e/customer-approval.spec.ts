// What a manager holds in Customers, an employee does with a manager's PIN on the spot (BASE-F84; the old customers
// module's rule «what the manager has, another profile may do with a manager's approval (PIN)»): the employee asks to
// merge a duplicate card (CUSTOMER-F13), «An approval is needed» opens over the screen, the owner approves it with their
// PIN on the employee's own device and it is done once. Screenshots of the dialog over the card in the three viewports.
// The owner's PIN and the approvals go with the file (approval-helpers.ts), as everything else it creates (`afterAll`).
import { expect, test } from '@playwright/test';

import { approvalDialog, forgetThePinAndTheApprovals, ownerApproves, ownerChoosesPin, type Side } from './approval-helpers';
import {
  cardOf,
  cleanUp,
  createCard,
  e2eName,
  FLOW_VIEWPORTS,
  spanishMobile,
} from './customer-helpers';
import { A, capture, EMPLOYEE, login, shown, testid } from './helpers';
import { toastSaying } from './toast-helpers';

test.describe.configure({ mode: 'serial' });

let owner: Side;
let employee: Side;

test.beforeAll(async ({ browser }) => {
  // What a run that failed left: with the owner's PIN still set, the way in to hub `a` asks for a PIN.
  forgetThePinAndTheApprovals('customer');
  const context = await browser.newContext({ baseURL: A });
  owner = { context, page: await context.newPage() };
  await login(owner.page, A, '/customer/customers');
  // The employee enters while nobody of the business has a PIN: the way in is erplora.com's, as every spec's.
  const shop = await browser.newContext({ baseURL: A });
  employee = { context: shop, page: await shop.newPage() };
  await login(employee.page, A, '/customer/customers', EMPLOYEE);
  // Only now: a PIN of the business's turns the next way in into the PIN pad.
  await ownerChoosesPin(context);
});

test.afterAll(async () => {
  forgetThePinAndTheApprovals('customer');
  cleanUp();
  await employee?.context.close();
  await owner?.context.close();
});

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
    const dialog = approvalDialog(page);
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId('approval-action')).toHaveText(/^(Approving: Merge two customer cards|Se aprueba: Fusionar dos fichas de cliente)$/);
    // The PIN pad (or the faces to choose from) painted; `capture` waits for the sheet to stop moving.
    await expect(dialog.locator('[data-testid=pin-face], [data-testid=pinpad-key-1]').first()).toBeVisible();
    await capture(page, `CLOSE-CUSTOMER-${viewport.label}`);
    await ownerApproves(page);
    await expect(dialog).toBeHidden();
    await expect(toastSaying(page, duplicate.name)).toBeVisible();
    expect((await cardOf(owner.context, duplicate.id)).status).toBe(404);
    expect((await cardOf(owner.context, stays.id)).status).toBe(200);
  });
}

// flow: CUSTOMER-F27
test('CUSTOMER-F27: Groups is no screen of the employee: «No access» by its address, with no «Add»', async () => {
  const { page } = employee;
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${A}/customer/groups`);
  // Groups sets the business's customers up: not in an employee's menu (BASE-F118).
  await expect(testid(page, 'no-access')).toBeVisible();
  await expect(shown(page).locator('[data-testid=customer-groups-add]')).toHaveCount(0);
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
