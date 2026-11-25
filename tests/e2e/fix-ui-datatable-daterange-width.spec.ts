// flow: UI DataTable date filter — in Payments › Payments the Date column filters by a range of two DateFields of
// @erplora/ui, each with its calendar icon apart from the date (PAYMENT-F06). As in the market (Shopify, Odoo, Square)
// each end shows its whole picked date, never cut by its box nor under its icon, in the panel behind the funnel (1440,
// 834), in the 360px panel of the cards at 1440 and in the sheet at 390, with the Hub in Spanish and in English, and
// nothing runs past the panel or the sheet. The Amount range keeps its short boxes.
//
// How it is measured: a DateField is a read-only text field, so a date cut by its box makes the field's `scrollWidth`
// pass its `clientWidth`; and the date, drawn in the field's font, ends at least MIN_GAP px before the icon starts.
// Payments keeps its column filters behind the funnel: every size measures the ends in its panel (no hub list paints a
// date range in the open row; the row's 8.75rem is guarded by ui's DataTable.visual.test.ts).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { dayAsShown, pickDay } from './date-time-fields';
import { A, login, record, shot, shown, signedInSpanish, untilStill } from './helpers';

const KEY = 'FIX-UI-DATATABLE-DATERANGE-ICON-CLIPS-PLACEHOLDER';
const TABLE = 'payment-payments';
const DATE_ENDS = ['payment_date_from', 'payment_date_to'];
const AMOUNT_ENDS = ['amount_from', 'amount_to'];
const LIST = '/payment/payments';
/** The Hub's language gives a DateField its format: «28/11/2026» or «11/28/2026». */
const LANGUAGES = ['es', 'en'] as const;
type Language = (typeof LANGUAGES)[number];
/** Fewer blank px between the date and its icon: the icon touches the date. */
const MIN_GAP = 6;

interface Case {
  label: string;
  width: number;
  height: number;
  /** The view picked before measuring (the default otherwise). */
  view?: 'cards';
  /** Where the column filters are in that view. */
  where: 'row' | 'panel';
}
const CASES: Case[] = [
  // The list is `filterable`: its filters live behind the funnel in every view and size.
  { label: '1440', width: 1440, height: 900, where: 'panel' },
  { label: '834', width: 834, height: 1112, where: 'panel' },
  // The cards fold the filters behind the funnel too: at 1440 its panel is 360px beside the cards.
  { label: '1440-cards', width: 1440, height: 900, view: 'cards', where: 'panel' },
  // A phone paints cards: the panel is the sheet over the content area.
  { label: '390', width: 390, height: 844, where: 'panel' },
];

/** What a date end shows and how it fits, in px. */
interface Fit {
  value: string;
  /** Its box: left edge and width. */
  x: number;
  box: number;
  /** The field's content and its own width: a wider content is a cut date. */
  scrollWidth: number;
  clientWidth: number;
  /** Blank px between the end of the date, drawn in the field's font, and the start of its icon. */
  gap: number;
}

/** The owner on the list of payments, with the Hub in `language`. */
async function signedIn(browser: Browser, language: Language, size: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const viewport = { width: size.width, height: size.height };
  if (language === 'es') return signedInSpanish(browser, viewport, LIST);
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, LIST);
  return { context, page };
}

/** The 28th, which every month has, of the month the calendar opens on: picking it moves no month. */
function dayOfThisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-28`;
}

/** The column filters: the open filter row, or the panel behind the funnel (opened here). */
async function filters(page: Page): Promise<{ where: 'row' | 'panel'; scope: Locator }> {
  const view = shown(page);
  const toggle = view.locator(`[data-testid=${TABLE}-filters-toggle]`);
  if (!(await toggle.isVisible())) return { where: 'row', scope: view.locator(`[data-testid=${TABLE}-filters]`) };
  await toggle.click();
  const panel = view.locator(`[data-testid=${TABLE}-filters-panel]`);
  await expect(panel).toBeVisible();
  // It slides in (0.18 s): measured once it stands still.
  await untilStill(page);
  return { where: 'panel', scope: panel };
}

/** Measures a date end: what it shows, its box, its content against its width and the room between its date and icon. */
async function fit(end: Locator): Promise<Fit> {
  return end.evaluate((host) => {
    const field = host.querySelector('input')!;
    const style = getComputedStyle(field);
    const pen = document.createElement('canvas').getContext('2d')!;
    pen.font = style.font;
    const dateEnd = field.getBoundingClientRect().left + parseFloat(style.paddingLeft) + pen.measureText(field.value).width;
    const icon = host.querySelector('[slot="end"]')!.getBoundingClientRect();
    const box = host.getBoundingClientRect();
    return { value: field.value, x: box.x, box: box.width, scrollWidth: field.scrollWidth, clientWidth: field.clientWidth, gap: icon.left - dateEnd };
  });
}

for (const size of CASES) {
  test(`UI DataTable filtro de fechas at ${size.label}: each end of the Date range shows its whole date, the calendar icon apart; Amount keeps its short boxes`, async ({
    browser,
  }) => {
    const day = dayOfThisMonth();
    for (const language of LANGUAGES) {
      const { context, page } = await signedIn(browser, language, size);
      try {
        await shown(page).locator(`[data-testid=${TABLE}-empty], [data-testid=${TABLE}-row]`).first().waitFor({ state: 'visible' });
        if (size.view === 'cards') await shown(page).locator(`[data-testid=${TABLE}-view-cards]`).click();
        const { where, scope } = await filters(page);
        const end = (name: string) => scope.locator(`[data-testid=${TABLE}-filter-${name}]`);
        for (const name of DATE_ENDS) await pickDay(page, end(name), day);
        // Measured once both are picked: a tap scrolls its end into view, and measured one by one each end could
        // look inside the panel while the other is out of it.
        const dates: Record<string, Fit> = {};
        for (const name of DATE_ENDS) dates[name] = await fit(end(name));
        const area = (await scope.boundingBox())!;
        const amounts: Record<string, { x: number; box: number }> = {};
        for (const name of AMOUNT_ENDS) {
          const box = (await scope.locator(`[data-testid=${TABLE}-filter-${name}]`).boundingBox())!;
          amounts[name] = { x: box.x, box: box.width };
        }
        record(`${KEY}-${size.label}-${language}`, { where, area: { x: area.x, width: area.width }, dates, amounts });
        await page.screenshot({ path: shot(`${KEY}-${size.label}${language === 'es' ? '' : '-en'}`) });

        expect(where, `${language}: where the filters are`).toBe(size.where);
        for (const [name, own] of Object.entries(dates)) {
          expect(own.value, `${language} ${name}: the picked day`).toBe(dayAsShown(day, language));
          expect(own.scrollWidth, `${language} ${name}: «${own.value}» whole in its box (px)`).toBeLessThanOrEqual(own.clientWidth);
          expect(own.gap, `${language} ${name}: the calendar icon stands apart from the whole date (blank px)`).toBeGreaterThanOrEqual(MIN_GAP);
        }
        for (const [name, own] of Object.entries({ ...dates, ...amounts })) {
          // Nothing runs past the row, the panel or the sheet.
          expect(own.x, `${language} ${name} starts inside the ${where}`).toBeGreaterThanOrEqual(area.x - 0.5);
          expect(own.x + own.box, `${language} ${name} ends inside the ${where}`).toBeLessThanOrEqual(area.x + area.width + 0.5);
        }
        // The numeric range is as before: in the row, its short boxes of 5.5–7rem.
        if (where === 'row') {
          for (const [name, own] of Object.entries(amounts)) {
            expect(own.box, `${language} ${name}: the short number box of the row`).toBeGreaterThanOrEqual(88 - 0.5);
            expect(own.box, `${language} ${name}: the short number box of the row`).toBeLessThanOrEqual(112 + 0.5);
          }
        }
      } finally {
        await context.close();
      }
    }
  });
}

// Between 641 and 1024 px the search box shrinks to leave room for the toolbar (12–22rem), and its example text was cut
// short with no sign: «Search reference or benefic» at 820 and «…beneficia» at 834. As in the market (Shopify, Square,
// Gmail) the example text fits whole where it has room and ends in «…» where it has none; the box keeps its widths.
// Measured with the page in English and in Spanish («Buscar referencia o beneficiario…», the `django_language` the
// account would pick).
const SEARCH_SIZES = [
  { label: '820', width: 820, height: 1180 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** The search box's native field: its example text, the room it gives it and the text's own width, in px. */
interface SearchFit {
  placeholder: string;
  box: number;
  room: number;
  text: number;
  textOverflow: string;
  scrollWidth: number;
  clientWidth: number;
}

for (const size of SEARCH_SIZES) {
  test(`UI DataTable filtro de fechas at ${size.label}: the search box's example text fits whole, or ends in «…» where it has no room`, async ({
    browser,
  }) => {
    const measured: Partial<Record<'en' | 'es', SearchFit>> = {};
    for (const language of ['en', 'es'] as const) {
      const { context, page } = await signedIn(browser, language, size);
      try {
        await shown(page).locator(`[data-testid=${TABLE}-empty], [data-testid=${TABLE}-row]`).first().waitFor({ state: 'visible' });
        const input = shown(page).locator(`[data-testid=${TABLE}-search] input`);
        await expect(input).toHaveAttribute('placeholder', language === 'es' ? 'Buscar referencia o beneficiario…' : 'Search reference or beneficiary…');
        const own: SearchFit = await input.evaluate((field: HTMLInputElement) => {
          const style = getComputedStyle(field);
          const pen = document.createElement('canvas').getContext('2d')!;
          pen.font = style.font;
          return {
            placeholder: field.placeholder,
            box: field.getBoundingClientRect().width,
            room: field.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
            text: pen.measureText(field.placeholder).width,
            textOverflow: style.textOverflow,
            scrollWidth: field.scrollWidth,
            clientWidth: field.clientWidth,
          };
        });
        measured[language] = own;
        record(`${KEY}-search-${size.label}-${language}`, own);
        await page.screenshot({ path: shot(`${KEY}-search-${size.label}${language === 'en' ? '' : '-es'}`) });
      } finally {
        await context.close();
      }
    }
    // The native field never reports the cut example text (`scrollWidth` stays its `clientWidth`, measured): the
    // text's own width, drawn in its font, against the room inside its padding (the icon and the clear button).
    for (const [language, own] of Object.entries(measured)) {
      if (own.text > own.room + 0.5) {
        expect(own.textOverflow, `${language}: «${own.placeholder}» (${own.text.toFixed(1)} px in ${own.room.toFixed(1)} px) ends in «…»`).toBe('ellipsis');
      }
    }
  });
}
