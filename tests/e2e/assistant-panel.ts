// How the specs of the Hub's assistant drive its panel and its card, as a person does: open the panel, ask, decide
// the card, and wait for the dangerous card to settle before its capture; and the card as the server sends it. The
// hooks of a spec of the panel are in provider-helpers.ts, those of a spec of the card in assistant-card-helpers.ts.
import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { DONE } from './assistant-provider';
import { A, capture, EMPLOYEE, exposeMovingInPage, login, THREE_SIZES as VIEWPORTS, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { assistantDoor, openAssistant } from './topbar';

// ── The panel ──

export const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
export const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
/** The assistant's answers, each one its row (a failure before any word has no bubble). */
export const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
/** The last answer's bubble: its words. */
export const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
export const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
/** «Send», offered again once a turn has ended. */
export const send = (page: Page): Locator => panel(page).locator('[data-testid="assistant-send"]');
/** The receipts under the answers: what the Hub says it did with each write. */
export const receipts = (page: Page): Locator => panel(page).locator('[data-testid="assistant-receipt"]');
/** «What will happen» on the dangerous card: what the write would leave, as the app's preview says it. */
export const previewBlock = (page: Page): Locator => card(page).locator('[data-testid="assistant-confirm-preview"]');
/** What is left of the month's messages, under the box. */
export const foot = (page: Page): Locator => panel(page).locator('[data-testid="assistant-usage"]');

/** Answers the card with its button (`submit` or `cancel`) and waits until it has gone: while Ionic dismisses a modal,
 *  its focus trap keeps the keyboard inside it. */
export async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

/** Cancels the card: nothing is done. */
export const cancel = (page: Page): Promise<void> => decide(page, 'cancel');

/** Cancels the Spanish card: nothing was done, and the answer says so. */
export async function cancelInSpanish(page: Page): Promise<void> {
  await cancel(page);
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
}

/** The word typed in the card that asks for it and the card confirmed: the assistant says it is done. */
export async function confirmedWithTheWord(page: Page): Promise<void> {
  await card(page).locator('[data-testid="assistant-confirm-input"] input').fill('confirm');
  await expect(card(page).locator('[data-testid="assistant-confirm-submit"] button')).toBeEnabled();
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText(DONE.en);
}

export async function home(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(assistantDoor(page)).toBeVisible();
}

/** On a phone the panel opens once «⋮» has gone: while Ionic dismisses it, its focus trap keeps the keyboard (hub#742). */
export async function openPanel(page: Page): Promise<void> {
  await openAssistant(page);
  await expect(box(page)).toBeVisible();
}

/** The home, loaded again, with the panel open. */
export async function openPanelAtHome(page: Page): Promise<void> {
  await home(page);
  await openPanel(page);
}

/** The panel open on the home at a computer's size. */
export async function openPanelAtTheDesk(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPanelAtHome(page);
}

/** The owner signed in, with the panel open on the home at a computer's size. */
export async function panelAtTheDesk(page: Page): Promise<void> {
  await login(page, A, '/');
  await openPanelAtTheDesk(page);
}

/** The Hub's language cookie, as the sign-in sets it: the pages loaded after it are in `language`. */
async function speaking(context: BrowserContext, language: string): Promise<void> {
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
}

/** The panel open on the home at a computer's size, with the app in Spanish: where a card's words are looked at. */
export async function openPanelInSpanish(page: Page): Promise<void> {
  await speaking(page.context(), 'es');
  await openPanelAtTheDesk(page);
}

/** The owner of `a`, signed in, with the app in `language` from the next page loaded. */
export async function ownerIn(browser: Browser, language: string): Promise<[BrowserContext, Page]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await speaking(context, language);
  return [context, page];
}

/** Writes `text` and sends it with Enter; resolves when the turn has ended (the composer offers «Send» again). */
export async function ask(page: Page, text: string, options: { settle?: boolean } = {}): Promise<void> {
  // The previous turn has ended (its text may arrive before its end): while one runs, Enter sends nothing.
  await expect(send(page)).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
  if (options.settle ?? true) await expect(send(page)).toBeVisible({ timeout: 30_000 });
}

/** Asks for what needs the person's say (`text`): its card comes up within `timeout` (Playwright's by default), while
 *  the turn may still run. */
export async function askForACard(page: Page, text: string, options: { timeout?: number } = {}): Promise<void> {
  await ask(page, text, { settle: false });
  await expect(card(page)).toBeVisible(options);
}

/** A card as the server sends it: each datum by its label and in words, a list `named` when the screen says its items
 *  (live.assistant.NAMED). */
export type SentCard = { fields: { name: string; label: string; kind: string; value: unknown; named?: boolean; money?: unknown }[] };

/** The card of the confirm frame of a turn's answer (`text/event-stream`: one `data: <JSON>` per frame), if any. */
export function confirmedCard(stream: string): SentCard | undefined {
  const frames = stream
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => JSON.parse(line.slice(5)) as { type: string; card?: SentCard });
  return frames.find((frame) => frame.type === 'confirm')?.card;
}

/** The card the server sends for the person to confirm, as it arrives: the answer of the turn that carries it (a first
 *  turn may only ask for the tool). */
export async function sentCard(page: Page): Promise<SentCard> {
  const answer = await page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
  );
  return confirmedCard(await answer.text())!;
}

/** Asks for the price write `tool` with `data`: its card comes up, and the server sends its price as 15.00 in the minor
 *  unit of a list in dollars, with that currency's two decimals. */
export async function askForAPriceInDollars(page: Page, tool: string, data: Record<string, unknown>): Promise<void> {
  const sent = sentCard(page);
  await askForACard(page, `E2E-ASK ${tool} ${JSON.stringify(data)}`);
  expect((await sent).fields.find((field) => field.name === 'price')).toMatchObject({
    kind: 'money',
    value: 1500,
    money: { currency: 'USD', decimals: 2 },
  });
}

/** The last answer captured at each size, as `<key>-<size>`. */
export async function lastAnswerAtEachSize(page: Page, key: string): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(lastAnswer(page)).toBeVisible();
    await capture(page, `${key}-${vp.label}`);
  }
}

/** The panel as a person sees it at each size; `settled`, when given, must hold at the very moment of each capture. */
export async function shots(
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
export async function confirmationReady(page: Page): Promise<void> {
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
export async function confirmationSettled(page: Page): Promise<boolean> {
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
export async function signedInWith(browser: Browser, needed: readonly string[]): Promise<{ context: BrowserContext; page: Page; turnedOn: string[] }> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const turnedOn: string[] = [];
  await turnOnMissing(context, A, needed, turnedOn);
  return { context, page, turnedOn };
}

/** Cancels the Spanish card at a computer's size: nothing was done, and the answer says so. */
export async function cancelAtComputerSize(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await cancelInSpanish(page);
}

/** The page saved as `name` once nothing moves. */
export async function captureStill(page: Page, name: string): Promise<void> {
  await untilStill(page);
  await capture(page, name);
}

/** The dangerous card saved as `name`, with «Confirmation» focused and nothing moving. */
export async function captureConfirmation(page: Page, name: string): Promise<void> {
  await confirmationReady(page);
  await untilStill(page);
  expect(await confirmationSettled(page), `${name} caught before it settled`).toBe(true);
  await capture(page, name);
}

/** Leaves `a` with the apps it had and closes the context. */
export async function leave(context: BrowserContext, turnedOn: string[]): Promise<void> {
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
}

export async function freshPage(browser: Browser, credentials = EMPLOYEE): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/', credentials);
  return page;
}
