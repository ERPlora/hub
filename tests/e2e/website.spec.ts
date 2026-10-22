// The website module end to end (apps/website, rounds 2026-10-21 and 2026-10-22, PLAN §29): the owner fills the
// editor at /website (hero, contact, «About us» typed key by key and then hidden, the footer's line, the «Forest»
// palette, «Auto» and the «Modern» design) and publishes; a visitor without a session opens `/` and gets the public
// page with «Log in», the footer's line and without the hidden section, laid out for a phone, a tablet and a computer
// with nothing scrolling sideways and the top bar's menu folding on the phone; «Log in» takes her to the SaaS's sign-in; «Auto» follows the device's light or
// dark. Then each of the four designs is published in turn and captured at 390, 820 and 1440 px, light and dark
// (`.artifacts/WEBSITE-<design>-<width>-<mode>.png`), with the editor's own captures. At the end the site is taken
// offline again (`website.site.unpublish`): the other specs on hub `a` expect its `/` to jump to the login.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, HUB_DIR, hostPage, SAAS, shot } from './helpers';

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

interface ModeColours {
  primary: string;
  bg: string;
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

/** The page at rest for its capture: no focus ring, no colour still in transition (Bootstrap's buttons fade 150 ms,
 * and the dev server injects the stylesheets after the first paint). */
async function settled(page: Page): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
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
  // Bootstrap's own stylesheet reached the page (the bundle, under the public CSP).
  await expect(page.locator('header .navbar')).toHaveCSS('display', 'flex');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
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
    await settled(page);
    await page.screenshot({ path: shot(`WEBSITE-${template}-${width}-${mode}-menu`), fullPage: false });
    await toggler.click();
    await expect(page.locator('#ws-nav')).toBeHidden();
  } else {
    await expect(page.locator('.navbar-toggler')).toBeHidden();
    await expect(page.locator('#ws-nav a[href="#contact"]')).toBeVisible();
  }
  // The buttons take the palette: on bold's dark bar the dark set, elsewhere the page's own.
  const bar = template === 'bold' ? FOREST.dark : FOREST[mode];
  const login = page.locator('header a[href="/auth/login"]');
  if (template !== 'minimal' && template !== 'classic') {
    await expect(login).toHaveCSS('background-color', rgb(bar.primary));
    await expect(login).toHaveCSS('color', bar === FOREST.light ? 'rgb(255, 255, 255)' : 'rgb(0, 0, 0)');
  }
  await settled(page);
  await page.screenshot({ path: shot(`WEBSITE-${template}-${width}-${mode}`), fullPage: true });
  await context.close();
}

test('the owner publishes the website and a visitor sees it on the hub’s address, in any design and mode', async ({ browser }) => {
  test.setTimeout(480_000);
  const { context, page } = await hostPage(browser, A, { next: '/website', viewport: WIDTHS[1440] });
  try {
    await expect(page.getByTestId('website-editor')).toBeVisible();

    // The editor: hero, contact, the «Forest» palette, «Auto» and the «Modern» design.
    await field(page, 'website-field-topbar-name').fill("Pepe's Bistro");
    await field(page, 'website-field-hero-title').fill(HERO);
    await field(page, 'website-field-hero-tagline').fill(TAGLINE);

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

    await openSection(page, 'contact');
    await setToggle(page, 'website-show-contact', true);
    await field(page, 'website-field-contact-phone').fill(PHONE);
    await field(page, 'website-field-contact-email').fill(EMAIL);
    await openSection(page, 'footer');
    await field(page, 'website-field-footer-text').fill(FOOTER);
    await page.getByTestId('website-palette-forest').click();
    await expect(page.getByTestId('website-palette-forest')).toHaveAttribute('aria-checked', 'true');
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
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `the editor does not scroll sideways at ${width} px`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`WEBSITE-editor-${width}`) });
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
