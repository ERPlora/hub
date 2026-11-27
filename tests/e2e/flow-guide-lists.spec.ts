// hub#2570 — the guide of Automations numbers its five first steps and bullets its four limits. Tailwind's preflight
// took the markers and the indent off both lists, so the nine lines read as loose sentences under their headings.
// Measured in each size and language: the marker style the browser paints, and the text of every item indented
// from its heading by the room its marker takes.
// flow: FLOW-F08
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, saveSessionForTheSweep, shown, signedInSpanish, THREE_SIZES } from './helpers';

const GUIDE = '/flow/automations/guide';
/** The least room a «5.» or a bullet needs before the text of its item. */
const MARKER_ROOM = 16;

async function openGuide(browser: Browser, size: (typeof THREE_SIZES)[number], lang: 'en' | 'es'): Promise<Page> {
  if (lang === 'es') return (await signedInSpanish(browser, size, GUIDE)).page;
  const context = await browser.newContext({ baseURL: A, viewport: size, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, GUIDE);
  await saveSessionForTheSweep(context);
  return page;
}

/** The list of a section: its marker style, and how far each item's text starts from the section's heading. */
async function listOf(section: Locator, tag: 'ol' | 'ul') {
  return section.evaluate((el, tagName) => {
    const heading = el.querySelector('h2')!.getBoundingClientRect();
    const list = el.querySelector(tagName)!;
    return {
      marker: getComputedStyle(list).listStyleType,
      indents: [...list.querySelectorAll(':scope > li')].map((li) => Math.round(li.getBoundingClientRect().left - heading.left)),
      rightEdge: Math.max(...[...list.querySelectorAll(':scope > li')].map((li) => li.getBoundingClientRect().right)),
    };
  }, tag);
}

for (const lang of ['en', 'es'] as const) {
  for (const size of THREE_SIZES) {
    test(`the guide numbers its first steps and bullets its limits, ${lang} at ${size.label}`, async ({ browser }) => {
      const page = await openGuide(browser, size, lang);
      try {
        const first = shown(page).locator('[data-testid=flow-guide-section-first]');
        const limits = shown(page).locator('[data-testid=flow-guide-section-limits]');
        await expect(first.locator('ol > li')).toHaveCount(5);
        await expect(limits.locator('ul > li')).toHaveCount(4);

        const steps = await listOf(first, 'ol');
        expect(steps.marker, 'the first steps are numbered').toBe('decimal');
        for (const indent of steps.indents) expect(indent, 'a step leaves room for its number').toBeGreaterThanOrEqual(MARKER_ROOM);

        const cannot = await listOf(limits, 'ul');
        expect(cannot.marker, 'the limits are bulleted').toBe('disc');
        for (const indent of cannot.indents) expect(indent, 'a limit leaves room for its bullet').toBeGreaterThanOrEqual(MARKER_ROOM);

        for (const right of [steps.rightEdge, cannot.rightEdge]) expect(right).toBeLessThanOrEqual(size.width);
        await capture(page, `flow-guide-lists-${lang}-${size.label}`, { fullPage: true });
      } finally {
        await page.context().close();
      }
    });
  }
}
