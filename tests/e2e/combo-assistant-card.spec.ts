// hub#669: since hub#416 the assistant's card left out every id its schema does not mark, so «withdraw the menu of the
// day», «remove the starters», «change the lentils for the soup» or «put the mains first» said no menu, no course, no
// choice and no product. Now each one is named as the screens name it — a menu and a course by their name, a choice and
// a product by the product's name —, read as the person, in their language, never by its id. End to end with the
// stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded
// with it (README of this folder, «El asistente»). Cancelled, nothing changes. What this file creates is named
// «E2E Tarjeta …» (SKU `E2E-TJ-…`) and goes away before and after; the apps it turns on are turned off again.
// flow: COMBO-F04 COMBO-F05 COMBO-F06 BASE-F97
import { type BrowserContext, expect, test } from '@playwright/test';

import { cancel, cardSpec, datumOf, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, psql, untilStill } from './helpers';
import { createProduct, stamp } from './inventory-helpers';
import { post } from './service-helpers';

/** A business is born with every app off; Menus and combos requires Inventory and Taxes. */
const NEEDED = ['tax', 'inventory', 'combo'];
const TAG = 'E2E Tarjeta';

/** What the screens call each record, by the language of the card. */
const WORDS = {
  es: { menu: 'Menú', course: 'Plato', choice: 'Elección', newProduct: 'Producto nuevo', courses: 'Platos' },
  en: { menu: 'Menu', course: 'Course', choice: 'Choice', newProduct: 'New product', courses: 'Courses' },
};
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

/** Every menu, course, choice and product this file made, from hub `a`'s database. */
function cleanUp(): void {
  const menus = `select id from combo_combo where name like '${TAG}%'`;
  const dishes = `select id from inventory_product where sku like 'E2E-TJ-%'`;
  psql(
    [
      `delete from combo_choiceoption where product_id in (${dishes})`,
      `delete from combo_choicegroup where combo_id in (${menus})`,
      `delete from combo_combo where id in (${menus})`,
      `delete from inventory_product where id in (${dishes})`,
    ].join('; '),
  );
}

cardSpec(NEEDED, cleanUp);

/** A menu eaten in with two courses, the lentils in the first one, and the soup that may replace them, through the
 *  apps' own APIs. */
async function aMenu(context: BrowserContext) {
  const tag = stamp();
  const lentils = await createProduct(context, { name: `${TAG} Lentejas ${tag}`, sku: `E2E-TJ-LEN-${tag}` });
  const soup = await createProduct(context, { name: `${TAG} Sopa ${tag}`, sku: `E2E-TJ-SOP-${tag}` });
  const menu = await post<{ id: string; name: string; kitchen_name: string }>(context, '/combo/combos', {
    name: `${TAG} Menú del día ${tag}`,
    kitchen_name: `COCINA ${tag}`,
    price: 1350,
    tax_category_key: 'restaurant.food',
  });
  const starters = await post<{ id: string; name: string }>(context, '/combo/groups', { combo_id: menu.id, name: 'Primeros' });
  const mains = await post<{ id: string; name: string }>(context, '/combo/groups', { combo_id: menu.id, name: 'Segundos' });
  const choice = await post<{ id: string }>(context, '/combo/options', { group_id: starters.id, product_id: lentils.id });
  return { lentils, soup, menu, starters, mains, choice };
}

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`combo-assistant-card — in ${language}, a write of Menus says which menu, course, choice or product, never by its id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const { lentils, soup, menu, starters, mains, choice } = await aMenu(context);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Retira el menú del día», a dangerous write: the menu by its name (never its kitchen name), titled as its list
    // calls one, in every size.
    const withdrawn = await datumOf(page, 'combo__combo__delete', { id: menu.id });
    expect([withdrawn.label, withdrawn.value]).toEqual([words.menu, menu.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.menu}: ${menu.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(menu.kitchen_name);
      await untilStill(page);
      await capture(page, `hub-669-menu-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Cambia las lentejas por la sopa»: a write that is not dangerous is said in one line, the choice and the product
    // that replaces it by their names.
    const changed = await fieldsOf(page, 'combo__option__update', { id: choice.id, new_product_id: soup.id });
    expect(changed.map((field) => [field.name, field.label, field.value])).toEqual([
      ['id', words.choice, lentils.name],
      ['new_product_id', words.newProduct, soup.name],
    ]);
    await expect(card(page)).toContainText(lentils.name);
    await expect(card(page)).toContainText(soup.name);
    await expect(card(page)).not.toContainText(lentils.sku);
    await cancel(page);

    // «Pon los segundos antes que los primeros»: the menu by its name and its courses by theirs, in the order sent.
    const reordered = await fieldsOf(page, 'combo__group__reorder', { id: menu.id, group_ids: [mains.id, starters.id] });
    expect(reordered.map((field) => [field.name, field.label, field.value])).toEqual([
      ['id', words.menu, menu.name],
      ['group_ids', words.courses, [mains.name, starters.name]],
    ]);
    await expect(card(page)).toContainText(menu.name);
    await expect(card(page)).toContainText(mains.name);
    await cancel(page);

    // «Quita los primeros», a dangerous write: the course by its name, titled as its form calls one. No id on any card:
    // `fieldsOf` checks each one.
    const removed = await datumOf(page, 'combo__group__delete', { id: starters.id });
    expect([removed.label, removed.value]).toEqual([words.course, starters.name]);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${words.course}: ${starters.name}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await untilStill(page);
      await capture(page, `hub-669-course-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // Cancelled, nothing changed: the menu still there with its two courses in their order and the lentils in the first.
    const detail = await api<{ id: string; groups: { name: string; options: { product_name: string }[] }[] }>(
      context, A, 'GET', `/combo/combos/detail?id=${menu.id}`,
    );
    expect(detail.status, JSON.stringify(detail.data)).toBe(200);
    expect(detail.data.groups.map((group) => [group.name, group.options.map((option) => option.product_name)])).toEqual([
      [starters.name, [lentils.name]],
      [mains.name, []],
    ]);
    await context.close();
  });
}
