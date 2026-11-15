// flow: COMBO-F02, MODIFIER-F02 — hub#888: in a window, fields refused with the same words lose their marks one by one
// as each is corrected, in Menus and Modifiers too: every field carries the name the server refuses it by, the amount
// (MoneyInput) included, so the window tells which refused field a keystroke corrects. Seen in Menus › «+» and in
// Modifiers › «New group», at 390, 834 and 1440: the save is refused for three fields with the same words; typing in
// one takes the mark from it alone, then another, and the third keeps its own. The refusal is answered in the browser
// (`page.route`), so nothing is created. Once more in Spanish.
import { type SameWordsWindow, testTheMarksGoOneByOne } from './same-words-helpers';
import { stamp } from './sale-helpers';

const TAG = `E2E888 ${stamp()}`;

/** «New menu» eaten in: its VAT category is chosen by its key, which the search reads in any language. The closed
 *  price is left empty (it is 0 until typed) so that typing «1» in it is an amount. */
const MENU: SameWordsWindow = {
  app: 'COMBO',
  page: '/combo/menus',
  add: 'combo-menus-add',
  testid: 'combo-menu-form',
  save: '**/api/combo/combos',
  fill: async (form) => {
    await form.locator('[data-testid=combo-menu-form-name] input').fill(`${TAG} Menu`);
    const tax = form.locator('[data-testid=combo-menu-form-tax_category] input');
    await tax.click();
    await tax.fill('restaurant.food');
    await form.page().locator('[data-testid="combo-menu-form-tax_category-option-restaurant.food"]').click();
  },
  keys: ['price', 'name', 'kitchen_name'],
  created: `select count(*) from combo_combo where name like '${TAG}%'`,
};

const GROUP: SameWordsWindow = {
  app: 'MODIFIER',
  page: '/modifier/groups',
  add: 'modifier-groups-add',
  testid: 'modifier-group-form',
  save: '**/api/modifier/groups',
  fill: async (form) => {
    await form.locator('[data-testid=modifier-group-form-name] input').fill(`${TAG} Sauces`);
    await form.locator('[data-testid=modifier-group-form-min_choices] input').fill('1');
    await form.locator('[data-testid=modifier-group-form-max_choices] input').fill('2');
  },
  keys: ['max_choices', 'name', 'min_choices'],
  created: `select count(*) from modifier_modifiergroup where name like '${TAG}%'`,
};

testTheMarksGoOneByOne([MENU, GROUP]);
