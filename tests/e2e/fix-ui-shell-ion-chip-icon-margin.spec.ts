// The icon of an Ionic chip keeps its gap to the chip's text under the shell (FIX-UI-SHELL-ION-CHIP-ICON-MARGIN-WIPED-BY-PREFLIGHT):
// the icon of every `ion-chip` of the Hub sat against its text, as the «⚠Not configured» of Inventory › Products and of the
// product form (`margin-inline-end: 0px` measured on its `ion-icon`). Tailwind's preflight (`* { margin: 0 }`, layer `base`)
// is a document rule, and a document rule always beats the `::slotted(ion-icon:first-child|last-child)` margins Ionic gives
// the icon of a chip (both modes: 8px to the text, 4px pulled toward the chip's edge and 4px into its padding on top and
// below); the shell's theme takes the reset back for the chip's own icons, as it did for its sides and for the icon of a
// button. Measured at 390×844, 834×1112 and 1440×900 on the chip of a product with no usable tax category, in the list
// filtered by «Not configured» and in the product's form: Ionic's margins, a gap of at least 6px between the icon and the
// text, the icon 8px from the chip's edge (Ionic's 12px padding less its 4px pull) and whole inside the chip, and the chip
// no taller than Ionic's 32px, as on main. The table's «Clear filters» ends in its own icon, mirrored: measured at 1440×900
// (its row of column filters is a desk's), the icon after the text with the same gap and 8px from the chip's end edge.
// What the run creates is deleted.
// flow: ui-shell-ion-chip-icon-margin
import { expect, type Locator, test } from '@playwright/test';

import { A, api, login, psql, record, shot, shown } from './helpers';
import { cleanInventory, createProduct, dialog, productsReady, stamp, VIEWPORTS } from './inventory-helpers';

const KEY = 'FIX-UI-SHELL-ION-CHIP-ICON-MARGIN-WIPED-BY-PREFLIGHT';

/** Ionic's margins of an `ion-icon` that is the first or the last child of an `ion-chip`, in ios and in md (`ion-chip.js`). */
const IONIC_ICON = {
  first: { start: '-4px', end: '8px', top: '-4px', bottom: '-4px' },
  last: { start: '8px', end: '-4px', top: '-4px', bottom: '-4px' },
};
/** How far Ionic pulls the icon toward the chip's edge. */
const IONIC_ICON_PULL = 4;
/** Ionic's `:host` padding of `ion-chip` on each side (both modes), which the shell keeps (FIX-UI-SHELL-ION-CHIP-PADDING-WIPED-BY-PREFLIGHT). */
const IONIC_INLINE = 12;
/** Ionic's `min-height` of `ion-chip`. */
const IONIC_MIN_HEIGHT = 32;
/** The least room between the icon's box and the text's that still reads as a gap (Ionic gives 8px). */
const MIN_GAP = 6;

test.afterAll(cleanInventory);

interface IconBox {
  /** The icon's computed margins. */
  marginStart: string;
  marginEnd: string;
  marginTop: string;
  marginBottom: string;
  /** Between the icon's box and the chip's text, in px. */
  gap: number;
  /** From the chip's nearest inner edge (inside its border) to the icon, in px. */
  inset: number;
  /** The icon's box lies whole inside the chip's. */
  inside: boolean;
  height: number;
}

/** The chip's own icon (its first or its last child) and its text, as laid out on the page. */
function iconBox(chip: Locator, side: 'first' | 'last'): Promise<IconBox> {
  return chip.evaluate((el, side) => {
    const icon = el.querySelector(':scope > ion-icon');
    const label = el.querySelector(':scope > ion-label');
    const end = side === 'first' ? el.firstElementChild : el.lastElementChild;
    if (!icon || !label || end !== icon) throw new Error(`no icon ${side}, or no label, in ${el.outerHTML}`);
    // The text's own boxes: an `ion-label` laid out inline (the list's chip) spans the text, and so does its range.
    const range = document.createRange();
    range.selectNodeContents(label);
    const text = [...range.getClientRects()].filter((r) => r.width > 0);
    if (!text.length) throw new Error(`no text in ${el.outerHTML}`);
    const style = getComputedStyle(icon);
    const chipStyle = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    const at = icon.getBoundingClientRect();
    return {
      marginStart: style.marginInlineStart,
      marginEnd: style.marginInlineEnd,
      marginTop: style.marginTop,
      marginBottom: style.marginBottom,
      gap: side === 'first' ? Math.min(...text.map((r) => r.left)) - at.right : at.left - Math.max(...text.map((r) => r.right)),
      inset:
        side === 'first'
          ? at.left - box.left - parseFloat(chipStyle.borderLeftWidth)
          : box.right - parseFloat(chipStyle.borderRightWidth) - at.right,
      inside: at.width >= 1 && at.left >= box.left - 0.5 && at.right <= box.right + 0.5 && at.top >= box.top - 0.5 && at.bottom <= box.bottom + 0.5,
      height: box.height,
    };
  }, side);
}

/** Ionic's margins on the icon, its gap to the text and its place 8px from the edge; the chip whole and as tall as on main. */
function expectIonicIcon(measured: IconBox, side: 'first' | 'last', what: string): void {
  const detail = `${what}: ${JSON.stringify(measured)}`;
  const ionic = IONIC_ICON[side];
  expect(measured.marginStart, detail).toBe(ionic.start);
  expect(measured.marginEnd, detail).toBe(ionic.end);
  expect(measured.marginTop, detail).toBe(ionic.top);
  expect(measured.marginBottom, detail).toBe(ionic.bottom);
  expect(measured.gap, detail).toBeGreaterThanOrEqual(MIN_GAP);
  expect(Math.abs(measured.inset - (IONIC_INLINE - IONIC_ICON_PULL)), detail).toBeLessThanOrEqual(0.5);
  expect(measured.inside, detail).toBe(true);
  expect(measured.height, detail).toBeLessThanOrEqual(IONIC_MIN_HEIGHT + 0.5);
}

test('ui-shell-ion-chip-icon-margin — the «Not configured» chip keeps its icon apart from its text, in the list and in the form, at every width', async ({
  page,
  context,
}) => {
  await login(page, A, '/inventory/dashboard');
  // A product whose tax category Taxes deactivated is «Not configured» (INVENTORY-F05); `e2e.inv_*` is what `cleanInventory` removes.
  const key = `e2e.inv_icon_${stamp().toLowerCase()}`;
  const created = await api(context, A, 'POST', '/tax/categories', { key, name: 'E2E chip icon tax' });
  expect(created.status).toBe(201);
  const product = await createProduct(context, { name: 'E2E Chip icon wine', sku: `E2E-ICON-${stamp()}`, tax_category_key: key });
  psql(`update tax_taxcategory set is_active = false where key = '${key}'`);
  try {
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${A}/inventory/products?status=unconfigured`);
      await productsReady(page);
      // The session, for ui-clip-sweep.sh over this same page.
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
      const marker = shown(page).locator(`[data-testid=inventory-products-unconfigured-${product.id}]`);
      await expect(marker).toBeVisible();
      await page.waitForTimeout(400);
      const list = await iconBox(marker, 'first');
      record(`${KEY}-list-${vp.label}`, list);
      await page.screenshot({ path: shot(`${KEY}-${vp.label}`) });

      await marker.click();
      const form = dialog(page, 'inventory-product-form');
      const formChip = form.locator('[data-testid=inventory-product-tax-unconfigured]');
      await expect(formChip).toBeVisible();
      await page.waitForTimeout(400);
      const inForm = await iconBox(formChip, 'first');
      record(`${KEY}-form-${vp.label}`, inForm);
      if (vp.label === '390') {
        await formChip.scrollIntoViewIfNeeded();
        await page.screenshot({ path: shot(`${KEY}-form-390`) });
      }
      await form.locator('[data-testid=inventory-product-form-cancel]').click();
      await expect(form).toBeHidden();

      expectIonicIcon(list, 'first', `list ${vp.label}`);
      expectIonicIcon(inForm, 'first', `form ${vp.label}`);
    }
  } finally {
    psql(`update tax_taxcategory set is_active = true where key = '${key}'`);
  }
});

// The table's «Clear filters» (DataTable of @erplora/ui) ends in its icon: the same cure, on the other side.
test('ui-shell-ion-chip-icon-margin — «Clear filters» of a table keeps its icon apart from its text', async ({ page }) => {
  await login(page, A, '/combo/menus');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${A}/combo/menus`);
  const view = shown(page);
  await view.locator('[data-testid=combo-menus-filter-name] input').fill(`E2E Chip icon ${stamp()}`);
  const clear = view.locator('[data-testid=combo-menus-filters-clear]');
  await expect(clear).toBeVisible();
  const measured = await iconBox(clear, 'last');
  record(`${KEY}-clear-filters-1440`, measured);
  expectIonicIcon(measured, 'last', '«Clear filters» 1440');
  await clear.click();
  await expect(clear).toBeHidden();
});
