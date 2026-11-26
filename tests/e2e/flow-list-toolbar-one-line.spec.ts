// flow: FLOW-F02
// «Your automations» with one automation: the search box, «Order» and the filters button sit side by side like the
// other lists of the Hub (Tasks), «Order» as wide as what it shows, and the search box's example text is read whole.
// On a desk the list's bar is one line and the first automation shows near the top; on a phone the search box takes
// its own line and the rest follows, as in Tasks. «Showing» and «Starts with» live behind the filters button, with
// their labels whole, and narrow the list. Measured in boxes, in Spanish and English, in a phone, a tablet and a desk.
// Its automations are named «E2E FlowBar …».
import { expect, type Locator, type Page, test } from '@playwright/test';

import { cutLabels } from './field-labels';
import { deleteFlowsNamed, filterList, manualFlow, signedIn } from './flow-helpers';
import { capture, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { noHorizontalScroll } from './schedule-helpers';

const TAG = 'E2E FlowBar';
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1280', width: 1280, height: 720 },
] as const;
type Size = (typeof SIZES)[number];
const WORDS = {
  es: { paused: 'Solo las que están en pausa', noMatch: 'Aquí no hay nada que encaje con eso.' },
  en: { paused: 'Only the paused ones', noMatch: 'Nothing here matches that.' },
} as const;

test.beforeAll(() => deleteFlowsNamed(TAG));
test.afterAll(() => deleteFlowsNamed(TAG));

interface Box {
  top: number;
  bottom: number;
  width: number;
}

const boxOf = (locator: Locator): Promise<Box> =>
  locator.evaluate((element) => {
    const { top, bottom, width } = element.getBoundingClientRect();
    return { top, bottom, width };
  });

/** How much wider the search box's example text is than the room its field gives it (0 or less: read whole). */
function searchTextOverflow(search: Locator): Promise<number> {
  return search.locator('input').evaluate((input: HTMLInputElement) => {
    const style = getComputedStyle(input);
    const context = document.createElement('canvas').getContext('2d')!;
    context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const room = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    return context.measureText(input.placeholder).width - room;
  });
}

/** Whether the option a select shows is cut. */
function cutText(select: Locator): Promise<boolean> {
  return select.evaluate((host) => {
    const text = host.shadowRoot?.querySelector<HTMLElement>('.select-text');
    return !!text && text.scrollWidth > text.clientWidth;
  });
}

async function expectBar(page: Page, size: Size): Promise<void> {
  const list = shown(page).locator('[data-testid=flow-list-section]');
  const search = list.locator('[data-testid=flow-list-search]');
  const order = list.locator('[data-testid=flow-list-sort]');
  const funnel = list.locator('[data-testid=flow-list-filters-toggle]');
  const where = size.label;
  const [searchBox, orderBox, bar] = await Promise.all([search, order, list.locator('.data-table__bar-main')].map(boxOf));

  expect(orderBox.width, `${where}: «Order» as wide as what it shows`).toBeLessThanOrEqual(16 * 16 + 1);
  expect(await cutText(order), `${where}: «Order» cut`).toBe(false);
  expect(await searchTextOverflow(search), `${where}: the search box's text is cut`).toBeLessThanOrEqual(0);
  await expect(funnel, `${where}: the filters button`).toBeVisible();
  const funnelBox = await boxOf(funnel);
  if (size.width >= 1024) {
    for (const [name, box] of [['«Order»', orderBox], ['the filters button', funnelBox]] as const) {
      expect(Math.abs(box.top + box.bottom - searchBox.top - searchBox.bottom) / 2, `${where}: ${name} on the search's line`).toBeLessThanOrEqual(8);
    }
    expect(bar.bottom - bar.top, `${where}: the bar is one line`).toBeLessThanOrEqual(64);
    const first = list.locator('[data-testid=flow-list-row]').first();
    expect((await boxOf(first)).top, `${where}: the first automation near the top`).toBeLessThanOrEqual(size.height / 2);
  } else if (size.width <= 640) {
    expect(orderBox.top, `${where}: «Order» under the search box`).toBeGreaterThanOrEqual(searchBox.bottom);
  }
  await noHorizontalScroll(page, where);
}

/** «Showing» and «Starts with» behind the filters button, their labels whole; «paused» leaves the running one out,
 *  and «Show them all again» brings it back. */
async function expectFilters(page: Page, size: Size, name: string, words: (typeof WORDS)[keyof typeof WORDS]): Promise<void> {
  const list = shown(page).locator('[data-testid=flow-list-section]');
  await list.locator('[data-testid=flow-list-filters-toggle]').click();
  const panel = shown(page).locator('[data-testid=flow-list-filters-panel]');
  await expect(panel.locator('[data-testid=flow-list-filter-state]')).toBeVisible();
  await expect(panel.locator('[data-testid=flow-list-filter-trigger_kind]')).toBeVisible();
  expect(await cutLabels(panel), `${size.label}: the filters' labels`).toEqual([]);
  await capture(page, `hub-2542-flow-list-filters-${words === WORDS.es ? 'es' : 'en'}-${size.label}`);
  await panel.locator('[data-testid=flow-list-filters-close]').click();
  await filterList(page, 'flow-list', 'state', words.paused);
  await expect(list.locator('[data-testid=flow-list-nomatch]')).toContainText(words.noMatch);
  await list.locator('[data-testid=flow-list-clear]').click();
  await expect(list.locator('[data-testid=flow-list-row]', { hasText: name })).toBeVisible();
}

async function runAt(page: Page, size: Size, name: string, lang: keyof typeof WORDS): Promise<void> {
  const list = shown(page).locator('[data-testid=flow-list-section]');
  await expect(list.locator('[data-testid=flow-list-row]', { hasText: name })).toBeVisible();
  // The example text shows while the search box is empty.
  await expectBar(page, size);
  await capture(page, `hub-2542-flow-list-bar-${lang}-${size.label}`);
  await list.locator('[data-testid=flow-list-search] input').fill(name);
  await expect(list.locator('[data-testid=flow-list-search] input')).toHaveValue(name);
  await expect(list.locator('[data-testid=flow-list-row]')).toHaveCount(1);
  await expect(list.locator('[data-testid=flow-list-row]')).toContainText(name);
  await expectFilters(page, size, name, WORDS[lang]);
}

for (const size of SIZES) {
  test(`FLOW-F02 the list's search, «Order» and filters button fit side by side, in Spanish at ${size.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} es ${size.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedInSpanish(browser, size, '/flow/automations');
    try {
      await manualFlow(context, name, [{ id: 's1', kind: 'ask', title: `${name}?` }], []);
      await saveSessionForTheSweep(context);
      await runAt(page, size, name, 'es');
    } finally {
      await context.close();
    }
  });

  test(`FLOW-F02 the list's search, «Order» and filters button fit side by side, in English at ${size.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} en ${size.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/flow/automations', size);
    try {
      await manualFlow(context, name, [{ id: 's1', kind: 'ask', title: `${name}?` }], []);
      await runAt(page, size, name, 'en');
    } finally {
      await context.close();
    }
  });
}
