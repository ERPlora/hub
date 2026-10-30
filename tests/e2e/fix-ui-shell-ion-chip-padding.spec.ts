// An Ionic chip keeps its own side padding under the shell (FIX-UI-SHELL-ION-CHIP-PADDING-WIPED-BY-PREFLIGHT): every
// `ion-chip` of the Hub lost it and its text sat against the pill's edge (`paddingLeft: 0px` measured on a service of
// «New appointment» and on the table's «Clear filters»; Inventory's categories carried 12px of their own on one side).
// Tailwind's preflight (`* { padding: 0 }`, layer `base`) is a document rule, and a document rule always beats the
// `:host` padding Ionic gives the chip (6px 12px, both modes); the shell's theme takes the reset back for the chip's
// sides, as it did for `ion-title.md` and `ion-badge`. Measured at 390×844, 834×1112 and 1440×900 on the two chips with
// a remove button, a category of the product form (Inventory) and a service of «New appointment» (Appointments), and at
// 1440×900 on «Clear filters»: Ionic's 12px on both sides, the label and the button that far from the edge, the margin
// still 0 (each row sets its gap), and the chip no taller than Ionic's 32px or its 40px remove button, as on main (with
// Ionic's 6px on top and below too, a chip with a remove button grew from 40 to 52px, nearly the 56px of its field).
// «Clear filters» ends in its own icon, which keeps Ionic's margin too (FIX-UI-SHELL-ION-CHIP-ICON-MARGIN-WIPED-BY-PREFLIGHT):
// pulled 4px toward the edge, it sits 8px from it. What the run creates is deleted.
// flow: UI shell relleno de ion-chip
import { type Browser, expect, type Locator, test } from '@playwright/test';

import { A, login, psql, shot, shown } from './helpers';
import { dialog, pickCombo, productsReady } from './inventory-helpers';
import { pick, post } from './service-helpers';

const TAG = 'E2E Chip';
const RUN = Date.now().toString(36);

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** Ionic's own `:host` padding of `ion-chip` on each side, in ios and in md (`chip.ios.css`, `chip.md.css`). */
const IONIC_INLINE = 12;
/** How far Ionic pulls a chip's own icon (its `ion-icon` child, first or last) toward the chip's edge (`ion-chip.js`). */
const IONIC_ICON_PULL = 4;
/** Ionic's `min-height` of `ion-chip`: a chip of one line of text is that tall with or without its 6px on top and below. */
const IONIC_MIN_HEIGHT = 32;

function cleanup(): void {
  const categories = `select id from inventory_category where name like '${TAG}%'`;
  const services = `select id from service_service where name like '${TAG}%'`;
  psql(
    [
      `delete from inventory_productcategory where category_id in (${categories})`,
      `delete from inventory_category where name like '${TAG}%'`,
      `delete from service_assignment where service_id in (${services})`,
      `delete from service_service where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanup);
test.afterAll(cleanup);

async function ownerPage(browser: Browser, next: string) {
  const context = await browser.newContext({ baseURL: A, viewport: VIEWPORTS[0], locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
  return { context, page };
}

interface ChipBox {
  /** The chip's computed padding on each side and its margin on the start side. */
  paddingStart: string;
  paddingEnd: string;
  marginStart: string;
  /** From the chip's inner edge (inside its border) to the label's box, in px. */
  labelInset: number;
  /** From the remove button's right edge to the chip's inner edge, in px. */
  endInset: number;
  /** The label shows its whole text. */
  labelFits: boolean;
  /** The chip's height and that of its last child (the remove button, or the icon of «Clear filters»), in px. */
  height: number;
  tailHeight: number;
}

/** The chip's box as laid out on the page. */
function chipBox(chip: Locator): Promise<ChipBox> {
  return chip.evaluate((el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    const label = el.querySelector('ion-label');
    const tail = el.lastElementChild;
    if (!label || !tail || tail === label) throw new Error(`no label or no remove button in ${el.outerHTML}`);
    return {
      paddingStart: style.paddingInlineStart,
      paddingEnd: style.paddingInlineEnd,
      marginStart: style.marginInlineStart,
      labelInset: label.getBoundingClientRect().left - box.left - parseFloat(style.borderLeftWidth),
      endInset: box.right - parseFloat(style.borderRightWidth) - tail.getBoundingClientRect().right,
      labelFits: label.scrollWidth <= label.clientWidth + 0.5,
      height: box.height,
      tailHeight: tail.getBoundingClientRect().height,
    };
  });
}

/** Ionic's 12px on both sides, the label and the last child that far from the edge (`endInset`: a remove button; a chip's
 *  own icon sits closer); margin and height as on main. */
function expectIonicPadding(measured: ChipBox, what: string, endInset = IONIC_INLINE): void {
  const detail = `${what}: ${JSON.stringify(measured)}`;
  expect(measured.paddingStart, detail).toBe(`${IONIC_INLINE}px`);
  expect(measured.paddingEnd, detail).toBe(`${IONIC_INLINE}px`);
  expect(measured.marginStart, detail).toBe('0px');
  expect(Math.abs(measured.labelInset - IONIC_INLINE), detail).toBeLessThanOrEqual(0.5);
  expect(Math.abs(measured.endInset - endInset), detail).toBeLessThanOrEqual(0.5);
  expect(measured.labelFits, detail).toBe(true);
  expect(measured.height, detail).toBeLessThanOrEqual(Math.max(IONIC_MIN_HEIGHT, measured.tailHeight) + 0.5);
}

test('UI shell relleno de ion-chip — a category of the product form keeps Ionic’s padding, at every width', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/inventory/products');
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  try {
    const drinks = await post<{ id: string; name: string }>(context, '/inventory/categories', { name: `${TAG} drinks ${RUN}` });
    const food = await post<{ id: string; name: string }>(context, '/inventory/categories', { name: `${TAG} food ${RUN}` });
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${A}/inventory/products`);
      await productsReady(page);
      await shown(page).locator('[data-testid=inventory-products-add]').click();
      const form = dialog(page, 'inventory-product-form');
      await expect(form).toBeVisible();
      const categories = form.locator('[data-testid=inventory-product-categories]');
      await pickCombo(page, categories, drinks.name, drinks.name);
      await pickCombo(page, categories, food.name, food.name);
      const chips = form.locator('[data-testid^="inventory-product-categories-chip-"]');
      await expect(chips).toHaveText([drinks.name, food.name]);
      for (const [index, name] of [drinks.name, food.name].entries()) {
        expectIonicPadding(await chipBox(chips.nth(index)), `«${name}» ${vp.label}`);
      }
      await chips.last().scrollIntoViewIfNeeded();
      await page.waitForTimeout(400);
      await page.screenshot({ path: shot(`FIX-UI-SHELL-ION-CHIP-PADDING-WIPED-BY-PREFLIGHT-${vp.label}`) });
      await form.locator('[data-testid=inventory-product-form-cancel]').click();
      await expect(form).toBeHidden();
    }
  } finally {
    await context.close();
  }
});

test('UI shell relleno de ion-chip — a service of «New appointment» keeps Ionic’s padding, at every width', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/appointment/agenda');
  try {
    const service = await post<{ id: string; name: string }>(context, '/service/services', {
      name: `${TAG} Haircut ${RUN}`,
      price: 2000,
      duration_minutes: 30,
      tax_category_key: 'service.generic',
    });
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${A}/appointment/agenda`);
      const view = shown(page);
      await view.locator('[data-testid=appointment-list-empty], [data-testid=appointment-list-row]').first().waitFor({ state: 'visible' });
      await view.locator('[data-testid=appointment-list-add]').click();
      const form = dialog(page, 'appointment-form');
      await expect(form).toBeVisible();
      await pick(page, 'appointment-form-service-add', `Haircut ${RUN}`, service.name);
      const chip = form.locator(`[data-testid=appointment-form-service-${service.id}]`);
      await expect(chip).toHaveText(service.name);
      expectIonicPadding(await chipBox(chip), `«${service.name}» ${vp.label}`);
      if (vp === VIEWPORTS[0]) {
        await chip.scrollIntoViewIfNeeded();
        await page.waitForTimeout(400);
        await page.screenshot({ path: shot('FIX-UI-SHELL-ION-CHIP-PADDING-WIPED-BY-PREFLIGHT-appointment-390') });
      }
      await form.locator('[data-testid=appointment-form-cancel]').click();
      await expect(form).toBeHidden();
    }
  } finally {
    await context.close();
  }
});

// The table's «Clear filters» is a chip too, with its icon in the remove button's place. It sits in the row of column
// filters, which a desk shows (on a phone the filters fold behind the funnel, whose «Clear» is a button).
test('UI shell relleno de ion-chip — «Clear filters» of a table keeps Ionic’s padding', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/combo/menus');
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${A}/combo/menus`);
    const view = shown(page);
    await view.locator('[data-testid=combo-menus-filter-name] input').fill(`${TAG} ${RUN}`);
    const clear = view.locator('[data-testid=combo-menus-filters-clear]');
    await expect(clear).toBeVisible();
    expectIonicPadding(await chipBox(clear), '«Clear filters» 1440', IONIC_INLINE - IONIC_ICON_PULL);
    await clear.click();
    await expect(clear).toBeHidden();
  } finally {
    await context.close();
  }
});
