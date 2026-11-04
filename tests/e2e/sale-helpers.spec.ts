// flow: ninguno — FIX tests/e2e (ayudante `tillIsPhone` de las e2e de Ventas; rv-hub-292)
// `tillIsPhone` (sale-helpers.ts) answers for the window the page is in, never for the size before. The till lays itself
// out a frame after a resize (its media query and its ResizeObserver), and the specs that read its cart button straight
// after `setViewportSize` tapped the previous size's button. On a real till that late frame is too short to catch every
// time, so this page stands in for a till that is slow on purpose: it changes `pos-till--phone` 1.5 s after its media
// query changes. The lag is the page's; the test waits for nothing. No stack: the page is written in place.
import { expect, type Page, test } from '@playwright/test';

import { numberRow, tillIsPhone } from './sale-helpers';

/** A till as `PosPage.vue` marks it (`pos-till`, `pos-till--phone` by its media query) inside a shown page, slow to
 *  follow the window: its class catches up `lag` ms after the media query changes. */
const slowTill = (lag: number) => `
  <div class="ion-page">
    <div class="pos-till" data-testid="pos-till">till</div>
  </div>
  <script>
    const till = document.querySelector('[data-testid=pos-till]');
    const media = matchMedia('(max-width: 820px), (max-height: 500px)');
    const follow = () => till.classList.toggle('pos-till--phone', media.matches);
    follow();
    media.addEventListener('change', () => setTimeout(follow, ${lag}));
  </script>`;

test('tillIsPhone answers for the window the till is in now, not for the size before, however late the till follows', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.setContent(slowTill(1500));
  expect(await tillIsPhone(page), 'a phone at 390').toBe(true);
  await page.setViewportSize({ width: 834, height: 1112 });
  expect(await tillIsPhone(page), 'no phone at 834, straight after 390').toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await tillIsPhone(page), 'a phone at 390, straight after 834').toBe(true);
  await page.setViewportSize({ width: 1440, height: 900 });
  expect(await tillIsPhone(page), 'no phone at 1440, straight after 390').toBe(false);
});

// flow: ninguno — FIX tests/e2e (the `numberRow` helper of the SALE-F29 specs; hub#731)
// `numberRow` (sale-helpers.ts) says whether the date is the paper's next line after the number, and that cannot depend on
// the font. `ReceiptPaper.vue` asks for a font the Hub does not serve, so every machine draws its own, and the text box of
// a line is as tall as that font says, not as tall as the line: on a Mac, 3.5 px of nothing between two text boxes read as
// a blank line, red with the paper right. These lines disagree with a 10 px font's text box on any machine: 8 px is shorter
// than the box and 18 px far taller, still short of twice the font, where a line starts to hold a blank one. No stack: the
// page is written in place.
const LINE_HEIGHTS = [8, 18];

interface PaperShape {
  lineHeight: number;
  /** 200 px cannot hold the number and the date on one line; 400 px can. */
  width?: number;
  rowGap?: number;
  wrap?: 'wrap' | 'wrap-reverse';
  rowCss?: string;
  numberCss?: string;
  dateCss?: string;
  beforeDate?: string;
}

/** The number and the date as `ReceiptPaper.vue` lays them out (`.sale-receipt__meta`): two flex items in a row that wraps. */
const paper = ({ lineHeight, width = 200, rowGap = 0, wrap = 'wrap', rowCss = '', numberCss = '', dateCss = '', beforeDate = '' }: PaperShape) => `
  <div data-testid="paper" style="width: ${width}px; font: 10px/${lineHeight}px monospace">
    <div style="display: flex; flex-wrap: ${wrap}; justify-content: space-between; gap: ${rowGap}px 8px; ${rowCss}">
      <span data-testid="sale-receipt-number" style="${numberCss}">Receipt: <strong style="white-space: nowrap">TICKET-2026-000004</strong></span>
      <span data-testid="sale-receipt-datetime" style="${dateCss}">${beforeDate}Nov 3, 2026, 2:08 PM</span>
    </div>
  </div>`;

/** Empty space on the paper that the boxes of the two flex items hide: each of them leaves those boxes touching. */
const HIDDEN_SEPARATIONS: Record<string, Partial<PaperShape>> = {
  'padding above the date': { dateCss: 'padding-top: 6px' },
  'padding below the number': { numberCss: 'padding-bottom: 6px' },
  'a row taller than its two lines, which stretch': { rowCss: 'min-height: 60px' },
  'a blank line inside the date': { beforeDate: '<br>' },
  'a taller line for the date alone': { dateCss: 'line-height: 30px' },
};

const rowOf = async (page: Page, shape: PaperShape) => {
  await page.setContent(paper(shape));
  return numberRow(page.locator('[data-testid=paper]'));
};

test.describe('numberRow: where the date sits against the number, whatever font the machine draws them with', () => {
  for (const lineHeight of LINE_HEIGHTS) {
    test(`with ${lineHeight} px lines, the date on the next line is right under the number`, async ({ page }) => {
      const row = await rowOf(page, { lineHeight });
      expect(row.numberLines, 'the number on one line').toBe(1);
      expect(row.dateLines, 'the date on one line').toBe(1);
      expect(row.dateBeside, 'the date does not fit beside the number').toBe(false);
      expect(row.dateUnder, 'no blank line between them: the next line of the paper').toBe(true);
    });

    test(`with ${lineHeight} px lines, a gap between the two lines is not right under`, async ({ page }) => {
      const row = await rowOf(page, { lineHeight, rowGap: 8 });
      expect(row.dateUnder, 'the 8 px of `gap: 0.5rem` between the lines').toBe(false);
    });

    test(`with ${lineHeight} px lines, a date on the line above is not right under`, async ({ page }) => {
      const row = await rowOf(page, { lineHeight, wrap: 'wrap-reverse' });
      expect(row.dateBeside, 'the date is on another line').toBe(false);
      expect(row.dateUnder, 'the date is above the number').toBe(false);
    });

    test(`with ${lineHeight} px lines, a date that fits shares the number's line`, async ({ page }) => {
      const row = await rowOf(page, { lineHeight, width: 400 });
      expect(row.dateBeside, 'the date after the number, on its line').toBe(true);
      expect(row.dateUnder, 'beside is not under').toBe(false);
    });

    for (const [separation, shape] of Object.entries(HIDDEN_SEPARATIONS)) {
      test(`with ${lineHeight} px lines, ${separation} is not right under`, async ({ page }) => {
        const row = await rowOf(page, { lineHeight, ...shape });
        expect(row.dateBeside, 'the date is on another line').toBe(false);
        expect(row.dateUnder, `${separation}: empty space between the number and the date`).toBe(false);
      });
    }
  }

  test('lines of 30 px with a 10 px font hold a blank line of their own: not right under', async ({ page }) => {
    const row = await rowOf(page, { lineHeight: 30 });
    expect(row.dateUnder, 'more empty space between the two texts than a whole line of text').toBe(false);
  });
});
