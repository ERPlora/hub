// flow: BASE-F84 BASE-F85 DEMO-F06
// FIX-HUB-BASE-APPROVAL-LABEL-WITHOUT-DISCOUNT-FIGURE (base/WORKBOOK.md BASE-F84 and BASE-F85; hub#2180, hub#2186):
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
import { execSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, compactBar, createItem, EMPLOYEE, login, OWNER, psql, REPO_DIR, shot, shown, untilStill } from './helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-BASE-APPROVAL-LABEL-WITHOUT-DISCOUNT-FIGURE';
const OWNER_PIN = '2580';
/** The line the employee asks for: its text and its quantity, which the dialog says in Spanish («2,5»). */
const LINE_TEXT = `Café con leche ${Date.now().toString(36)}`;
const SAID_ES = `Se aprueba: Añadir una línea: 2,5 × ${LINE_TEXT}`;
const SAID_EN = `Add a line: 2.5 × ${LINE_TEXT}`;
/** A phone, a tablet and a desk (the SaaS panel's `VIEWPORTS`). */
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

test.describe.configure({ mode: 'serial' });

let provider: Provider;
let owner: { context: BrowserContext; page: Page };
let employee: { context: BrowserContext; page: Page };
let started = '';
let itemId = '';

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** None of this month's assistant messages of the business `a` spent: a run never uses up the plan's allowance. */
function unspent(): void {
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

/** Every account of `email` in this hub's database: the cleanup leaves none of them with what this file made. */
const accountsOf = (email: string): string => `SELECT username FROM auth_user WHERE email = '${email}'`;

/** No PIN of the owner's left behind, in any of their accounts: the business's way in stays erplora.com's. */
function forgetThePin(): void {
  psql(`UPDATE base_credential SET pin_hash = '', pin_set_at = NULL WHERE username IN (${accountsOf(OWNER.email)})`);
}

test.beforeAll(async ({ browser }) => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  unspent();
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
  const pin = await api<{ set: boolean }>(context, A, 'POST', '/me/pin', { pin: OWNER_PIN });
  expect(pin.status, JSON.stringify(pin.data)).toBe(200);
});

test.afterAll(async () => {
  forgetThePin();
  if (started) {
    psql(
      `DELETE FROM base_approval WHERE requested_by IN (${accountsOf(EMPLOYEE.email)}) AND operation = 'demo.item.add_line' AND created_at >= '${started}'`,
    );
  }
  if (itemId) await api(owner.context, A, 'POST', '/demo/items/delete', { id: itemId });
  unspent();
  await employee?.context.close();
  await owner?.context.close();
  await provider?.close();
});

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
/** «An approval is needed», over the screen that asked. */
const approval = (page: Page): Locator => page.locator('ion-modal').filter({ has: page.getByTestId('approval-action') });
/** The topbar's way to the assistant: the sparkles, or on a phone «More options» (the sparkles folded with the bell). */
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function openPanel(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
}

const escaped = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

test('BASE-F84: the dialog says the figures of the very line it approves, and a manager approves it with their PIN', async () => {
  const { page } = employee;
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  const box = panel(page).locator('[data-testid="assistant-input"] textarea');
  await box.fill(`E2E-ASK demo__item__add_line {"id":"${itemId}","text":"${LINE_TEXT}","qty":"2.5"}`);
  await box.press('Enter');
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await card(page).locator('[data-testid="assistant-confirm-submit"]').click();

  const dialog = approval(page);
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
  await expect(page.locator('ion-toast').filter({ hasText: new RegExp(`Aprobado por ${escaped(name)}`) }).first()).toBeVisible();
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
