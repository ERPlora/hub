// What the e2e of the assistant's confirmation card shares (BASE-F97): the hooks of a spec that asks for a write through
// the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`; the SaaS seeded with it, README «El asistente»),
// around the spec's own cleaning and the apps it needs, and the card as the server sends it and the person sees it. The
// specs of the card that still carry their own copy move to it when they are touched (hub#837).
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { DONE, type Provider, startProvider } from './assistant-provider';
import { answers, box, card, emptyMonth, panel, saasSql, send } from './assistant-real';
import { A, login, turnOffTurnedOn, turnOnMissing } from './helpers';
import { STACK } from './stack';

/** An id as a schema's `format: uuid` takes it: never on a card. */
export const AN_ID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
export const VIEWPORTS = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** How long the first turn of a stack that just started may take. */
const FIRST_TURN_MS = 120_000;

/** Registers the hooks of a spec of the card: the provider, the apps `needed` turned on (a business is born with every
 *  app off) and off again after, only those it turned on, and `cleanUp` before each test and after the last. */
export function cardSpec(needed: string[], cleanUp: () => void): void {
  let provider: Provider | undefined;
  const turnedOn: string[] = [];
  test.beforeAll(async ({ browser }) => {
    provider = await startProvider(PROVIDER_PORT);
    const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
    expect(seeded, `the SaaS ${STACK.saasDatabase} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page, A, '/');
    await turnOnMissing(context, A, needed, turnedOn);
    // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    await context.close();
  });
  test.beforeEach(() => {
    emptyMonth();
    cleanUp();
  });
  test.afterAll(async ({ browser }) => {
    cleanUp();
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page, A, '/');
    await turnOffTurnedOn(context, A, turnedOn);
    await context.close();
    await provider?.close();
  });
}

/** The owner of `a`, signed in, with the card in `language`. */
export async function ownerIn(browser: Browser, language: string): Promise<[BrowserContext, Page]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  return [context, page];
}

/** Writes `text` and sends it; resolves once its answer has started (its card is up before the turn ends). */
export async function ask(page: Page, text: string): Promise<void> {
  await expect(send(page)).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
}

/** A card as the server sends it: each datum by its label and in words, a list `named` when the screen says its items
 *  (live.assistant.NAMED). */
export type SentCard = { fields: { name: string; label: string; value: unknown; named?: boolean }[] };

/** The card of the confirm frame of a turn's answer (`text/event-stream`: one `data: <JSON>` per frame), if any. */
export function confirmedCard(stream: string): SentCard | undefined {
  const frames = stream
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => JSON.parse(line.slice(5)) as { type: string; card?: SentCard });
  return frames.find((frame) => frame.type === 'confirm')?.card;
}

/** Asks for the write `tool` and returns what its card sends, never saying an id on the way. */
export async function fieldsOf(page: Page, tool: string, data: Record<string, unknown>): Promise<SentCard['fields']> {
  const answer = page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
    { timeout: FIRST_TURN_MS },
  );
  await ask(page, `E2E-ASK ${tool} ${JSON.stringify(data)}`);
  // The card comes with the answer of the turn, which waits for the gateway: seconds on a stack that just started.
  const { fields } = confirmedCard(await (await answer).text())!;
  await expect(card(page)).toBeVisible();
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).not.toContainText(AN_ID);
  return fields;
}

/** The datum `name` of the card of `tool`. */
export async function datumOf(
  page: Page,
  tool: string,
  data: Record<string, unknown>,
  name = 'id',
): Promise<SentCard['fields'][number]> {
  const fields = await fieldsOf(page, tool, data);
  const field = fields.find((one) => one.name === name);
  expect(field, `the card of ${tool} names no ${name}: ${JSON.stringify(fields)}`).toBeDefined();
  return field!;
}

/** Cancels the card: nothing is done. */
export async function cancel(page: Page): Promise<void> {
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
}

/** The word typed in the card that asks for it and the card confirmed: the assistant says it is done. */
export async function confirmedWithTheWord(page: Page): Promise<void> {
  await card(page).locator('[data-testid="assistant-confirm-input"] input').fill('confirm');
  await expect(card(page).locator('[data-testid="assistant-confirm-submit"] button')).toBeEnabled();
  await card(page).locator('[data-testid="assistant-confirm-submit"]').click();
  await expect(card(page)).toBeHidden();
  await expect(panel(page).locator('[data-testid="assistant-bubble-assistant"]').last()).toContainText(DONE.en);
}
