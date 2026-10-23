// flow: UI DataTable filtro de fechas — FIX-UI-DATATABLE-DATERANGE-ICON-CLIPS-PLACEHOLDER (seen by APP-PAYMENT,
// hub#182): in Payments › Payments the Date column filters by a range, two native date fields with the browser's
// calendar icon. In the filter row each end was as narrow as a numeric «From/To» box (5.5–7rem): the icon covered
// the last character of the empty field at 1440 and 834 px, «dd/mm/yyy▢». As in the market (Shopify, Odoo,
// Square) the date field fits whole: each end of the Date range shows its whole date with the icon apart from it
// in the filter row (1440, 834), in the 360px panel of the cards at 1440 and in the sheet behind the funnel at 390
// (ui#28), with the browser in Spanish and in English, and nothing runs past the row, the panel or the sheet
// (saas#558). The Amount range keeps its short boxes. With ui ca89d4a the row's ends left the icon 3px from a cut
// «y» (the panel and the sheet already fitted).
//
// How it is measured (Chromium): the native field's `scrollWidth` never exceeds its `clientWidth`, clipped or not,
// so the evidence is its pixels: the blank columns between the date's last ink and the icon's. 3px is the icon's
// own padding, all a clipped or touching date leaves; a whole date keeps 8px or more (box 112px: 3, cut; 117px: 3,
// touching; 122px: 8 — measured on this field). In the row each end also gets the width a free date field of its
// font asks for (116px at 13px), what the browser gives a date field by default.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, record, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-UI-DATATABLE-DATERANGE-ICON-CLIPS-PLACEHOLDER';
const TABLE = 'payment-payments';
const DATE_ENDS = ['payment_date_from', 'payment_date_to'];
const AMOUNT_ENDS = ['amount_from', 'amount_to'];
// The browser's locale gives the native field its format: «dd/mm/yyyy» or «mm/dd/yyyy».
const LOCALES = ['es-ES', 'en-US'] as const;
/** Fewer blank px between the date and its icon: the date is cut or the icon touches it. */
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
  { label: '1440', width: 1440, height: 900, where: 'row' },
  { label: '834', width: 834, height: 1112, where: 'row' },
  // The cards fold the filters behind the funnel (ui#28): at 1440 its panel is 360px beside the cards.
  { label: '1440-cards', width: 1440, height: 900, view: 'cards', where: 'panel' },
  // A phone paints cards: the panel is the sheet over the content area.
  { label: '390', width: 390, height: 844, where: 'panel' },
];

/** What a date end has and needs, in px. */
interface Fit {
  /** Its box: left edge and width. */
  x: number;
  box: number;
  /** Room the native field gives its date and its icon (inside its padding). */
  room: number;
  /** Width a free date field of the same font takes: its whole date and its calendar icon. */
  needed: number;
  /** Blank columns between the date's last ink and the icon's, in a screenshot of the native field. */
  gap: number;
}

async function signedIn(browser: Browser, locale: string, size: Case): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: size.width, height: size.height }, locale });
  const page = await context.newPage();
  await login(page, A, '/payment/payments');
  return { context, page };
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

/** The blank columns before the last run of ink (the calendar icon) in a PNG of the native field. */
async function iconGap(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(async (base64) => {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext('2d')!;
    context.drawImage(bitmap, 0, 0);
    const { data, width, height } = context.getImageData(0, 0, bitmap.width, bitmap.height);
    const at = (x: number, y: number) => [0, 1, 2].map((c) => data[(y * width + x) * 4 + c]);
    // The field's background: the most common colour of its top line.
    const counts = new Map<string, number>();
    for (let x = 0; x < width; x++) counts.set(at(x, 0).join(), (counts.get(at(x, 0).join()) ?? 0) + 1);
    const background = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0].split(',').map(Number);
    // Its middle band, where the date and the icon are: an outlined field (`fill="outline"`) also crosses its
    // border lines at the top and the bottom of the native field.
    const ink = (x: number) => {
      for (let y = Math.round(height * 0.25); y < Math.round(height * 0.75); y++) {
        if (Math.max(...at(x, y).map((v, c) => Math.abs(v - background[c]))) > 48) return true;
      }
      return false;
    };
    const runs: Array<[number, number]> = [];
    for (let x = 0; x < width; x++) {
      if (!ink(x)) continue;
      const last = runs.at(-1);
      if (last && last[1] === x - 1) last[1] = x;
      else runs.push([x, x]);
    }
    return runs.length < 2 ? 0 : runs.at(-1)![0] - runs.at(-2)![1] - 1;
  }, png.toString('base64'));
}

/** Measures a date end: its box, the room of its native field, what a free date field of its font needs and the gap. */
async function fit(page: Page, end: Locator): Promise<Fit> {
  const input = end.locator('input');
  const own = await input.evaluate((field: HTMLInputElement) => {
    const style = getComputedStyle(field);
    const twin = document.createElement('input');
    twin.type = 'date';
    twin.style.cssText = `position: absolute; visibility: hidden; width: auto; padding: 0; border: 0; font: ${style.font}; letter-spacing: ${style.letterSpacing}`;
    document.body.append(twin);
    const needed = twin.getBoundingClientRect().width;
    twin.remove();
    const box = (field.closest('ion-input') as HTMLElement).getBoundingClientRect();
    return { x: box.x, box: box.width, room: field.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight), needed };
  });
  return { ...own, gap: await iconGap(page, await input.screenshot()) };
}

for (const size of CASES) {
  test(`UI DataTable filtro de fechas at ${size.label}: each end of the Date range shows its whole date, the calendar icon apart; Amount keeps its short boxes`, async ({
    browser,
  }) => {
    for (const locale of LOCALES) {
      const { context, page } = await signedIn(browser, locale, size);
      try {
        await shown(page).locator(`[data-testid=${TABLE}-empty], [data-testid=${TABLE}-row]`).first().waitFor({ state: 'visible' });
        if (size.view === 'cards') await shown(page).locator(`[data-testid=${TABLE}-view-cards]`).click();
        const { where, scope } = await filters(page);
        const area = (await scope.boundingBox())!;
        const dates: Record<string, Fit> = {};
        for (const name of DATE_ENDS) {
          const end = scope.locator(`[data-testid=${TABLE}-filter-${name}]`);
          await expect(end.locator('input'), `${locale}: ${name} is a date field`).toHaveAttribute('type', 'date');
          dates[name] = await fit(page, end);
        }
        const amounts: Record<string, { x: number; box: number }> = {};
        for (const name of AMOUNT_ENDS) {
          const box = (await scope.locator(`[data-testid=${TABLE}-filter-${name}]`).boundingBox())!;
          amounts[name] = { x: box.x, box: box.width };
        }
        record(`${KEY}-${size.label}-${locale}`, { where, area: { x: area.x, width: area.width }, dates, amounts });
        await page.screenshot({ path: shot(`${KEY}-${size.label}${locale === 'es-ES' ? '' : '-en'}`) });

        expect(where, `${locale}: where the filters are`).toBe(size.where);
        for (const [name, own] of Object.entries(dates)) {
          expect(own.gap, `${locale} ${name}: the calendar icon stands apart from the whole date (blank px)`).toBeGreaterThanOrEqual(MIN_GAP);
          if (where === 'row') {
            expect(own.room, `${locale} ${name}: the width of a date field (${own.needed.toFixed(1)} px)`).toBeGreaterThanOrEqual(own.needed - 0.5);
          }
        }
        for (const [name, own] of Object.entries({ ...dates, ...amounts })) {
          // saas#558: nothing runs past the row, the panel or the sheet.
          expect(own.x, `${locale} ${name} starts inside the ${where}`).toBeGreaterThanOrEqual(area.x - 0.5);
          expect(own.x + own.box, `${locale} ${name} ends inside the ${where}`).toBeLessThanOrEqual(area.x + area.width + 0.5);
        }
        // The numeric range is as before: in the row, its short boxes of 5.5–7rem.
        if (where === 'row') {
          for (const [name, own] of Object.entries(amounts)) {
            expect(own.box, `${locale} ${name}: the short number box of the row`).toBeGreaterThanOrEqual(88 - 0.5);
            expect(own.box, `${locale} ${name}: the short number box of the row`).toBeLessThanOrEqual(112 + 0.5);
          }
        }
      } finally {
        await context.close();
      }
    }
  });
}
