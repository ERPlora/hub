// flow: TAX-F17
// Taxes' hook of the Home (FIX-TAX-SETUP-HOOKS; the old module's own `setup` item «Tus impuestos», taxes#19; the old
// hub's dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads it in Spanish (gh:hub#2356):
// «Tus impuestos» pending and «Importante» in «Termina de configurar tu negocio» while no active root rule applies today,
// its «Configurar» leading to Rules, where the first one is created with «+»; then «Hecho», back to pending without a
// reload when that rule is deactivated and «Hecho» again when it is restored. In each of the three sizes, the capture
// `FIX-TAX-SETUP-HOOKS-<width>` with the step pending in sight. The rules the hub already had in force are deactivated
// for the run and active again after it; the run's own hang from «e2e.» categories, deleted by `cleanUp()` before and
// after.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { cleanUp, createRule, FLOW_VIEWPORTS, freshCategory, horizontalOverflow, pickCombo } from './tax-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-TAX-SETUP-HOOKS';
const STEP = 'tax.rules';
/** The hub's own root rules in force, deactivated while the run needs a hub with no rate to charge. */
const PARKED = 'e2e_fix_tax_hooks_parked';

test.beforeAll(() => {
  cleanUp();
  psql(
    [
      `drop table if exists ${PARKED}`,
      `create table ${PARKED} as select id from tax_taxrule where is_active and parent_id is null`,
      `update tax_taxrule set is_active = false where id in (select id from ${PARKED})`,
    ].join('; '),
  );
});

test.afterAll(() => {
  try {
    cleanUp();
  } finally {
    psql([`update tax_taxrule set is_active = true where id in (select id from ${PARKED})`, `drop table ${PARKED}`].join('; '));
  }
});

/**
 * The owner on `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home, with
 * the instant of every `/api/live` the page opens: a new stream brings every result again, so a step that changes
 * without one came over the stream already open, re-run by its events.
 */
async function spanishOwner(
  browser: Browser,
  viewport: { width: number; height: number },
): Promise<{ context: BrowserContext; page: Page; streams: number[] }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  const streams: number[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/live')) streams.push(Date.now());
  });
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page, streams };
}

/** How long the SDK keeps a subscription nobody reads any more (`RELEASE_GRACE_MS` of `@erplora/ui/sdk`, 2 s), plus a
 *  margin: back from Rules, the rule form's own query leaves the stream that late, and the stream opens again then. */
const RELEASED = 2_500;

/** Waits until the page has opened no `/api/live` for longer than a subscription takes to be released: every
 *  subscription of the screen is declared and every one of the screen left behind is gone. */
async function settled(streams: number[]): Promise<void> {
  await expect.poll(() => Date.now() - (streams.at(-1) ?? 0), { timeout: 15_000 }).toBeGreaterThan(RELEASED);
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const step = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);
const pill = (page: Page): Locator => step(page).locator('[data-testid="setup-pill"]');
const configure = (page: Page): Locator => step(page).locator(`[data-testid="setup-configure-${STEP}"]`);

/** «Ver todo»: a step below a more important pending one, or a done one, may be folded. */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
  await expect(step(page)).toBeVisible();
}

/** Deactivates (TAX-F08) or restores (TAX-F08) a rule by the API as the owner. */
async function inForce(context: BrowserContext, id: string, action: 'deactivate' | 'activate'): Promise<void> {
  const changed = await api(context, A, 'POST', `/tax/rules/${action}`, { id });
  expect(changed.status, JSON.stringify(changed.data)).toBe(200);
}

test(`${KEY} TAX-F17: «Tus impuestos» pending with no rate in force, it leads to Rules, the first rule ticks it, deactivated it is pending again and restored done`, async ({
  browser,
}) => {
  const { context, page, streams } = await spanishOwner(browser, { width: 1440, height: 900 });
  try {
    const key = await freshCategory(context, 'home');
    // The old module's item, with the words of the notice of the tax screens, «Importante», while no rate applies.
    await unfolded(page);
    await expect(step(page).locator('.setup-row-title')).toHaveText('Tus impuestos');
    await expect(step(page).locator('.setup-row-desc')).toHaveText(
      'Configura los tipos de IVA del país en el que vendes para que el TPV pueda calcular el precio de una venta.',
    );
    await expect(pill(page)).toHaveText('Importante');

    // «Configurar» leads to Rules, where the notice says the same and «+» creates the first rule (TAX-F04): Spain,
    // the category, 21 %, since always.
    await configure(page).click();
    await expect(page).toHaveURL(`${A}/tax/rules`);
    const view = shown(page);
    await expect(view.locator('[data-testid=tax-setup]')).toContainText('Tus impuestos');
    await view.locator('[data-testid=tax-rules-row], [data-testid=tax-rules-empty]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=tax-rules-add]').click();
    const form = page.locator('ion-modal[data-testid=tax-rule-form]');
    await expect(form).toBeVisible();
    await pickCombo(page, form, 'tax-rule-form-country_code', 'Espa', 'ES');
    await pickCombo(page, form, 'tax-rule-form-tax_category_key', key, key);
    await form.locator('[data-testid=tax-rule-form-rate_pct] input').fill('21');
    await form.locator('[data-testid=tax-rule-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(view.locator('[data-testid=tax-setup]')).toHaveCount(0);
    const ruleId = psql(
      `select r.id from tax_taxrule r join tax_taxcategory c on c.id = r.category_id where c.key = '${key}' and r.is_active`,
    );
    expect(ruleId, 'the rule was created active').toMatch(/^[0-9a-f-]{36}$/);

    // Back on the Home: done, with nothing left to configure.
    await page.goBack();
    await expect(page).toHaveURL(`${A}/`);
    await unfolded(page);
    await expect(pill(page)).toHaveText('Hecho');
    await expect(configure(page)).toHaveCount(0);

    // Deactivated, no rate applies: pending again without a reload, over the stream already open; restored, done.
    await settled(streams);
    const onTheHome = streams.length;
    await inForce(context, ruleId, 'deactivate');
    await expect(pill(page)).toHaveText('Importante');
    await expect(configure(page)).toBeVisible();
    await inForce(context, ruleId, 'activate');
    await expect(pill(page)).toHaveText('Hecho');
    expect(streams.length, 'the rule deactivated and restored reached the Home without a new /api/live').toBe(onTheHome);
  } finally {
    await context.close();
    cleanUp();
  }
});

for (const size of FLOW_VIEWPORTS) {
  test(`${KEY} TAX-F17 at ${size.label}: «Tus impuestos» pending in sight, then done without a reload once a rule is created`, async ({
    browser,
  }) => {
    const { context, page, streams } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      await unfolded(page);
      await expect(pill(page)).toHaveText('Importante');
      await step(page).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await expect.poll(() => horizontalOverflow(page), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await capture(page, `${KEY}-${size.label}`);

      // A rule created elsewhere (another device, the assistant): the step is done over the stream already open.
      await settled(streams);
      const onTheHome = streams.length;
      const key = await freshCategory(context, `home${size.label}`);
      await createRule(context, { country_code: 'ES', tax_category_key: key, rate_pct: '21' });
      await unfolded(page);
      await expect(pill(page)).toHaveText('Hecho');
      expect(streams.length, 'the rule created reached the Home without a new /api/live').toBe(onTheHome);
    } finally {
      await context.close();
      cleanUp();
    }
  });
}
