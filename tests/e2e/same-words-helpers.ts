// e2e helpers of hub#888: a window whose save is refused for several fields with the same words, and what each field
// shows. FormModal takes the mark away from the refused field a person corrects, told by its `name`; the specs refuse
// in the browser (`page.route`), so nothing is created, and read the mark as Ionic paints it (`ion-invalid` and the
// words under the field). Shared by form-modal-picker-same-words.spec.ts and table-reservation-same-words.spec.ts.
import { expect, type Locator, type Page } from '@playwright/test';

/** The window's save (a POST to `save`, Playwright's glob of its API path) is refused for `keys`, every one with the
 *  same `words`; `page.unroute(save)` lets saves through again. */
export async function refuseWithTheSameWords(page: Page, save: string, keys: readonly string[], words: string): Promise<void> {
  await page.route(save, (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const body = { error: { code: 'invalid_payload', message: words, fields: Object.fromEntries(keys.map((key) => [key, words])) } };
    return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

/** `field` is marked: Ionic's `ion-invalid`, with `words` under it. */
export async function expectMarked(field: Locator, words: string): Promise<void> {
  await expect(field).toHaveClass(/ion-invalid/);
  await expect(field).toContainText(words);
}

/** `field` is not marked: no `ion-invalid`, and not `words` under it. */
export async function expectUnmarked(field: Locator, words: string): Promise<void> {
  await expect(field).not.toHaveClass(/ion-invalid/);
  await expect(field).not.toContainText(words);
}
