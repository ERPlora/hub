// Every flow of Taxes, one test each (its key in the title and in `// flow:`), done end to end on the
// real stack. A flow with a screen is seen at 390×844, 834×1112 and 1440×900: `threeShots` resizes,
// brings what the flow shows into sight, checks nothing scrolls sideways and saves
// `.artifacts/APP-TAX-<key>-<width>.png`. The flows without a screen (TAX-F12, F15, F18) are checked
// through the API the pages, the assistant and an integration use. Deeper cases live in
// tax-categories.spec.ts, tax-rules.spec.ts, tax-employee.spec.ts and the app's pytest and Vitest suites.
import { expect, test } from '@playwright/test';

import { A, api, login, shown } from './helpers';
import {
  cleanUp,
  createRule,
  freshCategory,
  listReady,
  pickCombo,
  pickSelect,
  type Rule,
  rowAction,
  rows,
  rulesOf,
  searchFor,
  threeShots,
} from './tax-helpers';

test.afterAll(() => cleanUp());

type Envelope = { error?: { code: string; message: string; fields?: Record<string, string> } };

// flow: TAX-F01 · gh:pm#611
test('TAX-F01: the owner finds a category by what it reads, with the rate it charges today', async ({ page }) => {
  await login(page, A, '/tax/categories');
  await listReady(page, 'categories');
  // The factory catalogue prices a sale: no «Your taxes» step.
  await expect(shown(page).locator('[data-testid=tax-setup]')).toHaveCount(0);
  await shown(page).locator('[data-testid=tax-categories-search] input').fill('food');
  const food = () => shown(page).locator('[data-testid=tax-categories-row][data-id="restaurant.food"]');
  await expect(food()).toContainText('10.00%');
  await expect(food()).toContainText('System');
  await threeShots(page, 'TAX-F01', food);
});

// flow: TAX-F02
test('TAX-F02: «+» creates a custom category; a repeated key is refused under Key', async ({ page }) => {
  await login(page, A, '/tax/categories');
  await listReady(page, 'categories');
  const key = `e2e.books_${Date.now().toString(36)}`;
  const dialog = page.locator('ion-modal[data-testid=tax-category-form]');
  await shown(page).locator('[data-testid=tax-categories-add]').click();
  await dialog.locator('[data-testid=tax-category-form-key] input').fill(key);
  await dialog.locator('[data-testid=tax-category-form-name] input').fill('E2E books');
  await dialog.locator('[data-testid=tax-category-form-submit]').click();
  await expect(dialog).toBeHidden();
  await searchFor(page, 'categories', key);
  const row = () => shown(page).locator(`[data-testid=tax-categories-row][data-id="${key}"]`);
  await expect(row()).toContainText('Custom');
  await threeShots(page, 'TAX-F02', row);

  await shown(page).locator('[data-testid=tax-categories-add]').click();
  await dialog.locator('[data-testid=tax-category-form-key] input').fill(key);
  await dialog.locator('[data-testid=tax-category-form-name] input').fill('Again');
  await dialog.locator('[data-testid=tax-category-form-submit]').click();
  await expect(dialog.locator('[data-testid=tax-category-form-key] .error-text')).toContainText('already a tax category');
  await dialog.locator('[data-testid=tax-category-form-cancel]').click();
});

// flow: TAX-F03 · gh:taxes#12
test('TAX-F03: a component is read right under its root; Status reaches the deactivated ones', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f03');
  const root = await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 21 });
  await createRule(context, {
    country_code: 'ES',
    tax_category_key: key,
    rate_pct: 5.2,
    tax_type: 'surcharge',
    parent_id: root.id,
    component_label: 'Equivalence surcharge',
  });
  const old = await createRule(context, { country_code: 'PT', tax_category_key: key, rate_pct: 23 });
  expect((await api(context, A, 'POST', '/tax/rules/deactivate', { id: old.id })).status).toBe(200);
  await listReady(page, 'rules');
  await searchFor(page, 'rules', key);
  await expect(rows(page, 'rules')).toHaveCount(2);
  await expect(rows(page, 'rules').nth(1)).toContainText('↳');
  await expect(rows(page, 'rules').nth(1)).toContainText('Equivalence surcharge');
  await threeShots(page, 'TAX-F03', () => rows(page, 'rules').nth(1));

  // The deactivated one is behind Status «Deactivated».
  await pickSelect(page, shown(page).locator('[data-testid=tax-rules-status]'), /^Deactivated$/);
  await expect(rows(page, 'rules')).toHaveCount(1);
  await expect(rows(page, 'rules').first()).toContainText('PT');
  // taxes#12: on a phone, a card's actions are comfortable targets (44 px or more). Crossing to 390
  // turns the table into cards: the table row's Restore is still on screen for a moment and is torn
  // down while measured (its box comes back null), so the target is the card's own, once painted.
  await page.setViewportSize({ width: 390, height: 844 });
  const restore = shown(page).locator(`ion-card[data-testid=tax-rules-row] [data-testid=tax-rules-row-${old.id}-restore]`);
  await expect(restore).toBeVisible();
  await expect
    .poll(async () => {
      const box = await restore.boundingBox();
      return box && Math.min(box.width, box.height);
    }, { message: 'the Restore target on a phone' })
    .toBeGreaterThanOrEqual(44);
});

// flow: TAX-F03 · gh:hub#2406
test('TAX-F03: on a phone «Load more» brings the rest and the footer counts every rule on screen', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f03_more');
  // 51 rules of one category, one country each: one more than a page.
  const countries = 'AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU'.split(' ');
  expect(countries).toHaveLength(51);
  const bulk = await api(context, A, 'POST', '/tax/rules/bulk_create', {
    rules: countries.map((country_code) => ({ country_code, tax_category_key: key, rate_pct: 10 })),
  });
  expect(bulk.status).toBe(201);
  await listReady(page, 'rules');
  await shown(page).locator('[data-testid=tax-rules-search] input').fill(key);
  const footer = shown(page).locator('.data-table__pager-info');
  // The search has landed (it is debounced): the first page of the 51.
  await expect(footer).toContainText(/1\s*[–-]\s*50 of 51 rules/);
  await expect(rows(page, 'rules')).toHaveCount(50);
  await shown(page).locator('[data-testid=tax-rules-load-more]').click();
  await expect(rows(page, 'rules')).toHaveCount(51);
  await expect(footer).toContainText('51 rules');
  // hub#2406: never «Showing 51–51» over 51 rules on screen.
  await expect(footer).not.toContainText(/51\s*[–-]\s*51/);
  await expect(shown(page).locator('[data-testid=tax-rules-load-more]')).toHaveCount(0);
});

// flow: TAX-F04 · gh:pm#513 · gh:taxes#47
test('TAX-F04: a rule is created with the Country and Category combos; an overlap is told under «Valid from» at every width', async ({
  page,
  context,
}) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f04');
  await listReady(page, 'rules');
  const dialog = page.locator('ion-modal[data-testid=tax-rule-form]');
  async function fill(rate: string, from: string): Promise<void> {
    await shown(page).locator('[data-testid=tax-rules-add]').click();
    await expect(dialog).toBeVisible();
    await pickCombo(page, dialog, 'tax-rule-form-country_code', 'Spain', 'ES');
    await pickCombo(page, dialog, 'tax-rule-form-tax_category_key', key, key);
    await dialog.locator('[data-testid=tax-rule-form-rate_pct] input').fill(rate);
    await dialog.locator('[data-testid=tax-rule-form-valid_from] input').fill(from);
  }
  await fill('10', '2026-01-01');
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  await expect(dialog).toBeHidden();
  await searchFor(page, 'rules', key);
  await expect(rows(page, 'rules').first()).toContainText('10.00%');

  // The same slot again from June: refused under «Valid from», in sight on a phone too (pm#513).
  await fill('21', '2026-06-01');
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  const validFrom = () => dialog.locator('[data-testid=tax-rule-form-valid_from]');
  await expect(validFrom().locator('.error-text')).toContainText('overlaps another active rule');
  await threeShots(page, 'TAX-F04', () => validFrom());
  await dialog.locator('[data-testid=tax-rule-form-cancel]').click();
  expect(await rulesOf(context, key)).toHaveLength(1);
});

// flow: TAX-F05 · gh:pm#332 · gh:hub#292
test('TAX-F05: an exempt rule pins its rate to 0 % and keeps its cause', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f05');
  await listReady(page, 'rules');
  const dialog = page.locator('ion-modal[data-testid=tax-rule-form]');
  await shown(page).locator('[data-testid=tax-rules-add]').click();
  await pickCombo(page, dialog, 'tax-rule-form-country_code', 'Spain', 'ES');
  await pickCombo(page, dialog, 'tax-rule-form-tax_category_key', key, key);
  await pickSelect(page, dialog.locator('[data-testid=tax-rule-form-operation_class]'), /^Exempt$/);
  const rate = dialog.locator('[data-testid=tax-rule-form-rate_pct]');
  await expect(rate.locator('input')).toHaveValue('0');
  await expect(rate.locator('input')).toBeDisabled();
  await expect(rate).toContainText('This operation carries no tax, so its rate is 0 %.');
  await dialog.locator('[data-testid=tax-rule-form-exempt_reason] input').fill('e1');
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  await expect(dialog).toBeHidden();
  await searchFor(page, 'rules', key);
  const row = () => rows(page, 'rules').first();
  await expect(row()).toContainText('Exempt · E1');
  await expect(row()).toContainText('0.00%');
  await threeShots(page, 'TAX-F05', row);
  // What Invoicing and VeriFactu read: the qualification and the cause, upper-cased.
  const calc = await api<{ tax: number; tax_operation_class: string; tax_exempt_reason: string }>(
    context,
    A,
    'GET',
    `/tax/rates/calculate?amount=4000&tax_category_key=${key}`,
  );
  expect([calc.status, calc.data.tax, calc.data.tax_operation_class, calc.data.tax_exempt_reason]).toEqual([200, 0, 'exempt', 'E1']);
});

// flow: TAX-F06
test('TAX-F06: a surcharge hangs from its root and charges on top of it', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f06');
  const root = await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 21 });
  await listReady(page, 'rules');
  const dialog = page.locator('ion-modal[data-testid=tax-rule-form]');
  await shown(page).locator('[data-testid=tax-rules-add]').click();
  await pickCombo(page, dialog, 'tax-rule-form-country_code', 'Spain', 'ES');
  await pickCombo(page, dialog, 'tax-rule-form-tax_category_key', key, key);
  await dialog.locator('[data-testid=tax-rule-form-rate_pct] input').fill('5.2');
  await pickSelect(page, dialog.locator('[data-testid=tax-rule-form-tax_type]'), /^Surcharge$/);
  await pickSelect(page, dialog.locator('[data-testid=tax-rule-form-parent_id]'), /21\.00%/);
  await dialog.locator('[data-testid=tax-rule-form-component_label] input').fill('Equivalence surcharge');
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  await expect(dialog).toBeHidden();
  await searchFor(page, 'rules', key);
  await expect(rows(page, 'rules')).toHaveCount(2);
  const component = () => rows(page, 'rules').nth(1);
  await expect(component()).toContainText('Equivalence surcharge');
  await expect(component()).toContainText('5.20%');
  await threeShots(page, 'TAX-F06', component);
  const saved = await rulesOf(context, key);
  expect(saved.find((r) => r.parent_id)?.parent_id).toBe(root.id);
  // 100.00 at 21 % + 5.2 %: 21.00 + 5.20 of tax over the same base.
  const calc = await api<{ tax: number; tax_rate_pct: string }>(context, A, 'GET', `/tax/rates/calculate?amount=10000&tax_category_key=${key}`);
  expect([calc.data.tax, Number(calc.data.tax_rate_pct)]).toEqual([2620, 26.2]);
});

// flow: TAX-F07 · gh:sales#529
test('TAX-F07: «Set end date» closes the rate in force and the new one starts the next day', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f07');
  const first = await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 10, valid_from: '2026-01-01' });
  await listReady(page, 'rules');
  await searchFor(page, 'rules', key);
  await rowAction(page, 'rules', first.id, 'end');
  const end = page.locator('ion-modal[data-testid=tax-rule-end]');
  await expect(end).toBeVisible();
  await end.locator('[data-testid=tax-rule-end-valid_to] input').fill('2026-12-31');
  await end.locator('[data-testid=tax-rule-end-submit]').click();
  await expect(end).toBeHidden();
  await expect(rows(page, 'rules').first()).toContainText('Dec 31, 2026');
  await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 21, valid_from: '2027-01-01' });
  await expect(rows(page, 'rules')).toHaveCount(2);
  await threeShots(page, 'TAX-F07', () => rows(page, 'rules').nth(1));
  // Each day charges its own rate.
  for (const [date, tax] of [
    ['2026-12-31', 1000],
    ['2027-01-01', 2100],
  ] as const) {
    const calc = await api<{ tax: number }>(context, A, 'GET', `/tax/rates/calculate?amount=10000&tax_category_key=${key}&date=${date}`);
    expect(calc.data.tax, date).toBe(tax);
  }
});

// flow: TAX-F08
test('TAX-F08: «Deactivate» asks first; the rule comes back with «Restore»', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f08');
  const rule = await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 21 });
  await listReady(page, 'rules');
  await searchFor(page, 'rules', key);
  await rowAction(page, 'rules', rule.id, 'deactivate');
  const confirm = page.locator('ion-modal[data-testid=tax-rule-deactivate]');
  await expect(confirm).toContainText('Deactivate tax rule');
  await expect(confirm).toContainText('The rule will no longer apply to new transactions.');
  await threeShots(page, 'TAX-F08', () => confirm.locator('[data-testid=tax-rule-deactivate-submit]'));
  await confirm.locator('[data-testid=tax-rule-deactivate-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(shown(page).locator('[data-testid=tax-rules-empty]')).toBeVisible();
  // The calculation no longer finds a rule: never a guessed 0 %.
  const refused = await api<Envelope>(context, A, 'GET', `/tax/rates/calculate?amount=1000&tax_category_key=${key}`);
  expect([refused.status, refused.data.error?.code]).toEqual([409, 'tax.no_rate']);
  await pickSelect(page, shown(page).locator('[data-testid=tax-rules-status]'), /^Deactivated$/);
  await rowAction(page, 'rules', rule.id, 'restore');
  await expect(shown(page).locator('[data-testid=tax-rules-empty]')).toBeVisible();
  expect((await rulesOf(context, key, 'active')).map((r) => r.id)).toEqual([rule.id]);
});

// flow: TAX-F11 · gh:pm#629
test('TAX-F11: a Canary Islands rule is IGIC, and wins over the national one for a business there', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f11');
  await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: 21 });
  await listReady(page, 'rules');
  const dialog = page.locator('ion-modal[data-testid=tax-rule-form]');
  await shown(page).locator('[data-testid=tax-rules-add]').click();
  await pickCombo(page, dialog, 'tax-rule-form-country_code', 'Spain', 'ES');
  await dialog.locator('[data-testid=tax-rule-form-region_code] input').fill('ES-CN');
  await pickCombo(page, dialog, 'tax-rule-form-tax_category_key', key, key);
  await dialog.locator('[data-testid=tax-rule-form-rate_pct] input').fill('7');
  await pickSelect(page, dialog.locator('[data-testid=tax-rule-form-tax_type]'), /^IGIC/);
  await dialog.locator('[data-testid=tax-rule-form-submit]').click();
  await expect(dialog).toBeHidden();
  await searchFor(page, 'rules', key);
  await expect(rows(page, 'rules')).toHaveCount(2);
  const canary = () => rows(page, 'rules').filter({ hasText: 'ES-CN' });
  await expect(canary()).toContainText('IGIC');
  await threeShots(page, 'TAX-F11', canary);
  const there = await api<{ tax: number; tax_kind: string }>(
    context,
    A,
    'GET',
    `/tax/rates/calculate?amount=10000&tax_category_key=${key}&region_code=ES-CN`,
  );
  const mainland = await api<{ tax: number; tax_kind: string }>(context, A, 'GET', `/tax/rates/calculate?amount=10000&tax_category_key=${key}`);
  expect([there.data.tax, there.data.tax_kind, mainland.data.tax, mainland.data.tax_kind]).toEqual([700, 'igic', 2100, 'vat']);
});

// flow: TAX-F13
test('TAX-F13: the aliases say which category an outside text is', async ({ page }) => {
  await login(page, A, '/tax/aliases');
  await listReady(page, 'aliases');
  await searchFor(page, 'aliases', 'beer');
  // «beer» is drunk in the bar (10 %); «takeaway_beer» is sold to take away (21 %).
  const beer = () => rows(page, 'aliases').filter({ hasText: 'restaurant.alcohol' }).first();
  await expect(beer()).toContainText('Shipped');
  await expect(rows(page, 'aliases').filter({ hasText: 'takeaway_beer' })).toContainText('retail.alcohol');
  await threeShots(page, 'TAX-F13', beer);
});

// flow: TAX-F14
test('TAX-F14: «+» teaches an alias, kept lowercase; a repeated one is refused under Alias', async ({ page, context }) => {
  await login(page, A, '/tax/aliases');
  await listReady(page, 'aliases');
  const text = `e2e Craft ${Date.now().toString(36)}`;
  const dialog = page.locator('ion-modal[data-testid=tax-alias-form]');
  await shown(page).locator('[data-testid=tax-aliases-add]').click();
  await dialog.locator('[data-testid=tax-alias-form-alias] input').fill(`  ${text}  `);
  await pickCombo(page, dialog, 'tax-alias-form-category', 'alcohol', 'restaurant.alcohol');
  await dialog.locator('[data-testid=tax-alias-form-submit]').click();
  await expect(dialog).toBeHidden();
  const kept = text.toLowerCase();
  await searchFor(page, 'aliases', kept);
  const row = () => rows(page, 'aliases').first();
  await expect(row()).toContainText('Learned');
  await expect(row()).toContainText('restaurant.alcohol');
  await threeShots(page, 'TAX-F14', row);
  // The importer reads it from now on, however it is written.
  const resolved = await api<{ tax_category_key: string; matched_by: string }>(
    context,
    A,
    'GET',
    `/tax/aliases/resolve?text=${encodeURIComponent(kept.toUpperCase())}`,
  );
  expect([resolved.data.tax_category_key, resolved.data.matched_by]).toEqual(['restaurant.alcohol', 'alias']);

  await shown(page).locator('[data-testid=tax-aliases-add]').click();
  await dialog.locator('[data-testid=tax-alias-form-alias] input').fill(kept);
  await pickCombo(page, dialog, 'tax-alias-form-category', 'alcohol', 'restaurant.alcohol');
  await dialog.locator('[data-testid=tax-alias-form-submit]').click();
  await expect(dialog.locator('[data-testid=tax-alias-form-alias] .error-text')).toContainText('That alias already exists.');
  await dialog.locator('[data-testid=tax-alias-form-cancel]').click();
});

// flow: TAX-F17
test('TAX-F17: with no rule in force, «Your taxes» tells whoever manages and «Set up» leads to Rules', async ({ page, context }) => {
  await login(page, A, '/tax/categories');
  const active = await api<{ rows: Rule[] }>(context, A, 'GET', '/tax/rules?status=active&limit=100');
  const roots = active.data.rows.filter((r) => !r.parent_id);
  expect(roots.length).toBeGreaterThan(0);
  try {
    for (const rule of roots) expect((await api(context, A, 'POST', '/tax/rules/deactivate', { id: rule.id })).status).toBe(200);
    await listReady(page, 'categories');
    const notice = () => shown(page).locator('[data-testid=tax-setup]');
    await expect(notice()).toContainText('Your taxes');
    await expect(notice()).toContainText('Set up the VAT rates of the country you sell in so the till can price a sale.');
    await threeShots(page, 'TAX-F17', notice);
    await shown(page).locator('[data-testid=tax-setup-action]').click();
    await page.waitForURL(/\/tax\/rules$/);
    await expect(notice()).toBeVisible();
    await expect(shown(page).locator('[data-testid=tax-setup-action]')).toHaveCount(0);
  } finally {
    for (const rule of roots) await api(context, A, 'POST', '/tax/rules/activate', { id: rule.id });
  }
  // One rule in force again: the step is gone by itself.
  await expect(shown(page).locator('[data-testid=tax-setup]')).toHaveCount(0);
  const status = await api<{ configured: boolean }>(context, A, 'GET', '/tax/rules/status');
  expect(status.data.configured).toBe(true);
});

// flow: TAX-F12
test('TAX-F12: several rules at once are saved all or none', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const key = await freshCategory(context, 'f12');
  const refused = await api<Envelope>(context, A, 'POST', '/tax/rules/bulk_create', {
    rules: [
      { country_code: 'ES', tax_category_key: key, rate_pct: 21 },
      { country_code: 'PT', tax_category_key: key, rate_pct: 150 },
    ],
  });
  expect(refused.status).toBe(422);
  expect(Object.keys(refused.data.error?.fields ?? {})).toContain('rules.1.rate_pct');
  expect(await rulesOf(context, key)).toEqual([]);
  const saved = await api<{ rules: Rule[] }>(context, A, 'POST', '/tax/rules/bulk_create', {
    rules: [
      { country_code: 'ES', tax_category_key: key, rate_pct: 21 },
      { country_code: 'PT', tax_category_key: key, rate_pct: 23 },
    ],
  });
  expect([saved.status, saved.data.rules.length]).toEqual([201, 2]);
  expect(await rulesOf(context, key)).toHaveLength(2);
});

// flow: TAX-F15
test('TAX-F15: the importer gets the category of a text by key, name or alias, and nothing for a stranger', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  const read = (text: string) =>
    api<{ text: string; tax_category_key: string | null; matched_by: string | null }>(context, A, 'GET', `/tax/aliases/resolve?text=${encodeURIComponent(text)}`);
  expect((await read('  Restaurant.FOOD ')).data).toEqual({ text: 'restaurant.food', tax_category_key: 'restaurant.food', matched_by: 'key' });
  expect((await read('beer')).data).toMatchObject({ tax_category_key: 'restaurant.alcohol', matched_by: 'alias' });
  expect((await read('Restauración — comida')).data).toMatchObject({ tax_category_key: 'restaurant.food', matched_by: 'name' });
  expect((await read('surely not a category')).data).toMatchObject({ tax_category_key: null, matched_by: null });
});

// flow: TAX-F18
test('TAX-F18: the tax of an amount, added or included, to the cent', async ({ page, context }) => {
  await login(page, A, '/tax/rules');
  type Calc = { base: number; tax: number; total: number; tax_rate_pct: string; source: string };
  const added = await api<Calc>(context, A, 'GET', '/tax/rates/calculate?amount=1000&tax_category_key=restaurant.food');
  expect([added.data.base, added.data.tax, added.data.total, Number(added.data.tax_rate_pct), added.data.source]).toEqual([1000, 100, 1100, 10, 'rule']);
  const included = await api<Calc>(context, A, 'GET', '/tax/rates/calculate?amount=1210&tax_category_key=product.generic&tax_included=true');
  expect([included.data.base, included.data.tax, included.data.total]).toEqual([1000, 210, 1210]);
  // A category without a rule is refused, never charged at a guessed 0 %.
  const none = await api<Envelope>(context, A, 'GET', '/tax/rates/calculate?amount=1000&tax_category_key=product.generic&country_code=PT');
  expect([none.status, none.data.error?.code]).toEqual([409, 'tax.no_rate']);
});
