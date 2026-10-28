// FIX-UI-SEARCHBAR-CLEAR-BUTTON-SAYS-RESET — Ionic 8 names the clear button of every `ion-searchbar` (the cross that
// shows once something is typed) with a constant `aria-label="reset"`, in English whatever the person's language, so a
// screen reader read «reset» on the tables' search (`DataTable`) and on the loose search boxes (Files, the till). The
// shared `syncSearchbarInputName` names it in the person's language — «Borrar búsqueda» / «Clear search» — and the field
// keeps its hint. The demo list is a `DataTable`; Files names its own searchbar through the helper, as the till does.
// flow: ui-datatable-search
import { type Locator, type Page, expect, test } from '@playwright/test';

import { A, decodeSubs, hostPage, listReady, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-UI-SEARCHBAR-CLEAR-BUTTON-SAYS-RESET';
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
type Language = 'es' | 'en';
type Sub = { op: string; params: Record<string, unknown> };
const CLEAR: Record<Language, string> = { es: 'Borrar búsqueda', en: 'Clear search' };

/** Opens `path` of hub `a` in `language` (the Hub's language cookie, as the sign-in sets it). */
async function openIn(page: Page, language: Language, path: string): Promise<void> {
  await page.context().addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${path}`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language}`));
}

/** Types into `bar`: its clear button shows, named in `language` and never «reset»; the field keeps its hint. */
async function typeAndCheckClear(bar: Locator, language: Language, text: string): Promise<Locator> {
  const input = bar.locator('input');
  await input.fill(text);
  const clear = bar.locator('button.searchbar-clear-button');
  await expect(clear).toBeVisible();
  await expect(clear).toHaveAttribute('aria-label', CLEAR[language]);
  await expect(bar.getByRole('button', { name: CLEAR[language], exact: true })).toBeVisible();
  const hint = await input.getAttribute('placeholder');
  expect(hint, 'the field has a visible hint').toBeTruthy();
  await expect(input).toHaveAttribute('aria-label', hint as string);
  return clear;
}

for (const viewport of VIEWPORTS) {
  test(`ui-datatable-search at ${viewport.label}: the clear button of a search box is named in the person's language, never «reset»`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/demo/items' });
    try {
      for (const language of ['es', 'en'] as const) {
        // A DataTable: the demo list.
        await openIn(page, language, '/demo/items');
        await listReady(page);
        const table = shown(page).locator('[data-testid=demo-items-search]');
        // The list as the search leaves it (the server's, after the box's debounce), for the capture.
        const searched = page.waitForRequest((req) =>
          req.url().includes('/api/live') &&
          (decodeSubs(req.url()) as Sub[]).some((s) => s.op === 'demo.item.list' && s.params.search === 'zz'),
        );
        const clear = await typeAndCheckClear(table, language, 'zz');
        await searched;
        await listReady(page);
        if (language === 'es') {
          await untilStill(page);
          await page.screenshot({ path: shot(`${KEY}-${viewport.label}`) });
          // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
          if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
        }
        // It is the working button: it empties the search.
        await clear.click();
        await expect(table.locator('input')).toHaveValue('');

        // A loose searchbar named through the helper: Files.
        await openIn(page, language, '/files');
        const files = shown(page).locator('[data-testid=files-search]');
        await files.waitFor({ state: 'visible' });
        await expect(shown(page).locator('[data-testid="files-loading"]:visible')).toHaveCount(0);
        await typeAndCheckClear(files, language, 'zz');
        if (language === 'es') {
          await untilStill(page);
          await page.screenshot({ path: shot(`${KEY}-files-${viewport.label}`) });
        }
      }
    } finally {
      await context.close();
    }
  });
}
