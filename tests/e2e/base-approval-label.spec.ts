// flow: BASE-F84 BASE-F85 DEMO-F06
// «An approval is needed» says what is approved with the figures of that very request, as Toast and Square print
// «Approve 50 % discount», so the manager knows how much they approve. Opened from a real app that declares its
// sentence: Demo names «add a line» as approvable and says it with the line's quantity and text (DEMO-F06). The
// employee (employee@example.com, who only views Demo) asks the assistant to add a line; on the «yes» of its card the
// dialog says «Se aprueba: Añadir una línea: 2,5 × <text>» in Spanish (the cashier's language) at a phone, a tablet
// and a desk; the owner approves it with their PIN on the employee's device, the line is added once, and Employees ›
// Approvals says the figure in the language of who reads it. The e2e's AI provider (assistant-provider.ts) asks for
// the write as written (`E2E-ASK`); the SaaS must be seeded with it (README of this folder, «El asistente»). The
// owner's PIN exists only while this file runs, after the employee has entered (a PIN in hub `a` turns every browser's
// way in into the PIN pad), and everything this file creates goes with it (`afterAll`).
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { approvalDialog, forgetThePin, forgetThePinAndTheApprovalsSince, ownerChoosesPin } from './approval-helpers';
import { type Provider } from './assistant-provider';
import { box, card, openPanelAtTheDesk } from './assistant-panel';
import { emptyMonth } from './assistant-real';
import { A, api, EMPLOYEE, login, psql, shot, shown, THREE_SIZES as VIEWPORTS, untilStill } from './helpers';
import { createItem } from './demo-items';
import { seededProvider } from './provider-helpers';
import { toastSaying } from './toast-helpers';

const KEY = 'FIX-HUB-BASE-APPROVAL-LABEL-WITHOUT-DISCOUNT-FIGURE';
const OWNER_PIN = '2580';
/** The line the employee asks for: its text and its quantity, which the dialog says in Spanish («2,5»). */
const LINE_TEXT = `Café con leche ${Date.now().toString(36)}`;
const SAID_ES = `Se aprueba: Añadir una línea: 2,5 × ${LINE_TEXT}`;
const SAID_EN = `Add a line: 2.5 × ${LINE_TEXT}`;

test.describe.configure({ mode: 'serial' });

let provider: Provider;
let owner: { context: BrowserContext; page: Page };
let employee: { context: BrowserContext; page: Page };
let started = '';
let itemId = '';

test.beforeAll(async ({ browser }) => {
  provider = await seededProvider();
  emptyMonth();
  started = psql('SELECT now()::text');
  const context = await browser.newContext({ baseURL: A });
  owner = { context, page: await context.newPage() };
  await login(owner.page, A, '/');
  itemId = (await createItem(context, A, `E2E approval label ${Date.now().toString(36)}`)).id;
  // The employee enters while nobody of the business has a PIN: the way in is erplora.com's, as every spec's.
  const device = await browser.newContext({ baseURL: A });
  employee = { context: device, page: await device.newPage() };
  await login(employee.page, A, '/', EMPLOYEE);
  // In Spanish (the Hub's language cookie, as the sign-in sets it): the longest texts.
  await device.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  // Only now the owner chooses a PIN («My profile»): who may approve, on the employee's device.
  forgetThePin();
  await ownerChoosesPin(context, OWNER_PIN);
});

test.afterAll(async () => {
  forgetThePinAndTheApprovalsSince(started, 'demo.item.add_line');
  if (itemId) await api(owner.context, A, 'POST', '/demo/items/delete', { id: itemId });
  emptyMonth();
  await employee?.context.close();
  await owner?.context.close();
  await provider?.close();
});

const escaped = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

test('BASE-F84: the dialog says the figures of the very line it approves, and a manager approves it with their PIN', async () => {
  const { page } = employee;
  await openPanelAtTheDesk(page);
  await box(page).fill(`E2E-ASK demo__item__add_line {"id":"${itemId}","text":"${LINE_TEXT}","qty":"2.5"}`);
  await box(page).press('Enter');
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await card(page).locator('[data-testid="assistant-confirm-submit"]').click();

  const dialog = approvalDialog(page);
  await expect(dialog.getByTestId('approval-action')).toHaveText(SAID_ES);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(dialog.getByTestId('approval-action')).toBeVisible();
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${viewport.label}`) });
  }
  // Nothing is added while it waits for the approval.
  const before = await api<{ lines: { text: string }[] }>(owner.context, A, 'GET', `/demo/items/detail?id=${itemId}`);
  expect(before.data.lines).toEqual([]);

  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(dialog.getByTestId('pinpad').or(dialog.getByTestId('pin-face').first())).toBeVisible();
  if (await dialog.getByTestId('pin-face').count()) {
    await dialog.getByTestId('pin-face').filter({ hasText: /owner/i }).first().click();
  }
  await expect(dialog.getByTestId('pinpad')).toBeVisible();
  const name = (await dialog.getByTestId('pin-door-chosen').locator('.pin-door__name').innerText()).trim();
  for (const digit of OWNER_PIN) await dialog.getByTestId(`pinpad-key-${digit}`).click();
  await expect(toastSaying(page, new RegExp(`Aprobado por ${escaped(name)}`))).toBeVisible();
  await expect(dialog).toBeHidden();

  // Once: the line is in the item, with what the dialog said.
  await expect
    .poll(async () => (await api<{ lines: { text: string; qty: string }[] }>(owner.context, A, 'GET', `/demo/items/detail?id=${itemId}`)).data.lines)
    .toEqual([expect.objectContaining({ text: LINE_TEXT, qty: expect.stringMatching(/^2\.50*$/) })]);
});

test('BASE-F85: Employees › Approvals says the figure in the language of who reads it', async () => {
  const record = await api<{ approvals: { action: string; operation_label: string; used: boolean }[] }>(
    owner.context,
    A,
    'GET',
    '/approvals',
  );
  expect(record.status).toBe(200);
  const row = record.data.approvals.find((approved) => approved.action.includes(LINE_TEXT));
  expect(row).toMatchObject({ action: SAID_EN, operation_label: 'Add a line to an item', used: true });

  const { page } = owner;
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`${A}/employees#approvals`);
    const search = shown(page).locator('[data-testid=approvals-search] input');
    await expect(search).toBeVisible();
    await search.fill(LINE_TEXT);
    await expect(shown(page).getByText(SAID_EN).first()).toBeVisible();
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-record-${viewport.label}`) });
  }
});
