// flow: money-text (FIX-HUB-PYTHON-MONEY-GLUES-CURRENCY-CODE-TO-AMOUNT; base/business.py `money_text`)
// The server writes an amount as the browser does (`Intl.NumberFormat`): a currency written in letters keeps off the
// figure by a no-break space (CLDR's currency spacing, which Babel skips), «PLN 15.50», never «PLN15.50». Hub `a`
// publishes its site with Services' catalog and moves to Poland (`PUT /internal/hubs/{id}`, signed the way the SaaS
// sends it): the public page the server paints and the public catalog the bundle reads write the price as Intl does,
// in English «PLN 15.50» at 390, 834 and 1440 (captures `FIX-HUB-PYTHON-MONEY-GLUES-CURRENCY-CODE-TO-AMOUNT-<width>`)
// and in Spanish «15,50 PLN». The receipt, the invoice and the inventory export are not painted on a screen of the Hub
// (the screens paint their own paper with Intl): their pytest says the same. What the run creates is deleted after
// it, the site saved as it was found and taken offline, and `a`'s registration put back, also when a test fails.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, hostPage, psql, registerBusinessIn, registrationOf, type Registration, shot } from './helpers';

const KEY = 'FIX-HUB-PYTHON-MONEY-GLUES-CURRENCY-CODE-TO-AMOUNT';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const WIDE = { width: 1440, height: 900 };
const TAG = `E2E-MONEY-${Date.now().toString(36)}`;
/** The run's service: 1550 in the currency's minor unit, 15.50 złoty. */
const SERVICE = `${TAG} Haircut`;
/** What `new Intl.NumberFormat(language, {style: 'currency', currency: 'PLN'}).format(15.5)` writes, U+00A0 included. */
const INTL = {
  en: new Intl.NumberFormat('en', { style: 'currency', currency: 'PLN' }).format(15.5),
  es: new Intl.NumberFormat('es', { style: 'currency', currency: 'PLN' }).format(15.5),
};

interface Site {
  template: string;
  theme: Record<string, unknown>;
  content: Record<string, Record<string, unknown>>;
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
async function visitor(browser: Browser, viewport: { width: number; height: number }, locale: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport, locale });
  return { context, page: await context.newPage() };
}

/** The run's card in the page's catalog block. */
const card = (page: Page): Locator => page.locator('[data-ep-block="catalog"] .card').filter({ hasText: SERVICE });

/** The price of the run's service as the page's catalog card writes it, character by character. */
async function cardPrice(page: Page): Promise<string> {
  await expect(card(page)).toContainText('15');
  return (await card(page).textContent()) ?? '';
}

/** The public catalog as the bundle reads it (no session, in the visitor's `language`): the label of the run's service. */
async function publicLabel(context: BrowserContext, language: string): Promise<string> {
  const answer = await context.request.get(`${A}/api/website/public/catalog`, { headers: { 'Accept-Language': language } });
  expect(answer.status()).toBe(200);
  const catalog = (await answer.json()) as Catalog;
  const item = catalog.groups.flatMap((group) => group.items).find((row) => row.name === SERVICE);
  expect(item, `${SERVICE} in the public catalog`).toBeTruthy();
  return item?.price_label ?? '';
}

/** The public page at rest for its capture: no focus ring, no colour still in transition. */
async function settled(page: Page): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
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
  const published = await api(owner.context, A, 'POST', '/website/site/publish');
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

test(`${KEY}: money-text the server writes a price in złoty as the browser does, «PLN 15.50» in English, in 390, 834 and 1440`, async ({
  browser,
}) => {
  if (!original) throw new Error('beforeAll did not run');
  await registerBusinessIn(original, 'PL');
  expect(INTL.en).toBe('PLN 15.50');
  for (const size of SIZES) {
    const { context, page } = await visitor(browser, { width: size.width, height: size.height }, 'en-GB');
    await page.goto(`${A}/`);
    const price = await cardPrice(page);
    expect(price, size.name).toContain(INTL.en);
    expect(price, size.name).not.toContain('PLN15.50');
    expect(await publicLabel(context, 'en-GB')).toBe(INTL.en);
    await card(page).scrollIntoViewIfNeeded();
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
    await context.close();
  }
});

test(`${KEY}: money-text a visitor speaking Spanish reads «15,50 PLN», as the browser writes it`, async ({ browser }) => {
  if (!original) throw new Error('beforeAll did not run');
  await registerBusinessIn(original, 'PL');
  expect(INTL.es).toBe('15,50 PLN');
  const { context, page } = await visitor(browser, WIDE, 'es-ES');
  await page.goto(`${A}/`);
  expect(await cardPrice(page)).toContain(INTL.es);
  expect(await publicLabel(context, 'es-ES')).toBe(INTL.es);
  await context.close();
});
