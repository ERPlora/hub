// Every flow of the website app (apps/website, WEBSITE-F01 … F12), one test each (its key in the title and in
// `// flow:`), done end to end on the real stack as the owner of hub `a` and as a visitor without a session, and seen
// at 390×844, 834×1112 and 1440×900: `threeShots` resizes, brings what the flow shows into sight, checks nothing
// scrolls sideways and saves `.artifacts/APP-WEBSITE-<key>-<width>.png`. Each test starts from the same site, saved
// and taken offline through the API (`reset`), so any one runs alone. The four designs in light and dark, the
// palette's colours and the editor's typing regression stay in website.spec.ts; the deeper cases of each flow live in
// the app's pytest and Vitest suites.
//
// Google is never asked (Places is paid): the stack has no `GOOGLE_PLACES_API_KEY` (checked before the first test),
// and WEBSITE-F12 shows the reviews from a last good answer written straight into the site's row. At the end the site
// is offline again and its reviews gone: the other specs on hub `a` expect `/` to jump to the login.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, hostPage, HUB_DIR, MAIL_DIR, OWNER, psql, SAAS, shot, topbarApps } from './helpers';
import { readMailCode } from './mail';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
const WIDE = { width: 1440, height: 900 };
const TEMPLATES = ['classic', 'modern', 'minimal', 'bold'] as const;
/** Hub `a`'s public address, as the editor and the QR give it. */
const PUBLIC_URL = `${A}/`;
const HERO = 'Fresh bread every morning';
const PHONE = '+34 600 123 456';
/** Google's own example of a Place ID (Sydney's office): never asked here. */
const PLACE_ID = 'ChIJN1t_tDeuEmsRUsoyG83frY4';
/** The site's row of hub `a` (phase 1: one row per hub in shared tables). */
const SITE_ROW = "hub_id = (select id from base_hub where slug = 'a')";

interface Rows<T> {
  rows: T[];
}
interface Site {
  template: string;
  theme: Record<string, unknown>;
  content: Record<string, Record<string, unknown>>;
  is_live: boolean;
  published_version: number;
  reviews: { state: string };
}

/** The site every test starts from: classic, «Ocean» in light, a title, a phone and an address, nothing else. */
function baseline(template: string = 'classic'): Record<string, unknown> {
  return {
    template,
    theme: { palette: 'ocean', custom: null, mode: 'light' },
    content: {
      topbar: { name: "Pepe's Bakery", logo: null },
      hero: { title: HERO, tagline: 'Since 1998 in Gran Vía', cover: null },
      about: { hidden: true, title: '', text: '', image: null },
      catalog: { hidden: true, title: '', source: null, category_ids: [], show_prices: true },
      gallery: { hidden: false, title: '', images: [] },
      reviews: { hidden: false, title: '', place_ref: '' },
      contact: {
        hidden: false,
        title: '',
        phone: PHONE,
        whatsapp: '',
        email: '',
        socials: { instagram: '', facebook: '', tiktok: '', x: '' },
        hours: [
          { day: 'mon', intervals: [{ opens: '08:00', closes: '14:00' }] },
          { day: 'sun', intervals: [] },
        ],
      },
      location: { hidden: false, title: '', address_lines: ['Gran Vía 1', 'Madrid'], map_url: '' },
      footer: { text: "Pepe's Bakery S.L." },
    },
  };
}

let owner: { context: BrowserContext; page: Page };

/** Saves `body` as the draft through the API (the editor's own operation) and checks it was taken. */
async function saveSite(body: Record<string, unknown>): Promise<Site> {
  const saved = await api<Site>(owner.context, A, 'POST', '/website/site', body);
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  return saved.data;
}

async function publishApi(): Promise<void> {
  const published = await api<{ is_live: boolean }>(owner.context, A, 'POST', '/website/site/publish');
  expect(published.status, JSON.stringify(published.data)).toBe(200);
  expect(published.data.is_live).toBe(true);
}

async function unpublishApi(): Promise<void> {
  const offline = await api<{ is_live: boolean }>(owner.context, A, 'POST', '/website/site/unpublish');
  expect(offline.status, JSON.stringify(offline.data)).toBe(200);
  expect(offline.data.is_live).toBe(false);
}

async function getSite(): Promise<Site> {
  const site = await api<Site>(owner.context, A, 'GET', '/website/site');
  expect(site.status).toBe(200);
  return site.data;
}

/** The baseline saved, offline, no reviews kept; then the editor opened afresh at a computer's width. */
async function reset(page: Page, body: Record<string, unknown> = baseline()): Promise<void> {
  await page.goto('about:blank');
  await saveSite(body);
  await unpublishApi();
  psql(`update website_site set reviews_snapshot = '{}'::jsonb where ${SITE_ROW}`);
  await page.setViewportSize(WIDE);
  await page.goto(`${A}/website`);
  await expect(page.getByTestId('website-editor')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('website-save-state')).toHaveText(/All changes saved/);
}

/** The catalog the page lists: the same four services of Services website.spec.ts seeds (its checks count them). */
async function seedServices(context: BrowserContext): Promise<void> {
  const MENU = [
    { category: 'Menus', name: 'Lunch menu', price: 1650, duration_minutes: 60 },
    { category: 'Menus', name: 'Tasting menu', price: 4800, duration_minutes: 120 },
    { category: 'Events', name: 'Private dining room', price: 35000, duration_minutes: 180 },
    { category: 'Events', name: 'Cooking class', price: 6500, duration_minutes: 90 },
  ];
  const categories = await api<Rows<{ name: string }>>(context, A, 'GET', '/service/categories?limit=100');
  expect(categories.status).toBe(200);
  for (const name of new Set(MENU.map((service) => service.category))) {
    if (categories.data.rows.some((category) => category.name === name)) continue;
    const created = await api(context, A, 'POST', '/service/categories', { name });
    expect(created.status, `category ${name}: ${JSON.stringify(created.data)}`).toBe(201);
  }
  const services = await api<Rows<{ name: string }>>(context, A, 'GET', '/service/services?limit=100');
  expect(services.status).toBe(200);
  for (const service of MENU) {
    if (services.data.rows.some((row) => row.name === service.name)) continue;
    const created = await api(context, A, 'POST', '/service/services', { ...service, tax_category_key: 'service.generic' });
    expect(created.status, `service ${service.name}: ${JSON.stringify(created.data)}`).toBe(201);
  }
}

/** A photo drawn in the page (no binary in the repository): a gradient with `label` in a corner, as a JPEG. */
async function photo(page: Page, label: string, hue: number): Promise<Buffer> {
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

const field = (page: Page, testid: string): Locator => page.getByTestId(testid).locator('input, textarea').first();
const preview = (page: Page) => page.frameLocator('[data-testid="website-preview-frame"]');

async function openSection(page: Page, name: string): Promise<void> {
  const accordion = page.getByTestId(`website-section-${name}`);
  if ((await accordion.getAttribute('class'))?.includes('accordion-expanded')) return;
  await accordion.locator('ion-item[slot="header"]').click();
  await expect(accordion).toHaveClass(/accordion-expanded/);
}

async function setToggle(page: Page, testid: string, on: boolean): Promise<void> {
  const toggle = page.getByTestId(testid);
  if ((await toggle.evaluate((el) => (el as HTMLElement & { checked: boolean }).checked)) !== on) await toggle.click();
  await expect.poll(() => toggle.evaluate((el) => (el as HTMLElement & { checked: boolean }).checked)).toBe(on);
}

/** Saves what is unsaved (the autosave may have done it already: then «Save» is off) and waits for the server. */
async function save(page: Page): Promise<void> {
  const state = page.getByTestId('website-save-state');
  if ((await state.textContent())?.includes('Unsaved')) await page.getByTestId('website-save').click();
  await expect(state).toHaveText(/All changes saved/, { timeout: 15_000 });
}

/** The confirmation `title` asks, accepted. */
async function confirmDialog(page: Page, title: string): Promise<void> {
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: title });
  await expect(dialog).toBeVisible();
  await dialog.locator('.ep-form-modal__submit').click();
  await expect(dialog).toBeHidden();
}

/** The editor's view on a phone or a tablet («Edit» or «Preview»); a computer shows both side by side. */
async function showView(page: Page, view: 'Edit' | 'Preview'): Promise<void> {
  const tabs = page.getByTestId('website-view');
  if (await tabs.isVisible()) await tabs.locator('ion-segment-button').filter({ hasText: view }).click();
}

/** How many pixels the page scrolls sideways (0 when everything fits its width), the editor's content included. */
async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const content = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-content') as
      | (HTMLElement & { getScrollElement?: () => Promise<HTMLElement> })
      | null;
    const inner = content?.getScrollElement ? await content.getScrollElement() : null;
    const outer = document.documentElement.scrollWidth - window.innerWidth;
    const own = inner ? inner.scrollWidth - inner.clientWidth : 0;
    return Math.max(outer, own);
  });
}

/** At each of the three sizes: `target` in sight (after `before`, for a view that changes with the width), no sideways
 * scroll, and the screenshot `APP-WEBSITE-<key>-<width>`. */
async function threeShots(page: Page, key: string, target: () => Locator, before?: () => Promise<void>): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    if (before) await before();
    const seen = target();
    await expect(async () => {
      await seen.scrollIntoViewIfNeeded({ timeout: 2000 });
      await expect(seen).toBeInViewport({ timeout: 1000 });
    }, `${key} at ${vp.label}`).toPass();
    await expect.poll(() => horizontalOverflow(page), `${key} at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`APP-WEBSITE-${key}-${vp.label}`) });
  }
  await page.setViewportSize(WIDE);
}

/** The public page at rest for its capture: no focus ring, no colour still in transition (Bootstrap's buttons fade
 * 150 ms, and the dev server injects the stylesheets after the first paint). */
async function settled(page: Page): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
}

/** A visitor: a fresh context without a session, at `width`, speaking `locale`. */
async function visitor(
  browser: Browser,
  viewport: { width: number; height: number } = WIDE,
  locale = 'en-GB',
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport, locale });
  return { context, page: await context.newPage() };
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  // Places is paid: this spec must run where the Hub cannot ask Google at all.
  const env = join(HUB_DIR, '.env');
  const configured = existsSync(env) && /^\s*GOOGLE_PLACES_API_KEY\s*=\s*\S/m.test(readFileSync(env, 'utf8'));
  if (configured || process.env.GOOGLE_PLACES_API_KEY) {
    throw new Error('website-flows.spec.ts never asks Google: run it on a stack without GOOGLE_PLACES_API_KEY.');
  }
  owner = await hostPage(browser, A, { next: '/website', viewport: WIDE });
  await seedServices(owner.context);
});

test.afterAll(async () => {
  if (!owner) return;
  await saveSite(baseline());
  await unpublishApi();
  psql(`update website_site set reviews_snapshot = '{}'::jsonb where ${SITE_ROW}`);
  await owner.context.close();
});

// flow: WEBSITE-F01
test('WEBSITE-F01: the draft saves on its own after typing, and a refused field says why without losing it', async () => {
  const { page } = owner;
  await reset(page);
  await openSection(page, 'hero');
  await field(page, 'website-field-hero-title').fill('Bread and cakes since 1998');
  // The autosave, two seconds after the last change; nothing to press.
  await expect(page.getByTestId('website-save-state')).toHaveText(/Unsaved changes/);
  await expect(page.getByTestId('website-save-state')).toHaveText(/All changes saved/, { timeout: 15_000 });
  expect((await getSite()).content.hero.title).toBe('Bread and cakes since 1998');
  // Visitors see none of it until it is published.
  expect((await getSite()).is_live).toBe(false);

  await openSection(page, 'contact');
  await field(page, 'website-field-contact-email').fill('not-an-email');
  await page.getByTestId('website-save').click();
  const email = page.getByTestId('website-field-contact-email');
  await expect(email).toHaveClass(/ion-invalid/);
  await expect(email).toContainText('Enter a valid email address.');
  await expect(field(page, 'website-field-contact-email')).toHaveValue('not-an-email');
  await expect(page.getByTestId('website-save-error')).toBeVisible();
  await threeShots(page, 'F01', () => page.getByTestId('website-field-contact-email'), () => showView(page, 'Edit'));
  await field(page, 'website-field-contact-email').fill('');
  await save(page);
  expect((await getSite()).content.contact.email).toBe('');
});

// flow: WEBSITE-F02
test('WEBSITE-F02: a design, a palette with its colours changed and the background go to the draft and its preview', async () => {
  const { page } = owner;
  await reset(page);
  await page.getByTestId('website-template-bold').click();
  await expect(page.getByTestId('website-template-bold')).toHaveAttribute('aria-checked', 'true');
  await page.getByTestId('website-palette-rose').click();
  await expect(page.getByTestId('website-palette-rose')).toHaveAttribute('aria-checked', 'true');
  // A colour written wrong is not taken, and says how to write it.
  const primary = field(page, 'website-colour-primary');
  await primary.fill('#12');
  await primary.blur();
  await expect(page.getByTestId('website-colour-primary')).toHaveClass(/ion-invalid/);
  await expect(page.getByTestId('website-colour-primary')).toContainText('Write the colour as #RRGGBB, for example #1A73E8.');
  await primary.fill('#aa3355');
  await primary.blur();
  await expect(page.getByTestId('website-colours-reset')).toBeVisible();
  await page.getByTestId('website-mode').locator('ion-segment-button').filter({ hasText: 'Dark' }).click();
  await save(page);
  const site = await getSite();
  expect(site.template).toBe('bold');
  expect(site.theme).toMatchObject({ palette: 'rose', custom: { primary: '#aa3355' }, mode: 'dark' });
  // Nothing of the content changed with the design.
  expect(site.content.hero.title).toBe(HERO);
  await expect(preview(page).locator('body.ws-bold')).toBeVisible();
  await expect(preview(page).locator('html')).toHaveAttribute('data-bs-theme', 'dark');
  await threeShots(page, 'F02', () => page.getByTestId('website-palette-rose'), () => showView(page, 'Edit'));
  // «Reset colours» gives the palette's own back.
  await page.getByTestId('website-colours-reset').click();
  await expect(page.getByTestId('website-colours-reset')).toHaveCount(0);
  await save(page);
  expect((await getSite()).theme).toMatchObject({ palette: 'rose', custom: null });
});

// flow: WEBSITE-F03
test('WEBSITE-F03: «Show» puts a section on the page and takes it off; the bar, the header and the footer have none', async () => {
  const { page } = owner;
  await reset(page);
  for (const fixed of ['topbar', 'hero', 'footer']) await expect(page.getByTestId(`website-show-${fixed}`)).toHaveCount(0);
  await openSection(page, 'about');
  await setToggle(page, 'website-show-about', true);
  await field(page, 'website-field-about-text').fill('We bake with flour from the valley.');
  await save(page);
  await expect(preview(page).locator('[data-ep-section="about"]')).toContainText('We bake with flour from the valley.');
  await threeShots(page, 'F03', () => preview(page).locator('[data-ep-section="about"]'), () => showView(page, 'Preview'));
  await showView(page, 'Edit');
  await setToggle(page, 'website-show-about', false);
  await save(page);
  await expect(preview(page).locator('[data-ep-section="about"]')).toHaveCount(0);
  // Hidden, never lost.
  expect((await getSite()).content.about).toMatchObject({ hidden: true, text: 'We bake with flour from the valley.' });
});

// flow: WEBSITE-F04
test('WEBSITE-F04: an image is uploaded from its field, a file that is no image is refused, and «Remove» empties it', async () => {
  const { page } = owner;
  await reset(page);
  await openSection(page, 'topbar');
  await page.getByTestId('website-image-logo-file').setInputFiles({
    name: 'fake.png',
    mimeType: 'image/png',
    buffer: Buffer.from('this is not a picture'),
  });
  await expect(page.getByTestId('website-image-logo-error')).toHaveText('This file is not a PNG image.', { timeout: 15_000 });
  await page.getByTestId('website-image-logo-file').setInputFiles({
    name: 'logo.jpg',
    mimeType: 'image/jpeg',
    buffer: await photo(page, 'Logo', 20),
  });
  const thumbnail = page.getByTestId('website-image-logo-image');
  await expect(thumbnail).toBeVisible({ timeout: 15_000 });
  await expect(thumbnail).toHaveAttribute('src', /^\/p\/media\/[0-9a-f]{32}\/website\/img\/[0-9a-f]{16}\.jpg$/);
  await save(page);
  const logo = (await getSite()).content.topbar.logo as { id: string; url: string };
  expect(logo.url).toBe(await thumbnail.getAttribute('src'));
  // The Hub serves it, cached for a year.
  const served = await owner.context.request.get(`${A}${logo.url}`);
  expect(served.status()).toBe(200);
  expect(served.headers()['content-type']).toBe('image/jpeg');
  expect(served.headers()['cache-control']).toContain('immutable');
  await threeShots(page, 'F04', () => page.getByTestId('website-image-logo'), () => showView(page, 'Edit'));
  await page.getByTestId('website-image-logo-remove').click();
  await expect(page.getByTestId('website-image-logo-image')).toHaveCount(0);
  await save(page);
  expect((await getSite()).content.topbar.logo).toBeNull();
});

// flow: WEBSITE-F05
test('WEBSITE-F05: the catalog shows Services’ offer by category with its prices, on the preview and on the page', async ({
  browser,
}) => {
  const { page } = owner;
  await reset(page);
  await openSection(page, 'catalog');
  await setToggle(page, 'website-show-catalog', true);
  await page.getByTestId('website-catalog-source').click();
  await page.locator('ion-select-popover ion-radio').filter({ hasText: 'Services' }).click();
  await expect(page.getByTestId('website-catalog-categories')).toBeVisible();
  await setToggle(page, 'website-catalog-prices', true);
  await save(page);
  expect((await getSite()).content.catalog).toMatchObject({ source: 'service', show_prices: true, category_ids: [] });
  const block = preview(page).locator('[data-ep-block="catalog"]');
  for (const name of ['Lunch menu', 'Tasting menu', 'Private dining room', 'Cooking class']) {
    await expect(block.locator('.card-title').filter({ hasText: name })).toHaveCount(1);
  }
  await expect(block).toContainText('€16.50');
  await threeShots(page, 'F05', () => page.getByTestId('website-catalog-source'), () => showView(page, 'Edit'));
  await publishApi();
  const { context, page: visiting } = await visitor(browser, { width: 390, height: 844 });
  await visiting.goto(`${A}/`);
  const catalog = visiting.locator('[data-ep-block="catalog"]');
  await expect(catalog.locator('.nav-pills .nav-link')).toHaveCount(2);
  await expect(catalog).toContainText('Lunch menu');
  await expect(catalog).toContainText('€16.50');
  await context.close();
});

// flow: WEBSITE-F06
test('WEBSITE-F06: the preview paints the draft beside the editor, at a computer’s or a phone’s width, never indexed', async () => {
  const { page } = owner;
  await reset(page);
  await expect(page.getByTestId('website-preview-frame')).toBeVisible();
  await expect(preview(page).getByRole('heading', { level: 1 })).toHaveText(HERO);
  await expect(preview(page).locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  await page.getByTestId('website-preview-width').locator('ion-segment-button').filter({ hasText: 'Phone' }).click();
  await expect(page.locator('.wp-stage--mobile')).toBeVisible();
  await page.getByTestId('website-preview-reload').click();
  await expect(preview(page).locator('body[data-ep-template="classic"]')).toBeVisible();
  // Its own answer: framed by the hub only, never kept, no nonce.
  const answer = await owner.context.request.get(`${A}/api/website/site/preview`);
  expect(answer.status()).toBe(200);
  expect(answer.headers()['cache-control']).toBe('no-store');
  expect(answer.headers()['x-frame-options']).toBe('SAMEORIGIN');
  const csp = answer.headers()['content-security-policy'] ?? '';
  expect(csp).toContain("frame-ancestors 'self'");
  expect(csp).not.toContain('nonce-');
  // On a phone or a tablet the preview is a tab of its own.
  await threeShots(page, 'F06', () => page.getByTestId('website-preview-frame'), () => showView(page, 'Preview'));
  await page.setViewportSize({ width: 390, height: 844 });
  await showView(page, 'Preview');
  await expect(page.getByTestId('website-editor')).toBeHidden();
  await showView(page, 'Edit');
  await expect(page.getByTestId('website-editor')).toBeVisible();
  await page.setViewportSize(WIDE);
  await page.getByTestId('website-preview-width').locator('ion-segment-button').filter({ hasText: 'Computer' }).click();
});

// flow: WEBSITE-F07
test('WEBSITE-F07: «Publish» asks first, saves what is unsaved and puts the page online; later changes wait', async ({ browser }) => {
  const { page } = owner;
  await reset(page);
  await expect(page.getByTestId('website-status-offline').or(page.getByTestId('website-status-never'))).toBeVisible();
  await openSection(page, 'hero');
  await field(page, 'website-field-hero-tagline').fill('Open every day');
  await page.getByTestId('website-publish').click();
  await expect(page.locator('ion-modal.ep-form-modal')).toContainText(`Whoever opens ${PUBLIC_URL} will see this version`);
  await confirmDialog(page, 'Publish your website?');
  await expect(page.getByTestId('website-status-live')).toHaveText(`Your website is online at ${PUBLIC_URL}`, { timeout: 15_000 });
  await expect(page.getByTestId('website-status-changes')).toHaveCount(0);
  const before = await getSite();
  expect(before.is_live).toBe(true);
  expect(before.content.hero.tagline).toBe('Open every day');
  const { context, page: visiting } = await visitor(browser);
  await visiting.goto(`${A}/`);
  await expect(visiting.getByText('Open every day')).toBeVisible();
  // A change after publishing stays in the draft until the next publication.
  await field(page, 'website-field-hero-tagline').fill('Open every day but Sunday');
  await save(page);
  await expect(page.getByTestId('website-status-changes')).toHaveText('You have changes that are not published yet.');
  await visiting.reload();
  await expect(visiting.getByText('Open every day', { exact: true })).toBeVisible();
  await context.close();
  await threeShots(page, 'F07', () => page.getByTestId('website-status-live'));
  // Declined, nothing is published.
  await page.getByTestId('website-publish').click();
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: 'Publish your website?' });
  await dialog.locator('.ep-form-modal__cancel').click();
  await expect(dialog).toBeHidden();
  expect((await getSite()).published_version).toBe(before.published_version);
});

// flow: WEBSITE-F08
test('WEBSITE-F08: «Take offline» asks first, and the address goes back to the team’s sign-in; nothing is lost', async ({
  browser,
}) => {
  const { page } = owner;
  await reset(page);
  await publishApi();
  await expect(page.getByTestId('website-status-live')).toBeVisible({ timeout: 15_000 });
  const version = (await getSite()).published_version;
  await page.getByTestId('website-unpublish').click();
  await expect(page.locator('ion-modal.ep-form-modal')).toContainText(`${PUBLIC_URL} will go back to your team's sign-in page`);
  await confirmDialog(page, 'Take your website offline?');
  await expect(page.getByTestId('website-status-offline')).toHaveText('Your website is offline. Publish it to put it back online.', {
    timeout: 15_000,
  });
  await expect(page.getByTestId('website-unpublish')).toHaveCount(0);
  const site = await getSite();
  expect(site.published_version).toBe(version);
  expect(site.content.hero.title).toBe(HERO);
  await threeShots(page, 'F08', () => page.getByTestId('website-status-offline'));
  const { context, page: visiting } = await visitor(browser);
  await visiting.goto(`${A}/`);
  await visiting.waitForURL((url) => url.origin === SAAS, { timeout: 30_000 });
  await context.close();
});

// flow: WEBSITE-F09
test('WEBSITE-F09: «Share and QR» gives the address to copy and its QR as PNG and SVG', async () => {
  const { page } = owner;
  await reset(page);
  await owner.context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: A });
  await page.getByTestId('website-share').click();
  await expect(page.getByTestId('website-share-url')).toContainText(PUBLIC_URL);
  // Offline, the address still opens the team's sign-in; signed in here, it opens the app.
  await expect(page.getByTestId('website-share-not-live')).toBeVisible();
  await expect(page.getByTestId('website-share-signed-in')).toBeVisible();
  const qr = page.getByTestId('website-share-qr');
  await expect(qr).toBeVisible();
  await expect.poll(() => qr.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await page.getByTestId('website-share-copy').click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(PUBLIC_URL);
  for (const [button, name] of [
    ['website-share-png', 'website-qr-a.png'],
    ['website-share-svg', 'website-qr-a.svg'],
  ] as const) {
    const download = page.waitForEvent('download');
    await page.getByTestId(button).click();
    expect((await download).suggestedFilename()).toBe(name);
  }
  await threeShots(page, 'F09', () => page.getByTestId('website-share-qr'));
  await page.getByTestId('website-share-close').click();
  await expect(page.getByTestId('website-share-qr')).toBeHidden();
});

// flow: WEBSITE-F10
test('WEBSITE-F10: a visitor opens the address and gets the page in any design, without cookies, in her language', async ({
  browser,
}) => {
  test.setTimeout(300_000);
  const { page } = owner;
  for (const template of TEMPLATES) {
    await reset(page, baseline(template));
    await publishApi();
    for (const vp of VIEWPORTS) {
      const { context, page: visiting } = await visitor(browser, { width: vp.width, height: vp.height });
      const response = await visiting.goto(`${A}/`);
      expect(response?.status(), `${template} at ${vp.label}`).toBe(200);
      const headers = response?.headers() ?? {};
      expect(headers['set-cookie'], 'the public page sets no cookie').toBeUndefined();
      expect(headers['cache-control']).toBe('public, max-age=60');
      expect(headers.vary).toMatch(/Accept-Language/);
      expect(headers.vary).toMatch(/Cookie/);
      // Its own policy: our bundle only, no nonce (the page is cached and shared), framed by nobody.
      const csp = headers['content-security-policy'] ?? '';
      expect(csp).toMatch(/script-src 'self'(;| [^;]*localhost)/);
      expect(csp).toContain("frame-ancestors 'none'");
      expect(csp).not.toContain('nonce-');
      expect(csp).not.toContain('strict-dynamic');
      await expect(visiting.locator('body')).toHaveClass(new RegExp(`ws-${template}`));
      await expect(visiting.getByRole('heading', { level: 1 })).toHaveText(new RegExp(HERO, 'i'));
      await expect(visiting.locator('header a[href="/auth/login"]')).toHaveText('Log in');
      await expect(visiting.locator('[data-ep-section="contact"]')).toContainText(PHONE);
      await expect(visiting.locator('[data-ep-section="location"]')).toContainText('Gran Vía 1');
      await expect(visiting.locator('header .navbar')).toHaveCSS('display', 'flex');
      expect(await visiting.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
      expect(await context.cookies(), 'nothing was left in the browser').toEqual([]);
      await settled(visiting);
      await visiting.screenshot({ path: shot(`APP-WEBSITE-F10-${template}-${vp.label}`), fullPage: true });
      if (template === 'classic') await visiting.screenshot({ path: shot(`APP-WEBSITE-F10-${vp.label}`) });
      await context.close();
    }
  }
  // The chrome speaks the visitor's browser's language; what the owner wrote stays as written.
  const { context: spanish, page: es } = await visitor(browser, WIDE, 'es-ES');
  await es.goto(`${A}/`);
  await expect(es.locator('html')).toHaveAttribute('lang', 'es');
  await expect(es.locator('header a[href="/auth/login"]')).toHaveText('Entrar');
  await expect(es.locator('[data-ep-section="contact"]')).toContainText('Lunes');
  await expect(es.locator('[data-ep-section="contact"]')).toContainText('Cerrado');
  await expect(es.getByRole('heading', { level: 1 })).toHaveText(new RegExp(HERO, 'i'));
  await spanish.close();

  // «Log in» takes the visitor to ERPlora's sign-in and, signed in, back to the app; with a session `/` is the app.
  const { context: guest, page: entering } = await visitor(browser);
  await entering.goto(`${A}/`);
  await entering.locator('header a[href="/auth/login"]').click();
  await entering.waitForURL((url) => url.origin === SAAS, { timeout: 30_000 });
  const form = entering.getByTestId('login-form');
  await form.getByTestId('login-email').locator('input').fill(OWNER.email);
  await form.getByTestId('login-password').locator('input').fill(OWNER.password);
  const since = Date.now() - 2_000;
  await form.getByTestId('login-submit').click();
  const codeForm = entering.getByTestId('verify-email-form');
  const step = await Promise.race([
    codeForm.waitFor({ state: 'visible', timeout: 30_000 }).then(() => 'code' as const),
    entering.waitForURL((url) => url.origin === A, { timeout: 30_000 }).then(() => 'back' as const),
  ]);
  if (step === 'code') {
    const code = await readMailCode({ dir: MAIL_DIR, to: OWNER.email, since, timeout: 30_000 });
    const inputs = codeForm.locator('input:not([type=hidden])');
    if ((await inputs.count()) >= code.length) {
      for (const [index, digit] of [...code].entries()) await inputs.nth(index).fill(digit);
    } else {
      await inputs.first().fill(code);
    }
    await codeForm.getByTestId('verify-email-submit').click();
  }
  await entering.waitForURL(`${A}/`, { timeout: 30_000 });
  await topbarApps(entering).waitFor({ state: 'attached', timeout: 30_000 });
  await expect(entering.locator('body[class*="ws-"]')).toHaveCount(0);
  await entering.goto(`${A}/`);
  await topbarApps(entering).waitFor({ state: 'attached', timeout: 30_000 });
  await guest.close();
});

// flow: WEBSITE-F11
test('WEBSITE-F11: the gallery takes photos one by one, in the order the owner sets, and the page shows that grid', async ({
  browser,
}) => {
  test.setTimeout(240_000);
  const { page } = owner;
  await reset(page);
  await openSection(page, 'gallery');
  await expect(page.getByTestId('website-gallery-empty')).toBeVisible();
  for (const [index, [label, hue]] of ([
    ['One', 10],
    ['Two', 140],
    ['Three', 260],
  ] as const).entries()) {
    await page.getByTestId('website-gallery-add-file').setInputFiles({
      name: `work-${index + 1}.jpg`,
      mimeType: 'image/jpeg',
      buffer: await photo(page, label, hue),
    });
    await expect(page.getByTestId(`website-gallery-photo-${index}-image`)).toBeVisible({ timeout: 15_000 });
  }
  await expect(page.getByTestId('website-gallery-count')).toHaveText('3 of 12 photos');
  const src = (index: number) => page.getByTestId(`website-gallery-photo-${index}-image`).getAttribute('src');
  const [one, two, three] = [await src(0), await src(1), await src(2)];
  // «Three» up one place, then «One» out: «Three», «Two».
  await page.getByTestId('website-gallery-photo-2-up').click();
  expect([await src(0), await src(1), await src(2)]).toEqual([one, three, two]);
  await page.getByTestId('website-gallery-photo-0-remove').click();
  await expect(page.getByTestId('website-gallery-count')).toHaveText('2 of 12 photos');
  expect([await src(0), await src(1)]).toEqual([three, two]);
  await save(page);
  const images = (await getSite()).content.gallery.images as { url: string }[];
  expect(images.map((image) => image.url)).toEqual([three, two]);
  await threeShots(page, 'F11', () => page.getByTestId('website-gallery-count'), () => showView(page, 'Edit'));
  await publishApi();
  const { context, page: visiting } = await visitor(browser, { width: 834, height: 1112 });
  await visiting.goto(`${A}/`);
  const grid = visiting.locator('[data-ep-section="gallery"] .row-cols-2');
  await expect(grid).toHaveClass(/\brow-cols-md-3\b.*\brow-cols-lg-4\b/);
  const photos = grid.locator('img');
  expect(await photos.evaluateAll((all) => all.map((image) => image.getAttribute('src')))).toEqual([three, two]);
  for (let index = 0; index < 2; index++) {
    await photos.nth(index).scrollIntoViewIfNeeded();
    await expect.poll(() => photos.nth(index).evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  }
  // Each one opens whole in another tab.
  await expect(grid.locator('a').first()).toHaveAttribute('target', '_blank');
  await expect(visiting.locator('header a[href="#gallery"]')).toHaveCount(1);
  await context.close();
});

// flow: WEBSITE-F12
test('WEBSITE-F12: the business’s Google Maps link is checked, and its rating and reviews show on the page', async ({ browser }) => {
  const { page } = owner;
  await reset(page);
  await openSection(page, 'reviews');
  const status = page.getByTestId('website-reviews-status');
  await expect(status).toHaveAttribute('data-state', 'empty');
  await field(page, 'website-field-reviews-place_ref').fill('Peluquería Manoli');
  await page.getByTestId('website-save').click();
  await expect(page.getByTestId('website-field-reviews-place_ref')).toContainText(
    'Paste the link of your business on Google Maps, or its Place ID.',
  );
  await field(page, 'website-field-reviews-place_ref').fill(PLACE_ID);
  await save(page);
  // This server has no key of Google's: the link is kept and the note says the reviews are not available yet.
  await expect(status).toHaveAttribute('data-state', 'unavailable');
  // Google's last good answer for that place, as the Hub keeps it in the site's row (the cache was never filled).
  const answer = {
    place_id: PLACE_ID,
    place_ref: PLACE_ID,
    name: "Pepe's Bakery",
    rating: 4.7,
    count: 128,
    maps_uri: `https://maps.google.com/?cid=1&place=${PLACE_ID}`,
    fetched_at: new Date().toISOString(),
    reviews: [
      {
        author: 'Lucía Romero',
        author_uri: 'https://www.google.com/maps/contrib/1',
        rating: 5,
        text: 'The best croissants in Madrid.',
        time: new Date(Date.now() - 40 * 86_400_000).toISOString(),
        uri: 'https://www.google.com/maps/reviews/1',
      },
    ],
  };
  // In base64: `psql()` hands the SQL to a shell inside double quotes, where the JSON's own quotes would end it.
  const encoded = Buffer.from(JSON.stringify(answer), 'utf8').toString('base64');
  psql(`update website_site set reviews_snapshot = convert_from(decode('${encoded}', 'base64'), 'UTF8')::jsonb where ${SITE_ROW}`);
  await page.reload();
  await openSection(page, 'reviews');
  await expect(status).toHaveAttribute('data-state', 'ready');
  await expect(status).toContainText('Rating 4.7 out of 5 · reviews on Google: 128');
  await threeShots(page, 'F12', () => page.getByTestId('website-reviews-status'), () => showView(page, 'Edit'));
  await publishApi();
  const { context, page: visiting } = await visitor(browser, { width: 390, height: 844 });
  const google: string[] = [];
  visiting.on('request', (request) => {
    if (/google(apis)?\.com/.test(new URL(request.url()).hostname)) google.push(request.url());
  });
  await visiting.goto(`${A}/`);
  const section = visiting.locator('[data-ep-section="reviews"]');
  await expect(section).toContainText('4.7');
  await expect(section).toContainText('128 reviews on Google');
  await expect(section).toContainText('Lucía Romero');
  await expect(section).toContainText('The best croissants in Madrid.');
  await expect(section.getByRole('link', { name: /Write a review/ })).toHaveAttribute(
    'href',
    `https://search.google.com/local/writereview?placeid=${PLACE_ID}`,
  );
  await expect(visiting.locator('header a[href="#reviews"]')).toHaveCount(1);
  await section.scrollIntoViewIfNeeded();
  await settled(visiting);
  await visiting.screenshot({ path: shot('APP-WEBSITE-F12-page-390') });
  expect(google, 'the visitor’s browser never talks to Google').toEqual([]);
  await context.close();
});
