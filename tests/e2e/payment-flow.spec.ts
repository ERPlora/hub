// Every flow of Payments with a screen, one test each (its key in the title and in `// flow:`), done end to end
// on the real stack, hidden, and seen at 390×844, 834×1112 and 1440×900: `threeShots` resizes, brings what the
// flow shows into sight, checks nothing scrolls sideways and saves `.artifacts/APP-PAYMENT-<key>-<width>.png`.
// PAYMENT-F07 (a completed payment starts the automations) has no screen of its own: its evidence is
// apps/payment/tests/test_relay.py, through the worker's real relay. The deeper cases of each flow live in the
// app's pytest and Vitest suites. Everything created here is named «E2E Pay …» and removed before and after.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, horizontalOverflow, login, psql, shot, shown } from './helpers';

const TAG = 'E2E Pay';
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

const stamp = (): string => Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${stamp()}`;

/** Deletes what the spec created; the counter of a day goes too when no payment of that day is left. */
function cleanUp(): void {
  const methods = `select id from payment_paymentmethod where name like '${TAG}%'`;
  psql(
    [
      `delete from payment_payment where method_id in (${methods}) or beneficiary_name like '${TAG}%'`,
      `delete from payment_paymentmethod where name like '${TAG}%'`,
      `delete from payment_paymentcounter c where not exists (select 1 from payment_payment p where p.reference like 'PAY-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

async function signedIn(browser: Browser, next: string, employee = false): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, employee ? EMPLOYEE : undefined);
  return { context, page };
}

/** At each of the three sizes: `target` in sight, no sideways scroll, and the screenshot. */
async function threeShots(page: Page, key: string, target: () => Locator): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const seen = target();
    // A list turns its rows into cards on a phone: what was there is painted again, so it retries.
    await expect(async () => {
      await seen.scrollIntoViewIfNeeded({ timeout: 2000 });
      await expect(seen).toBeInViewport({ timeout: 1000 });
    }, `${key} at ${vp.label}`).toPass();
    await expect.poll(() => horizontalOverflow(page), `${key} at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`APP-PAYMENT-${key}-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** A row (or, on a phone, a card) of a payment list by its id. */
const rowOf = (page: Page, table: string, id: string): Locator =>
  shown(page).locator(`[data-testid=${table}-row][data-id="${id}"]`).first();

/** Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. */
async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  await expect(rowOf(page, table, id)).toBeVisible();
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`).first();
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await shown(page).locator(`[data-testid=${table}-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

/** Picks `text` in the ion-select `testid` (a popover). */
async function choose(page: Page, testid: string, text: string): Promise<void> {
  await page.locator(`[data-testid=${testid}]`).click();
  const option = page.locator('ion-popover').getByText(text, { exact: true });
  await option.click();
  await expect(option).toBeHidden();
}

async function waitForList(page: Page, table: string): Promise<void> {
  await shown(page).locator(`[data-testid=${table}-empty], [data-testid=${table}-row]`).first().waitFor({ state: 'visible' });
}

/** Sets the Date filter of Payments: in the filters panel behind the funnel (the list is `filterable`), or in the
 *  filter row of a list that opens it. */
async function filterDates(page: Page, from: string, to: string): Promise<void> {
  const view = shown(page);
  const toggle = view.locator('[data-testid=payment-payments-filters-toggle]');
  const panel = view.locator('[data-testid=payment-payments-filters-panel]');
  const folded = await toggle.isVisible();
  if (folded) {
    await toggle.click();
    await expect(panel).toBeVisible();
  }
  const scope = folded ? panel : view;
  await scope.locator('[data-testid=payment-payments-filter-payment_date_from] input').fill(from);
  await scope.locator('[data-testid=payment-payments-filter-payment_date_to] input').fill(to);
  if (folded) {
    await panel.locator('[data-testid=payment-payments-filters-apply]').click();
    await expect(panel).toBeHidden();
  }
}

interface Method {
  id: string;
  name: string;
}

interface Payment {
  id: string;
  reference: string;
  status: string;
  method_name: string;
}

async function method(context: BrowserContext, label = 'Bank', account = ''): Promise<Method> {
  const res = await api<Method>(context, A, 'POST', '/payment/methods', { name: named(label), bank_account_ref: account });
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data;
}

async function payment(context: BrowserContext, methodId: string, body: Record<string, unknown> = {}): Promise<Payment> {
  const res = await api<Payment>(context, A, 'POST', '/payment/payments', {
    method_id: methodId,
    payment_date: '2026-10-14',
    amount: 4000,
    beneficiary_name: named('Proveedor'),
    ...body,
  });
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data;
}

async function step(context: BrowserContext, id: string, ...steps: Array<'approve' | 'mark_sent' | 'mark_completed'>): Promise<void> {
  for (const name of steps) {
    const res = await api(context, A, 'POST', `/payment/payments/${name}`, { id });
    expect(res.status, JSON.stringify(res.data)).toBe(200);
  }
}

// flow: PAYMENT-F01 · gh:payments#6 — methods are created from the screen; a twin name is refused under Name
test('PAYMENT-F01: «New method» creates an Active method that «New payment» offers; a twin name is refused under Name', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/payment/methods');
  try {
    const bank = named('Bank');
    await waitForList(page, 'payment-methods');
    await shown(page).locator('[data-testid=payment-methods-add]').click();
    const form = page.locator('ion-modal[data-testid=payment-method-form]');
    await expect(form.locator('ion-title')).toHaveText('New method');
    await page.locator('[data-testid=payment-method-form-name] input').fill(bank);
    await page.locator('[data-testid=payment-method-form-account] input').fill('ES9121000418450200051332');
    await page.locator('[data-testid=payment-method-form-submit]').click();
    await expect(form).toBeHidden();
    const id = psql(`select id from payment_paymentmethod where name = '${bank}'`);
    const row = rowOf(page, 'payment-methods', id);
    await expect(row).toContainText('Bank transfer');
    await expect(row).toContainText('Active');
    // The list masks the account: the country and its last four.
    await expect(row).toContainText('ES** **** **** **** **** 1332');

    // The same name in another case is refused under Name, and what was typed stays.
    await shown(page).locator('[data-testid=payment-methods-add]').click();
    await page.locator('[data-testid=payment-method-form-name] input').fill(bank.toUpperCase());
    await page.locator('[data-testid=payment-method-form-submit]').click();
    const name = page.locator('[data-testid=payment-method-form-name]');
    await expect(name).toHaveClass(/ion-invalid/);
    await expect(name).toContainText('There is already a payment method with that name. Pick another name.');
    await expect(page.locator('[data-testid=payment-method-form-name] input')).toHaveValue(bank.toUpperCase());
    await threeShots(page, 'PAYMENT-F01', () => name);
    await page.locator('[data-testid=payment-method-form-cancel]').click();
    expect(psql(`select count(*) from payment_paymentmethod where lower(name) = lower('${bank}')`)).toBe('1');

    // From now on «New payment» offers it.
    await page.goto(`${A}/payment/payments`);
    await waitForList(page, 'payment-payments');
    await shown(page).locator('[data-testid=payment-payments-add]').click();
    await page.locator('[data-testid=payment-form-method]').click();
    await expect(page.locator('ion-popover').getByText(bank, { exact: true })).toBeVisible();
  } finally {
    await context.close();
  }
});

// flow: PAYMENT-F02 · gh:payments#8, gh:pm#513, gh:pm#521 — the amount as typed, refusals under their field, one payment per attempt
test('PAYMENT-F02: «New payment» records a Draft with its reference; a bad IBAN is refused under its field; the same attempt records one payment', async ({
  browser,
}) => {
  const { context, page } = await signedIn(browser, '/payment/payments');
  try {
    const bank = await method(context);
    const supplier = named('Proveedor');
    await waitForList(page, 'payment-payments');
    await shown(page).locator('[data-testid=payment-payments-add]').click();
    const form = page.locator('ion-modal[data-testid=payment-form]');
    await expect(page.locator('[data-testid=payment-form-date] input')).not.toHaveValue('');
    await choose(page, 'payment-form-method', bank.name);
    await page.locator('[data-testid=payment-form-amount] input').fill('1,250.50');
    await page.locator('[data-testid=payment-form-beneficiary] input').fill(supplier);
    await page.locator('[data-testid=payment-form-concept] input').fill('Tintes de octubre');
    await page.locator('[data-testid=payment-form-iban] input').fill('ES00 1234');
    await page.locator('[data-testid=payment-form-submit]').click();
    const iban = page.locator('[data-testid=payment-form-iban]');
    await expect(iban).toHaveClass(/ion-invalid/);
    await expect(iban).toContainText('That IBAN is not valid: check the country, the check digits and the length.');
    await expect(page.locator('[data-testid=payment-form-beneficiary] input')).toHaveValue(supplier);
    await threeShots(page, 'PAYMENT-F02', () => iban);
    expect(psql(`select count(*) from payment_payment where beneficiary_name = '${supplier}'`)).toBe('0');

    await page.locator('[data-testid=payment-form-iban] input').fill('ES91 2100 0418 4502 0005 1332');
    await page.locator('[data-testid=payment-form-submit]').click();
    await expect(form).toBeHidden();
    await expect.poll(() => psql(`select count(*) from payment_payment where beneficiary_name = '${supplier}'`)).toBe('1');
    const id = psql(`select id from payment_payment where beneficiary_name = '${supplier}'`);
    const reference = psql(`select reference from payment_payment where id = '${id}'`);
    expect(reference).toMatch(/^PAY-\d{8}-\d{4,}$/);
    const row = rowOf(page, 'payment-payments', id);
    await expect(row).toContainText(reference);
    await expect(row).toContainText('€1,250.50');
    await expect(row).toContainText('Draft');

    // The same attempt sent twice (a retry after a lost answer) records one payment and answers it again.
    const key = crypto.randomUUID();
    const body = { method_id: bank.id, payment_date: '2026-10-14', amount: 990, beneficiary_name: named('Retry'), idempotency_key: key };
    const first = await api<Payment>(context, A, 'POST', '/payment/payments', body);
    const again = await api<Payment>(context, A, 'POST', '/payment/payments', body);
    expect([first.status, again.status]).toEqual([201, 201]);
    expect(again.data.id).toBe(first.data.id);
    expect(psql(`select count(*) from payment_payment where idempotency_key = '${key}'`)).toBe('1');
    const reused = await api<{ error: { code: string } }>(context, A, 'POST', '/payment/payments', { ...body, amount: 991 });
    expect([reused.status, reused.data.error.code]).toEqual([409, 'payment.idempotency_key_reused']);
  } finally {
    await context.close();
  }
});

// flow: PAYMENT-F03 — «Approve» on a draft; who approved shows under the status; a second approval is refused
test('PAYMENT-F03: «Approve» turns a Draft Approved and says who approved it', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/payment/payments');
  try {
    const bank = await method(context);
    const draft = await payment(context, bank.id);
    await waitForList(page, 'payment-payments');
    const row = rowOf(page, 'payment-payments', draft.id);
    await expect(shown(page).locator(`[data-testid=payment-payments-row-${draft.id}-advance]`).first()).toContainText('Approve');
    await rowAction(page, 'payment-payments', draft.id, 'advance');
    await expect(row).toContainText('Approved');
    await expect(row).toContainText('Approved by');
    await threeShots(page, 'PAYMENT-F03', () => rowOf(page, 'payment-payments', draft.id));
    expect(psql(`select status from payment_payment where id = '${draft.id}'`)).toBe('approved');
    const again = await api<{ error: { code: string } }>(context, A, 'POST', '/payment/payments/approve', { id: draft.id });
    expect([again.status, again.data.error.code]).toEqual([409, 'payment.invalid_transition']);
  } finally {
    await context.close();
  }
});

// flow: PAYMENT-F04 — «Mark as sent», then «Mark as completed»; a completed payment offers nothing more
test('PAYMENT-F04: «Mark as sent» and «Mark as completed» take an Approved payment to Completed, with no action left', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/payment/payments');
  try {
    const bank = await method(context);
    const approved = await payment(context, bank.id);
    await step(context, approved.id, 'approve');
    const draft = await payment(context, bank.id);
    await waitForList(page, 'payment-payments');
    const row = rowOf(page, 'payment-payments', approved.id);
    for (const [label, status] of [
      ['Mark as sent', 'Sent'],
      ['Mark as completed', 'Completed'],
    ] as const) {
      await expect(shown(page).locator(`[data-testid=payment-payments-row-${approved.id}-advance]`).first()).toContainText(label);
      await rowAction(page, 'payment-payments', approved.id, 'advance');
      await expect(row).toContainText(status);
    }
    await expect(shown(page).locator(`[data-testid=payment-payments-row-${approved.id}-advance]:visible`)).toHaveCount(0);
    await expect(shown(page).locator(`[data-testid=payment-payments-row-${approved.id}-cancel]:visible`)).toHaveCount(0);
    await threeShots(page, 'PAYMENT-F04', () => rowOf(page, 'payment-payments', approved.id));
    expect(psql(`select status from payment_payment where id = '${approved.id}'`)).toBe('completed');
    // Skipping a step changes nothing and says why.
    const skipped = await api<{ error: { code: string } }>(context, A, 'POST', '/payment/payments/mark_completed', { id: draft.id });
    expect([skipped.status, skipped.data.error.code]).toEqual([409, 'payment.invalid_transition']);
    expect(psql(`select status from payment_payment where id = '${draft.id}'`)).toBe('draft');
  } finally {
    await context.close();
  }
});

// flow: PAYMENT-F05 — «Cancel payment» asks the reason; without one it cannot be pressed; the row shows it
test('PAYMENT-F05: «Cancel payment» asks the reason and the row shows it under Cancelled', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/payment/payments');
  try {
    const bank = await method(context);
    const draft = await payment(context, bank.id);
    await waitForList(page, 'payment-payments');
    await rowAction(page, 'payment-payments', draft.id, 'cancel');
    const form = page.locator('ion-modal[data-testid=payment-cancel]');
    await expect(form.locator('ion-title')).toHaveText(`Cancel payment — ${draft.reference}`);
    await expect(page.locator('[data-testid=payment-cancel-submit]')).toHaveAttribute('aria-disabled', 'true');
    await page.locator('[data-testid=payment-cancel-reason] textarea').fill('   ');
    await expect(page.locator('[data-testid=payment-cancel-submit]')).toHaveAttribute('aria-disabled', 'true');
    await page.locator('[data-testid=payment-cancel-reason] textarea').fill('Duplicated');
    await page.locator('[data-testid=payment-cancel-submit]').click();
    await expect(form).toBeHidden();
    const row = rowOf(page, 'payment-payments', draft.id);
    await expect(row).toContainText('Cancelled');
    await expect(row).toContainText('Reason: Duplicated');
    await threeShots(page, 'PAYMENT-F05', () => rowOf(page, 'payment-payments', draft.id));
    expect(psql(`select cancel_reason from payment_payment where id = '${draft.id}'`)).toBe('Duplicated');
    const again = await api<{ error: { code: string } }>(context, A, 'POST', '/payment/payments/cancel', { id: draft.id, reason: 'again' });
    expect([again.status, again.data.error.code]).toEqual([409, 'payment.not_cancellable']);
  } finally {
    await context.close();
  }
});

// flow: PAYMENT-F06 · gh:payments#21, gh:payments#29 — a piece of the reference finds it; the date filters from / to
test('PAYMENT-F06: the search finds a payment by a piece of its reference and the Date filters from one day to another', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/payment/payments');
  try {
    const bank = await method(context);
    const august = await payment(context, bank.id, { payment_date: '2026-08-21', beneficiary_name: named('Agosto') });
    const september = await payment(context, bank.id, { payment_date: '2026-09-15', beneficiary_name: named('Septiembre') });
    await waitForList(page, 'payment-payments');
    const view = shown(page);

    // A piece of the reference (its last digits) finds it, and only it.
    await view.locator('[data-testid=payment-payments-search] input').fill(september.reference.slice(-4));
    await expect(rowOf(page, 'payment-payments', september.id)).toBeVisible();
    await expect(view.locator(`[data-testid=payment-payments-row][data-id="${august.id}"]`)).toHaveCount(0);
    await view.locator('[data-testid=payment-payments-search] input').fill('');

    // The Date from the 1st to the 31st of August keeps August's payment only.
    await filterDates(page, '2026-08-01', '2026-08-31');
    await expect(rowOf(page, 'payment-payments', august.id)).toBeVisible();
    await expect(view.locator(`[data-testid=payment-payments-row][data-id="${september.id}"]`)).toHaveCount(0);
    await threeShots(page, 'PAYMENT-F06', () => rowOf(page, 'payment-payments', august.id));

    // From the 1st of September only: September's, not August's.
    await filterDates(page, '2026-09-01', '');
    await expect(rowOf(page, 'payment-payments', september.id)).toBeVisible();
    await expect(view.locator(`[data-testid=payment-payments-row][data-id="${august.id}"]`)).toHaveCount(0);
  } finally {
    await context.close();
  }
});

// flow: PAYMENT-F06 — the employee only looks: no «New payment», no «New method», no row action
test('PAYMENT-F06: an employee sees the payments and the methods, with no New payment, no New method and no row action', async ({ browser }) => {
  const owner = await signedIn(browser, '/payment/payments');
  const bank = await method(owner.context);
  const draft = await payment(owner.context, bank.id);
  await owner.context.close();
  const { context, page } = await signedIn(browser, '/payment/payments', true);
  try {
    await waitForList(page, 'payment-payments');
    await expect(rowOf(page, 'payment-payments', draft.id)).toBeVisible();
    await expect(shown(page).locator('[data-testid=payment-payments-add]')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid$=-advance]:visible, [data-testid$=-cancel]:visible')).toHaveCount(0);
    await page.goto(`${A}/payment/methods`);
    await waitForList(page, 'payment-methods');
    await expect(rowOf(page, 'payment-methods', bank.id)).toBeVisible();
    await expect(shown(page).locator('[data-testid=payment-methods-add]')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid$=-deactivate]:visible, [data-testid$=-edit]:visible')).toHaveCount(0);
  } finally {
    await context.close();
  }
});

// flow: PAYMENT-F08 · gh:pm#155 — the row opens «Editing method — {name}»; deactivated, it leaves «New payment»
test('PAYMENT-F08: a row opens «Editing method — {name}» with the whole account; a rename shows on its payments; Deactivate and Activate', async ({
  browser,
}) => {
  const { context, page } = await signedIn(browser, '/payment/methods');
  try {
    const bank = await method(context, 'Bank', 'ES9121000418450200051332');
    const paid = await payment(context, bank.id);
    await page.reload();
    await waitForList(page, 'payment-methods');
    await rowOf(page, 'payment-methods', bank.id).click();
    const form = page.locator('ion-modal[data-testid=payment-method-form]');
    await expect(form.locator('ion-title')).toHaveText(`Editing method — ${bank.name}`);
    await expect(page.locator('[data-testid=payment-method-form-account] input')).toHaveValue('ES9121000418450200051332');
    await threeShots(page, 'PAYMENT-F08', () => page.locator('[data-testid=payment-method-form-account]'));
    const renamed = named('Renamed');
    await page.locator('[data-testid=payment-method-form-name] input').fill(renamed);
    await page.locator('[data-testid=payment-method-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(rowOf(page, 'payment-methods', bank.id)).toContainText(renamed);
    const detail = await api<Payment>(context, A, 'GET', `/payment/payments/detail?id=${paid.id}`);
    expect(detail.data.method_name).toBe(renamed);

    // Deactivated, it leaves «New payment»; Activate brings it back.
    await rowAction(page, 'payment-methods', bank.id, 'deactivate');
    await expect(rowOf(page, 'payment-methods', bank.id)).toContainText('Deactivated');
    await page.goto(`${A}/payment/payments`);
    await waitForList(page, 'payment-payments');
    await shown(page).locator('[data-testid=payment-payments-add]').click();
    await expect(page.locator('[data-testid=payment-form-method] ion-select-option', { hasText: renamed })).toHaveCount(0);
    await page.locator('[data-testid=payment-form-cancel]').click();
    await page.goto(`${A}/payment/methods`);
    await waitForList(page, 'payment-methods');
    await rowAction(page, 'payment-methods', bank.id, 'activate');
    await expect(rowOf(page, 'payment-methods', bank.id)).toContainText('Active');
    expect(psql(`select is_active from payment_paymentmethod where id = '${bank.id}'`)).toBe('t');
  } finally {
    await context.close();
  }
});
