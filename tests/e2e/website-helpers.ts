// What the specs of the website editor (website*.spec.ts and the fixes seen in it) share and the rest of the e2e does not.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, hostPage, type Registration, registerBusinessIn, registrationOf, settled } from './helpers';

/** The site as `GET /website/site` answers it: what a spec puts back after. */
export interface Site {
  template: string;
  theme: Record<string, unknown>;
  content: Record<string, Record<string, unknown>>;
  is_live: boolean;
}

/** The owner of `a` on the website's editor at `viewport`, and the site as the run finds it. */
export async function ownerOfTheSite(
  browser: Browser,
  viewport: { width: number; height: number },
): Promise<{ owner: { context: BrowserContext; page: Page }; found: Site }> {
  const owner = await hostPage(browser, A, { next: '/website', viewport });
  const site = await api<Site>(owner.context, A, 'GET', '/website/site');
  expect(site.status).toBe(200);
  return { owner, found: site.data };
}

/**
 * The page at rest for its capture: no focus ring (the website's own step), then the harness's one wait, `settled`
 * (helpers.ts): nothing moving, in the document or in any shadow root (Bootstrap's buttons fade 150 ms, the dev server
 * injects the stylesheets after the first paint, and in the editor Ionic animates its dialogs and toasts in theirs),
 * and the page painted as it is now.
 */
export async function atRest(page: Page): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await settled(page);
}

/** The editor's section `name` (`website-section-<name>`) opened, if it was not already. */
export async function openSection(page: Page, name: string): Promise<void> {
  const accordion = page.getByTestId(`website-section-${name}`);
  if ((await accordion.getAttribute('class'))?.includes('accordion-expanded')) return;
  await accordion.locator('ion-item[slot="header"]').click();
  await expect(accordion).toHaveClass(/accordion-expanded/);
}

/** A photo drawn in the page (no binary in the repository): a gradient with `label` in a corner, as a JPEG. */
export async function photo(page: Page, label: string, hue: number): Promise<Buffer> {
  const url = await page.evaluate(
    ({ label, hue }) => {
      const canvas = document.createElement('canvas');
      canvas.width = 600;
      canvas.height = 600;
      const draw = canvas.getContext('2d') as CanvasRenderingContext2D;
      const gradient = draw.createLinearGradient(0, 0, 600, 600);
      gradient.addColorStop(0, `hsl(${hue}, 70%, 70%)`);
      gradient.addColorStop(1, `hsl(${hue + 40}, 60%, 35%)`);
      draw.fillStyle = gradient;
      draw.fillRect(0, 0, 600, 600);
      draw.fillStyle = 'rgba(255, 255, 255, 0.9)';
      draw.font = '600 48px Georgia, serif';
      draw.fillText(label, 40, 560);
      return canvas.toDataURL('image/jpeg', 0.86);
    },
    { label, hue },
  );
  return Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');
}

/** The site as it was, with a service `name` at 15,50 and Services' whole catalog with its prices shown, published: the
 *  site as it was, to put it back. */
export async function publishedWithAService(context: BrowserContext, name: string): Promise<Site> {
  const site = await api<Site>(context, A, 'GET', '/website/site');
  expect(site.status).toBe(200);
  const found = site.data;
  const created = await api(context, A, 'POST', '/service/services', { name, price: 1550, duration_minutes: 30, tax_category_key: 'service.generic' });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  const content = {
    ...found.content,
    catalog: { ...found.content.catalog, hidden: false, source: 'service', category_ids: [], show_prices: true },
  };
  const saved = await api(context, A, 'POST', '/website/site', { template: found.template, theme: found.theme, content });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  const published = await api(context, A, 'POST', '/website/site/publish');
  expect(published.status, JSON.stringify(published.data)).toBe(200);
  return found;
}

/** The site put back as it was (`found`) and offline: the other specs on hub `a` expect `/` to jump to the login. */
export async function siteBackOffline(context: BrowserContext, found: Site): Promise<void> {
  const restored = await api(context, A, 'POST', '/website/site', { template: found.template, theme: found.theme, content: found.content });
  expect(restored.status, JSON.stringify(restored.data)).toBe(200);
  const offline = await api(context, A, 'POST', '/website/site/unpublish');
  expect(offline.status, JSON.stringify(offline.data)).toBe(200);
}

/** What a spec of the public page keeps to put back: `a`'s registration, the owner on the editor and the site as found. */
export interface KeptSite {
  original: Registration;
  owner: { context: BrowserContext; page: Page };
  found: Site;
}

/** `a`'s registration kept, the owner on the website's editor at a desk's size, and the site published with a service
 *  `name` (`publishedWithAService`). */
export async function publishedSiteOf(browser: Browser, name: string): Promise<KeptSite> {
  const original = registrationOf('a');
  const owner = await hostPage(browser, A, { next: '/website', viewport: { width: 1440, height: 900 } });
  return { original, owner, found: await publishedWithAService(owner.context, name) };
}

/** Registers the hooks of a spec of the public page: `cleanUp` and the site published with the service `name`
 *  (`publishedSiteOf`) before its tests, and everything put back after them (`siteAndCountryBack`). Gives what it kept,
 *  filled once the first hook has run. */
export function publishedSiteSpec(name: string, cleanUp: () => void): Partial<KeptSite> {
  const kept: Partial<KeptSite> = {};
  test.beforeAll(async ({ browser }) => {
    cleanUp();
    Object.assign(kept, await publishedSiteOf(browser, name));
  });
  test.afterAll(() => siteAndCountryBack(kept, cleanUp));
  return kept;
}

/** After the spec: `a` registered where it was, its site put back and offline, `cleanUp`, and the owner's context closed. */
export async function siteAndCountryBack(kept: Partial<KeptSite>, cleanUp: () => void): Promise<void> {
  try {
    if (kept.original) await registerBusinessIn(kept.original, kept.original.country);
    if (kept.owner && kept.found) await siteBackOffline(kept.owner.context, kept.found);
  } finally {
    cleanUp();
    await kept.owner?.context.close();
  }
}

/** The label of the price of the service `name` in the public catalog, as the bundle reads it: no session, and in the
 *  visitor's `language` when one is given. */
export async function publicPriceLabel(context: BrowserContext, name: string, language?: string): Promise<string> {
  const answer = await context.request.get(`${A}/api/website/public/catalog`, language ? { headers: { 'Accept-Language': language } } : undefined);
  expect(answer.status()).toBe(200);
  const catalog = (await answer.json()) as { groups: { items: { name: string; price_label: string }[] }[] };
  const item = catalog.groups.flatMap((group) => group.items).find((row) => row.name === name);
  expect(item, `${name} in the public catalog`).toBeTruthy();
  return item?.price_label ?? '';
}
