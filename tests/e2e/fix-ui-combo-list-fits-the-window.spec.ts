// hub#443 — a Combo (ui:Combo) whose options come from the server opens its list where it fits in the
// window: Menus and combos › «New menu» › «VAT category» (COMBO-F02), in Chrome, against hub `a` and the
// real Taxes app. The list used to be placed while it only said «Loading…» and then grow down past the
// bottom of the window with the categories (a tablet held landscape, 1280×800: four categories seen and
// «Restaurant — food · 10%» out of reach unless typed). Now, at every size, the open list lies inside the
// window, beside the field (under it, or over it when there is more room there) without covering it, and
// every category can be scrolled to inside the list and chosen without typing; Save keeps it. Nothing is
// created but the menu, named «E2E VAT list …» and removed before and after.
// flow: COMBO-F02, ui:Combo
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, login, psql, shown } from './helpers';

const TAG = 'E2E VAT list';
const VIEWPORTS = [
  { label: '1280x800', width: 1280, height: 800 },
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];
const FIELD = 'combo-menu-form-tax_category';

function cleanUp(): void {
  psql(`delete from combo_combo where name like '${TAG}%'`);
}

test.describe.configure({ mode: 'serial' });
test.beforeAll(cleanUp);
test.afterAll(cleanUp);

async function ownerPage(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/combo/menus');
  return { context, page };
}

interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

/** The open list's box (the popover's content, where Ionic paints it), the field's, its floating label's (drawn
 *  on the field's top border, half of it above the field's box) and the window's height. */
function boxes(page: Page): Promise<{ list: Box | null; field: Box; label: Box; window: number }> {
  return page.evaluate((testid) => {
    const box = (el: Element): Box => {
      const r = el.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, left: r.left, right: r.right };
    };
    const popover = document.querySelector('ion-popover.combo__popover:not(.overlay-hidden)');
    const content = popover?.shadowRoot?.querySelector('.popover-content') ?? null;
    const field = document.querySelector(`[data-testid=${testid}]`)!;
    const label = field.querySelector('.label-text')!;
    return { list: content ? box(content) : null, field: box(field), label: box(label), window: window.innerHeight };
  }, FIELD);
}

/** Scrolls the list's own scroller until `option` is in view (as a finger would), and says where it ended. */
async function scrollListTo(page: Page, testid: string): Promise<Box> {
  return page.evaluate(async (id) => {
    const option = document.querySelector(`[data-testid="${id}"]`)!;
    const content = option.closest('ion-content') as (HTMLElement & { getScrollElement(): Promise<HTMLElement> }) | null;
    const scroller = await content!.getScrollElement();
    const r = option.getBoundingClientRect();
    const s = scroller.getBoundingClientRect();
    if (r.bottom > s.bottom) scroller.scrollTop += r.bottom - s.bottom;
    if (r.top < s.top) scroller.scrollTop -= s.top - r.top;
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    const after = option.getBoundingClientRect();
    return { top: after.top, bottom: after.bottom, left: after.left, right: after.right };
  }, testid);
}

for (const vp of VIEWPORTS) {
  test(`COMBO-F02 / ui:Combo — «VAT category» opens its whole list inside the window (${vp.label})`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, { width: vp.width, height: vp.height });
    try {
      await shown(page).locator('[data-testid=combo-menus-row], [data-testid=combo-menus-empty]').first().waitFor();
      await shown(page).locator('[data-testid=combo-menus-add]').click();
      const form = page.locator('ion-modal[data-testid=combo-menu-form]');
      await expect(form).toBeVisible();
      const name = `${TAG} ${vp.label} ${Date.now().toString(36)}`;
      const nameInput = page.locator('[data-testid=combo-menu-form-name] input');
      await nameInput.fill(name);
      await nameInput.blur();
      await expect(page.locator('[data-testid=combo-menu-form-help-service]')).toHaveAttribute('data-active', 'true');

      // A touch on the field opens every category, as the server sends them (more than fit under a low field).
      const input = page.locator(`[data-testid=${FIELD}] input`);
      await input.click();
      await expect(input).toHaveAttribute('aria-expanded', 'true');
      const options = page.locator(`[data-testid^=${FIELD}-option-]`);
      await expect.poll(() => options.count(), { message: 'the categories arrive' }).toBeGreaterThan(8);
      await expect(page.locator(`[data-testid=${FIELD}-loading]`)).toHaveCount(0);

      // The list, once the categories are in, lies inside the window and beside the field, never over it nor
      // over its label (when it opens over the field, the label «VAT category» stays readable).
      await expect
        .poll(
          async () => {
            const { list, field, label, window } = await boxes(page);
            if (!list) return 'no list';
            const inside = list.top >= -0.5 && list.bottom <= window + 0.5;
            const beside = list.top >= field.bottom - 0.5 || list.bottom <= Math.min(field.top, label.top) + 0.5;
            return inside && beside
              ? 'inside, beside the field'
              : `list ${Math.round(list.top)}–${Math.round(list.bottom)}, field ${Math.round(field.top)}–${Math.round(field.bottom)}, label from ${Math.round(label.top)}, window ${window}`;
          },
          { message: `the open list fits in the window at ${vp.label}` },
        )
        .toBe('inside, beside the field');
      await capture(page, `HUB-443-vat-list-open-${vp.label}`);

      // Every category is reachable by scrolling the list itself: the last one ends up inside the window.
      const ids = await options.evaluateAll((els) => els.map((el) => el.getAttribute('data-testid')!));
      const last = await scrollListTo(page, ids[ids.length - 1]);
      const { window } = await boxes(page);
      expect(last.top, 'the last category, scrolled to, starts inside the window').toBeGreaterThanOrEqual(0);
      expect(last.bottom, 'the last category, scrolled to, ends inside the window').toBeLessThanOrEqual(window + 0.5);
      await capture(page, `HUB-443-vat-list-scrolled-${vp.label}`);

      // «Restaurant — food» is chosen from the list, without typing, and kept by Save.
      const food = options.filter({ hasText: 'Restaurant — food' }).first();
      const foodId = await food.getAttribute('data-testid');
      await scrollListTo(page, foodId!);
      await food.click();
      await expect(input).toHaveValue(/Restaurant — food/);
      await page.locator('[data-testid=combo-menu-form-submit]').click();
      await expect(form).toBeHidden();
      await expect
        .poll(() => psql(`select coalesce(t.key, '') from combo_combo c left join tax_taxcategory t on t.id = c.tax_category_id where c.name = '${name}'`))
        .toBe('restaurant.food');
    } finally {
      await context.close();
    }
  });
}
