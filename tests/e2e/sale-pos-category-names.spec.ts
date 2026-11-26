// flow: SALE-F01, SALE-F38 — a hair salon's till, in English and in Spanish, at the three sizes: «All», «Services» and
// the template's retail category («Productos de venta», "Retail products") read whole in the category strip, and when
// the strip does not fit, its hidden end fades from the first paint, before anything moves it (hub#2409). Captures
// `HUB-2409-<language>-<width>`. The categories this file creates are deleted after it.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown, turnOn } from './helpers';
import { drawerOff, restoreDrawer } from './sale-helpers';

const SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1280, height: 720 },
] as const;
const LANGUAGES = ['en', 'es'] as const;
/** The retail category of the hair salon template, in each of its languages. */
const RETAIL = ['Productos de venta', 'Retail products'];
const made: string[] = [];

function forget(): void {
  psql(`delete from inventory_category where name in (${RETAIL.map((name) => `'${name}'`).join(', ')})`);
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  await turnOn(context, A, 'service');
  forget();
  for (const name of RETAIL) {
    const res = await api<{ id: string }>(context, A, 'POST', '/inventory/categories', { name, order: 1 });
    expect(res.status, name).toBe(201);
    made.push(res.data.id);
  }
  await context.close();
});

test.afterAll(() => {
  forget();
  restoreDrawer();
});

/** The till freshly opened at `size`, in `language`, with the retail categories in its strip. */
async function tillAt(browser: Browser, language: string, size: { width: number; height: number }): Promise<Page> {
  const context = await browser.newContext({ baseURL: A, viewport: size, locale: language });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language}`));
  await expect(shown(page).locator('[data-testid=pos-category-services]')).toBeVisible();
  for (const id of made) await expect(shown(page).locator(`[data-testid=pos-category-${id}]`)).toBeVisible();
  return page;
}

/** The strip as painted, untouched: the names that do not read whole, whether it hides categories and whether it fades. */
function strip(page: Page): Promise<{ cut: string[]; hides: boolean; fades: boolean }> {
  return shown(page)
    .locator('.pos-cats')
    .evaluate((el) => {
      const style = getComputedStyle(el);
      const mask = style.getPropertyValue('mask-image') || style.getPropertyValue('-webkit-mask-image') || 'none';
      const cut = [...el.querySelectorAll<HTMLElement>('.pos-cat__name')]
        .filter((name) => name.scrollWidth > name.clientWidth + 1 || name.scrollHeight > name.clientHeight + 1)
        .map((name) => name.textContent?.trim() ?? '');
      return { cut, hides: el.scrollWidth - el.clientWidth > 1, fades: mask !== 'none' };
    });
}

/** Every size is measured and captured, each failure said with its size. */
const softly = expect.configure({ soft: true });

/** The strip fades exactly when it hides categories, measured until it holds. */
async function fadeTellsWhatHides(page: Page, where: string): Promise<void> {
  await softly
    .poll(async () => {
      const now = await strip(page);
      return now.fades === now.hides;
    }, { message: `${where}: the fade tells whether categories are hidden` })
    .toBe(true);
}

for (const language of LANGUAGES) {
  test(`SALE-F01 (hub#2409), ${language}: every category reads whole, and the hidden end fades from the first paint`, async ({
    browser,
  }) => {
    for (const size of SIZES) {
      const page = await tillAt(browser, language, size);
      const where = `${language} at ${size.width}×${size.height}`;
      await softly.poll(async () => (await strip(page)).cut, { message: `${where}: names cut` }).toEqual([]);
      await fadeTellsWhatHides(page, where);
      // Four categories never fit beside the check: the fade is not only right when nothing is hidden.
      if (size.width === 1280) expect((await strip(page)).hides, where).toBe(true);
      await capture(page, `HUB-2409-${language}-${size.width}`);
      // Slid to its end, the last categories read whole and the fade moves to the start.
      await shown(page)
        .locator('.pos-cats')
        .evaluate((el) => el.scrollTo({ left: el.scrollWidth, behavior: 'instant' }));
      await fadeTellsWhatHides(page, `${where}, slid to its end`);
      await capture(page, `HUB-2409-${language}-${size.width}-end`);
      await page.context().close();
    }
  });
}
