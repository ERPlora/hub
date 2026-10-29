// flow: WEBSITE-F02, WEBSITE-F10 — the four designs, light and dark, at three widths (one test per flow: website-flows.spec.ts)
// The website module end to end (apps/website, rounds 2026-10-21 and 2026-10-22, PLAN §29): the owner fills the
// editor at /website (hero with a cover photo, contact, «About us» typed key by key and then hidden, the footer's
// line, the «Forest» palette, «Auto» and the «Modern» design) and publishes; a visitor without a session opens `/`
// and gets the public page with the cover, «Log in», the footer's line, ERPlora's credit and without the hidden section, laid out for a
// phone, a tablet and a computer with nothing scrolling sideways and the top bar's menu folding on the phone; «Log in» takes her to the SaaS's sign-in; «Auto» follows the device's light or
// dark. Then each of the four designs is published in turn and captured at 390, 820 and 1440 px, light and dark
// (`.artifacts/WEBSITE-<design>-<width>-<mode>.png`), with the editor's own captures. At the end the site is taken
// offline again (`website.site.unpublish`): the other specs on hub `a` expect its `/` to jump to the login.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, HUB_DIR, hostPage, SAAS, settled } from './helpers';
import { atRest } from './website-helpers';

const WIDTHS = {
  390: { width: 390, height: 844 },
  820: { width: 820, height: 1180 },
  1440: { width: 1440, height: 900 },
} as const;
/** The designs, the one the editor publishes first («Modern») first. */
const TEMPLATES = ['modern', 'classic', 'minimal', 'bold'] as const;
const HERO = 'Fresh food every day';
const TAGLINE = 'Since 1998 in Gran Vía';
const PHONE = '+34 600 123 456';
const EMAIL = 'hola@pepe.es';
/** The footer's line, as an owner writes it (the demo once showed a lone «h»: it was the text typed there). */
const FOOTER = "Pepe's Bistro S.L. · Gran Vía 1, Madrid";
/** A business's page on Google Maps, as the address bar shows it. */
const PLACE_LINK = 'https://www.google.com/maps/place/Puerta+del+Sol/@40.4169473,-3.7035285,17z/';
/** The gallery's photos, each drawn with its own mark (two different files). */
const GALLERY = ['Lunch', 'Dinner'] as const;
/** Their addresses on the Hub, in the order the editor kept them (filled once they are uploaded). */
let galleryUrls: string[] = [];

interface ModeColours {
  primary: string;
  bg: string;
  link: string;
}
const PALETTES = JSON.parse(readFileSync(join(HUB_DIR, 'apps', 'website', 'palettes.json'), 'utf8')) as Record<
  string,
  { accent: string; light: ModeColours; dark: ModeColours }
>;
const FOREST = PALETTES.forest;

/** `#1f6b45` as the browser computes it: `rgb(31, 107, 69)`. */
function rgb(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((at) => Number.parseInt(hex.slice(at, at + 2), 16));
  return `rgb(${r}, ${g}, ${b})`;
}

test.describe.configure({ mode: 'serial' });

interface Rows<T> {
  rows: T[];
}

/** The catalog the page lists: a few services of Services in two categories, through its API, created once (the
 * stack keeps its rows between runs). */
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

/** The catalog section on, from Services, with its own heading and every category, an empty gallery and no place on
 * Google Maps (whatever a run before left). */
async function showServices(context: BrowserContext): Promise<void> {
  const site = await api<{ template: string; theme: unknown; content: Record<string, unknown> }>(context, A, 'GET', '/website/site');
  expect(site.status).toBe(200);
  const { template, theme, content } = site.data;
  const catalog = { hidden: false, title: '', source: 'service', category_ids: [], show_prices: true };
  const gallery = { hidden: false, title: '', images: [] };
  const reviews = { hidden: false, title: '', place_ref: '' };
  const saved = await api(context, A, 'POST', '/website/site', {
    template,
    theme,
    content: { ...content, catalog, gallery, reviews },
  });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
}

/** A photo for the header, drawn in the page (no binary in the repository): a warm gradient with soft lights and the
 * business's name as a small mark in a corner (never under the page's own title), as a JPEG. */
async function samplePhoto(page: Page, width: number, height: number, label: string): Promise<Buffer> {
  const url = await page.evaluate(
    ({ width, height, label }) => {
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const draw = canvas.getContext('2d') as CanvasRenderingContext2D;
      const gradient = draw.createLinearGradient(0, 0, width, height);
      gradient.addColorStop(0, '#f2c38b');
      gradient.addColorStop(0.55, '#b5532f');
      gradient.addColorStop(1, '#2f5f63');
      draw.fillStyle = gradient;
      draw.fillRect(0, 0, width, height);
      for (const [x, y, r, alpha] of [
        [0.2, 0.3, 0.35, 0.18],
        [0.8, 0.7, 0.45, 0.14],
        [0.6, 0.2, 0.2, 0.12],
      ]) {
        draw.fillStyle = `rgba(255, 255, 255, ${alpha})`;
        draw.beginPath();
        draw.arc(x * width, y * height, r * height, 0, Math.PI * 2);
        draw.fill();
      }
      draw.fillStyle = 'rgba(255, 255, 255, 0.85)';
      draw.font = `600 ${Math.round(height / 26)}px Georgia, serif`;
      draw.textAlign = 'right';
      draw.textBaseline = 'bottom';
      draw.fillText(label, width - height / 20, height - height / 20);
      return canvas.toDataURL('image/jpeg', 0.86);
    },
    { width, height, label },
  );
  return Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');
}

const field = (page: Page, testid: string) => page.getByTestId(testid).locator('input, textarea').first();

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

/** How far the editor's content is scrolled. */
async function scrolled(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const content = document.querySelector('ion-content') as HTMLElement & { getScrollElement(): Promise<HTMLElement> };
    return (await content.getScrollElement()).scrollTop;
  });
}

/** Saves what is unsaved (the autosave may have done it already: then «Save» is off) and waits for the server. */
async function save(page: Page): Promise<void> {
  const state = page.getByTestId('website-save-state');
  if ((await state.textContent())?.includes('Unsaved')) await page.getByTestId('website-save').click();
  await expect(state).toHaveText(/All changes saved/, { timeout: 15_000 });
}

async function publish(page: Page): Promise<void> {
  await page.getByTestId('website-publish').click();
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: 'Publish your website?' });
  await dialog.locator('.ep-form-modal__submit').click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId('website-status-live')).toBeVisible({ timeout: 15_000 });
}

/** A visitor: a fresh context without a session, as a phone, a tablet or a computer, in light or dark. */
async function visitor(
  browser: Browser,
  width: keyof typeof WIDTHS,
  colorScheme: 'light' | 'dark' = 'light',
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport: WIDTHS[width], locale: 'en-GB', colorScheme });
  return { context, page: await context.newPage() };
}

/** Opens `/` as a visitor: the public page in `template`, nothing scrolling sideways, the menu folding on a phone. */
async function visit(browser: Browser, template: string, width: keyof typeof WIDTHS, mode: 'light' | 'dark'): Promise<void> {
  const { context, page } = await visitor(browser, width, mode);
  const response = await page.goto(`${A}/`);
  expect(response?.status(), `/ at ${width}`).toBe(200);
  expect(await response?.headerValue('set-cookie'), 'the public page sets no cookie').toBeNull();
  await expect(page.locator('body')).toHaveClass(new RegExp(`ws-${template}`));
  // «Auto»: the device's light or dark, set by the public bundle; the palette's page colour with it.
  await expect(page.locator('html')).toHaveAttribute('data-ep-mode', 'auto');
  await expect(page.locator('html')).toHaveAttribute('data-bs-theme', mode);
  await expect(page.locator('body')).toHaveCSS('background-color', rgb(FOREST[mode].bg));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(new RegExp(HERO, 'i'));
  await expect(page.getByText(TAGLINE)).toBeVisible();
  await expect(page.locator('[data-ep-section="about"]')).toHaveCount(0);
  await expect(page.locator('[data-ep-section="contact"]')).toContainText(PHONE);
  await expect(page.locator('header a[href="/auth/login"]')).toHaveText('Log in');
  await expect(page.locator('footer a[href="/auth/login"]')).toHaveText('Log in');
  await expect(page.locator('footer [data-ep-footer-text]')).toHaveText(FOOTER);
  // The copyright line is ERPlora's credit, the same on every hub's site and linked to erplora.com, never the business.
  const credit = page.locator('footer [data-ep-credit]');
  await expect(credit).toHaveText(/^© \d{4} ERPlora$/);
  await expect(credit.getByRole('link', { name: 'ERPlora' })).toHaveAttribute('href', 'https://erplora.com');
  // The catalog: Services' offer as cards, priced, with a pill per category, refreshed live by the public bundle.
  const catalog = page.locator('[data-ep-block="catalog"]');
  for (const name of ['Lunch menu', 'Tasting menu', 'Private dining room', 'Cooking class']) {
    await expect(catalog.locator('.card-title').filter({ hasText: name })).toHaveCount(1);
  }
  await expect(catalog.locator('.nav-pills .nav-link')).toHaveCount(2);
  await expect(catalog.locator('.nav-pills')).toContainText('Menus');
  await expect(catalog.locator('.nav-pills')).toContainText('Events');
  await expect(catalog.locator('.badge').first()).toHaveText(/€/);
  // The cover fills the header (under its veil in classic and bold, framed beside the title in modern, wide under it
  // in minimal), and it loads.
  const cover = page.locator('[data-ep-section="hero"] img');
  await expect(cover).toBeVisible();
  await expect(cover).toHaveCSS('object-fit', 'cover');
  await expect.poll(() => cover.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  // No place on Google Maps: no reviews section, nor its link in the menu.
  await expect(page.locator('[data-ep-section="reviews"]')).toHaveCount(0);
  await expect(page.locator('a[href="#reviews"]')).toHaveCount(0);
  // The gallery: the two photos in a grid of squares, in the owner's order, served by the Hub, and they load.
  const grid = page.locator('[data-ep-section="gallery"] .row-cols-2');
  await expect(grid).toHaveCount(1);
  await expect(grid).toHaveClass(/\brow-cols-md-3\b.*\brow-cols-lg-4\b/);
  const photos = grid.locator('img');
  await expect(photos).toHaveCount(GALLERY.length);
  expect(await photos.evaluateAll((images) => images.map((image) => image.getAttribute('src')))).toEqual(galleryUrls);
  for (let index = 0; index < GALLERY.length; index++) {
    const photo = photos.nth(index);
    await expect(photo).toHaveAttribute('src', /^\/p\/media\//);
    await expect(photo).toHaveCSS('object-fit', 'cover');
    await photo.scrollIntoViewIfNeeded();
    await expect.poll(() => photo.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  }
  // Bootstrap's own stylesheet reached the page (the bundle, under the public CSP).
  await expect(page.locator('header .navbar')).toHaveCSS('display', 'flex');
  const overflow = await horizontalOverflow(page);
  expect(overflow, `nothing scrolls sideways at ${width} px`).toBeLessThanOrEqual(0);
  if (width === 390) {
    // On a phone the sections fold into the top bar's menu, and «Log in» stays on the bar.
    const toggler = page.locator('.navbar-toggler');
    await expect(toggler).toBeVisible();
    await expect(page.locator('#ws-nav')).toBeHidden();
    await toggler.click();
    // Bootstrap ignores a toggle while the menu slides: wait until it is open (`show`, no longer `collapsing`).
    await expect(page.locator('#ws-nav')).toHaveClass(/\bshow\b/);
    await expect(toggler).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('#ws-nav a[href="#contact"]')).toBeVisible();
    await expect(page.locator('header a[href="/auth/login"]')).toBeVisible();
    await atRest(page);
    await capture(page, `WEBSITE-${template}-${width}-${mode}-menu`);
    await toggler.click();
    await expect(page.locator('#ws-nav')).toBeHidden();
  } else {
    await expect(page.locator('.navbar-toggler')).toBeHidden();
    await expect(page.locator('#ws-nav a[href="#contact"]')).toBeVisible();
  }
  // «Log in» is an outline pill in the palette's link colour: on bold's dark bar the dark set, elsewhere the page's.
  const bar = template === 'bold' ? FOREST.dark : FOREST[mode];
  const login = page.locator('header a[href="/auth/login"]');
  await expect(login).toHaveCSS('color', rgb(bar.link));
  await expect(login).toHaveCSS('border-top-color', rgb(bar.link));
  await atRest(page);
  await capture(page, `WEBSITE-${template}-${width}-${mode}`, { fullPage: true });
  await context.close();
}

test('the owner publishes the website and a visitor sees it on the hub’s address, in any design and mode', async ({ browser }) => {
  test.setTimeout(480_000);
  const { context, page } = await hostPage(browser, A, { next: '/website', viewport: WIDTHS[1440] });
  try {
    await seedServices(context);
    await showServices(context);
    await page.reload();
    await expect(page.getByTestId('website-editor')).toBeVisible();

    // The editor: hero, contact, the «Forest» palette, «Auto» and the «Modern» design.
    await field(page, 'website-field-topbar-name').fill("Pepe's Bistro");
    await field(page, 'website-field-hero-title').fill(HERO);
    await field(page, 'website-field-hero-tagline').fill(TAGLINE);
    // The cover, through the editor's own upload.
    await page.getByTestId('website-image-cover-file').setInputFiles({
      name: 'cover.jpg',
      mimeType: 'image/jpeg',
      buffer: await samplePhoto(page, 1600, 900, "Pepe's Bistro"),
    });
    await expect(page.getByTestId('website-image-cover-image')).toBeVisible({ timeout: 15_000 });
    // The gallery (2026-10-22, for a hair salon's work): two photos through its own uploads, kept in their order.
    await openSection(page, 'gallery');
    for (const [index, label] of GALLERY.entries()) {
      await page.getByTestId('website-gallery-add-file').setInputFiles({
        name: `work-${index + 1}.jpg`,
        mimeType: 'image/jpeg',
        buffer: await samplePhoto(page, 900, 900, label),
      });
      await expect(page.getByTestId(`website-gallery-photo-${index}-image`)).toBeVisible({ timeout: 15_000 });
    }
    await expect(page.getByTestId('website-gallery-count')).toHaveText(/2 of 12 photos/);
    galleryUrls = await Promise.all(
      GALLERY.map(async (_label, index) => (await page.getByTestId(`website-gallery-photo-${index}-image`).getAttribute('src')) ?? ''),
    );

    // Regression (Ioan, 2026-10-22): typing key by key in a section opened by hand keeps the section open, the
    // cursor in the field and every letter, also across the autosave and its result coming back live.
    await openSection(page, 'about');
    await setToggle(page, 'website-show-about', true);
    const title = field(page, 'website-field-about-title');
    await title.fill('');
    await title.click();
    const before = await scrolled(page);
    await title.pressSequentially('We cook', { delay: 80 });
    await page.waitForTimeout(2_600);
    await title.pressSequentially(' at home', { delay: 80 });
    await expect(title).toBeFocused();
    await expect(title).toHaveValue('We cook at home');
    await expect(page.getByTestId('website-section-about')).toHaveClass(/accordion-expanded/);
    expect(Math.abs((await scrolled(page)) - before), 'the editor did not jump').toBeLessThanOrEqual(2);
    await setToggle(page, 'website-show-about', false);

    // Google reviews (2026-10-22): the business's link on Google Maps, checked by the server; this stack has no key of
    // Google's, so it says the reviews are not available yet and the page shows no section (asserted in `visit`).
    await openSection(page, 'reviews');
    const status = page.getByTestId('website-reviews-status');
    await expect(status).toHaveAttribute('data-state', 'empty');
    await field(page, 'website-field-reviews-place_ref').fill('Peluquería Manoli');
    await expect(status).toHaveAttribute('data-state', 'changed');
    await page.getByTestId('website-save').click();
    await expect(page.getByTestId('website-field-reviews-place_ref')).toHaveClass(/ion-invalid/);
    await expect(page.getByTestId('website-field-reviews-place_ref')).toContainText(
      'Paste the link of your business on Google Maps, or its Place ID.',
    );
    await field(page, 'website-field-reviews-place_ref').fill(PLACE_LINK);
    await save(page);
    await expect(status).toHaveAttribute('data-state', 'unavailable');
    await expect(status).toContainText('Google reviews are not available yet');
    await field(page, 'website-field-reviews-place_ref').fill('');
    await save(page);
    await expect(status).toHaveAttribute('data-state', 'empty');

    await openSection(page, 'contact');
    await setToggle(page, 'website-show-contact', true);
    await field(page, 'website-field-contact-phone').fill(PHONE);
    await field(page, 'website-field-contact-email').fill(EMAIL);
    await openSection(page, 'footer');
    await field(page, 'website-field-footer-text').fill(FOOTER);
    await page.getByTestId('website-palette-forest').click();
    await expect(page.getByTestId('website-palette-forest')).toHaveAttribute('aria-checked', 'true');
    // The palette's own two colours are on show, ready to change; nothing to reset.
    await expect(field(page, 'website-colour-primary')).toHaveValue(FOREST.light.primary);
    await expect(page.getByTestId('website-colours-reset')).toHaveCount(0);
    // (Vue sets an ion-segment-button's `value` as a property: no `[value=…]` selector matches it.)
    await page.getByTestId('website-mode').locator('ion-segment-button').filter({ hasText: 'Auto' }).click();
    await expect(page.getByTestId('website-mode-auto-hint')).toBeVisible();
    await page.getByTestId('website-template-modern').click();
    await save(page);
    const preview = page.frameLocator('[data-testid="website-preview-frame"]');
    await expect(page.getByTestId('website-preview-frame')).toBeVisible();
    await expect(preview.locator('body.ws-modern')).toBeVisible();
    await expect(preview.getByRole('heading', { level: 1 })).toHaveText(HERO);
    // The preview honours «Auto» too: the device turns dark, the frame follows.
    await page.emulateMedia({ colorScheme: 'dark' });
    await expect(preview.locator('html')).toHaveAttribute('data-bs-theme', 'dark');
    await page.emulateMedia({ colorScheme: 'light' });
    await expect(preview.locator('html')).toHaveAttribute('data-bs-theme', 'light');
    for (const width of [1440, 820, 390] as const) {
      await page.setViewportSize(WIDTHS[width]);
      await expect(page.getByTestId('website-editor')).toBeVisible();
      const overflow = await horizontalOverflow(page);
      expect(overflow, `the editor does not scroll sideways at ${width} px`).toBeLessThanOrEqual(0);
      await settled(page);
      await capture(page, `WEBSITE-editor-${width}`);
    }
    await page.setViewportSize(WIDTHS[1440]);

    await publish(page);

    // «Log in» takes the visitor to the SaaS's sign-in, which brings her back to the hub.
    const { context: guest, page: visiting } = await visitor(browser, 390);
    await visiting.goto(`${A}/`);
    // A page left open follows the device when it turns dark, and back.
    await expect(visiting.locator('html')).toHaveAttribute('data-bs-theme', 'light');
    await visiting.emulateMedia({ colorScheme: 'dark' });
    await expect(visiting.locator('html')).toHaveAttribute('data-bs-theme', 'dark');
    await visiting.emulateMedia({ colorScheme: 'light' });
    await expect(visiting.locator('html')).toHaveAttribute('data-bs-theme', 'light');
    await visiting.locator('header a[href="/auth/login"]').click();
    await visiting.waitForURL((url) => url.origin === SAAS, { timeout: 30_000 });
    expect(new URL(visiting.url()).origin).toBe(SAAS);
    await guest.close();

    // Each design in turn, the same texts and palette: published and seen at every width, light and dark.
    for (const template of TEMPLATES) {
      if (template !== 'modern') {
        await page.getByTestId(`website-template-${template}`).click();
        await save(page);
        await publish(page);
      }
      for (const width of [390, 820, 1440] as const) {
        for (const mode of ['light', 'dark'] as const) await visit(browser, template, width, mode);
      }
    }
  } finally {
    const offline = await api<{ is_live: boolean }>(context, A, 'POST', '/website/site/unpublish');
    expect(offline.status).toBe(200);
    expect(offline.data.is_live).toBe(false);
    await context.close();
  }
  // Offline again: `/` jumps to the login, as for every other spec.
  const { context: after, page: back } = await visitor(browser, 1440);
  await back.goto(`${A}/`);
  await back.waitForURL((url) => url.origin === SAAS, { timeout: 30_000 });
  await after.close();
});
