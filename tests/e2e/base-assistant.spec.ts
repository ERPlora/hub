// The assistant of the Hub (APP-BASE-9), end to end with its real dependencies: the Hub of this stack, its SaaS's
// gateway (`/internal/assistant/*`, `/internal/speech/transcribe`) and, behind it, the e2e's provider
// (assistant-provider.ts, an OpenAI-compatible server on 127.0.0.1 that this spec starts): no mock between the
// browser and the provider, no real provider, no real key. The SaaS must be seeded with that provider (README of this
// folder, «El asistente»): `assistant_seed.py gateway http://127.0.0.1:<E2E_AI_PROVIDER_PORT>/v1`.
// The month's messages of the business `a` are set on the SaaS's database before each test (`spend`), so a run never
// spends the plan's allowance and the 80 % and the spent month can be seen.
// flow: BASE-G110 BASE-G111 BASE-G112 BASE-G113 BASE-G114 BASE-G115 BASE-G116 BASE-G117 BASE-G118 BASE-G119
// flow: BASE-G120 BASE-G121 BASE-G122 BASE-G123 BASE-G124
import { execSync } from 'node:child_process';

import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { CLAIM_ANSWER, DICTATION, GREETING, type Provider, startProvider } from './assistant-provider';
import { A, api, EMPLOYEE, login, REPO_DIR, shot, shown, untilStill } from './helpers';
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
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]');
const lastAnswer = (page: Page): Locator => answers(page).last();
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');

/** Answers the card with its button (`submit` or `cancel`) and waits until it has gone: while Ionic dismisses a modal,
 *  its focus trap keeps the keyboard inside it. */
async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

async function home(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(shown(page).locator('[data-testid="assistant-button"]')).toBeVisible();
}

async function openPanel(page: Page): Promise<void> {
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await shown(page).locator('[data-testid="assistant-button"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
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

/** The panel as a person sees it at each size, saved as `APP-BASE-9-<key>-<size>`. */
async function shots(page: Page, key: string, ready: () => Promise<void> = async () => undefined): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await ready();
    await untilStill(page);
    await page.screenshot({ path: shot(`APP-BASE-9-${key}-${vp.label}`) });
  }
}

async function freshPage(browser: Browser, credentials = EMPLOYEE): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/', credentials);
  return page;
}

// The browser's fake microphone (BASE-G112's dictation): a worker-wide launch option, so for the whole file.
test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

test('BASE-G110 — the sparkles open the panel on the right: docked from 768 px, over the screen on a phone; Escape, × and the veil close it; it stays open across screens and reloads', async ({ page }) => {
  await login(page, A, '/');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await home(page);
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
    await untilStill(page);
    await page.screenshot({ path: shot(`APP-BASE-9-BASE-G110-${vp.label}`) });
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

test('BASE-G121 — «Ask the assistant» on the setup card opens it on the setup; a shortcut asks at once', async ({ page }) => {
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
  await expect(lastAnswer(page)).toContainText(GREETING);
  // The setup's instructions went to the model with the checklist read again by the Hub (hub#373).
  const instructions = JSON.stringify(provider.seen.filter((s) => s.path === '/v1/chat/completions').at(-1)?.body);
  expect(instructions).toContain('checklist');
});

test('BASE-G111 BASE-G113 BASE-G114 — a question and its answer: written as it comes, with its format; «Stop» keeps what came; «Go to Settings» opens it and closes the panel', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'Hola');
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]').last()).toHaveText('Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING);
  await shots(page, 'BASE-G111');

  // «Stop» half-way: what was written stays, the bubble says it stopped.
  await ask(page, 'E2E-SLOW', { settle: false });
  await expect(lastAnswer(page)).toContainText('Esta respuesta es larga');
  await panel(page).locator('[data-testid="assistant-stop"]').click();
  await expect(lastAnswer(page)).toContainText('Stopped.');
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible();

  await ask(page, 'E2E-FORMAT ¿Cómo van las ventas?');
  const answer = lastAnswer(page);
  await expect(answer.locator('h3, h4, h5, h6').first()).toHaveText('Ventas de hoy');
  await expect(answer.locator('strong').first()).toHaveText('120 €');
  await expect(answer.locator('li')).toHaveCount(2);
  await expect(answer.locator('table tbody tr')).toHaveCount(2);
  await expect(answer.locator('a[href="/settings#business"]')).toHaveText('Ajustes');
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

test('BASE-G115 — a write waits on its card: «Run it» runs it as the person; «Cancel» runs nothing', async ({ page, context }) => {
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
  await expect(lastAnswer(page)).toContainText('Hecho.');
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Done: Create in Demo');
  const made = await api<{ rows: { name: string }[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`);
  expect(made.data.rows.map((row) => row.name)).toEqual([name]);

  const other = `${name} no`;
  await ask(page, `E2E-CREATE ${other}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Not done, cancelled: Create in Demo');
  const none = await api<{ rows: unknown[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(other)}`);
  expect(none.data.rows).toEqual([]);
});

test('BASE-G119 — several things in a row: the read runs by itself, the write waits on its card', async ({ page, context }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  const name = `Mesa cadena ${Date.now().toString(36)}`;
  await ask(page, `E2E-CHAIN ${name}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText(`Create in Demo: ${name}`);
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText('Hecho.');
  // The read went to the model with its result, without a card; one message spent for the whole turn.
  const chats = provider.seen.filter((s) => s.path === '/v1/chat/completions').slice(-3);
  expect(JSON.stringify(chats[1].body)).toContain('"role":"tool"');
  const made = await api<{ rows: { name: string }[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`);
  expect(made.data.rows.map((row) => row.name)).toEqual([name]);
  await shots(page, 'BASE-G119');
});

test('BASE-G116 — a dangerous write lists its data and runs only after typing the word', async ({ page, context }) => {
  await login(page, A, '/');
  const item = await api<{ id: string }>(context, A, 'POST', '/demo/items', { name: `Para borrar ${Date.now().toString(36)}` });
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, `E2E-DELETE ${item.data.id}`, { settle: false });
  await expect(card(page)).toBeVisible();
  await expect(card(page)).toContainText('Delete in Demo. Check each datum before going on.');
  await expect(card(page)).toContainText(`Record: ${item.data.id}`);
  // The native button inside `ion-button` (its host carries no role for `aria-disabled` to count).
  const submit = card(page).locator('[data-testid="assistant-confirm-submit"] button');
  await expect(submit).toBeDisabled();
  await shots(page, 'BASE-G116', () => expect(card(page)).toBeVisible());
  await page.setViewportSize({ width: 1440, height: 900 });
  await card(page).locator('[data-testid="assistant-confirm-input"] input').fill('confirm');
  await expect(submit).toBeEnabled();
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText('Hecho.');
  const gone = await api(context, A, 'GET', `/demo/items/detail?id=${item.data.id}`);
  expect(gone.status).toBe(404);
});

test('BASE-G117 — an answer that says it changed something nothing changed is flagged, outside the answer', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'E2E-CLAIM crea la mesa 9');
  await expect(lastAnswer(page)).toHaveText(CLAIM_ANSWER);
  await expect(panel(page).locator('[data-testid="assistant-notice-claimed_change"]')).toContainText(
    'The assistant said it made a change, but no action was run. Nothing was changed.',
  );
  await shots(page, 'BASE-G117');
});

test('BASE-G120 — the conversation stays in the tab across reloads, «New conversation» empties it, and signing out forgets it', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await ask(page, 'Hola');
  await page.reload();
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]')).toHaveText(['Hola']);
  await expect(lastAnswer(page)).toHaveText(GREETING);
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

test('BASE-G122 — from 80 % the foot says what is left; a spent month says so, with «Upgrade plan» to the owner and who to ask to an employee', async ({ page, browser }) => {
  await login(page, A, '/');
  spend(25);
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await expect(panel(page).locator('[data-testid="assistant-usage"]')).toHaveText(/^You have 5 of 30 messages left this month\. They renew on \S+ 1\.$/);
  await shots(page, 'BASE-G122');
  await page.setViewportSize({ width: 1440, height: 900 });
  spend(30);
  await ask(page, 'Hola');
  const failure = panel(page).locator('[data-testid="assistant-failure"]').last();
  await expect(failure).toContainText("You have used all the assistant's messages of this month (30 of 30).");
  await expect(failure.locator('[data-testid="assistant-upgrade"]')).toHaveText(/Upgrade plan/);
  await page.screenshot({ path: shot('APP-BASE-9-BASE-G122-spent-1440') });

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

test('BASE-G123 — «Report a problem» sends the answer with its question and a reason', async ({ page }) => {
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
  expect((await sent).status()).toBe(200);
  await expect(page.locator('ion-toast')).toContainText('Thank you, we have received your report.');
  await expect(dialog).toBeHidden();
});

test('BASE-G124 — without connection the foot says so; a cut or a service down says so in the answer, with «Try again»', async ({ page, context }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  await context.setOffline(true);
  await expect(panel(page).locator('[data-testid="assistant-offline"]')).toHaveText('No connection: you can write, and send when it is back.');
  await box(page).fill('Hola');
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeDisabled();
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
  await expect(lastAnswer(page)).toHaveText(GREETING);
});

test('BASE-G118 — what the assistant can do is what the person can: a write the employee may not make is refused', async ({ browser, context }) => {
  const page = await freshPage(browser);
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
  const name = `Mesa empleado ${Date.now().toString(36)}`;
  await ask(page, `E2E-CREATE ${name}`);
  await expect(card(page)).toHaveCount(0);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Not done, not allowed: Create in Demo');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  // The tools offered to the model were only what this person may use.
  const tools = JSON.stringify((provider.seen.filter((s) => s.path === '/v1/chat/completions').at(-2)?.body as { tools?: unknown })?.tools);
  expect(tools).not.toContain('demo__item__create');
  await shots(page, 'BASE-G118');
  await page.context().close();
  const none = await api<{ rows: unknown[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`).catch(() => null);
  expect(none?.data.rows ?? []).toEqual([]);
});

test.describe('dictation and files', () => {
  test('BASE-G112 — a file goes with the question; one it cannot read is refused; a dictation lands in the box and is not sent', async ({ page }) => {
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
