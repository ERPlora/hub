// The assistant's card for a write of Time clock (FIX-HUB-ATTENDANCE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half
// is hub#416, BASE-F97): the person a clocking acts on and the working day a correction rewrites, by the name the screens
// give them, never by the id the model sent (and, since hub#416, never left out for whoever may read them). End to end
// with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be
// seeded with it (README of this folder, «El asistente»). The owner, in Spanish, asks to clock someone of the team in
// (ATTENDANCE-F12) and to correct that person's day (ATTENDANCE-F08, dangerous): each card names her; cancelled, nothing
// changes. What this file creates carries `E2EAac` and goes away; the apps it turns on are turned off again.
// flow: attendance-assistant-card
// flow: ATTENDANCE-F12 ATTENDANCE-F08 BASE-F97
import { execSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, compactBar, exposeMovingInPage, login, psql, REPO_DIR, shown, turnOn, untilStill } from './helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-ATTENDANCE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
const TAG = 'E2EAac';
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** The apps a clocking needs: a business is born with every app off. */
const NEEDED = ['staff', 'attendance'];
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${TAG}%')`;

type Day = { id: string; status: string; clock_in_at: string; clock_out_at: string | null; correction_count: number };
type Detail = Day & { name: string };

let provider: Provider;
let wasOn = new Set<string>();

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

function cleanup(): void {
  psql(
    [
      `delete from attendance_correction where record_id in (${RECORDS})`,
      `delete from attendance_break where record_id in (${RECORDS})`,
      `delete from attendance_record where id in (${RECORDS})`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const before = await api<{ apps: { id: string; state: string }[] }>(context, A, 'GET', '/apps');
  wasOn = new Set(before.data.apps.filter((app) => app.state === 'on').map((app) => app.id));
  await turnOn(context, A, ...NEEDED.filter((id) => !wasOn.has(id)));
  await context.close();
});

test.beforeEach(() => {
  // The month's assistant messages of the business `a` back to none: a run never spends the plan's allowance.
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
  cleanup();
});

test.afterAll(async ({ browser }) => {
  cleanup();
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  for (const app of [...NEEDED].reverse().filter((id) => !wasOn.has(id))) {
    const off = await api(context, A, 'POST', '/apps/disable', { app });
    expect(off.status, `turn off ${app}: ${JSON.stringify(off.data)}`).toBe(200);
  }
  await context.close();
  await provider?.close();
});

// ── The panel and its card (as base-assistant.spec.ts drives them) ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

async function openPanel(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/** Writes `text` and sends it; resolves once its answer has started (its card is up before the turn ends). */
async function ask(page: Page, text: string): Promise<void> {
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
}

/** The dangerous card ready for its capture: «Confirmation» focused, its label floated, then one frame for the label's
 *  move to start, so `untilStill` waits for it (base-assistant.spec.ts). */
async function confirmationReady(page: Page): Promise<void> {
  const field = card(page).locator('[data-testid="assistant-confirm-input"]');
  await expect(field).toHaveClass(/\bhas-focus\b/);
  await expect(field).toHaveClass(/\blabel-floating\b/);
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
}

/** «Confirmation» as its capture must show it: focused, its label floated and, in the same frame, nothing moving on the
 *  page, the label's move included (base-assistant.spec.ts, rv-ui-35). */
async function confirmationSettled(page: Page): Promise<boolean> {
  await exposeMovingInPage(page);
  return card(page)
    .locator('[data-testid="assistant-confirm-input"]')
    .evaluate(async (field) => {
      const label = field.querySelector('.label-text-wrapper');
      const look = () =>
        label && `${JSON.stringify(label.getBoundingClientRect())} ${getComputedStyle(label).transform} ${getComputedStyle(label).opacity}`;
      const before = look();
      await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
      const moving = (window as unknown as { __movingInPage: () => string[] }).__movingInPage();
      return (
        field.classList.contains('has-focus') &&
        field.classList.contains('label-floating') &&
        label !== null &&
        look() === before &&
        moving.length === 0
      );
    });
}

/** The owner, in Spanish, with a person of the team made through Staff's API: `[context, page, her id, her name]`. */
async function ownerWithBea(browser: import('@playwright/test').Browser): Promise<[BrowserContext, Page, string, string]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const created = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG}Bea`, last_name: 'Ruiz' });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  return [context, page, created.data.id, `${TAG}Bea Ruiz`];
}

async function daysOf(context: BrowserContext, memberId: string): Promise<Day[]> {
  const page = await api<{ rows: Day[] }>(context, A, 'GET', `/attendance/records?member_id=${memberId}`);
  expect(page.status, JSON.stringify(page.data)).toBe(200);
  return page.data.rows;
}

test('attendance-assistant-card — in Spanish clocking someone else in names them on the card, never by their id', async ({ browser }) => {
  const [context, page, bea, name] = await ownerWithBea(browser);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  await ask(page, `E2E-ASK attendance__record__clock_in ${JSON.stringify({ member_id: bea })}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Fichar la entrada en Control horario: ${name}`);
    await expect(card(page)).not.toContainText(bea);
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  expect(await daysOf(context, bea)).toEqual([]);
  await context.close();
});

test('attendance-assistant-card — in Spanish correcting a working day names it by its person and its day, never by its id', async ({ browser }) => {
  const [context, page, bea, name] = await ownerWithBea(browser);
  for (const write of ['/attendance/clock_in', '/attendance/clock_out']) {
    const done = await api(context, A, 'POST', write, { member_id: bea });
    expect(done.status, `${write}: ${JSON.stringify(done.data)}`).toBe(200);
  }
  const [day] = await daysOf(context, bea);
  // Named as «Correct working day» names it, in the reader's language: read through the API in Spanish.
  const detail = await api<Detail>(context, A, 'GET', `/attendance/records/detail?id=${day.id}`);
  expect(detail.status, JSON.stringify(detail.data)).toBe(200);
  expect(detail.data.name).toMatch(new RegExp(`^${name} · \\d{1,2} [a-z]{3,4} \\d{4}$`));
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanel(page);
  const correction = { record_id: day.id, clock_in_at: day.clock_in_at, clock_out_at: day.clock_out_at, reason: 'Olvidó fichar' };
  await ask(page, `E2E-ASK attendance__record__correct ${JSON.stringify(correction)}`);
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Jornada: ${detail.data.name}`);
    await expect(card(page)).not.toContainText(day.id);
    await confirmationReady(page);
    await untilStill(page);
    expect(await confirmationSettled(page), `${KEY}-correct-${vp.label} caught before it settled`).toBe(true);
    await capture(page, `${KEY}-correct-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  const [after] = await daysOf(context, bea);
  expect([after.clock_in_at, after.correction_count]).toEqual([day.clock_in_at, 0]);
  await context.close();
});
