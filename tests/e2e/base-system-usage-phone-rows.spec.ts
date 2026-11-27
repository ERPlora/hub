// flow: BASE-F40 — «Usage and plan» before the first night: on a phone every row of both lists reads its whole name
// with its figure or its sentence under it, as «Files» does; from the tablet up the figure stays beside the name.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, hostPage, shown, signedInSpanish } from './helpers';
import { splitWords } from './words';

const PHONES = [
  { label: '375', width: 375, height: 667 },
  { label: '390', width: 390, height: 844 },
  { label: '412', width: 412, height: 915 },
] as const;
const WIDER = [
  { label: '820', width: 820, height: 1180 },
  { label: '1280', width: 1280, height: 720 },
] as const;

type Viewport = { width: number; height: number };
type Opened = Promise<{ context: BrowserContext; page: Page }>;

const LANGUAGES = [
  {
    code: 'en',
    notMeasured: 'Measured every night: the first figure comes tomorrow.',
    open: (browser: Browser, viewport: Viewport): Opened => hostPage(browser, A, { viewport, next: '/system' }),
  },
  {
    code: 'es',
    notMeasured: 'Se mide cada noche: la primera cifra llega mañana.',
    open: (browser: Browser, viewport: Viewport): Opened => signedInSpanish(browser, viewport, '/system'),
  },
] as const;

/** Every row at every size is checked, so a failure names all the rows it lays out wrong. */
const soft = expect.configure({ soft: true });

type Box = { top: number; bottom: number; left: number; right: number; width: number };

/** Where the browser drew the name and the figure of a row. */
function layoutOf(row: Locator): Promise<{ name: Box; amount: Box }> {
  return row.evaluate((li) => {
    const box = (selector: string): Box => {
      const { top, bottom, left, right, width } = (li.querySelector(selector) as Element).getBoundingClientRect();
      return { top, bottom, left, right, width };
    };
    return { name: box('.system-usage-name'), amount: box('.system-usage-amount') };
  });
}

const rowsOf = (page: Page): Locator =>
  shown(page).locator('[data-testid^="system-usage-row-"], [data-testid^="system-usage-info-"]');

async function openUsage(page: Page, notMeasured: string): Promise<void> {
  await expect(shown(page).locator('[data-testid="system-usage-info-database"]')).toContainText(notMeasured);
  await expect(shown(page).locator('[data-testid="system-usage-loading"]')).toHaveCount(0);
}

async function eachRow(page: Page, check: (where: string, row: Locator) => Promise<void>): Promise<void> {
  const rows = rowsOf(page);
  const count = await rows.count();
  expect(count, 'both lists have rows').toBeGreaterThan(4);
  for (let index = 0; index < count; index++) {
    const row = rows.nth(index);
    await check(`${await row.getAttribute('data-testid')}`, row);
  }
}

async function capturedAt(page: Page, name: string): Promise<void> {
  await shown(page).locator('[data-testid="system-usage-information"]').scrollIntoViewIfNeeded();
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

for (const language of LANGUAGES) {
  test(`BASE-F40 (${language.code}): on a phone the figure or its sentence goes under the whole name`, async ({ browser }) => {
    const { context, page } = await language.open(browser, PHONES[0]);
    try {
      await openUsage(page, language.notMeasured);
      for (const phone of PHONES) {
        await page.setViewportSize({ width: phone.width, height: phone.height });
        await eachRow(page, async (where, row) => {
          const at = `${where} at ${phone.label}`;
          const name = row.locator('.system-usage-name');
          await soft.poll(() => splitWords(name), { message: `${at}: its name keeps every word on one line` }).toEqual([]);
          await soft.poll(() => splitWords(row.locator('.system-usage-amount')), { message: `${at}: whole words` }).toEqual([]);
          const { name: named, amount } = await layoutOf(row);
          soft(named.width, `${at}: its name has room`).toBeGreaterThan(40);
          soft(amount.top, `${at}: the figure is under the name`).toBeGreaterThanOrEqual(named.bottom - 1);
          soft(Math.abs(amount.left - named.left), `${at}: the figure starts where the name starts`).toBeLessThanOrEqual(1);
        });
        await capturedAt(page, `BASE-F40-usage-rows-${language.code}-${phone.label}`);
      }
    } finally {
      await context.close();
    }
  });

  test(`BASE-F40 (${language.code}): on a tablet and a desk the figure stays beside the name`, async ({ browser }) => {
    const { context, page } = await language.open(browser, WIDER[0]);
    try {
      await openUsage(page, language.notMeasured);
      for (const size of WIDER) {
        await page.setViewportSize({ width: size.width, height: size.height });
        await eachRow(page, async (where, row) => {
          const at = `${where} at ${size.label}`;
          const { name, amount } = await layoutOf(row);
          soft(amount.left, `${at}: the figure is beside the name`).toBeGreaterThanOrEqual(name.right);
          soft(amount.top < name.bottom && amount.bottom > name.top, `${at}: on the name's line`).toBe(true);
        });
        await capturedAt(page, `BASE-F40-usage-rows-${language.code}-${size.label}`);
      }
    } finally {
      await context.close();
    }
  });
}
