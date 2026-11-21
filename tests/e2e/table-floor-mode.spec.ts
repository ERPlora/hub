// The «Service / Edit plan» switch of the floor plan reads whole in English and in Spanish at 1440x900, 820x1180 and
// 375x667, in both modes, and leaves the zones and the edit buttons of its bar on the screen, clear of one another.
// The zone this file makes is removed afterwards.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { capture, horizontalOverflow, psql, settled, shown, signedInSpanish } from './helpers';
import { ownerPage, post } from './service-helpers';

const ZONE = `E2E Mode ${Date.now().toString(36).toUpperCase()}`;
const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
];
const WORDS = {
  en: { service: 'Service', edit: 'Edit plan' },
  es: { service: 'Servicio', edit: 'Editar plano' },
};
const BAR = ['table-floor-zones', 'table-floor-mode', 'table-floor-add', 'table-floor-zone-edit'];

type Language = keyof typeof WORDS;
interface Box {
  testid: string;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const cleanUp = () => psql(`delete from table_zone where name like 'E2E Mode %'`);

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** Each option's words, how much of them its button cuts off, how much of the button the switch hides (0 and 0 when
 *  the option reads whole) and how wide the button is. */
async function options(page: Page): Promise<{ words: string; cut: number; hidden: number; width: number }[]> {
  return shown(page)
    .locator('[data-testid=table-floor-mode]')
    .evaluate((segment) => {
      const frame = segment.getBoundingClientRect();
      return [...segment.querySelectorAll('ion-segment-button')].map((button) => {
        const label = button.querySelector('ion-label');
        const box = button.getBoundingClientRect();
        return {
          words: label?.textContent?.trim() ?? '',
          cut: label ? label.scrollWidth - label.clientWidth : 0,
          hidden: Math.round(Math.max(0, frame.left - box.left, box.right - frame.right)),
          width: box.width,
        };
      });
    });
}

/** The boxes of the bar's controls that are on the page. */
async function bar(page: Page): Promise<Box[]> {
  return shown(page)
    .locator('.table-floor__bar')
    .evaluate(
      (row, ids) =>
        ids.flatMap((testid) => {
          const control = row.querySelector(`[data-testid="${testid}"]`);
          if (!control) return [];
          const { left, right, top, bottom } = control.getBoundingClientRect();
          return [{ testid, left, right, top, bottom }];
        }),
      BAR,
    );
}

const apart = (a: Box, b: Box) => a.right <= b.left + 0.5 || b.right <= a.left + 0.5 || a.bottom <= b.top + 0.5 || b.bottom <= a.top + 0.5;

async function checkBar(page: Page, language: Language, size: (typeof SIZES)[number], mode: 'service' | 'edit'): Promise<void> {
  const where = `${language} at ${size.label}, ${mode}`;
  const words = WORDS[language];
  const shownOptions = await options(page);
  expect(
    shownOptions.map(({ words, cut, hidden }) => ({ words, cut, hidden })),
    `the options read whole, ${where}`,
  ).toEqual([
    { words: words.service, cut: 0, hidden: 0 },
    { words: words.edit, cut: 0, hidden: 0 },
  ]);
  const [service, edit] = shownOptions.map((option) => option.width);
  expect(Math.abs(service - edit), `both options as wide, ${where}`).toBeLessThan(1);
  const boxes = await bar(page);
  expect(boxes.map((box) => box.testid).sort(), `the bar's controls, ${where}`).toEqual(
    (mode === 'edit' ? BAR : BAR.slice(0, 2)).slice().sort(),
  );
  for (const box of boxes) {
    expect(box.left, `${box.testid} starts on the screen, ${where}`).toBeGreaterThanOrEqual(0);
    expect(box.right, `${box.testid} ends on the screen, ${where}`).toBeLessThanOrEqual(size.width);
  }
  for (const [index, box] of boxes.entries()) {
    for (const other of boxes.slice(index + 1)) expect(apart(box, other), `${box.testid} clear of ${other.testid}, ${where}`).toBe(true);
  }
  expect(await horizontalOverflow(page), `nothing past the right edge, ${where}`).toBe(0);
  await capture(page, `table-floor-mode-${language}-${size.label}-${mode}`);
}

async function signedIn(browser: Browser, language: Language): Promise<{ context: BrowserContext; page: Page }> {
  const first = { width: SIZES[0].width, height: SIZES[0].height };
  return language === 'es' ? signedInSpanish(browser, first, '/table/floor-plan') : ownerPage(browser, '/table/floor-plan', first);
}

for (const language of ['en', 'es'] as const) {
  test(`The floor plan's mode switch reads whole in ${language} at every size, and the bar keeps its controls on the screen`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, language);
    try {
      const zone = await post<{ id: string }>(context, '/table/zones', { name: `${ZONE} ${language}` });
      await page.reload();
      await shown(page).locator(`[data-testid=table-floor-zone-tab-${zone.id}]`).click();
      for (const size of SIZES) {
        await page.setViewportSize({ width: size.width, height: size.height });
        for (const mode of ['service', 'edit'] as const) {
          await shown(page).locator(`[data-testid=table-floor-mode-${mode}]`).click();
          await expect(shown(page).locator(`[data-testid=table-floor-mode-${mode}]`)).toHaveClass(/segment-button-checked/);
          await settled(page);
          await checkBar(page, language, size, mode);
        }
        await shown(page).locator('[data-testid=table-floor-mode-service]').click();
      }
    } finally {
      await context.close();
    }
  });
}
