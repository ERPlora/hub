// hub#526: since hub#416 the assistant's card left out every id its schema does not mark, so «delete the product red
// wine», «put it in Drinks», «delete the category Drinks» or «receive 6 of it» said no product and no category. Now each
// one is named as the screens name it — a product and a category by their name —, read as the person, in their
// language, never by its id. End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this folder, «El asistente»). Cancelled, nothing
// changes. What this file creates is named «E2E …» (SKU `E2E-…`) and goes away (inventory-helpers.ts `cleanInventory`);
// the apps it turns on are turned off again.
// flow: INVENTORY-F04 INVENTORY-F07 INVENTORY-F08 INVENTORY-F13 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cancel, cardSpec, datumOf, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, untilStill } from './helpers';
import { cleanInventory, createProduct, stamp } from './inventory-helpers';

/** A business is born with every app off; Inventory requires Taxes. */
const NEEDED = ['tax', 'inventory'];

/** What the screens call each record, by the language of the card; a quantity as each language writes it, and the
 *  count the card said instead of a receipt's lines (hub#970). */
const WORDS = {
  es: { product: 'Producto', category: 'Categoría', products: 'Productos', twoAndAHalf: '2,5', oneItem: '1 elemento' },
  en: { product: 'Product', category: 'Category', products: 'Products', twoAndAHalf: '2.5', oneItem: '1 item' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

cardSpec(NEEDED, cleanInventory);

/** A category and a product in it, through the app's own API. */
async function aCatalog(context: BrowserContext) {
  const tag = stamp();
  const created = await api<{ id: string; name: string; slug: string }>(context, A, 'POST', '/inventory/categories', {
    name: `E2E Bebidas ${tag}`,
    slug: `e2e-drinks-${tag.toLowerCase()}`,
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  const category = created.data;
  const product = await createProduct(context, {
    name: `E2E Vino tinto ${tag}`,
    sku: `E2E-VT-${tag}`,
    category_ids: [category.id],
  });
  return { category, product };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`inventory-assistant-card — in ${language}, a write of Inventory says which product or category, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const { category, product } = await aCatalog(context);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra el producto vino tinto», a dangerous write: the product by its name, titled as the screens call one, in
    // every size.
    const deleted = await datumOf(page, 'inventory__product__delete', { id: product.id });
    expect([deleted.label, deleted.value]).toEqual([words.product, product.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.product}: ${product.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(product.sku);
      await untilStill(page);
      await capture(page, `hub-526-product-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Quita el vino tinto de Bebidas»: a write that is not dangerous is said in one line, the product and the category
    // by their names.
    const unlinked = await fieldsOf(page, 'inventory__product_category__remove', {
      product_id: product.id,
      category_id: category.id,
    });
    expect(unlinked.map((field) => [field.name, field.label, field.value])).toEqual([
      ['product_id', words.product, product.name],
      ['category_id', words.category, category.name],
    ]);
    await expect(card(page)).toContainText(product.name);
    await expect(card(page)).toContainText(category.name);
    await cancel(page);

    // «Recibe 6 de vino tinto y 2,5 de cerveza», a write that is not dangerous, said in one line: the server sends each
    // line of the receipt with its product by its name and marks the list said in words, so the screen says each line
    // by its product and its quantity as the person writes one («E2E Vino tinto … · 6», «2,5» in Spanish), never
    // «1 elemento» (hub#970), in every size; no id (`fieldsOf`).
    const tag = stamp();
    const beer = await createProduct(context, { name: `E2E Cerveza ${tag}`, sku: `E2E-CZ-${tag}` });
    const received = await datumOf(
      page,
      'inventory__stock__receive',
      { items: [{ product_id: product.id, qty: '6' }, { product_id: beer.id, qty: '2.5' }] },
      'items',
    );
    expect([received.label, received.value, received.named]).toEqual([
      words.products,
      [{ product_id: product.name, qty: '6' }, { product_id: beer.name, qty: '2.5' }],
      true,
    ]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${product.name} · 6`);
      await expect(card(page)).toContainText(`${beer.name} · ${words.twoAndAHalf}`);
      await expect(card(page)).not.toContainText(words.oneItem);
      await expect(card(page)).not.toContainText(product.sku);
      await untilStill(page);
      await capture(page, `hub-970-receipt-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Borra la categoría Bebidas», a dangerous write: the category by its name (never its slug), titled as the screens
    // call one. No id on any card: `fieldsOf` checks each one.
    const removed = await datumOf(page, 'inventory__category__delete', { id: category.id });
    expect([removed.label, removed.value]).toEqual([words.category, category.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.category}: ${category.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(category.slug);
      await untilStill(page);
      await capture(page, `hub-526-category-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // Cancelled, nothing changed: the product still there, in its category, with no stock received; the category
    // still there.
    const detail = await api<{ id: string; stock: string; category_ids: string[] }>(
      context, A, 'GET', `/inventory/products/detail?id=${product.id}`,
    );
    expect(detail.status, JSON.stringify(detail.data)).toBe(200);
    expect([detail.data.id, Number(detail.data.stock), detail.data.category_ids]).toEqual([product.id, 0, [category.id]]);
    const categories = await api<{ rows: { id: string }[] }>(
      context, A, 'GET', `/inventory/categories?search=${encodeURIComponent(category.name)}`,
    );
    expect(categories.status, JSON.stringify(categories.data)).toBe(200);
    expect(categories.data.rows.map((row) => row.id)).toEqual([category.id]);
    await context.close();
  });
}
