// flow: website-business-currency (FIX-HUB-WEBSITE-PRICES-IN-EUR-WHATEVER-THE-COUNTRY; apps/website/WORKBOOK.md
// WEBSITE-F05, F06 and F10)
// The website prices its catalog in the business's currency: its country's, as erplora.com registered it
// (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` publishes its site with
// Services' catalog and moves to Poland: without publishing again, its public page (painted by the server, refreshed by
// the bundle from the public catalog, which answers the same) and the editor's preview price a service of the run in
// złoty, with no «€», at 390, 834 and 1440 (captures `FIX-HUB-WEBSITE-PRICES-IN-EUR-WHATEVER-THE-COUNTRY-<width>` and
// `…-preview-<width>`). Back in Spain the same page is in euros again (`…-es-1440`). What the run creates is deleted
// after it, the site saved as it was found and taken offline, and `a`'s registration put back, also when a test fails.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, hostPage, psql, registerBusinessIn, registrationOf, type Registration } from './helpers';
import { atRest } from './website-helpers';

const KEY = 'FIX-HUB-WEBSITE-PRICES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const WIDE = { width: 1440, height: 900 };
const TAG = `E2E-WSCUR-${Date.now().toString(36)}`;
/** The run's service: 1550 in the currency's minor unit, 15.50 in złoty or in euros. */
const SERVICE = `${TAG} Haircut`;
/** 15.50 as the page prints it for a visitor speaking English (as Intl: «PLN 15.50», «€15.50»; flow money-text). */
const ZLOTY = /PLN\s?15\.50/;
const EUROS = /€\s?15\.50/;

interface Site {
  template: string;
  theme: Record<string, unknown>;
  content: Record<string, Record<string, unknown>>;
  is_live: boolean;
}
interface Catalog {
  groups: { items: { name: string; price_label: string }[] }[];
}

/** `a`'s registration and its site as the run found them (put back after). */
let original: Registration | undefined;
let found: Site | undefined;
let owner: { context: BrowserContext; page: Page } | undefined;

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

function cleanUp(): void {
  const services = `select id from service_service where name like '${TAG}%'`;
  psql(
    [
      `delete from service_assignment where service_id in (${services})`,
      `delete from service_service where name like '${TAG}%'`,
    ].join('; '),
  );
}

/** A visitor: a fresh context without a session, at `viewport`, speaking `locale`. */
async function visitor(browser: Browser, viewport: { width: number; height: number }, locale = 'en-GB'): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport, locale });
  return { context, page: await context.newPage() };
}

/** The run's card in the page's catalog block (`root`: the page, or the editor's preview frame). */
const card = (root: Page | ReturnType<Page['frameLocator']>): Locator =>
  root.locator('[data-ep-block="catalog"] .card').filter({ hasText: SERVICE });

/** The public catalog as the bundle reads it (no session): the label of the run's service. */
async function publicLabel(context: BrowserContext): Promise<string> {
  const answer = await context.request.get(`${A}/api/website/public/catalog`);
  expect(answer.status()).toBe(200);
  const catalog = (await answer.json()) as Catalog;
  const item = catalog.groups.flatMap((group) => group.items).find((row) => row.name === SERVICE);
  expect(item, `${SERVICE} in the public catalog`).toBeTruthy();
  return item?.price_label ?? '';
}

/** The editor's «Preview» on a phone or a tablet; a computer shows it beside the editor. */
async function showPreview(page: Page): Promise<void> {
  const tabs = page.getByTestId('website-view');
  if (await tabs.isVisible()) await tabs.locator('ion-segment-button').filter({ hasText: 'Preview' }).click();
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  original = registrationOf('a');
  owner = await hostPage(browser, A, { next: '/website', viewport: WIDE });
  const site = await api<Site>(owner.context, A, 'GET', '/website/site');
  expect(site.status).toBe(200);
  found = site.data;
  const created = await api(owner.context, A, 'POST', '/service/services', {
    name: SERVICE,
    price: 1550,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  // The site as it was, with Services' whole catalog and its prices shown, published.
  const content = {
    ...found.content,
    catalog: { ...found.content.catalog, hidden: false, source: 'service', category_ids: [], show_prices: true },
  };
  const saved = await api(owner.context, A, 'POST', '/website/site', { template: found.template, theme: found.theme, content });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  const published = await api<{ is_live: boolean }>(owner.context, A, 'POST', '/website/site/publish');
  expect(published.status, JSON.stringify(published.data)).toBe(200);
});

test.afterAll(async () => {
  try {
    if (original) await registerBusinessIn(original, original.country);
    if (owner && found) {
      const restored = await api(owner.context, A, 'POST', '/website/site', {
        template: found.template,
        theme: found.theme,
        content: found.content,
      });
      expect(restored.status, JSON.stringify(restored.data)).toBe(200);
      // The other specs on hub `a` expect `/` to jump to the login.
      const offline = await api(owner.context, A, 'POST', '/website/site/unpublish');
      expect(offline.status, JSON.stringify(offline.data)).toBe(200);
    }
  } finally {
    cleanUp();
    await owner?.context.close();
  }
});

test(`${KEY}: website-business-currency a business in Poland sees its prices in złoty on its page and in the preview, in 390, 834 and 1440`, async ({
  browser,
}) => {
  if (!original || !owner) throw new Error('beforeAll did not run');
  await registerBusinessIn(original, 'PL');
  for (const size of SIZES) {
    // The visitor's page, without publishing again: the server's paint and the bundle's refresh, both in złoty.
    const { context, page } = await visitor(browser, { width: size.width, height: size.height });
    await page.goto(`${A}/`);
    const block = page.locator('[data-ep-block="catalog"]');
    await expect(card(page)).toContainText(ZLOTY);
    await expect(block).not.toContainText('€');
    expect(await publicLabel(context)).toMatch(ZLOTY);
    await card(page).scrollIntoViewIfNeeded();
    await atRest(page);
    await capture(page, `${KEY}-${size.name}`);
    await context.close();
    // The editor's preview paints the same page.
    const editor = owner.page;
    await editor.setViewportSize({ width: size.width, height: size.height });
    await editor.goto(`${A}/website`);
    await expect(editor.getByTestId('website-editor')).toBeVisible({ timeout: 30_000 });
    await showPreview(editor);
    const preview = editor.frameLocator('[data-testid="website-preview-frame"]');
    await expect(card(preview)).toContainText(ZLOTY);
    await expect(preview.locator('[data-ep-block="catalog"]')).not.toContainText('€');
    await card(preview).scrollIntoViewIfNeeded();
    await atRest(editor);
    await capture(editor, `${KEY}-preview-${size.name}`);
  }
  // A visitor speaking Spanish reads the same złoty in Spanish.
  const { context, page } = await visitor(browser, WIDE, 'es-ES');
  await page.goto(`${A}/`);
  await expect(card(page)).toContainText(/15,50\s?PLN/);
  await context.close();
});

test(`${KEY}: website-business-currency back in Spain, the same page is in euros again`, async ({ browser }) => {
  if (!original) throw new Error('beforeAll did not run');
  await registerBusinessIn(original, 'ES');
  const { context, page } = await visitor(browser, WIDE);
  await page.goto(`${A}/`);
  await expect(card(page)).toContainText(EUROS);
  await expect(page.locator('[data-ep-block="catalog"]')).not.toContainText('PLN');
  expect(await publicLabel(context)).toMatch(EUROS);
  await card(page).scrollIntoViewIfNeeded();
  await atRest(page);
  await capture(page, `${KEY}-es-1440`);
  await context.close();
});
