// The switch that turns an app on or off in Apps, its row's note (why it cannot move, or what went wrong) and how a
// person flips it.
import { expect, type Locator, type Page } from '@playwright/test';

import { appRow } from './screen';

/** The `ion-toggle` of `id`'s row, in the list or on its card. */
export const appSwitch = (page: Page, id: string): Locator => appRow(page, id).locator('ion-toggle');

/** Why `id`'s switch cannot move, or what went wrong: under its state in the list, a line of its card. */
export const appNote = (page: Page, id: string): Locator => appRow(page, id).locator('.data-table__cell-note, .data-table__card-note');

/** Flips `id`'s switch as a person does: a tap on it. */
export async function flipApp(page: Page, id: string): Promise<void> {
  await appSwitch(page, id).click();
}

/** `id`'s switch shows `checked` and can (or cannot) move, and its row says `note` when one is given. */
export async function expectSwitch(page: Page, id: string, state: { checked: boolean; disabled: boolean; note?: string }): Promise<void> {
  await expect(appSwitch(page, id)).toHaveJSProperty('checked', state.checked);
  await expect(appSwitch(page, id)).toHaveJSProperty('disabled', state.disabled);
  if (state.note !== undefined) await expect(appNote(page, id)).toHaveText(state.note);
}
