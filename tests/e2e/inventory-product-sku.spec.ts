// flow: INVENTORY-F01 · hub#2539 — «New product» kept «Save» off without a word while the SKU was empty. Now the SKU
// may be left empty and the product gets the catalog's next number; while the name or the tax category is missing, the
// window says which on its own line above the buttons, a status a screen reader announces as it changes.
// Real hub, SaaS, Taxes and Inventory; the products made are removed.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { cutLabels } from './field-labels';
import { A, capture, login, psql, shown, signedInSpanish } from './helpers';
import { fill, pickCombo, presentedDialog, productRow, productsReady, searchProducts, stamp } from './inventory-helpers';
import { WINDOW_SIZES } from './screen';

const TEXTS = {
  en: {
    name: 'Enter the name to continue.',
    tax: 'Choose the tax category to continue.',
    sku: 'Leave it empty to number it automatically (10000, 10001…).',
    query: 'generic',
    option: /Product — generic/,
  },
  es: {
    name: 'Escribe el nombre para continuar.',
    tax: 'Elige la categoría fiscal para continuar.',
    sku: 'Déjalo vacío para numerarlo solo (10000, 10001…).',
    query: 'general',
    option: /Producto — general/,
  },
} as const;
type Lang = keyof typeof TEXTS;

const NAME = 'E2E No SKU';

test.afterAll(() => {
  const made = `select id from inventory_product where name like '${NAME}%'`;
  psql(`delete from inventory_stockmovement where product_id in (${made})`);
  psql(`delete from inventory_productcategory where product_id in (${made})`);
  psql(`delete from inventory_product where name like '${NAME}%'`);
});

/** What is wrong with where the hint sits: it must lie inside the window and the screen, whole on its line, above «Save». */
async function hintMisplaced(form: Locator): Promise<string[]> {
  const hint = await form.locator('[data-testid=inventory-product-form-hint]').elementHandle();
  const save = await form.locator('[data-testid=inventory-product-form-submit]').elementHandle();
  return form.evaluate(
    (modal, [note, button]) => {
      const box = (el: Element) => el.getBoundingClientRect();
      const window = box(modal.shadowRoot?.querySelector('[part~="content"]') ?? modal.querySelector('.ep-form-modal__content')!);
      const [h, s] = [box(note!), box(button!)];
      const problems: string[] = [];
      if (h.height === 0 || h.width === 0) problems.push('the hint has no box');
      if (h.left < window.left - 0.5 || h.right > window.right + 0.5) problems.push(`the hint leaves the window: ${h.left}–${h.right} in ${window.left}–${window.right}`);
      if (h.bottom > s.top + 0.5) problems.push(`the hint is not above «Save»: its bottom ${h.bottom}, Save's top ${s.top}`);
      if (h.top < 0 || h.bottom > innerHeight) problems.push(`the hint is off the screen: ${h.top}–${h.bottom} of ${innerHeight}`);
      if (note!.scrollWidth > note!.clientWidth + 1) problems.push('the hint overflows its line');
      return problems;
    },
    [hint, save] as const,
  );
}

async function newProductWithoutSku(page: Page, lang: Lang, size: (typeof WINDOW_SIZES)[number]): Promise<void> {
  const texts = TEXTS[lang];
  await productsReady(page);
  const form = await presentedDialog(page, 'inventory-product-form', () => shown(page).locator('[data-testid=inventory-products-add]').click());
  const hint = form.locator('[data-testid=inventory-product-form-hint]');
  const save = form.locator('[data-testid=inventory-product-form-submit]');

  await expect(hint).toHaveText(texts.name);
  await expect(hint).toHaveAttribute('role', 'status');
  await expect(save).toHaveJSProperty('disabled', true);
  await expect(form.locator('[data-testid=inventory-product-sku] .helper-text')).toHaveText(texts.sku);
  expect(await cutLabels(form)).toEqual([]);
  expect(await hintMisplaced(form)).toEqual([]);
  await capture(page, `INVENTORY-F01-no-sku-${lang}-${size.label}`);

  const name = `${NAME} ${lang} ${size.label} ${stamp()}`;
  await fill(form, 'inventory-product-name', name);
  await expect(hint).toHaveText(texts.tax);
  expect(await hintMisplaced(form)).toEqual([]);
  await fill(form, 'inventory-product-price', '4,50');
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), texts.query, texts.option);
  await expect(hint).toHaveCount(0);
  await expect(save).toHaveJSProperty('disabled', false);
  await save.click();
  await expect(form).toBeHidden();

  const sku = psql(`select sku from inventory_product where name = '${name}' and not is_deleted`).trim();
  expect(sku).toMatch(/^[1-9][0-9]{4,8}$/);
  await searchProducts(page, name);
  await expect(productRow(page, sku)).toBeVisible();
}

for (const size of WINDOW_SIZES) {
  const viewport = { width: size.width, height: size.height };

  test(`INVENTORY-F01 ${size.label} en: «Save» off says what is missing, and a product without SKU is numbered`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page, A, '/inventory/products');
    await newProductWithoutSku(page, 'en', size);
  });

  test(`INVENTORY-F01 ${size.label} es: «Guardar» apagado dice qué falta, y un producto sin SKU se numera`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, viewport, '/inventory/products');
    await newProductWithoutSku(page, 'es', size);
    await context.close();
  });
}
