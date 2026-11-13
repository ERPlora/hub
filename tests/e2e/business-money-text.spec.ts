// flow: money-text (base/business.py `money_text`)
// The server writes an amount as the browser does (`Intl.NumberFormat`): a currency written in letters keeps off the
// figure by a no-break space (CLDR's currency spacing, which Babel skips), «PLN 15.50», never «PLN15.50». Hub `a`
// publishes its site with Services' catalog and moves to Poland (`PUT /internal/hubs/{id}`, signed the way the SaaS
// sends it): the public page the server paints and the public catalog the bundle reads write the price as Intl does,
// in English «PLN 15.50» at 390, 834 and 1440
// and in Spanish «15,50 PLN». The receipt, the invoice and the inventory export are not painted on a screen of the Hub
// (the screens paint their own paper with Intl): their pytest says the same. What the run creates is deleted after
// it, the site saved as it was found and taken offline, and `a`'s registration put back, also when a test fails.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, psql, registerBusinessIn, shot } from './helpers';
import { atRest, publicPriceLabel, publishedSiteSpec } from './website-helpers';

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
const publicLabel = (context: BrowserContext, language: string): Promise<string> => publicPriceLabel(context, SERVICE, language);

/** `a`'s registration and its site as the run found them (put back after). */
const kept = publishedSiteSpec(SERVICE, cleanUp);

test(`the server writes a price in złoty as the browser does, «PLN 15.50» in English, in 390, 834 and 1440`, async ({
  browser,
}) => {
  const { original } = kept;
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
    await atRest(page);
    await page.screenshot({ path: shot(`${KEY}-${size.name}`) });
    await context.close();
  }
});

test(`a visitor speaking Spanish reads «15,50 PLN», as the browser writes it`, async ({ browser }) => {
  const { original } = kept;
  if (!original) throw new Error('beforeAll did not run');
  await registerBusinessIn(original, 'PL');
  expect(INTL.es).toBe('15,50 PLN');
  const { context, page } = await visitor(browser, WIDE, 'es-ES');
  await page.goto(`${A}/`);
  expect(await cardPrice(page)).toContain(INTL.es);
  expect(await publicLabel(context, 'es-ES')).toBe(INTL.es);
  await context.close();
});
