// The Hub's assistant end to end with its real dependencies: the Hub of this stack, its SaaS's
// gateway (`/internal/assistant/*`, `/internal/speech/transcribe`) and, behind it, the e2e's provider
// (assistant-provider.ts, an OpenAI-compatible server on 127.0.0.1 that this spec starts): no mock between the
// browser and the provider, no real provider, no real key. The SaaS must be seeded with that provider (README of this
// folder, «El asistente»): `assistant_seed.py gateway http://127.0.0.1:<E2E_AI_PROVIDER_PORT>/v1`.
// The month's messages of the business `a` are set on the SaaS's database before each test (`spend`), so a run never
// spends the plan's allowance and the 80 % and the spent month can be seen.
import { execSync } from 'node:child_process';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { CLAIM_ANSWER, DICTATION, DONE, GREETING, NOT_DONE, type Provider, startProvider, STEPS_SAID } from './assistant-provider';
import { A, api, capture, compactBar, EMPLOYEE, exposeMovingInPage, login, REPO_DIR, shot, shown, turnOffTurnedOn, turnOnMissing, untilStill, upgradeLandsInside } from './helpers';
import { cleanPricing, CODE as PRICING_CODE, createProduct, post, TAG as PRICING_TAG } from './pricing-helpers';
import { STACK } from './stack';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

let provider: Provider;

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** This month's messages of the business `a` on erplora.com. */
function spend(messages: number): void {
  const hub = "(select id from hubs_hub where slug = 'a')";
  saasSql(`delete from assistant_assistantusage where hub_id = ${hub}`);
  if (messages === 0) return;
  saasSql(
    'insert into assistant_assistantusage (id, demo, month, messages, tokens_input, tokens_output, tokens_embedding, ' +
      'transcriptions, speech_characters, cost_usd, created_at, updated_at, hub_id) ' +
      `select gen_random_uuid(), '', date_trunc('month', now() at time zone 'UTC')::date, ${messages}, 0, 0, 0, 0, 0, 0, ` +
      `now(), now(), id from hubs_hub where slug = 'a'`,
  );
}

test.beforeAll(async () => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
});

test.afterAll(async () => {
  await provider?.close();
});

test.beforeEach(() => {
  spend(0);
});

// ── The panel ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
/** The assistant's answers, each one its row (a failure before any word has no bubble). */
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
/** The last answer's bubble: its words. */
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
/** The last receipt under the answers: what the Hub says it did with a write (BASE-F97, step 5). */
const receipt = (page: Page): Locator => panel(page).locator('[data-testid="assistant-receipt"]').last();

/** Answers the card with its button (`submit` or `cancel`) and waits until it has gone: while Ionic dismisses a modal,
 *  its focus trap keeps the keyboard inside it. */
async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

/** The topbar's way to the assistant: the sparkles, or on a phone «More options» (the sparkles folded with the bell). */
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function home(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
}

async function openPanel(page: Page): Promise<void> {
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) {
      const row = page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]');
      await row.click();
      // While Ionic dismisses the menu, its focus trap keeps the keyboard out of the composer (hub#742), as in `decide`.
      await expect(row).toHaveCount(0);
    }
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/** The panel open on the home at a computer's size, with the app in Spanish: where a card's words are looked at. */
async function openPanelInSpanish(page: Page): Promise<void> {
  await page.context().addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
}

/** Writes `text` and sends it with Enter; resolves when the turn has ended (the composer offers «Send» again). */
async function ask(page: Page, text: string, options: { settle?: boolean } = {}): Promise<void> {
  // The previous turn has ended (its text may arrive before its end): while one runs, Enter sends nothing.
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
  if (options.settle ?? true) await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
}

/** The panel as a person sees it at each size; `settled`, when given, must hold at the very moment of each capture. */
async function shots(
  page: Page,
  key: string,
  ready: () => Promise<void> = async () => undefined,
  settled?: () => Promise<boolean>,
): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await ready();
    await untilStill(page);
    if (settled) expect(await settled(), `APP-BASE-9-${key}-${vp.label} caught before it settled`).toBe(true);
    await capture(page, `APP-BASE-9-${key}-${vp.label}`);
  }
}

/** The dangerous card ready for its capture: «Confirmation» focused (the dialog focuses it once presented, after its own
 *  animation) and its label floating, then one frame for the label's move to start, so `untilStill` waits for it. */
async function confirmationReady(page: Page): Promise<void> {
  await expect(card(page)).toBeVisible();
  const field = card(page).locator('[data-testid="assistant-confirm-input"]');
  await expect(field).toHaveClass(/\bhas-focus\b/);
  await expect(field).toHaveClass(/\blabel-floating\b/);
  await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
}

/** The dangerous card's «Confirmation» as its capture must show it: focused, its label floated and, in the same frame,
 *  nothing moving on the page, the label's move included (rv-ui-35: the first size caught the first frame of the label's
 *  move, with a gap in the outline). Stillness is asked of the e2e's one detector, put in the page by
 *  `exposeMovingInPage` (helpers.ts), never of the label's own animations; and, as the detector leaves endless moves out
 *  (a spinner's), the label must also look the same two frames apart. */
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

/** A context of its own signed in on `a` with `needed` on, and what that took (`turnedOn`, for `turnOffTurnedOn`). */
async function signedInWith(browser: Browser, needed: readonly string[]): Promise<{ context: BrowserContext; page: Page; turnedOn: string[] }> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const turnedOn: string[] = [];
  await turnOnMissing(context, A, needed, turnedOn);
  return { context, page, turnedOn };
}

/** Cancels the Spanish card at a computer's size: nothing was done, and the answer says so. */
async function cancelAtComputerSize(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
}

/** The page saved as `name` once nothing moves. */
async function captureStill(page: Page, name: string): Promise<void> {
  await untilStill(page);
  await capture(page, name);
}

/** The dangerous card saved as `name`, with «Confirmation» focused and nothing moving. */
async function captureConfirmation(page: Page, name: string): Promise<void> {
  await confirmationReady(page);
  await untilStill(page);
  expect(await confirmationSettled(page), `${name} caught before it settled`).toBe(true);
  await capture(page, name);
}

/** Leaves `a` with the apps it had and closes the context. */
async function leave(context: BrowserContext, turnedOn: string[]): Promise<void> {
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
}

async function freshPage(browser: Browser, credentials = EMPLOYEE): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/', credentials);
  return page;
}

// The browser's fake microphone, for the dictation test: a worker-wide launch option, so for the whole file.
test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

test('the sparkles open the panel on the right (on a phone, from «More options»): docked from 768 px, over the screen on a phone; Escape, × and the veil close it; it stays open across screens and reloads', async ({ page }) => {
  await login(page, A, '/');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await home(page);
    if (vp.width < 768) {
      // As in the old hub: the sparkles and the bell folded into one «More options», so the title stays centred.
      await expect(shown(page).locator('[data-testid="assistant-button"]')).toHaveCount(0);
      await expect(shown(page).locator('[data-testid="hub-bell"]')).toHaveCount(0);
      await opener(page).click();
      await expect(page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]')).toHaveText('Assistant');
      await expect(page.locator('ion-popover [data-testid="topbar-chrome-more-bell"] ion-label')).toHaveText('Notifications');
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-9-BASE-G110-more-${vp.label}`) });
      await page.keyboard.press('Escape');
      await expect(page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]')).toHaveCount(0);
    }
    await openPanel(page);
    await expect(panel(page)).toContainText('Ask me about your sales, your stock or anything about your business.');
    await expect(panel(page).locator('[data-testid="assistant-shortcut"]').first()).toHaveText('What is left to set up?');
    // Measured once it has slid in.
    await untilStill(page);
    const aside = await panel(page).boundingBox();
    const pane = await page.locator('ion-app > ion-split-pane').boundingBox();
    expect(Math.round(aside!.x + aside!.width)).toBe(vp.width);
    if (vp.width < 768) {
      // Over the screen, all of it on a phone, with the veil behind.
      expect(Math.round(aside!.width)).toBe(vp.width);
      await expect(page.locator('[data-testid="assistant-veil"]')).toBeVisible();
    } else {
      // Docked: the screen leaves it its width and keeps working beside it.
      expect(aside!.width).toBeGreaterThanOrEqual(360);
      expect(aside!.width).toBeLessThanOrEqual(420);
      expect(Math.round(pane!.x + pane!.width)).toBe(Math.round(aside!.x));
      await expect(page.locator('[data-testid="assistant-veil"]')).toHaveCount(0);
    }
    await capture(page, `APP-BASE-9-BASE-G110-${vp.label}`);
    // A phone of 420 px or less is all panel (the veil is under it): its ×; wider, Escape wherever the focus is.
    if (vp.width <= 420) await panel(page).locator('[data-testid="assistant-close"]').click();
    else await page.keyboard.press('Escape');
    await expect(panel(page)).toHaveAttribute('data-open', 'false');
    await untilStill(page);
    const after = await page.locator('ion-app > ion-split-pane').boundingBox();
    expect(Math.round(after!.width)).toBe(vp.width);
  }
  // Between a phone and a tablet, 420 px of panel over a veil that closes it.
  await page.setViewportSize({ width: 600, height: 900 });
  await openPanel(page);
  await untilStill(page);
  expect(Math.round((await panel(page).boundingBox())!.width)).toBe(420);
  await page.locator('[data-testid="assistant-veil"]').click({ position: { x: 20, y: 400 } });
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
  await page.setViewportSize({ width: 1440, height: 900 });
  // Open, it stays so on another screen and after reloading; the × closes it, and the sparkles again.
  await openPanel(page);
  await page.goto(`${A}/settings`);
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await page.reload();
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await panel(page).locator('[data-testid="assistant-close"]').click();
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
  await page.reload();
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
});

test('hub-e2e-capture — capture() keeps the panel open after a turn at 390, 834 and 1440: on a phone it is all the screen, its border from top to bottom', async ({ page }) => {
  // At 390 the open panel's first and last 8 rows are the same (white with its left border), which capture() must not
  // mistake for a page not yet painted at its size.
  const KEY = 'FIX-HUB-E2E-CAPTURE-REFUSES-ASSISTANT-PANEL-ON-PHONE';
  await login(page, A, '/');
  await page.setViewportSize({ width: 390, height: 844 });
  await home(page);
  await openPanel(page);
  await ask(page, 'Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(lastAnswer(page)).toBeVisible();
    await capture(page, `${KEY}-${vp.label}`);
  }
});

// hub#742, hub#1121: on a phone the panel opens from «More options», and while Ionic dismisses that menu its focus trap
// pulls the keyboard back into it: the Enter written in the box reached a row of the menu (it opened the bell's list)
// and «Hola» stayed in the box. The panel opens once the menu has gone. The menu's way out is slowed, so a run never gets
// past that moment by luck (a loaded machine did), and the question is written as soon as the box is there, with no
// wait for the menu, as a person does.
test('hub-e2e-open-panel — on a phone the panel takes a question with Enter as soon as it has opened from «More options»', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 390, height: 844 });
  await home(page);
  const devtools = await page.context().newCDPSession(page);
  await devtools.send('Animation.enable');
  await devtools.send('Animation.setPlaybackRate', { playbackRate: 0.05 });
  await opener(page).click();
  await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  await ask(page, 'Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  // Nothing of the menu caught the keys: neither the menu nor the bell's list is left on screen.
  await expect(page.locator('ion-popover:not(.overlay-hidden)')).toHaveCount(0);
});

test('«Ask the assistant» on the setup card opens it on the setup; a shortcut asks at once', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await shown(page).locator('[data-testid="setup-review"]').click();
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(panel(page)).toContainText("Review your business's setup. Choose an option or write your question.");
  await shots(page, 'BASE-G121');
  const turn = page.waitForRequest((request) => request.url().endsWith('/api/assistant/turn'));
  await panel(page).locator('[data-testid="assistant-shortcut"]').first().click();
  const sent = (await turn).postDataJSON() as { setup: boolean; messages: { role: string; content: string }[] };
  expect(sent.setup).toBe(true);
  expect(sent.messages.at(-1)).toEqual({ role: 'user', content: 'What is left to set up?' });
  await expect(lastAnswer(page)).toContainText(GREETING.en);
  // The setup's instructions went to the model with the checklist read again by the Hub (hub#373).
  const instructions = JSON.stringify(provider.seen.filter((s) => s.path === '/v1/chat/completions').at(-1)?.body);
  expect(instructions).toContain('checklist');
});

test('a question and its answer: written as it comes, with its format; «Stop» keeps what came; «Go to Settings» opens it and closes the panel', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'Hola');
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]').last()).toHaveText('Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  await shots(page, 'BASE-G111');

  // «Stop» half-way: what was written stays, the bubble says it stopped.
  await ask(page, 'E2E-SLOW', { settle: false });
  await expect(lastAnswer(page)).toContainText('This answer is long');
  await panel(page).locator('[data-testid="assistant-stop"]').click();
  await expect(lastAnswer(page)).toContainText('Stopped.');
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible();

  await ask(page, 'E2E-FORMAT ¿Cómo van las ventas?');
  const answer = lastAnswer(page);
  await expect(answer.locator('h3, h4, h5, h6').first()).toHaveText('Today’s sales');
  await expect(answer.locator('strong').first()).toHaveText('€120');
  await expect(answer.locator('li')).toHaveCount(2);
  await expect(answer.locator('table tbody tr')).toHaveCount(2);
  await expect(answer.locator('a[href="/settings#business"]')).toHaveText('Settings');
  const go = panel(page).locator('[data-testid="assistant-go"]');
  await expect(go).toHaveText(['Go to Settings']);
  await shots(page, 'BASE-G113', async () => {
    // The table scrolls inside its own box: the panel never scrolls sideways.
    const sideways = await panel(page).locator('[data-testid="assistant-thread"]').evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(sideways).toBeLessThanOrEqual(0);
    await answer.scrollIntoViewIfNeeded();
  });
  await shots(page, 'BASE-G114', () => go.scrollIntoViewIfNeeded());
  await go.click();
  await expect(page).toHaveURL(`${A}/settings#business`);
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
});

test('a write waits on its card: «Run it» runs it as the person; «Cancel» runs nothing', async ({ page, context }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  const name = `Mesa asistente ${Date.now().toString(36)}`;
  await ask(page, `E2E-CREATE ${name}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText('Run this action?');
  await expect(card(page)).toContainText(`Create in Demo: ${name}`);
  await shots(page, 'BASE-G115', () => expect(card(page)).toBeVisible());
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText(DONE.en);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Done: Create in Demo');
  const made = await api<{ rows: { name: string }[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`);
  expect(made.data.rows.map((row) => row.name)).toEqual([name]);

  const other = `${name} no`;
  await ask(page, `E2E-CREATE ${other}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText(NOT_DONE.en);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Not done, cancelled: Create in Demo');
  const none = await api<{ rows: unknown[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(other)}`);
  expect(none.data.rows).toEqual([]);
});

test('several things in a row: the read runs by itself, the write waits on its card', async ({ page, context }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  const name = `Mesa cadena ${Date.now().toString(36)}`;
  await ask(page, `E2E-CHAIN ${name}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText(`Create in Demo: ${name}`);
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText(DONE.en);
  // The read went to the model with its result, without a card; one message spent for the whole turn.
  const chats = provider.seen.filter((s) => s.path === '/v1/chat/completions').slice(-3);
  expect(JSON.stringify(chats[1].body)).toContain('"role":"tool"');
  const made = await api<{ rows: { name: string }[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`);
  expect(made.data.rows.map((row) => row.name)).toEqual([name]);
  await shots(page, 'BASE-G119');
});

// flow: BASE-F101 (asking for several things in a row)
test('BASE-F101 — several things in a row: what each round says is its own paragraph of the one bubble, never glued to the previous one', async ({ page }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-ROUNDS-TEXT-RUN-TOGETHER';
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, `E2E-STEPS Mesa pasos ${Date.now().toString(36)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await decide(page, 'cancel');
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  // Three rounds (before the read, before the write, after the card), one bubble, one paragraph each.
  await expect(answers(page)).toHaveCount(1);
  await expect(lastAnswer(page).locator('.assistant-md > p')).toHaveText([...STEPS_SAID.en, NOT_DONE.en]);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(lastAnswer(page)).toBeVisible();
    await capture(page, `${KEY}-${vp.label}`);
  }
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
});

test('a dangerous write lists its data and runs only after typing the word', async ({ page, context }) => {
  await login(page, A, '/');
  const item = await api<{ id: string }>(context, A, 'POST', '/demo/items', { name: `Para borrar ${Date.now().toString(36)}` });
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, `E2E-DELETE ${item.data.id}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText('Delete in Demo. Check each datum before going on.');
  // A record is never shown by its id; Demo marks no read that names it.
  await expect(card(page)).not.toContainText(item.data.id);
  // The native button inside `ion-button` (its host carries no role for `aria-disabled` to count).
  const submit = card(page).locator('[data-testid="assistant-confirm-submit"] button');
  await expect(submit).toBeDisabled();
  await shots(page, 'BASE-G116', () => confirmationReady(page), () => confirmationSettled(page));
  await page.setViewportSize({ width: 1440, height: 900 });
  const typing = card(page).locator('[data-testid="assistant-confirm-input"] input');
  // Typed wrong: «Run it» stays off and nothing is deleted.
  await typing.fill('confirmed');
  await expect(submit).toBeDisabled();
  expect((await api(context, A, 'GET', `/demo/items/detail?id=${item.data.id}`)).status).toBe(200);
  // Typed right, in its own way: what goes to the Hub is what was typed, which the server checks again (rv-hub-247).
  await typing.fill('  Confirm ');
  await expect(submit).toBeEnabled();
  const sent = page.waitForRequest((request) => request.url().endsWith('/api/assistant/turn') && Boolean(request.postDataJSON()?.decision));
  await decide(page, 'submit');
  expect((await sent).postDataJSON().decision).toMatchObject({ accepted: true, typed: '  Confirm ' });
  await expect(lastAnswer(page)).toContainText(DONE.en);
  const gone = await api(context, A, 'GET', `/demo/items/detail?id=${item.data.id}`);
  expect(gone.status).toBe(404);
});

// Cancelled: nothing changes, so the only thing to clean is the language cookie's context, closed at the end.
test('BASE-F97 BASE-F98 — in Spanish the card names every datum in Spanish, also one the screen does not name itself, and the platform by its screen', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  // In Spanish (the Hub's language cookie, as the sign-in sets it).
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const before = await api<Record<string, unknown>>(context, A, 'GET', '/access/settings');
  expect(before.status, JSON.stringify(before.data)).toBe(200);
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'E2E-ASK base__access__settings_update {"pin_inactivity_minutes":10,"pin_length":6}', { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText('¿Ejecutar esta acción?');
  await expect(card(page)).not.toContainText('Pin Length');
  await expect(card(page)).not.toContainText('Pin Inactivity Minutes');
  await expect(card(page)).not.toContainText('Base');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Cambiar en Ajustes. Revisa cada dato antes de seguir.');
    await expect(card(page)).toContainText('Volver a pedir tras (minutos): 10');
    await expect(card(page)).toContainText('Dígitos del PIN: 6');
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toHaveText('No se hizo, cancelado: Cambiar en Ajustes');
  expect((await api(context, A, 'GET', '/access/settings')).data).toEqual(before.data);
  await context.close();
});

// flow: assistant-card (BASE-F97 BASE-F98)
// An object datum is said by its values, as a summary says an address. Cancelled: nothing is sent.
test('assistant-card — in Spanish an object datum (a WhatsApp template) is said by its values, never by its inner keys', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-OBJECT-SHOWS-INNER-KEYS-IN-ENGLISH';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await openPanelInSpanish(page);
  const send = {
    to: '+34600111222',
    template: { name: 'cita_recordatorio', language: 'es', variables: ['Ana', '10:00'] },
    client_message_id: '0192f5a0-0000-7000-8000-000000000001',
  };
  await ask(page, `E2E-ASK whatsapp_inbox__message__send ${JSON.stringify(send)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText('Enviar en Bandeja de WhatsApp. Revisa cada dato antes de seguir.');
  for (const inner of ['name:', 'language:', 'variables:']) await expect(card(page)).not.toContainText(inner);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Plantilla: cita_recordatorio · es · Ana, 10:00');
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await context.close();
});

// flow: base-assistant-card-attempt-keys (BASE-F97)
// A write's attempt key is nothing a person can judge, so the card leaves it out; the write still gets it whole, and
// the same print asked again with its key, as a retry, is still one job.
test('base-assistant-card-attempt-keys — in Spanish a print leaves its key out of the card and runs with it: asked twice, it is one job', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-ATTEMPT-KEYS';
  const { context, page, turnedOn } = await signedInWith(browser, ['printing']);
  await openPanelInSpanish(page);
  const stamp = Date.now();
  const product = `Café ${stamp}`;
  const jobKey = `e2e-attempt-${stamp}`;
  const print = { job_key: jobKey, document_type: 'barcode_label', document: { product_name: product, barcode: '8412345678905', price: 1.5 } };
  const jobs = async () =>
    (await api<{ rows: { reference: string }[] }>(context, A, 'GET', `/printing/jobs?search=${encodeURIComponent(product)}`)).data.rows;
  await ask(page, `E2E-ASK printing__job__create ${JSON.stringify(print)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // The document by the queue's word for it, never as the model sent it.
    await expect(card(page)).toContainText(`Crear en Impresión: Etiqueta de código de barras · ${product}`);
    await expect(card(page)).not.toContainText(jobKey);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  // The Hub's receipt says it ran, and so does the answer: a job that can be cancelled is no refusal.
  await decide(page, 'submit');
  await expect(receipt(page)).toHaveText('Hecho: Crear en Impresión');
  await expect(lastAnswer(page)).toHaveText('Hecho.');
  expect(await jobs()).toHaveLength(1);
  // The same print again, with its key: a retry. Its card leaves the key out again, and it adds no second job.
  await ask(page, `E2E-ASK printing__job__create ${JSON.stringify(print)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).not.toContainText(jobKey);
  await decide(page, 'submit');
  await expect(receipt(page)).toHaveText('Hecho: Crear en Impresión');
  await expect(panel(page).locator('[data-testid="assistant-receipt"]')).toHaveCount(2);
  await expect(lastAnswer(page)).toHaveText('Hecho.');
  expect(await jobs()).toHaveLength(1);
  await leave(context, turnedOn);
});

// flow: whatsapp_inbox-assistant-card (WHATSAPP_INBOX-F33)
// A template with a document header: the file goes by the name it was chosen with, never by its id, and the message
// key never shows. Cancelled: nothing is sent.
test('whatsapp_inbox-assistant-card — in Spanish a template names its header file by its name and leaves the message key out', async ({ browser }) => {
  const KEY = 'FIX-HUB-WHATSAPP-INBOX-ATTEMPT-KEYS-UNMARKED';
  const { context, page, turnedOn } = await signedInWith(browser, ['customer', 'whatsapp_inbox']);
  const stamp = Date.now();
  const file = `carta-${stamp}.pdf`;
  const pdf = Buffer.from(`%PDF-1.7\n${'\u0000'.repeat(64)}`, 'latin1').toString('base64');
  const kept = await api<{ id: string; name: string }>(context, A, 'POST', '/whatsapp_inbox/templates/samples', {
    header_format: 'DOCUMENT',
    name: file,
    content_base64: pdf,
  });
  expect(kept.status, `keep the header's file: ${JSON.stringify(kept.data)}`).toBe(201);
  await openPanelInSpanish(page);
  // A UUID, as the screen generates it: anything else is refused before the card (`invalid_arguments`, hub#741).
  const messageKey = crypto.randomUUID();
  const send = {
    to: '+34600111222',
    template: { name: 'carta_del_dia', language: 'es', header_sample: kept.data.id },
    client_message_id: messageKey,
  };
  await ask(page, `E2E-ASK whatsapp_inbox__message__send ${JSON.stringify(send)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText('Enviar en Bandeja de WhatsApp. Revisa cada dato antes de seguir.');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Plantilla: carta_del_dia · es · ${file}`);
    await expect(card(page)).not.toContainText(messageKey);
    await expect(card(page)).not.toContainText(kept.data.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: base-assistant-money-mark (BASE-F97)
// The card knows an amount by the money mark its app declares, whatever its description says («in minor units of the
// currency»), so 1500 reads «15,00 €». Cancelled: nothing is recorded.
test('base-assistant-money-mark — in Spanish a payment says its amount in the business’s currency, never in its minor unit', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS';
  const { context, page, turnedOn } = await signedInWith(browser, ['payment']);
  await openPanelInSpanish(page);
  const payment = { method: 'Caja', payment_date: '2026-11-02', amount: 1500, beneficiary_name: 'Cafés del Sur' };
  await ask(page, `E2E-ASK payment__payment__create ${JSON.stringify(payment)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(/Caja · 2 nov 2026 · 15,00\s€/);
    await expect(card(page)).not.toContainText('1500');
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: base-assistant-money-mark (BASE-F97)
// The same PR: a payment in dollars of a business in euros said «15,00 €», every amount in the business's currency. Now in
// the currency its write names, with that currency's decimals (none in yen), as Stripe or Square show it. Cancelled.
test('base-assistant-money-mark — in Spanish a payment in another currency says its amount in it, with its decimals', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS-USD';
  const { context, page, turnedOn } = await signedInWith(browser, ['payment']);
  await openPanelInSpanish(page);
  const payment = { method: 'Caja', payment_date: '2026-11-02', amount: 1500, beneficiary_name: 'Cafés del Sur', currency: 'USD' };
  await ask(page, `E2E-ASK payment__payment__create ${JSON.stringify(payment)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(/Caja · 2 nov 2026 · 15,00\s\$/);
    await expect(card(page)).not.toContainText('€');
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  // In yen, without decimals: 1500 is ¥1,500, never «15,00».
  await ask(page, `E2E-ASK payment__payment__create ${JSON.stringify({ ...payment, currency: 'JPY' })}`, { settle: false });
  await expect(card(page)).toContainText(/Caja · 2 nov 2026 · 1\.500\s¥/); // Its thousands grouped, as every amount of the Hub (hub#734).
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await leave(context, turnedOn);
});

type SentCard = { fields: { name: string; kind: string; value: unknown; money?: unknown }[] };

/** The card of the confirm frame of a turn's answer (`text/event-stream`: one `data: <JSON>` per frame), if any. */
function confirmedCard(stream: string): SentCard | undefined {
  const frames = stream
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => JSON.parse(line.slice(5)) as { type: string; card?: SentCard });
  return frames.find((frame) => frame.type === 'confirm')?.card;
}

/** The card the server sends for the person to confirm, as it arrives: the answer of the turn that carries it (the
 *  first one only asks for the tool). */
async function sentCard(page: Page): Promise<SentCard> {
  const answer = await page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
  );
  return confirmedCard(await answer.text())!;
}

// flow: base-assistant-money-mark (BASE-F97)
// The same PR: a price set on a price list in dollars said «15,00 €»: the write names the list, not its currency. The
// card reads the list as the person and says the price in its currency (a list is always in one with two decimals), as
// Shopify shows a price of a market. Cancelled: no price is set. What it creates carries the pricing specs' code and
// goes away.
test('base-assistant-money-mark — in Spanish a price set on a list in another currency says it in that currency', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS-LIST-USD';
  const NEEDED = ['inventory', 'customer', 'pricing'];
  const { context, page, turnedOn } = await signedInWith(browser, NEEDED);
  cleanPricing();
  const product = `${PRICING_TAG} Champú ${Date.now().toString(36)}`;
  await createProduct(context, product, `${PRICING_CODE}-USD`, 1250);
  for (const [code, currency] of [[`${PRICING_CODE}USD`, 'USD'], [`${PRICING_CODE}PLN`, 'PLN']]) {
    await post(context, '/pricing/price_lists', { code, name: `${PRICING_TAG} ${currency}`, currency });
  }
  await openPanelInSpanish(page);
  const price = { product, price_list: `${PRICING_CODE}USD`, price: 1500 };
  const sent = sentCard(page);
  await ask(page, `E2E-ASK pricing__price_item__add ${JSON.stringify(price)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  expect((await sent).fields.find((field) => field.name === 'price')).toMatchObject({
    kind: 'money',
    value: 1500,
    money: { currency: 'USD', decimals: 2 },
  });
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(new RegExp(`${PRICING_CODE}USD · 15,00\\s\\$`));
    await expect(card(page)).not.toContainText('€');
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  // In zlotys, the list's, never the business's euros.
  await ask(page, `E2E-ASK pricing__price_item__add ${JSON.stringify({ ...price, price_list: `${PRICING_CODE}PLN` })}`, { settle: false });
  await expect(card(page)).toContainText(new RegExp(`${PRICING_CODE}PLN · 15,00\\szł`));
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  cleanPricing();
  await leave(context, turnedOn);
});

// flow: base-assistant-money-mark (BASE-F97)
// The same PR: an amount inside a datum went worded by the server («13,50 US$», «1,50 PLN») and the one on top by the
// screen («1,50 $», «1,50 zł»): one currency, two ways on one card. Now the server sends every amount as money and the
// screen writes them all: charging a sale, its discount on top and the amount of its payment inside the list of payments
// arrive as the same money, in the same currency. Cancelled: nothing is charged.
test('base-assistant-money-mark — in Spanish an amount inside a datum and one on top arrive as the same money', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS-NESTED';
  const NEEDED = ['customer', 'tax', 'sale'];
  const { context, page, turnedOn } = await signedInWith(browser, NEEDED);
  await openPanelInSpanish(page);
  // A charge the write takes (hub#729: `invalid_arguments` refuses any other before the card): its key and a loose line,
  // because only a counter sale carries a discount of its own (a check's lives in the check).
  const sale = {
    idempotency_key: `e2e-charge-${Date.now().toString(36)}`,
    open_lines: [{ unit_price: 1500, tax_category_key: 'service.generic', name: 'E2E Corte' }],
    discount_amount: 150,
    payments: [{ method: 'Efectivo', amount: 1350 }],
  };
  const sent = sentCard(page);
  await ask(page, `E2E-ASK sale__sale__complete ${JSON.stringify(sale)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  const fields = (await sent).fields;
  expect(fields.map((field) => field.name)).not.toContain('idempotency_key');
  const top = fields.find((field) => field.name === 'discount_amount');
  const payments = fields.find((field) => field.name === 'payments');
  expect(top).toMatchObject({ kind: 'money', value: 150 });
  expect(payments?.value).toEqual([{ method: 'Efectivo', amount: { kind: 'money', value: 1350 } }]);
  // The same currency, the card's: neither carries one of its own, so the screen writes both with one symbol.
  expect(top?.money ?? null).toBeNull();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(/1,50\s€/);
    await expect(card(page)).not.toContainText(/EUR|US\$|1350/);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

/** A business is born with every app off: Appointments and the apps it needs, off again at the end if they were. */
const CITAS = ['customer', 'service', 'staff', 'schedule', 'appointment'];
/** A customer, a service and a professional by ids that name nothing in this business: the card leaves them out. */
const [CUSTOMER_ID, SERVICE_ID, MEMBER_ID] = [
  '0192f0b2-1111-7000-8000-000000000001',
  '0192f0b2-2222-7000-8000-000000000002',
  '0192f0b2-3333-7000-8000-000000000003',
];

/** Asks for a booking of `services` on 2 Nov 2026 at 10:00 through the front desk, its customer and professional by
 *  `CUSTOMER_ID` and `MEMBER_ID`, and checks at each size that its card says `line` and none of `never`, saved as `key`. */
async function bookingCardSays(page: Page, services: unknown[], line: string, never: readonly string[], key: string): Promise<void> {
  const booking = { customer_id: CUSTOMER_ID, services, staff_id: MEMBER_ID, start: '2026-11-02T10:00:00+01:00', source: 'counter' };
  await ask(page, `E2E-ASK appointment__appointment__create ${JSON.stringify(booking)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(line);
    for (const raw of never) await expect(card(page)).not.toContainText(raw);
    await captureStill(page, `${key}-${vp.label}`);
  }
}

// flow: assistant-card (BASE-F97)
// A booking's card says its day and time as the person's language writes them, at the business's hour, its channel by
// the label Appointments gives it, and nobody by an id. Cancelled: nothing is booked.
test('assistant-card — in Spanish a booking says its day and time and its channel in words, and nobody by an id', async ({ browser }) => {
  const { context, page, turnedOn } = await signedInWith(browser, CITAS);
  await openPanelInSpanish(page);
  const raw = ['2026-11-02', '+01:00', 'counter', CUSTOMER_ID, SERVICE_ID, MEMBER_ID];
  const line = 'Crear en Citas: 1 elemento · 2 nov 2026, 10:00 · Mostrador';
  await bookingCardSays(page, [{ service_id: SERVICE_ID }], line, raw, 'FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES');
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: assistant-card (BASE-F97)
// hub#860: with no id, the assistant sends a booking's service as a person says it («Tinte») and the card said «1
// elemento»: now it says the service by that name, with the day, the time and the channel in words. Cancelled: nothing
// is booked.
test('assistant-card — in Spanish a booking whose service comes by its name says that name, never how many', async ({ browser }) => {
  const { context, page, turnedOn } = await signedInWith(browser, CITAS);
  await openPanelInSpanish(page);
  const line = 'Crear en Citas: Tinte · 2 nov 2026, 10:00 · Mostrador';
  await bookingCardSays(page, [{ service: 'Tinte' }], line, ['elemento', CUSTOMER_ID, MEMBER_ID], 'hub-860-service-by-name');
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: assistant-card (BASE-F97)
// A write of the platform that names its record by an id says which one as its screen does: a device by its name or,
// with none, by what it is, as Settings › Devices. Revoking an API key names its key the same way, covered in
// base/tests. Cancelled: the device stays.
test('assistant-card — in Spanish removing a device names it as Settings › Devices does, never by its id', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES-device';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  type Device = { id: string; name: string; agent: string; current: boolean };
  const listed = await api<{ devices: Device[] }>(context, A, 'GET', '/devices');
  expect(listed.status, JSON.stringify(listed.data)).toBe(200);
  const device = listed.data.devices.find((row) => row.current) ?? listed.data.devices[0];
  expect(device, JSON.stringify(listed.data.devices)).toBeDefined();
  // Named as the business names it in Settings › Devices (headless Chromium says no browser it knows, so it has nothing
  // else to be said by), and given its name back at the end.
  const rename = async (name: string) => {
    const renamed = await api(context, A, 'POST', '/devices/rename', { id: device!.id, name });
    expect(renamed.status, JSON.stringify(renamed.data)).toBe(200);
  };
  await rename('Barra');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, `E2E-ASK base__device__remove {"id":"${device!.id}"}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Quitar en Ajustes. Revisa cada dato antes de seguir.');
    // The record by the title its schema gives it, never «Registro».
    await expect(card(page)).toContainText('Dispositivo: Barra');
    await expect(card(page)).not.toContainText(device!.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const after = await api<{ devices: Device[] }>(context, A, 'GET', '/devices');
  expect(after.data.devices.map((row) => row.id)).toContain(device!.id);
  await rename(device!.name);
  await context.close();
});

// flow: RESERVATION-F06 RESERVATION-F08 (the card: BASE-F97)
// Every record a write of Reservations names by its id goes by the name its screen gives it, read as the person:
// booking says the customer by the name of their card (and the day and the time: a normal card's line carries its first
// three data); moving a reservation to another table says which reservation, as the book's own dialog does (its guest,
// its day and its time), and the table by its number. Cancelled: nothing is booked nor moved. What the test made is
// deleted at the end.
test('RESERVATION-F06 — booking a table, the card names the customer; moving a reservation, the reservation and its new table; never by an id', async ({ browser }) => {
  const KEY = 'FIX-HUB-RESERVATION-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const needed = ['customer', 'table', 'schedule', 'reservation'];
  const turnedOn: string[] = [];
  await turnOnMissing(context, A, needed, turnedOn);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const made = async <T>(path: string, body: unknown): Promise<T> => {
    const answer = await api<T>(context, A, 'POST', path, body);
    expect(answer.status, `${path}: ${JSON.stringify(answer.data)}`).toBe(201);
    return answer.data;
  };
  // A week from today, on the business's calendar (Madrid), at 21:30: always ahead, whenever the suite runs.
  const ahead = new Date(Date.now() + 7 * 24 * 3600 * 1000);
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid' }).format(ahead);
  const weekday = (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
  const stamp = String(Date.now() % 100_000_000).padStart(8, '0');
  const name = `Ana García ${stamp.slice(-4)}`;
  const phone = `+346${stamp}`;
  const customer = await made<{ id: string }>('/customer/customers', { name, phone });
  const zone = await made<{ id: string }>('/table/zones', { name: `E2E Card ${stamp}` });
  const table = await made<{ id: string; number: string }>('/table/tables', { zone_id: zone.id, number: '7', capacity: 4 });
  // The book takes reservations in a slot; one of the stack's own already covering that evening serves as well.
  const slot = await api<{ id: string }>(context, A, 'POST', '/reservation/time_slots', {
    day_of_week: weekday, start_time: '21:00', end_time: '23:30', max_reservations: 10,
  });
  expect([201, 409], JSON.stringify(slot.data)).toContain(slot.status);
  const booked = await made<{ id: string }>('/reservation/reservations', {
    customer_id: customer.id, guest_phone: phone, date, time: '21:30', party_size: 2, source: 'in_person',
  });
  // The words the book names it by, as its read by id answers them in the person's language («Ana García 1234 · 6 nov
  // 2026 · 21:30»): what the card must say of it.
  const read = await api<{ label: string }>(context, A, 'GET', `/reservation/reservations/detail?id=${booked.id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  const label = read.data.label;
  expect(label.startsWith(`${name} · `), label).toBe(true);
  expect(label, label).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  const ids = [customer.id, table.id, booked.id];

  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  // Booking: for whom (the customer's card by its name), the day and the time; the table goes among its data, with its
  // zone (hub#550).
  const booking = { customer_id: customer.id, date, time: '21:30:00', party_size: 2, table_id: table.id, source: 'in_person' };
  await ask(page, `E2E-ASK reservation__reservation__create ${JSON.stringify(booking)}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText(`Crear en Reservas: ${label}`);
  for (const raw of [date, 'in_person', ...ids]) await expect(card(page)).not.toContainText(raw);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Crear en Reservas: ${label}`);
    await captureStill(page, `${KEY}-create-${vp.label}`);
  }
  await cancelAtComputerSize(page);

  // Moving it to table 7: which reservation, as the book's dialog says it, and the new table with its zone, as Tables
  // names it («7 (E2E Card …)»: the number repeats across zones, hub#550).
  await ask(page, `E2E-ASK reservation__reservation__update ${JSON.stringify({ id: booked.id, table_id: table.id })}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Cambiar en Reservas: ${label} · 7 (E2E Card ${stamp})`);
    for (const raw of [date, ...ids]) await expect(card(page)).not.toContainText(raw);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const after = await api<{ table_id: string | null }>(context, A, 'GET', `/reservation/reservations/detail?id=${booked.id}`);
  expect(after.data.table_id).toBeNull();

  // What the test made, deleted; and the apps it turned on, off again.
  const gone = async (path: string, id: string) => {
    const answer = await api(context, A, 'POST', path, { id });
    expect(answer.status, `${path}: ${JSON.stringify(answer.data)}`).toBe(200);
  };
  await gone('/reservation/reservations/delete', booked.id);
  if (slot.status === 201) await gone('/reservation/time_slots/delete', slot.data.id);
  await gone('/table/tables/delete', table.id);
  await gone('/table/zones/delete', zone.id);
  await gone('/customer/customers/delete', customer.id);
  await leave(context, turnedOn);
});

// flow: FLOW-F03 FLOW-F24 (the card: BASE-F97)
// Every record a write of Automations names by its id (automation, draft, run, question) goes by the name its screen
// gives it, read as the person: pausing an automation says it by its name; resuming a run that stopped by an error says
// it as the History does, with its automation in front («Bienvenida 1234 · 6 nov 2026, 21:30»). Both are dangerous: the
// card lists each datum and asks to type. Cancelled: nothing is paused nor resumed. What the test made is deleted at
// the end.
test('FLOW-F03 — pausing an automation, the card names it; resuming a run, its automation and when; never by an id', async ({ browser }) => {
  const KEY = 'FIX-HUB-FLOW-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const needed = ['task', 'flow'];
  const turnedOn: string[] = [];
  await turnOnMissing(context, A, needed, turnedOn);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const stamp = String(Date.now() % 10_000).padStart(4, '0');
  const name = `Bienvenida ${stamp}`;
  // On by hand, one step that creates a task and no permission granted: run now, it stops by an error at that step.
  const created = await api<{ id: string }>(context, A, 'POST', '/flow/flows', {
    name,
    trigger: { kind: 'manual' },
    steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: `E2E ${stamp}` } }],
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  const flow = created.data;
  const on = await api(context, A, 'POST', '/flow/flows/set_enabled', { id: flow.id, enabled: true });
  expect(on.status, JSON.stringify(on.data)).toBe(200);
  const ran = await api<{ id: string; status: string }>(context, A, 'POST', '/flow/flows/run', { id: flow.id });
  expect(ran.status, JSON.stringify(ran.data)).toBe(200);
  expect(ran.data.status).toBe('failed');
  // The words the History names the run by, as its read by id answers them in the person's language: what the card says.
  const read = await api<{ label: string }>(context, A, 'GET', `/flow/runs/detail?id=${ran.data.id}`);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  const label = read.data.label;
  expect(label.startsWith(`${name} · `), label).toBe(true);
  expect(label, label).not.toMatch(/\d{4}-\d{2}-\d{2}/);

  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  // Pausing it: which automation, by its name.
  await ask(page, `E2E-ASK flow__flow__set_enabled ${JSON.stringify({ id: flow.id, enabled: false })}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Cambiar en Automatizaciones. Revisa cada dato antes de seguir.');
    await expect(card(page)).toContainText(`Automatización: ${name}`);
    await expect(card(page)).toContainText('Encendida: No');
    await expect(card(page)).not.toContainText(flow.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);

  // Resuming the run: which one, as the History says it, with its automation in front.
  await ask(page, `E2E-ASK flow__run__retry ${JSON.stringify({ id: ran.data.id })}`, { settle: false });
  await expect(card(page)).toBeVisible();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Reintentar en Automatizaciones. Revisa cada dato antes de seguir.');
    await expect(card(page)).toContainText(`Ejecución: ${label}`);
    await expect(card(page)).not.toContainText(ran.data.id);
    await captureConfirmation(page, `${KEY}-run-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const after = await api<{ enabled: boolean }>(context, A, 'GET', `/flow/flows/detail?id=${flow.id}`);
  expect(after.data.enabled).toBe(true);
  const still = await api<{ status: string }>(context, A, 'GET', `/flow/runs/detail?id=${ran.data.id}`);
  expect(still.data.status).toBe('failed');

  // What the test made, deleted (its history stays, as Automations keeps it); and the apps it turned on, off again.
  const gone = await api(context, A, 'POST', '/flow/flows/delete', { id: flow.id });
  expect(gone.status, JSON.stringify(gone.data)).toBe(200);
  await leave(context, turnedOn);
});

// flow: BASE-F98 (dangerous actions: type to confirm) and BASE-F97 (the card)
// A dangerous write's card shows what it will do, not only what it sends: Base's «Remove the PIN» names whose PIN goes,
// as its read (`base.person.detail`) answers it to who asks. One whose preview cannot be read shows no card: nothing to
// confirm blind. Cancelled, and the second refused: nothing changes.
test('BASE-F98 — a dangerous card shows what will happen, as its app reads it for the person; one whose preview cannot be read shows no card', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-HIGH-RISK-CARD-NO-OPERATION-PREVIEW';
  // The employee enters once, as on their first day: a fresh database knows only who has entered.
  await (await freshPage(browser, EMPLOYEE)).context().close();
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const people = await api<{ people: { id: string; name: string; email: string }[] }>(context, A, 'GET', '/people');
  expect(people.status, JSON.stringify(people.data)).toBe(200);
  const employee = people.data.people.find((person) => person.email === EMPLOYEE.email);
  expect(employee, JSON.stringify(people.data.people)).toBeDefined();
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, `E2E-ASK base__person__pin_remove {"person":"${employee!.id}"}`, { settle: false });
  await expect(card(page)).toBeVisible();
  const preview = card(page).locator('[data-testid="assistant-confirm-preview"]');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Quitar en Empleados. Revisa cada dato antes de seguir.');
    await expect(preview).toContainText('Lo que va a pasar');
    await expect(preview.locator('li')).toHaveText([`Nombre: ${employee!.name}`, `Correo: ${EMPLOYEE.email}`]);
    // The person by their name, as Employees reads it, never by the id sent.
    await expect(card(page)).toContainText(`Persona: ${employee!.name}`);
    await expect(card(page)).not.toContainText(employee!.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toHaveText('No se hizo, cancelado: Quitar en Empleados');
  // A person this business does not have: the preview cannot be read, so no card; the receipt says it failed.
  await ask(page, 'E2E-ASK base__person__pin_remove {"person":"saas:0"}');
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toHaveText('No se hizo, falló: Quitar en Empleados');
  await context.close();
});

test('an answer that says it changed something nothing changed is flagged, outside the answer', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'E2E-CLAIM crea la mesa 9');
  await expect(lastAnswer(page)).toHaveText(CLAIM_ANSWER.en);
  await expect(panel(page).locator('[data-testid="assistant-notice-claimed_change"]')).toContainText(
    'The assistant said it made a change, but no action was run. Nothing was changed.',
  );
  await shots(page, 'BASE-G117');
});

test('the conversation stays in the tab across reloads, «New conversation» empties it, and signing out forgets it', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'Hola');
  await page.reload();
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]')).toHaveText(['Hola']);
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  await shots(page, 'BASE-G120');
  await page.setViewportSize({ width: 1440, height: 900 });
  await panel(page).locator('[data-testid="assistant-new"]').click();
  await expect(panel(page).locator('[data-testid="assistant-empty"]')).toBeVisible();
  await ask(page, 'Hola otra vez');
  await panel(page).locator('[data-testid="assistant-close"]').click();
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name').click();
  await presented;
  await page.locator('ion-popover [data-testid="user-menu-logout"]').click();
  await page.waitForURL((url) => !url.href.startsWith(A));
  await login(page, A, '/', undefined, { fresh: true });
  await openPanel(page);
  await expect(panel(page).locator('[data-testid="assistant-empty"]')).toBeVisible();
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]')).toHaveCount(0);
});

test('from 80 % the foot says what is left and each answer moves it; a spent month says so in the answer and in the foot, with «Upgrade plan» to the owner and who to ask to an employee', async ({ page, browser }) => {
  await login(page, A, '/');
  spend(25);
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  const foot = panel(page).locator('[data-testid="assistant-usage"]');
  await expect(foot).toHaveText(/^You have 5 of 30 messages left this month\. They renew on \S+ 1\.$/);
  await shots(page, 'BASE-G122');
  await page.setViewportSize({ width: 1440, height: 900 });
  // An answer spends one: the foot counts it at once, with no reload.
  await ask(page, 'Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  await expect(foot).toHaveText(/^You have 4 of 30 messages left this month\. They renew on \S+ 1\.$/);
  spend(30);
  await ask(page, 'Hola');
  const failure = panel(page).locator('[data-testid="assistant-failure"]').last();
  await expect(failure).toContainText(/You have used all the assistant's messages of this month \(30 of 30\)\. They renew on \S+ 1\./);
  await expect(failure.locator('[data-testid="assistant-upgrade"]')).toHaveText(/Upgrade plan/);
  // The foot says the same as the answer, and «Upgrade plan» only once.
  await expect(foot).toHaveText(/^You have used all 30 messages of this month\. They renew on \S+ 1\.$/);
  await expect(panel(page).locator('[data-testid="assistant-upgrade"]')).toHaveCount(1);
  await shots(page, 'BASE-G122-spent');
  await page.setViewportSize({ width: 1440, height: 900 });
  // With no session of erplora.com in this browser, the answer's «Upgrade plan» still lands inside it (BASE-F11, hub#723).
  await upgradeLandsInside(page, failure.locator('[data-testid="assistant-upgrade"]'));

  const employee = await freshPage(browser);
  await employee.setViewportSize({ width: 1440, height: 900 });
  await home(employee);
  await openPanel(employee);
  await ask(employee, 'Hola');
  const theirs = panel(employee).locator('[data-testid="assistant-failure"]').last();
  await expect(theirs).toContainText('Ask whoever runs the business to upgrade the plan.');
  await expect(theirs.locator('[data-testid="assistant-upgrade"]')).toHaveCount(0);
  await employee.context().close();
});

test('with a plan without the assistant the foot says so, and its «Upgrade plan» lands inside erplora.com (BASE-F11)', async ({ page }) => {
  // The plan `a` has on erplora.com, or Free without a subscription (`effective_plan`).
  const plan =
    "coalesce((select s.plan_id from hubs_subscription s join hubs_hub h on h.id = s.hub_id where h.slug = 'a'), (select id from hubs_plan where slug = 'free'))";
  const allowance = saasSql(`select assistant_messages_per_month from hubs_plan where id = ${plan}`);
  saasSql(`update hubs_plan set assistant_messages_per_month = 0 where id = ${plan}`);
  try {
    await login(page, A, '/');
    await page.setViewportSize({ width: 1440, height: 900 });
    await home(page);
    await openPanel(page);
    const foot = panel(page).locator('[data-testid="assistant-no-plan"]');
    await expect(foot).toContainText('Your plan does not include the assistant.');
    await shots(page, 'BASE-G122-no-plan');
    await page.setViewportSize({ width: 1440, height: 900 });
    await upgradeLandsInside(page, foot.locator('[data-testid="assistant-no-plan-upgrade"]'));
  } finally {
    saasSql(`update hubs_plan set assistant_messages_per_month = ${allowance} where id = ${plan}`);
  }
});

test('«Report a problem» sends the answer with its question and a reason', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'Hola');
  await panel(page).locator('[data-testid="assistant-report"]').last().click();
  const dialog = page.locator('ion-modal[data-testid="assistant-report-dialog"]');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Report this answer');
  await dialog.locator('[data-testid="assistant-report-reason-harmful"]').click();
  await dialog.locator('[data-testid="assistant-report-comment"] textarea').fill('No es lo que pregunté');
  await shots(page, 'BASE-G123', () => expect(dialog).toBeVisible());
  await page.setViewportSize({ width: 1440, height: 900 });
  const sent = page.waitForResponse((response) => response.url().endsWith('/api/assistant/report'));
  await dialog.locator('[data-testid="assistant-report-dialog-submit"]').click();
  const answered = await sent;
  expect(answered.status()).toBe(200);
  // flow: BASE-F105 (hub#870) — the «Hola» turn brought no pages of the web: the Hub closes it saying so
  // (`done.web`) and the chat sends it with the report, so erplora.com's support reads the answer even with its search on.
  expect(answered.request().postDataJSON()).toMatchObject({ reason: 'harmful', question: 'Hola', web: false });
  await expect(page.locator('ion-toast')).toContainText('Thank you, we have received your report.');
  await expect(dialog).toBeHidden();
});

test('without connection the foot says so; a cut or a service down says so in the answer, with «Try again»', async ({ page, context }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await context.setOffline(true);
  await expect(panel(page).locator('[data-testid="assistant-offline"]')).toHaveText('No connection: you can write, and send when it is back.');
  await box(page).fill('Hola');
  await expect(panel(page).locator('[data-testid="assistant-send"] button')).toBeDisabled();
  await context.setOffline(false);
  await expect(panel(page).locator('[data-testid="assistant-offline"]')).toHaveCount(0);

  // The provider down: erplora.com says the assistant is not available; «Try again» asks the same again.
  await ask(page, 'E2E-DOWN');
  const failure = panel(page).locator('[data-testid="assistant-failure"]').last();
  await expect(failure).toContainText('The assistant is not available right now.');
  await expect(failure.locator('[data-testid="assistant-retry"]')).toBeVisible();
  await shots(page, 'BASE-G124');

  // The connection cut half-way: the Hub could not be reached.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route('**/api/assistant/turn', (route) => route.abort('internetdisconnected'));
  await ask(page, 'Hola');
  await expect(panel(page).locator('[data-testid="assistant-failure"]').last()).toContainText('The assistant could not be reached.');
  await page.unroute('**/api/assistant/turn');
  await panel(page).locator('[data-testid="assistant-retry"]').last().click();
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
});

test('what the assistant can do is what the person can: a write the employee may not make is refused', async ({ browser, context }) => {
  const page = await freshPage(browser);
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  const name = `Mesa empleado ${Date.now().toString(36)}`;
  await ask(page, `E2E-CREATE ${name}`);
  await expect(card(page)).toBeHidden();
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Not done, not allowed: Create in Demo');
  await expect(lastAnswer(page)).toContainText(NOT_DONE.en);
  // The tools offered to the model were only what this person may use.
  const tools = JSON.stringify((provider.seen.filter((s) => s.path === '/v1/chat/completions').at(-2)?.body as { tools?: unknown })?.tools);
  expect(tools).not.toContain('demo__item__create');
  await shots(page, 'BASE-G118');
  await page.context().close();
  const none = await api<{ rows: unknown[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`).catch(() => null);
  expect(none?.data.rows ?? []).toEqual([]);
});

test.describe('dictation and files', () => {
  test('a file goes with the question; one it cannot read is refused; a dictation lands in the box and is not sent', async ({ page }) => {
    await login(page, A, '/');
    await page.setViewportSize({ width: 1440, height: 900 });
    await home(page);
    await openPanel(page);
    const input = panel(page).locator('[data-testid="assistant-attach-input"]');
    await input.setInputFiles([
      { name: 'notas.md', mimeType: '', buffer: Buffer.from('# Carta\n\nCafé 1,50 €') },
      { name: 'foto.heic', mimeType: 'image/heic', buffer: Buffer.from('x') },
    ]);
    await expect(panel(page).locator('[data-testid="assistant-file"]')).toHaveText(['notas.md']);
    await expect(panel(page).locator('[data-testid="assistant-composer-problem"]')).toHaveText(
      'foto.heic cannot be attached: images, PDF, Word, Excel, text or CSV.',
    );
    await ask(page, '¿Qué dice este archivo?');
    await expect(panel(page).locator('[data-testid="assistant-bubble-user"]').last()).toContainText('notas.md');
    const asked = JSON.stringify(provider.seen.filter((s) => s.path === '/v1/chat/completions').at(-1)?.body);
    expect(asked).toContain('Café 1,50 €');

    // Dictation: the browser's fake microphone; erplora.com transcribes it with the e2e provider.
    const mic = panel(page).locator('[data-testid="assistant-mic"]');
    await mic.click();
    await expect(mic).toHaveAttribute('aria-pressed', 'true');
    await page.waitForTimeout(1200);
    const before = await answers(page).count();
    await mic.click();
    await expect(box(page)).toHaveValue(DICTATION);
    expect(await answers(page).count()).toBe(before);
    await shots(page, 'BASE-G112');
  });
});
