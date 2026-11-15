// e2e helpers of hub#888: a window whose save is refused for several fields with the same words, and what each field
// shows. FormModal takes the mark away from the refused field a person corrects, told by its `name`; the specs refuse
// in the browser (`page.route`), so nothing is created, and read the mark as Ionic paints it (`ion-invalid` and the
// words under the field). Shared by form-modal-picker-same-words.spec.ts and by the specs of each app's windows, which
// declare their tests with `testTheMarksGoOneByOne`, or walk a window of their own with `testEachSameWordsCase`.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { capture, psql, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { VIEWPORTS } from './sale-helpers';
import { ownerPage } from './service-helpers';

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

/** A window of a spec: where it opens, the save it sends, and the three fields it refuses, in the order corrected. */
export interface SameWordsWindow {
  /** The screenshots' app: `CLOSE-<app>-hub888-<step>-<label>`. */
  app: string;
  page: string;
  add: string;
  testid: string;
  /** The save (POST) the window sends, answered in the browser. */
  save: string;
  /** Fills what the window needs before «Save» is on. */
  fill: (form: Locator) => Promise<void>;
  /** The keys refused, in the order they are corrected (typed again); the last one keeps its mark. Each field's hook is
   *  `<testid>-<key>`, and what is typed again keeps it valid for the window (an empty amount becomes «1»). */
  keys: readonly [string, string, string];
  /** What nothing reached the Hub reads as 0. */
  created: string;
}

/** In `window`, its three fields refused with the same `words` lose their marks one by one as each is typed again;
 *  the last keeps its own. Screenshots `CLOSE-<app>-hub888-<step>-<label>`. */
async function correctOneByOne(page: Page, window: SameWordsWindow, words: string, label: string): Promise<void> {
  const marked = (field: Locator): Promise<void> => expectMarked(field, words);
  const unmarked = (field: Locator): Promise<void> => expectUnmarked(field, words);
  await shown(page).locator(`[data-testid=${window.add}]`).click();
  const form = page.locator(`ion-modal[data-testid=${window.testid}]`);
  await expect(form).toBeVisible();
  await window.fill(form);
  const [first, second, last] = window.keys.map((key) => form.locator(`[data-testid=${window.testid}-${key}]`));

  await refuseWithTheSameWords(page, window.save, window.keys, words);
  await form.locator(`[data-testid=${window.testid}-submit]`).click();
  for (const field of [first, second, last]) await marked(field);
  await capture(page, `CLOSE-${window.app}-hub888-refused-${label}`);

  // The first field typed again: its mark alone goes.
  const typed = first.locator('input');
  await typed.fill(`${await typed.inputValue()}1`);
  await unmarked(first);
  await marked(second);
  await marked(last);
  await first.scrollIntoViewIfNeeded();
  await capture(page, `CLOSE-${window.app}-hub888-first-typed-${label}`);

  // The second one too; the last keeps its own until it is corrected or saved again.
  await second.locator('input').fill(`${await second.locator('input').inputValue()} 2`);
  await unmarked(second);
  await unmarked(first);
  await marked(last);
  await last.scrollIntoViewIfNeeded();
  await capture(page, `CLOSE-${window.app}-hub888-second-typed-${label}`);

  // Nothing reached the Hub.
  await page.unroute(window.save);
  expect(psql(window.created)).toBe('0');
}

/** The tests of `windows`: each at 390, 834 and 1440, and once more in Spanish, whose session the fleet's visual sweep
 *  reads (`E2E_SAVE_STORAGE_STATE`), where the window's «Cancel» says «Cancelar». */
export function testTheMarksGoOneByOne(windows: readonly SameWordsWindow[]): void {
  for (const window of windows) {
    for (const size of VIEWPORTS) {
      test(`hub#888 ${window.app} at ${size.label}: three fields refused with the same words lose their marks one by one`, async ({ browser }) => {
        const { context, page } = await ownerPage(browser, window.page, { width: size.width, height: size.height });
        try {
          await correctOneByOne(page, window, 'Check this field.', size.label);
        } finally {
          await context.close();
        }
      });
    }

    test(`hub#888 ${window.app} in Spanish: the window speaks Spanish and the fields lose their marks one by one`, async ({ browser }) => {
      const { context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, window.page);
      try {
        await saveSessionForTheSweep(context);
        await correctOneByOne(page, window, 'Revisa este campo.', 'es-1440');
        await expect(page.locator(`ion-modal[data-testid=${window.testid}] [data-testid=${window.testid}-cancel]`)).toHaveText('Cancelar');
      } finally {
        await context.close();
      }
    });
  }
}

/** A window's test in its own shape: the language it runs in, and its size. */
export interface SameWordsCase {
  language: 'en' | 'es';
  size: { label: string; width: number; height: number };
}

/** 390, 834 and 1440 in English, and 1440 once more in Spanish, whose session the fleet's visual sweep reads. */
const SAME_WORDS_CASES: readonly SameWordsCase[] = [
  ...VIEWPORTS.map((size) => ({ language: 'en' as const, size })),
  { language: 'es', size: { label: 'es-1440', width: 1440, height: 900 } },
];

/** One test per case of `SAME_WORDS_CASES`, titled by `title`: the owner on `path`, at its size and in its language,
 *  goes through `body`, and its context closes. */
export function testEachSameWordsCase(title: (c: SameWordsCase) => string, path: string, body: (page: Page, c: SameWordsCase) => Promise<void>): void {
  for (const c of SAME_WORDS_CASES) {
    test(title(c), async ({ browser }) => {
      const { context, page } = c.language === 'en' ? await ownerPage(browser, path, c.size) : await signedInSpanish(browser, c.size, path);
      try {
        if (c.language === 'es') await saveSessionForTheSweep(context);
        await body(page, c);
      } finally {
        await context.close();
      }
    });
  }
}
