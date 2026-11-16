// flow: TAX-F02, TAX-F04 — hub#888: in a window, fields refused with the same words lose their marks one by one as each
// is corrected, in Taxes too: every field carries the name the server refuses it by, so the window tells which refused
// field a keystroke corrects. Seen in Categories › «+» and in Rules › «+», at 390, 834 and 1440: the save is refused for
// three fields with the same words; typing in one takes the mark from it alone, then another, and the third keeps its
// own. The refusal is answered in the browser (`page.route`), so nothing is created. Once more in Spanish.
import { stamp } from './sale-helpers';
import { type SameWordsWindow, testTheMarksGoOneByOne } from './same-words-helpers';
import { pickCombo } from './tax-helpers';

const TAG = `E2E888 ${stamp()}`;

/** «New tax category»: a key and a name turn «Add» on; the description is left empty, so typing in it is a change. */
const CATEGORY: SameWordsWindow = {
  app: 'TAX-CATEGORY',
  page: '/tax/categories',
  add: 'tax-categories-add',
  testid: 'tax-category-form',
  save: '**/api/tax/categories',
  fill: async (form) => {
    await form.locator('[data-testid=tax-category-form-key] input').fill(`e2e.hub888_${Date.now().toString(36)}`);
    await form.locator('[data-testid=tax-category-form-name] input').fill(`${TAG} Category`);
  },
  keys: ['name', 'description', 'key'],
  created: `select count(*) from tax_taxcategory where name like '${TAG}%'`,
};

/** «New tax rule»: Spain (its code reads the same in any language), a category of the catalogue by its key and a
 *  rate turn «Add» on; the regime and the region are left empty, so typing in them is a change. */
const RULE: SameWordsWindow = {
  app: 'TAX-RULE',
  page: '/tax/rules',
  add: 'tax-rules-add',
  testid: 'tax-rule-form',
  save: '**/api/tax/rules',
  fill: async (form) => {
    await pickCombo(form.page(), form, 'tax-rule-form-country_code', '(ES)', 'ES');
    await pickCombo(form.page(), form, 'tax-rule-form-tax_category_key', 'restaurant.food', 'restaurant.food');
    await form.locator('[data-testid=tax-rule-form-rate_pct] input').fill('10');
    await form.locator('[data-testid=tax-rule-form-component_label] input').fill(`${TAG} Rule`);
  },
  keys: ['regime_key', 'component_label', 'region_code'],
  created: `select count(*) from tax_taxrule where component_label like '${TAG}%'`,
};

testTheMarksGoOneByOne([CATEGORY, RULE]);
