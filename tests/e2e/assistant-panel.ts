// What the specs of the Hub's assistant (base-assistant.spec.ts and base-assistant-card*.spec.ts) share: the hooks
// that start the e2e's provider and leave `a` with no message spent this month before each test, and the way they
// drive the panel and its card.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import type { Provider } from './assistant-provider';
import { saasSql } from './assistant-real';
import { A, capture, EMPLOYEE, exposeMovingInPage, login, THREE_SIZES as VIEWPORTS, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { providerSpec } from './provider-helpers';
import { assistantDoor, openAssistant } from './topbar';

/** This month's messages of the business `a` on erplora.com. */
export function spend(messages: number): void {
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

/** Registers the hooks of a spec of the panel: the e2e's provider started before its tests and closed after them
 *  (`providerSpec`, with nothing else to clean), and no message of `a` spent this month before each test. Gives the
 *  provider once they have run. */
export function panelSpec(): () => Provider {
  test.beforeEach(() => {
    spend(0);
  });
  return providerSpec(() => undefined);
}

// ── The panel ──

export const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
export const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
/** The assistant's answers, each one its row (a failure before any word has no bubble). */
export const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
/** The last answer's bubble: its words. */
export const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
export const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');

/** Answers the card with its button (`submit` or `cancel`) and waits until it has gone: while Ionic dismisses a modal,
 *  its focus trap keeps the keyboard inside it. */
export async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
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

/** The panel open on the home at a computer's size. */
export async function openPanelAtTheDesk(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await openPanel(page);
}

/** The owner signed in, with the panel open on the home at a computer's size. */
export async function panelAtTheDesk(page: Page): Promise<void> {
  await login(page, A, '/');
  await openPanelAtTheDesk(page);
}

/** The panel open on the home at a computer's size, with the app in Spanish: where a card's words are looked at. */
export async function openPanelInSpanish(page: Page): Promise<void> {
  await page.context().addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await openPanelAtTheDesk(page);
}

/** Writes `text` and sends it with Enter; resolves when the turn has ended (the composer offers «Send» again). */
export async function ask(page: Page, text: string, options: { settle?: boolean } = {}): Promise<void> {
  // The previous turn has ended (its text may arrive before its end): while one runs, Enter sends nothing.
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
  if (options.settle ?? true) await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
}

/** Asks for what needs the person's say (`text`): its card comes up, while the turn may still run. */
export async function askForACard(page: Page, text: string): Promise<void> {
  await ask(page, text, { settle: false });
  await expect(card(page)).toBeVisible();
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
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
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
