// A business signed up on erplora.com is born with Taxes on, with its country's taxes, and never with VeriFactu
// (hub#997, PLAN-HUB round 2026-11-07), end to end against this run's stack: a fresh owner signs up on the SaaS's
// screens and creates the business through its API as the panel does; the SaaS registers it in this Hub, the worker
// makes its database, and the owner comes in through the SaaS:
//   - a business of Spain, in 375x667, 820x1180 and 1440x900: Apps › «My apps» has Taxes, «Active» and «Mandatory in Spain», not
//     chosen (it takes nothing of the plan's limit) and alone; in «Add apps» VeriFactu is «Off» with «Turn on». The
//     Home asks «Turn on VeriFactu», never «Turn on Taxes»; «Your apps» still asks for an app (Taxes alone sells
//     nothing), Spain's rates are in («Your taxes» done) and «Start with a business like yours» is offered;
//   - a business of Portugal, in 1440: Taxes on, «Mandatory in Portugal»; no VeriFactu step, and «Your taxes» says its
//     country has no factory rates yet (TAX-F17).
// Each step leaves its capture `SIGN-UP-TAXES-<country>-<step>-<size>`.
// flow: BASE-F63 BASE-F14 BASE-F01 BASE-F38 TAX-F16 TAX-F17
import { expect, type Page, test } from '@playwright/test';

import { VIEWPORTS } from './assistant-card-helpers';
import { api, appRow, login, settledCapture, shown, testid } from './helpers';
import { businessOnSaas, type SaasOwner, signUpOnSaas } from './saas-owner';
import { STACK } from './stack';

test.use({ actionTimeout: 30_000 });
test.describe.configure({ mode: 'serial' });

interface App {
  id: string;
  state: string;
  chosen: boolean;
  mandatory: boolean;
}

interface SetupDocument {
  items: { key: string; state: string }[];
}

const setupRow = (page: Page, key: string) => testid(page, 'setup-card').locator(`[data-testid="setup-row"][data-key="${key}"]`);

/** The capture of a step at a size, once the screen settled and nothing scrolls sideways. */
const snap = (page: Page, step: string, size: string): Promise<void> => settledCapture(page, `SIGN-UP-TAXES-${step}-${size}`);

/** A fresh owner's business in `country`, signed up on erplora.com, and the owner in it on the Home: its origin. */
async function signedUpIn(owner: SaasOwner, country: string): Promise<string> {
  const business = await businessOnSaas(owner, { name: `Impuestos ${country} ${Date.now().toString(36)}`, country });
  const origin = STACK.hub(business.slug);
  await login(owner.page, origin, '/', owner.credentials);
  return origin;
}

/** What the business was born with, as Apps reads it, and what its Home asks for, by key. */
async function bornWith(owner: SaasOwner, origin: string): Promise<{ apps: Map<string, App>; asked: Map<string, string> }> {
  const listed = await api<{ apps: App[] }>(owner.context, origin, 'GET', '/apps');
  expect(listed.status).toBe(200);
  const setup = await api<SetupDocument>(owner.context, origin, 'GET', '/home/setup');
  expect(setup.status).toBe(200);
  return {
    apps: new Map(listed.data.apps.map((app) => [app.id, app])),
    asked: new Map(setup.data.items.map((item) => [item.key, item.state])),
  };
}

let spain: SaasOwner | undefined;
let portugal: SaasOwner | undefined;

test.afterAll(async () => {
  await spain?.context.close();
  await portugal?.context.close();
});

test('BASE-F63 BASE-F14 BASE-F01 TAX-F16 — a business of Spain is born with Taxes on and VeriFactu off', async ({
  browser,
}) => {
  test.setTimeout(300_000);
  spain = await signUpOnSaas(browser, 'sign-up-taxes-es');
  const origin = await signedUpIn(spain, 'ES');

  const { apps, asked } = await bornWith(spain, origin);
  expect(apps.get('tax')).toMatchObject({ state: 'on', chosen: false, mandatory: true });
  expect(apps.get('verifactu')).toMatchObject({ state: 'off', mandatory: true });
  expect([...apps.values()].filter((app) => app.state !== 'off').map((app) => app.id)).toEqual(['tax']);
  expect(asked.get('base.mandatory.verifactu')).toBe('pending');
  expect(asked.has('base.mandatory.tax')).toBe(false);
  expect(asked.get('base.apps')).toBe('pending');
  expect(asked.get('tax.rules')).toBe('done');

  const { page } = spain;
  for (const size of VIEWPORTS) {
    await page.setViewportSize({ width: size.width, height: size.height });

    // BASE-F14 — «My apps»: Taxes, «Active» and «Mandatory in Spain».
    await page.goto(`${origin}/apps`);
    await expect(testid(page, 'tab-mine')).toHaveClass(/segment-button-checked/);
    const taxes = appRow(page, 'tax');
    await expect(taxes.locator('[data-testid="apps-state"]')).toContainText('Active');
    await expect(taxes.locator('[data-testid="apps-mandatory"]')).toContainText('Mandatory in Spain');
    await expect(shown(page).locator('[data-testid="apps-row"]')).toHaveCount(1);
    await snap(page, 'ES-mine', size.label);

    // «Add apps»: VeriFactu, mandatory in Spain, is off with «Turn on»: its owner turns it on.
    await page.goto(`${origin}/apps#all`);
    await testid(page, 'apps-search').locator('input').fill('VeriFactu');
    const verifactu = appRow(page, 'verifactu');
    await expect(verifactu.locator('[data-testid="apps-state"]')).toContainText('Off');
    await expect(verifactu.locator('[data-testid="apps-mandatory"]')).toContainText('Mandatory in Spain');
    await expect(verifactu).toContainText('Turn on');
    await snap(page, 'ES-all', size.label);

    // BASE-F01, BASE-F38 — the Home: «Turn on VeriFactu», never «Turn on Taxes»; the template card is offered.
    await page.goto(`${origin}/`);
    await expect(testid(page, 'setup-card')).toHaveAttribute('aria-busy', 'false');
    await expect(setupRow(page, 'base.mandatory.verifactu')).toContainText('Turn on VeriFactu');
    await expect(setupRow(page, 'base.mandatory.tax')).toHaveCount(0);
    await expect(testid(page, 'blueprint-card')).toBeVisible();
    await snap(page, 'ES-home', size.label);
  }
});

test('BASE-F14 TAX-F17 — a business of Portugal is born with Taxes on, without factory rates nor VeriFactu', async ({
  browser,
}) => {
  test.setTimeout(240_000);
  portugal = await signUpOnSaas(browser, 'sign-up-taxes-pt');
  const origin = await signedUpIn(portugal, 'PT');

  const { apps, asked } = await bornWith(portugal, origin);
  expect(apps.get('tax')).toMatchObject({ state: 'on', chosen: false, mandatory: true });
  expect(apps.get('verifactu')).toMatchObject({ state: 'off', mandatory: false });
  expect(asked.has('base.mandatory.verifactu')).toBe(false);
  expect(asked.has('base.mandatory.tax')).toBe(false);
  expect(asked.get('tax.rules')).toBe('pending');

  const { page } = portugal;
  await page.goto(`${origin}/apps`);
  const taxes = appRow(page, 'tax');
  await expect(taxes.locator('[data-testid="apps-state"]')).toContainText('Active');
  await expect(taxes.locator('[data-testid="apps-mandatory"]')).toContainText('Mandatory in Portugal');
  await snap(page, 'PT-mine', '1440x900');

  await page.goto(`${origin}/`);
  await expect(testid(page, 'setup-card')).toHaveAttribute('aria-busy', 'false');
  await expect(setupRow(page, 'tax.rules')).toBeVisible();
  await expect(setupRow(page, 'base.mandatory.verifactu')).toHaveCount(0);
  await snap(page, 'PT-home', '1440x900');
});
