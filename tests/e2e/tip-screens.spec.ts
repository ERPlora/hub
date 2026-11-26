// flow: TIP-F01, TIP-F03, TIP-F05, TIP-F06 — on Tips → Tips the manager records the card tip the customer added on the
// card terminal, on its sale by its number, and puts the jar's cash into the pool; adjusts the first one and voids the
// second, each with its reason. On Tips → Settings the owner asks for a tip at the charge and changes a card suggestion
// to an amount, and «Save» says «Settings saved.». Both screens seen at a phone, an Android tablet and a desk. What this
// file makes is deleted after it, and the settings, the drawer and the apps it changed go back as they were.
import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown, turnOffTurnedOn, turnOnMissing } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';
import { capturedAtEachSize } from './screen';
import { ownerPage, rowAction } from './service-helpers';
import { pickSelect } from './tax-helpers';

const RUN = stamp();

interface Suggestion {
  percent?: number | null;
  amount?: number | null;
}
interface Settings {
  enabled: boolean;
  allow_custom: boolean;
  preselected: number;
  methods: { method_id: string; method_type: string; suggestions: Suggestion[] }[];
}
interface Tip {
  id: string;
  sale_number: string;
  pool: boolean;
  member_id: string | null;
  amount: number;
  status: string;
  adjust_reason: string;
  void_reason: string;
}

const turnedOn: string[] = [];
let before: Settings;
let saleNumber: string;

/** What the settings were, as the server takes them back. */
const sentBack = (settings: Settings) => ({
  enabled: settings.enabled,
  allow_custom: settings.allow_custom,
  preselected: settings.preselected,
  methods: settings.methods.map((method) => ({
    method_id: method.method_id,
    suggestions: method.suggestions.map((s) => (s.percent ? { percent: s.percent } : { amount: s.amount })),
  })),
});

test.beforeAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/sale/pos');
  await turnOnMissing(context, A, ['tip'], turnedOn);
  // The pool takes cash: without the drawer on, no session has to be open for it.
  await drawerOff(context);
  before = (await api<Settings>(context, A, 'GET', '/tip/settings')).data;
  const product = await createProduct(context, { name: `E2E Tip screens ${RUN}`, sku: `E2E-TIPS-${RUN}`, price: 2000 });
  saleNumber = (await chargeByApi(context, { lines: [{ product: product.sku, quantity: '1' }], payments: [{ method: 'card' }] })).number;
  await context.close();
});

test.afterAll(async ({ browser }) => {
  psql(`delete from tip_tip where created_at >= now() - interval '1 hour' and (sale_id is null or sale_id in (select sale_id from sale_saleline where sku = 'E2E-TIPS-${RUN}'))`);
  cleanSales();
  cleanInventory();
  restoreDrawer();
  const { context } = await ownerPage(browser, '/sale/pos');
  await api(context, A, 'POST', '/tip/settings', sentBack(before));
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

async function tipsOf(page: Page): Promise<Tip[]> {
  return (await api<{ rows: Tip[] }>(page.context(), A, 'GET', '/tip/tips?limit=20')).data.rows;
}

test('TIP-F03, TIP-F05, TIP-F06: the manager records a card tip and the pool, adjusts one and voids the other', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/tip/tips');
  const list = shown(page);
  await expect(list.locator('[data-testid=tip-list-period]')).toBeVisible();

  // A card tip on its sale, by its number.
  await list.locator('[data-testid=tip-list-add]').click();
  await expect(page.locator('[data-testid=tip-form-sale]')).toBeVisible();
  await page.locator('[data-testid=tip-form-sale] input').fill(saleNumber);
  await pickSelect(page, page.locator('[data-testid=tip-form-method]'), /^(Card|Tarjeta)$/);
  await page.locator('[data-testid=tip-form-amount] input').fill('3,00');
  await capture(page, 'tip-screens-record-1440x900');
  await page.locator('[data-testid=tip-form-submit]').click();
  await expect(page.locator('[data-testid=tip-form-sale]')).toBeHidden();
  await expect.poll(async () => (await tipsOf(page)).some((tip) => tip.sale_number === saleNumber)).toBe(true);

  // The jar's cash, to the pool.
  await list.locator('[data-testid=tip-list-add]').click();
  await page.locator('[data-testid=tip-form-target-pool]').click();
  await expect(page.locator('[data-testid=tip-form-pool-hint]')).toBeVisible();
  await page.locator('[data-testid=tip-form-amount] input').fill('12');
  await page.locator('[data-testid=tip-form-submit]').click();
  await expect(page.locator('[data-testid=tip-form-pool-hint]')).toBeHidden();

  const recorded = await tipsOf(page);
  const card = recorded.find((tip) => tip.sale_number === saleNumber)!;
  const pool = recorded.find((tip) => tip.pool && tip.amount === 1200)!;
  expect([card.amount, card.status]).toEqual([300, 'active']);
  expect([pool.member_id, pool.status]).toEqual([null, 'active']);
  await expect(list.locator(`[data-testid=tip-list-row][data-id="${card.id}"]`).first()).toBeVisible();
  await capturedAtEachSize(page, 'tip-screens-list', 'tip-list-row');

  // The card tip, adjusted with its reason.
  await rowAction(page, 'tip-list', card.id, 'adjust');
  await page.locator('[data-testid=tip-adjust-amount] input').fill('2,50');
  await page.locator('[data-testid=tip-adjust-reason] textarea').fill('The terminal charged 2.50 on top');
  await capture(page, 'tip-screens-adjust-1440x900');
  await page.locator('[data-testid=tip-adjust-submit]').click();
  await expect(page.locator('[data-testid=tip-adjust-reason]')).toBeHidden();

  // The pool's, voided with its reason.
  await rowAction(page, 'tip-list', pool.id, 'void');
  await page.locator('[data-testid=tip-void-reason] textarea').fill('Counted twice');
  await page.locator('[data-testid=tip-void-submit]').click();
  await expect(page.locator('[data-testid=tip-void-reason]')).toBeHidden();

  await expect
    .poll(async () => {
      const now = await tipsOf(page);
      const adjusted = now.find((tip) => tip.id === card.id)!;
      const voided = now.find((tip) => tip.id === pool.id)!;
      return [adjusted.amount, adjusted.adjust_reason, voided.status, voided.void_reason];
    })
    .toEqual([250, 'The terminal charged 2.50 on top', 'voided', 'Counted twice']);
});

test('TIP-F01: the owner asks for a tip at the charge and gives the card an amount among its suggestions', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/tip/settings');
  const card = before.methods.find((method) => method.method_type === 'card')!;
  const settings = shown(page);
  await expect(settings.locator('[data-testid=tip-settings-heading]')).toBeVisible();
  await capturedAtEachSize(page, 'tip-screens-settings', 'tip-settings-heading');

  const enabled = settings.locator('[data-testid=tip-settings-enabled]');
  if (!before.enabled) await enabled.click();
  await pickSelect(page, settings.locator(`[data-testid=tip-settings-${card.method_id}-0-kind]`), /^(Amount|Importe)$/);
  await settings.locator(`[data-testid=tip-settings-${card.method_id}-0-value] input`).fill('2,00');
  await settings.locator('[data-testid=tip-settings-save]').click();
  await expect(settings.locator('[data-testid=tip-settings-saved]')).toBeVisible();
  await capture(page, 'tip-screens-settings-saved-1440x900');

  const saved = (await api<Settings>(page.context(), A, 'GET', '/tip/settings')).data;
  expect(saved.enabled).toBe(true);
  const suggestion = saved.methods.find((method) => method.method_id === card.method_id)!.suggestions[0];
  expect([suggestion.percent ?? null, suggestion.amount]).toEqual([null, 200]);
});
