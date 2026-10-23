// flow: UI DataTable etiquetas de rango — FIX-UI-DATATABLE-RANGE-FILTER-LABELS (seen by the worker of
// APP-CART_CHECKOUT, hub#110): in the filter row the other filters read as their column («Order», «Email»,
// «Payment»), but the two ends of a range only said «From» / «To» («Desde» / «Hasta»): nobody could tell what they
// filter, and with two ranges in one list (Payments: Date and Amount) they looked the same. A date range said even
// less: its ends are native date fields that paint «dd/mm/yyyy», never a placeholder. As in the market (Shopify,
// Odoo: a range filter carries the name of its field) the column now heads its pair on screen in the row, at 1440
// and 834 px, in English and in Spanish. Behind the funnel (a `filterable` list such as Invoices, and every list on
// a phone, ui#28) each range already had its column as a title: there it is said once, «From» / «To» below it.
// The ends keep their widths (ui#29) and nothing runs past the row, the panel or the sheet.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, record, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-UI-DATATABLE-RANGE-FILTER-LABELS';

type Language = 'en' | 'es';
interface Range {
  /** The column's name, as the list says it in each language. */
  column: Record<Language, string>;
  ends: [string, string];
  /** The native field of each end: a day, an amount as typed (decimal keyboard) or a number. */
  field: 'date' | 'text' | 'number';
}
interface List {
  path: string;
  table: string;
  ranges: Range[];
  /** Where its filters are on a desk: the row under the toolbar, or the panel behind the funnel (`filterable`). */
  desk: 'row' | 'panel';
}
const ORDERS: List = {
  path: '/cart_checkout/orders',
  table: 'cart-checkout-orders',
  desk: 'row',
  ranges: [{ column: { en: 'Total', es: 'Total' }, ends: ['total_amount_from', 'total_amount_to'], field: 'text' }],
};
// Two ranges in one row: a date range and an amount.
const PAYMENTS: List = {
  path: '/payment/payments',
  table: 'payment-payments',
  desk: 'row',
  ranges: [
    { column: { en: 'Date', es: 'Fecha' }, ends: ['payment_date_from', 'payment_date_to'], field: 'date' },
    { column: { en: 'Amount', es: 'Importe' }, ends: ['amount_from', 'amount_to'], field: 'number' },
  ],
};
const INVOICES: List = {
  path: '/invoice/invoices',
  table: 'invoice-list',
  desk: 'panel',
  ranges: [
    { column: { en: 'Total', es: 'Total' }, ends: ['total_amount_from', 'total_amount_to'], field: 'text' },
    { column: { en: 'Date', es: 'Fecha' }, ends: ['issue_date_from', 'issue_date_to'], field: 'date' },
  ],
};
const HINTS: Record<Language, [string, string]> = { en: ['From', 'To'], es: ['Desde', 'Hasta'] };

const SIZES = [
  { label: '1440', width: 1440, height: 900, phone: false },
  { label: '834', width: 834, height: 1112, phone: false },
  // A phone paints cards: every list folds its filters into the sheet behind the funnel (ui#28).
  { label: '390', width: 390, height: 844, phone: true },
] as const;

/** What a range shows on screen, measured in its group (`role=group`, named by its column). */
interface Painted {
  /** The visible text of the group outside its ends (the ends are boxes with no text of their own). */
  heading: string;
  /** The box of that text, and whether it is cut with no «…». */
  box: { x: number; y: number; width: number; height: number } | null;
  cut: boolean;
  /** The heading comes before the ends: to their left on the same line, or on a line above. */
  before: boolean;
  /** Each end: its example text («From»/«To», not painted by a date field), its type and its box. */
  ends: Array<{ placeholder: string; type: string; x: number; width: number }>;
}

async function signedIn(browser: Browser, size: (typeof SIZES)[number], language: Language): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    baseURL: A,
    viewport: { width: size.width, height: size.height },
    locale: language === 'es' ? 'es-ES' : 'en-US',
  });
  const page = await context.newPage();
  await login(page, A, '/');
  if (language === 'es') await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  return { context, page };
}

/** The column filters of a list: the open filter row, or the panel behind the funnel (opened here). */
async function filters(page: Page, list: List): Promise<{ where: 'row' | 'panel'; scope: Locator }> {
  const view = shown(page);
  await view.locator(`[data-testid=${list.table}-empty], [data-testid=${list.table}-row]`).first().waitFor({ state: 'visible' });
  const toggle = view.locator(`[data-testid=${list.table}-filters-toggle]`);
  if (!(await toggle.isVisible())) return { where: 'row', scope: view.locator(`[data-testid=${list.table}-filters]`) };
  await toggle.click();
  const panel = view.locator(`[data-testid=${list.table}-filters-panel]`);
  await expect(panel).toBeVisible();
  await untilStill(page);
  return { where: 'panel', scope: panel };
}

async function painted(end: Locator): Promise<Painted> {
  return end.evaluate((from) => {
    const group = from.closest('[role=group]') as HTMLElement;
    const heads = [...group.querySelectorAll<HTMLElement>('*')].filter(
      (el) => !el.closest('ion-input') && [...el.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim()),
    );
    const heading = heads.map((el) => el.innerText.trim()).join(' ');
    const head = heads[0];
    const box = head ? head.getBoundingClientRect() : null;
    const ends = [...group.querySelectorAll<HTMLElement>('ion-input')].map((input) => {
      const field = input.querySelector('input') as HTMLInputElement;
      const own = input.getBoundingClientRect();
      return { placeholder: field.placeholder, type: field.type, x: own.x, width: own.width };
    });
    const first = group.querySelector('ion-input')!.getBoundingClientRect();
    return {
      heading,
      box: box && { x: box.x, y: box.y, width: box.width, height: box.height },
      cut: !!head && head.scrollWidth > head.clientWidth + 0.5 && getComputedStyle(head).textOverflow !== 'ellipsis',
      before: !!box && (box.right <= first.left + 0.5 || box.bottom <= first.top + 0.5),
      ends,
    };
  });
}

for (const size of SIZES) {
  test(`UI DataTable etiquetas de rango at ${size.label}: each range says its column on screen, «From» / «To» after it, in English and in Spanish`, async ({
    browser,
  }) => {
    for (const language of ['en', 'es'] as const) {
      const { context, page } = await signedIn(browser, size, language);
      try {
        for (const list of [ORDERS, PAYMENTS, INVOICES]) {
          await page.goto(`${A}${list.path}`);
          await expect(page.locator('html')).toHaveAttribute('lang', language === 'es' ? /^es/ : /^en/);
          const { where, scope } = await filters(page, list);
          expect(where, `${list.path}: where the filters are`).toBe(size.phone ? 'panel' : list.desk);
          const area = (await scope.boundingBox())!;
          const measured: Record<string, Painted> = {};
          for (const range of list.ranges) {
            const column = range.column[language];
            const own = await painted(scope.locator(`[data-testid=${list.table}-filter-${range.ends[0]}]`));
            measured[column] = own;
            const what = `${language} ${list.path} ${where} «${column}»`;
            // The column heads its pair on screen, once, before its ends.
            expect(own.heading, `${what}: the column on screen`).toBe(column);
            expect(own.box, `${what}: the column is painted`).not.toBeNull();
            expect(own.box!.width, `${what}: the column is painted`).toBeGreaterThan(0);
            expect(own.cut, `${what}: the column is whole or ends in «…»`).toBe(false);
            expect(own.before, `${what}: the column comes before its ends`).toBe(true);
            // Its ends still say «From» / «To» (a date field paints its own «dd/mm/yyyy»).
            expect(own.ends.map((end) => end.placeholder), `${what}: the ends' example texts`).toEqual(HINTS[language]);
            expect(own.ends.map((end) => end.type), `${what}: the ends' fields`).toEqual([range.field, range.field]);
            // Nothing runs past the row, the panel or the sheet (saas#558).
            for (const box of [own.box!, ...own.ends]) {
              expect(box.x, `${what}: starts inside the ${where}`).toBeGreaterThanOrEqual(area.x - 0.5);
              expect(box.x + box.width, `${what}: ends inside the ${where}`).toBeLessThanOrEqual(area.x + area.width + 0.5);
            }
            // In the row the ends keep their widths: a date field's 8.75rem (ui#29), a number's short box.
            if (where === 'row') {
              for (const end of own.ends) {
                if (range.field === 'date') expect(end.width, `${what}: a date end is 8.75rem`).toBeCloseTo(140, 0);
                else {
                  expect(end.width, `${what}: a short number box`).toBeGreaterThanOrEqual(88 - 0.5);
                  expect(end.width, `${what}: a short number box`).toBeLessThanOrEqual(112 + 0.5);
                }
              }
            }
          }
          // Two ranges in one list no longer read the same.
          const headings = Object.values(measured).map((own) => own.heading);
          expect(new Set(headings).size, `${language} ${list.path}: one heading per range`).toBe(headings.length);
          record(`${KEY}-${size.label}-${language}-${list.table}`, { where, area: { x: area.x, width: area.width }, measured });
          const name = list === PAYMENTS && language === 'en' ? `${KEY}-${size.label}` : `${KEY}-${size.label}-${language}-${list.table}`;
          await page.screenshot({ path: shot(name) });
        }
      } finally {
        await context.close();
      }
    }
  });
}
