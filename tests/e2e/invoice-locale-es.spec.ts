// flow: invoice-locale — FIX-HUB-INVOICE-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP: Django joins every app's Spanish
// catalogue and the first that translates a message wins, so the assistant's card named the issuer's data with
// customer's words, «NIF/CIF» and «Dirección». Changing the issuer is a dangerous write, whose card lists every datum by
// its name: it names them as the Issuer screen does, «NIF» and «Domicilio». The owner, in Spanish, asks the assistant
// (the e2e's provider, `E2E-ASK`: assistant-provider.ts; README «El asistente») to change the issuer's tax ID and
// address; the card says them so at 390, 834 and 1440, and «Cancel» changes nothing. (A series' «Activa» rides a normal
// card, a single line of values with no names: apps/invoice/tests/test_i18n.py checks the name the server gives it.)
import { execSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, capture, compactBar, login, REPO_DIR, shown } from './helpers';
import { issuerNow } from './invoice-helpers';
import { STACK } from './stack';

const KEY = 'FIX-HUB-INVOICE-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP';
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

/** The month's assistant messages of the business `a` back to none: a run never spends the plan's allowance. */
function unspend(): void {
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

test.beforeAll(async () => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
});

test.afterAll(async () => {
  await provider?.close();
  unspend();
});

test.beforeEach(() => {
  unspend();
});

// ── The assistant's panel (as invoice-assistant.spec.ts drives it) ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function openPanel(page: Page): Promise<void> {
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/** Writes `text` and sends it with Enter, without waiting for the turn to end (a card stops it half-way). */
async function ask(page: Page, text: string): Promise<void> {
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
}

async function cancel(page: Page): Promise<void> {
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
}

type SentCard = { fields: { name: string; label: string; value: unknown }[] };

/** The card of the confirm frame of a turn's answer (`text/event-stream`: one `data: <JSON>` per frame), if any. */
function confirmedCard(stream: string): SentCard | undefined {
  const frames = stream
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => JSON.parse(line.slice(5)) as { type: string; card?: SentCard });
  return frames.find((frame) => frame.type === 'confirm')?.card;
}

/** The card the server sends for the person to confirm, as it arrives: the answer of the turn that carries it. */
async function sentCard(page: Page): Promise<SentCard> {
  const answer = await page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
  );
  return confirmedCard(await answer.text())!;
}

const labelsOf = (sent: SentCard) => Object.fromEntries(sent.fields.map((field) => [field.name, field.label]));

/** The owner on `a` in Spanish, on the Issuer screen: the Hub's language cookie, as the sign-in sets it. */
async function spanishOwner(context: BrowserContext): Promise<Page> {
  const page = await context.newPage();
  await login(page, A, '/invoice/issuer');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/invoice/issuer`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return page;
}

test('invoice-locale — in Spanish the dangerous card of changing the issuer says «NIF» and «Domicilio», as the Issuer screen does', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-ES' });
  try {
    const page = await spanishOwner(context);
    const issuerBefore = await issuerNow(context);
    await openPanel(page);

    // «Cambia el NIF y el domicilio del emisor»: both by the Issuer screen's words.
    const sent = sentCard(page);
    const issuer = { legal_name: 'e2e Peluquería Ana SL', tax_id: 'B76543214', address: 'Calle Sol 9' };
    await ask(page, `E2E-ASK invoice__issuer__update ${JSON.stringify(issuer)}`);
    await expect(card(page)).toBeVisible({ timeout: 30_000 });
    expect(labelsOf(await sent)).toMatchObject({ tax_id: 'NIF', address: 'Domicilio' });
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await expect(card(page)).toContainText('NIF: B76543214');
      await expect(card(page)).toContainText('Domicilio: Calle Sol 9');
      await expect(card(page)).not.toContainText('NIF/CIF');
      await expect(card(page)).not.toContainText('Dirección');
      await capture(page, `${KEY}-${viewport.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);
    // Cancelled: the issuer is as it was.
    expect(await issuerNow(context)).toEqual(issuerBefore);
  } finally {
    await context.close();
  }
});
