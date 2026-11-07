// flow: WEBSITE-F02
// — On a phone, in Spanish, «Colores» of Página web split the name of the palette «Medianoche» in the middle of the
// word (hub#993): the eight palette cards went three to a row down to 360 px, so at 375 a card left its name 81 px
// and the word, too long for it, was broken over two lines. The owner of hub `a` opens Página web in Spanish and in
// English at 375, 820 and 1440 px: every palette's name is read whole, each word on one line (a name parts between
// words, never inside one), and inside its card, with no sideways scroll. The cards go three to a row on a tablet and a
// computer, as before, and two on that phone. Each language and width leaves its capture
// `FIX-HUB-WEBSITE-PALETTE-NAMES-WHOLE-<lang>-<width>`. Nothing is saved.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, HUB_DIR, horizontalOverflow, login, shot, untilStill } from './helpers';

const KEY = 'FIX-HUB-WEBSITE-PALETTE-NAMES-WHOLE';
/** Each width and how many palette cards go in a row there. */
const SIZES = [
  { width: 375, height: 667, perRow: 2 },
  { width: 820, height: 1180, perRow: 3 },
  { width: 1440, height: 900, perRow: 3 },
] as const;
const LANGUAGES = ['es', 'en'] as const;

/** The palettes' names as the editor writes them in `lang` (`website.palette.<id>` of the app's catalogue). */
function paletteNames(lang: (typeof LANGUAGES)[number]): Record<string, string> {
  const catalogue = JSON.parse(readFileSync(join(HUB_DIR, 'apps', 'website', 'frontend', 'locale', `${lang}.json`), 'utf8'));
  const { label: _label, hint: _hint, reset: _reset, ...names } = catalogue.website.palette as Record<string, string>;
  return names;
}

/** The owner on `a` with the Hub in `lang`, on the website's editor. */
async function ownerIn(browser: Browser, lang: string): Promise<{ context: BrowserContext; page: Page }> {
  const { width, height } = SIZES[0];
  const context = await browser.newContext({ baseURL: A, viewport: { width, height }, locale: lang === 'es' ? 'es-ES' : 'en-GB' });
  const page = await context.newPage();
  await login(page, A, '/website');
  await context.addCookies([{ name: 'django_language', value: lang, domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/website`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${lang}`));
  // The owner's session in this language for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE && lang === 'es') await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

/** How each palette card draws its name: the words split over two lines, and how far the name runs past the card's
 *  inner edges (0 when it fits). What ui-clip-sweep.sh calls SPLIT-WORD, measured on the card. */
async function drawnNames(cards: Locator): Promise<{ id: string; name: string; split: string[]; past: number; top: number }[]> {
  return cards.evaluateAll((all) =>
    all.map((card) => {
      const box = card.getBoundingClientRect();
      const style = getComputedStyle(card);
      const left = box.left + Number.parseFloat(style.borderLeftWidth) + Number.parseFloat(style.paddingLeft);
      const right = box.right - Number.parseFloat(style.borderRightWidth) - Number.parseFloat(style.paddingRight);
      const lines = (range: Range) =>
        new Set([...range.getClientRects()].filter((rect) => rect.width > 0).map((rect) => Math.round(rect.top))).size;
      const split: string[] = [];
      let past = 0;
      let name = '';
      const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = node.textContent ?? '';
        name += text.trim();
        const range = document.createRange();
        for (const word of text.matchAll(/\S+/g)) {
          range.setStart(node, word.index);
          range.setEnd(node, word.index + word[0].length);
          if (lines(range) > 1) split.push(word[0]);
          for (const rect of range.getClientRects()) {
            if (rect.width === 0) continue;
            past = Math.max(past, Math.round(left - rect.left), Math.round(rect.right - right));
          }
        }
      }
      return { id: (card as HTMLElement).dataset.testid ?? '', name, split, past, top: Math.round(box.top) };
    }),
  );
}

for (const lang of LANGUAGES) {
  test(`WEBSITE-F02 in ${lang}: every palette's name is read whole, at 375, 820 and 1440 px`, async ({ browser }) => {
    const names = paletteNames(lang);
    const { context, page } = await ownerIn(browser, lang);
    try {
      for (const size of SIZES) {
        await page.setViewportSize({ width: size.width, height: size.height });
        await expect(page.getByTestId('website-editor')).toBeVisible({ timeout: 30_000 });
        const cards = page.getByTestId('website-editor').locator('[data-testid^="website-palette-"][role="radio"]');
        await expect(cards).toHaveCount(Object.keys(names).length);
        await untilStill(page);
        const where = `${lang} at ${size.width}`;
        const drawn = await drawnNames(cards);
        expect.soft(drawn.filter((card) => card.top === drawn[0].top).length, `${where}: palette cards in a row`).toBe(size.perRow);
        for (const card of drawn) {
          const id = card.id.replace('website-palette-', '');
          expect.soft(card.name, `${where}: the card ${id} says its name`).toBe(names[id]);
          expect.soft(card.split, `${where}: «${card.name}» has no word split over two lines`).toEqual([]);
          expect.soft(card.past, `${where}: «${card.name}» stays inside its card`).toBeLessThanOrEqual(0);
        }
        expect.soft(await horizontalOverflow(page), `${where}: no sideways scroll`).toBeLessThanOrEqual(0);
        await cards.first().scrollIntoViewIfNeeded();
        await page.screenshot({ path: shot(`${KEY}-${lang}-${size.width}`) });
      }
    } finally {
      await context.close();
    }
  });
}
