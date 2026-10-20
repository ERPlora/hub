// What the specs of Automations share (apps/flow): a signed-in context in a size, picking in an `IonSelect`
// popover, confirming a dialog, the id of the automation the editor shows, and the API setup of an
// automation (the screens under test build their own steps; the API only sets the stage).
import { type Browser, type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, type Credentials, login, OWNER, shown } from './helpers';

export async function signedIn(
  browser: Browser,
  next: string,
  viewport: { width: number; height: number },
  credentials: Credentials = OWNER,
) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

/** Picks `text` in the popover of the `IonSelect` `testid` of the page shown. */
export async function choose(page: Page, testid: string, text: string): Promise<void> {
  await shown(page).locator(`[data-testid="${testid}"]`).click();
  const popover = page.locator('ion-popover.select-popover:not(.overlay-hidden)');
  await popover.locator('ion-radio', { hasText: text }).first().click();
  await expect(popover).toHaveCount(0);
}

/** Confirms the dialog titled `title` with its main button. */
export async function confirmDialog(page: Page, title: string, beforeConfirm?: () => Promise<void>): Promise<void> {
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: title });
  await expect(dialog.locator('.ep-form-modal__submit')).toBeInViewport();
  if (beforeConfirm) await beforeConfirm();
  await dialog.locator('.ep-form-modal__submit').click();
  await expect(dialog).toBeHidden();
}

export const idFromUrl = (page: Page): string => new URL(page.url()).pathname.split('/').at(-1)!;

/** An automation that starts by hand, made through the API with `steps` and `grants`, switched on. */
export async function manualFlow(context: BrowserContext, name: string, steps: unknown[], grants: string[]): Promise<string> {
  const created = await api<{ id: string }>(context, A, 'POST', '/flow/flows', { name, trigger: { kind: 'manual' }, steps });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  const id = created.data.id;
  if (grants.length) expect((await api(context, A, 'POST', '/flow/flows/grant', { id, operations: grants })).status).toBe(200);
  expect((await api(context, A, 'POST', '/flow/flows/set_enabled', { id, enabled: true })).status).toBe(200);
  return id;
}
