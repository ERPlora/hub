// flow: BASE-F110, WEBSITE-F10 — a business's own domain opens its public website and nothing else (HUBS-F17, saas#195)
// The SaaS names the domain in the photo, signed as it sends it; the browser reaches it through the ALB's stand-in (its
// resolver sends `www.minegocio.test` to the stack), so this is what a visitor gets: the published page with its bundle,
// its menu on a phone and its images, no call to `/api`, «Log in» on the business's own address, and a 404 on the app, the
// login, the API and `/internal` even with a session of the business in the browser. Both addresses tell search engines
// the domain is the main one, without a redirect (hub#818). A host the Hub does not know is the 400 it always was, and a
// domain given up joins it. Hub `a`'s photo and its site are put back after, also when a test
// fails: the other specs expect `/` of `a` to jump to the login.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, internalPut, psql } from './helpers';
import { STACK } from './stack';
import { atRest, ownerOfTheSite, photo, type Site } from './website-helpers';

const KEY = 'HUBS-F17-CUSTOM-DOMAIN';
const DOMAIN = 'www.minegocio.test';
const UNKNOWN = 'scanner.example.test';
const ON_DOMAIN = `http://${DOMAIN}:${STACK.hubPort}`;
const TITLE = 'Our own domain, in the browser';
const SIZES = [
  { name: '375', width: 375, height: 667 },
  { name: '820', width: 820, height: 1180 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const WIDE = { width: 1440, height: 900 };


test.describe.configure({ mode: 'serial' });
test.use({ launchOptions: { args: [`--host-resolver-rules=MAP ${DOMAIN} 127.0.0.1, MAP ${UNKNOWN} 127.0.0.1`] } });

let hubId = '';
let photoBefore: Record<string, unknown> = {};
let found: Site | undefined;
let owner: { context: BrowserContext; page: Page } | undefined;
let version = Math.floor(Date.now() / 1000);

/** The SaaS's photo of `a`: the one it found, with what the run says of its domain. */
async function pushPhoto(customDomain: string | null): Promise<void> {
  version += 1;
  const body = JSON.stringify({ ...photoBefore, hub_id: hubId, slug: 'a', version, custom_domain: customDomain });
  const response = await internalPut(`/internal/hubs/${hubId}/state`, body);
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** A visitor: a fresh context without a session. */
async function visitor(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport, locale: 'en-GB' });
  return { context, page: await context.newPage() };
}

test.beforeAll(async ({ browser }) => {
  [hubId] = psql(`select id from base_hub where slug = 'a'`).split('|');
  photoBefore = JSON.parse(psql(`select state from base_hub where slug = 'a'`) || '{}') as Record<string, unknown>;
  ({ owner, found } = await ownerOfTheSite(browser, WIDE));
  const cover = await api<{ id: string; url: string }>(owner.context, A, 'POST', '/website/images', {
    filename: 'cover.jpg',
    content_type: 'image/jpeg',
    data_base64: (await photo(owner.page, 'Cover', 30)).toString('base64'),
  });
  expect(cover.status, JSON.stringify(cover.data)).toBe(201);
  const content = {
    ...found.content,
    hero: { ...found.content.hero, title: TITLE, cover: { id: cover.data.id } },
    // A section of the body: the top bar has a menu.
    about: { ...found.content.about, hidden: false, title: 'About us', text: 'Fresh food every day.' },
    // The block the page's script refreshes elsewhere: here it has to ask nothing.
    catalog: { ...found.content.catalog, hidden: false, source: 'service', category_ids: [], show_prices: true },
  };
  const saved = await api(owner.context, A, 'POST', '/website/site', { template: 'classic', theme: found.theme, content });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  const published = await api(owner.context, A, 'POST', '/website/site/publish');
  expect(published.status, JSON.stringify(published.data)).toBe(200);
  await pushPhoto(DOMAIN);
});

test.afterAll(async () => {
  try {
    await pushPhoto(null);
    if (owner && found) {
      const restored = await api(owner.context, A, 'POST', '/website/site', { template: found.template, theme: found.theme, content: found.content });
      expect(restored.status, JSON.stringify(restored.data)).toBe(200);
      const offline = await api(owner.context, A, 'POST', '/website/site/unpublish');
      expect(offline.status, JSON.stringify(offline.data)).toBe(200);
    }
  } finally {
    await owner?.context.close();
  }
});

test(`${KEY}: the published page opens on the domain with its bundle, its image and no call to the API, at 375, 820 and 1440`, async ({ browser }) => {
  for (const size of SIZES) {
    const { context, page } = await visitor(browser, { width: size.width, height: size.height });
    const failures: string[] = [];
    const asked: string[] = [];
    page.on('console', (message) => {
      // Only here, over plain HTTP on a host that is not localhost: on the real domain it is HTTPS.
      if (message.type() === 'error' && !message.text().includes('Cross-Origin-Opener-Policy')) failures.push(message.text());
    });
    page.on('pageerror', (error) => failures.push(String(error)));
    page.on('request', (request) => asked.push(new URL(request.url()).pathname));
    const response = await page.goto(ON_DOMAIN);
    expect(response?.status()).toBe(200);
    await expect(page.getByRole('heading', { name: TITLE })).toBeVisible();
    // The bundle ran (the colour mode, the catalog) and the cover came from the domain.
    const cover = page.locator('header img, section img, main img').first();
    await expect(cover).toBeVisible();
    expect(await cover.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(true);
    expect(new URL(await cover.evaluate((image: HTMLImageElement) => image.src)).host).toBe(`${DOMAIN}:${STACK.hubPort}`);
    if (size.width < 768) {
      // Bootstrap's collapse: the menu of a phone, by the page's own script.
      await page.locator('.navbar-toggler').click();
      await expect(page.locator('.navbar-collapse')).toHaveClass(/show/);
    }
    await atRest(page);
    await capture(page, `${KEY}-${size.name}`);
    expect(asked.filter((path) => path.startsWith('/api/'))).toEqual([]);
    expect(failures).toEqual([]);
    await context.close();
  }
});

test(`${KEY}: «Log in» leaves the domain for the business's own address, where the login stays`, async ({ browser }) => {
  const { context, page } = await visitor(browser, WIDE);
  await page.goto(ON_DOMAIN);
  const login = page.locator('[data-ep-login]').first();
  await expect(login).toHaveAttribute('href', 'https://a.localhost/auth/login');
  await context.close();
  // On its own address nothing changed: the page's link is the same-origin one.
  const own = await visitor(browser, WIDE);
  await own.page.goto(A);
  await expect(own.page.locator('[data-ep-login]').first()).toHaveAttribute('href', '/auth/login');
  await own.context.close();
});

test(`${KEY}: both addresses tell search engines the domain is the main one, and neither redirects (hub#818)`, async ({ browser }) => {
  const { context, page } = await visitor(browser, WIDE);
  for (const address of [ON_DOMAIN, A]) {
    const response = await page.goto(address);
    expect(response?.status(), address).toBe(200);
    expect(response?.request().redirectedFrom(), address).toBeNull();
    await expect(page.getByRole('heading', { name: TITLE })).toBeVisible();
    await expect(page.locator('link[rel="canonical"]'), address).toHaveCount(1);
    await expect(page.locator('head link[rel="canonical"]'), address).toHaveAttribute('href', `https://${DOMAIN}/`);
  }
  await context.close();
});

test(`${KEY}: the app, the login, the API and /internal are not on the domain, even with a session of the business`, async () => {
  if (!owner) throw new Error('beforeAll did not run');
  // `owner` has its session on `a`: the same browser, on the domain, is a visitor.
  const page = await owner.context.newPage();
  await page.goto(ON_DOMAIN);
  await expect(page.getByRole('heading', { name: TITLE })).toBeVisible();
  await expect(page.locator('#spa-config')).toHaveCount(0);
  for (const path of ['/settings', '/website', '/login', '/auth/login', '/admin/', '/api/session/me', '/api/website/public/catalog', '/internal/usage']) {
    const response = await page.goto(`${ON_DOMAIN}${path}`);
    expect(response?.status(), path).toBe(404);
  }
  await page.close();
});

test(`${KEY}: the probe gives the business's id and nothing else; a host the Hub does not know is the 400 it always was`, async ({ browser }) => {
  const { context, page } = await visitor(browser, WIDE);
  const probe = await page.goto(`${ON_DOMAIN}/.well-known/erplora-hub`);
  expect(probe?.status()).toBe(200);
  expect(await probe?.json()).toEqual({ hub_id: hubId });
  const unknown = await page.goto(`http://${UNKNOWN}:${STACK.hubPort}/`);
  expect(unknown?.status()).toBe(400);
  await context.close();
});

test(`${KEY}: a domain given up stops serving`, async ({ browser }) => {
  await pushPhoto(null);
  const { context, page } = await visitor(browser, WIDE);
  expect((await page.goto(ON_DOMAIN))?.status()).toBe(400);
  await context.close();
  // Its own address keeps its website.
  const own = await visitor(browser, WIDE);
  await own.page.goto(A);
  await expect(own.page.getByRole('heading', { name: TITLE })).toBeVisible();
  // The page it kept while the domain was its main address names its own address now (hub#818).
  await expect(own.page.locator('head link[rel="canonical"]')).toHaveAttribute('href', 'https://a.localhost/');
  await own.context.close();
  await pushPhoto(DOMAIN);
});
