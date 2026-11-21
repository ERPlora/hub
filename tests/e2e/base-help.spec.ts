import { mkdirSync, rmSync, writeFileSync } from 'node:fs';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, settled, signedInSpanish, turnOffTurnedOn, turnOnMissing } from './helpers';

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
] as const;
const SHOTS = '/tmp/help-window-shots';
const FIX_SHOTS = '/tmp/help-fix-shots';

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];
const googleRequests: string[] = [];
const consoleErrors: string[] = [];
const pageErrors: string[] = [];
const assistantTurns: string[] = [];

const modal = () => page.locator('ion-modal[data-testid="help-window"]').last();
const content = () => page.locator('[data-testid="help-content"]');
const search = () => page.getByTestId('help-flow-search');

async function snap(name: string): Promise<void> {
  const png = await capture(page, name);
  writeFileSync(`${SHOTS}/${name}.png`, png);
}

async function snapHeader(name: string): Promise<void> {
  const header = page.locator('ion-header.app-topbar').last();
  await expect(header).toBeVisible();
  const clip = (await header.boundingBox())!;
  const png = await capture(page, name, { clip });
  writeFileSync(`${FIX_SHOTS}/${name}.png`, png);
}

async function theme(dark: boolean): Promise<void> {
  await page.evaluate((enabled) => document.documentElement.classList.toggle('ion-palette-dark', enabled), dark);
  await settled(page);
}

async function openHelp(): Promise<void> {
  await page.getByTestId('help-button').click();
  await expect(content()).toBeVisible();
  await expect(modal()).toHaveAttribute('data-size', 'lg');
  await expect(page.locator('[data-testid="help-loading"]')).toHaveCount(0);
  await settled(page);
}

async function closeHelp(): Promise<void> {
  await page.getByTestId('help-close').click();
  await expect(modal()).toBeHidden();
}

async function askAssistant(question: string): Promise<void> {
  await page.getByTestId('help-ask-assistant').click();
  await expect(modal()).toBeHidden();
  await expect(page.getByTestId('assistant-panel')).toHaveAttribute('data-open', 'true');
  await expect(page.getByTestId('assistant-input').locator('textarea')).toHaveValue(question);
}

async function checkSummaryLayout(): Promise<void> {
  const current = page.getByTestId('help-current-screen');
  const list = current.locator('ul').first();
  await expect(list).toBeVisible();
  const layout = await list.evaluate((element) => {
    const previous = element.previousElementSibling;
    const style = getComputedStyle(element);
    const body = element.closest('ion-modal')?.querySelector('.ep-form-modal__body');
    return {
      indent: Number.parseFloat(style.paddingInlineStart),
      marker: style.listStyleType,
      gap: previous ? element.getBoundingClientRect().top - previous.getBoundingClientRect().bottom : 0,
      overflow: body ? body.scrollWidth - body.clientWidth : 0,
    };
  });
  expect(layout.indent).toBeGreaterThanOrEqual(20);
  expect(layout.marker).toBe('disc');
  expect(layout.gap).toBeGreaterThanOrEqual(4);
  expect(layout.overflow).toBeLessThanOrEqual(0);
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
}

async function atTables(): Promise<void> {
  await page.goto(`${A}/table/floor-plan`);
  await expect(page.getByTestId('help-button')).toBeVisible();
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  rmSync(SHOTS, { recursive: true, force: true });
  mkdirSync(SHOTS, { recursive: true });
  rmSync(FIX_SHOTS, { recursive: true, force: true });
  mkdirSync(FIX_SHOTS, { recursive: true });
  ({ context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/table/floor-plan'));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.hostname.includes('youtube') || url.hostname.includes('ytimg') || url.hostname.includes('google')) {
      googleRequests.push(request.url());
    }
    if (url.pathname === '/api/assistant/turn') assistantTurns.push(request.url());
  });
  page.on('console', (message) => {
    if (message.type() === 'error' && message.location().url.startsWith(A)) consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await page.addInitScript(() => {
    const target = window as unknown as { helpCsp: string[] };
    target.helpCsp = [];
    document.addEventListener('securitypolicyviolation', (event) => {
      target.helpCsp.push(`${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  await turnOnMissing(context, A, ['table'], turnedOn);
  await atTables();
});

test.afterAll(async () => {
  if (context) {
    await turnOffTurnedOn(context, A, turnedOn);
    await context.close();
  }
});

test('Spanish whole summaries and every capture at three sizes in light and dark', async () => {
  await openHelp();
  await expect(page.getByTestId('help-current-screen')).toContainText('En esta pantalla · Plano de sala');
  await expect(page.getByTestId('help-current-screen')).toContainText('Estás aquí');
  await expect(page.getByTestId('help-current-screen')).toContainText('El color de cada mesa dice cómo está:');
  await expect(page.getByTestId('help-current-screen')).toContainText('Disponible');
  await expect(page.getByText('Ver más', { exact: true })).toHaveCount(0);
  await expect(page.locator('[data-help-section="video"]')).toHaveCount(0);
  await expect(content()).toHaveAttribute('lang', 'es');

  for (const size of SIZES) {
    for (const dark of [false, true]) {
      const mode = dark ? 'dark' : 'light';
      await closeHelp();
      await page.setViewportSize({ width: size.width, height: size.height });
      await theme(dark);
      await openHelp();
      await checkSummaryLayout();
      await snap(`help-window-${size.label}-${mode}-open`);

      await search().scrollIntoViewIfNeeded();
      const first = page.locator('.help-flow-header').first();
      await first.click();
      await expect(first).toHaveAttribute('aria-expanded', 'true');
      await snap(`help-window-${size.label}-${mode}-flow`);

      await search().locator('input').fill('comensales');
      await expect(page.locator('.help-flow-header').first()).toBeVisible();
      await snap(`help-window-${size.label}-${mode}-search-match`);

      await search().locator('input').fill('ninguna-tarea-dice-esto');
      await expect(page.getByTestId('help-flow-empty')).toContainText('Nada coincide con tu búsqueda');
      await snap(`help-window-${size.label}-${mode}-search-empty`);
    }
  }

  await closeHelp();
  await page.setViewportSize({ width: 390, height: 844 });
  for (const dark of [false, true]) {
    const mode = dark ? 'dark' : 'light';
    await theme(dark);
    await expect(page.getByTestId('help-button')).toBeVisible();
    await expect(page.getByTestId('action-bell')).toBeVisible();
    await expect(page.getByTestId('topbar-more')).toBeVisible();
    await expect(page.getByTestId('assistant-button')).toBeHidden();
    await expect(page.locator('ion-header.app-topbar ion-title').last()).toBeVisible();
    await snap(`help-phone-header-390-${mode}`);
  }

  await theme(false);
  await openHelp();
  const layout = await page.locator('.help-window__title-content').evaluate((element) => {
    const text = element.querySelector<HTMLElement>('.help-window__title-text')!;
    text.textContent = 'Ayuda · Un nombre de módulo de restaurante extremadamente largo';
    const iconBox = element.querySelector('.help-window__app-icon')!.getBoundingClientRect();
    const textBox = text.getBoundingClientRect();
    const titleBox = element.closest('ion-title')!.getBoundingClientRect();
    const style = getComputedStyle(text);
    return { iconRight: iconBox.right, textLeft: textBox.left, left: element.getBoundingClientRect().left, titleLeft: titleBox.left, width: text.clientWidth, scrollWidth: text.scrollWidth, whiteSpace: style.whiteSpace, overflow: style.textOverflow };
  });
  expect(layout.iconRight).toBeLessThanOrEqual(layout.textLeft);
  expect(layout.left - layout.titleLeft).toBeGreaterThanOrEqual(0);
  expect(layout.left - layout.titleLeft).toBeLessThanOrEqual(4);
  expect(layout.scrollWidth).toBeGreaterThan(layout.width);
  expect(layout.whiteSpace).toBe('nowrap');
  expect(layout.overflow).toBe('ellipsis');
  await closeHelp();

  await page.goto(`${A}/demo/items`);
  await expect(page.getByTestId('help-button')).toHaveCount(0);
});

test('a flow expands, search filters and clears, and the assistant receives only a draft', async () => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await atTables();
  await openHelp();
  const headers = page.locator('.help-flow-header');
  const total = await headers.count();
  expect(total).toBeGreaterThan(8);
  await expect(search()).toBeVisible();
  await search().locator('input').fill('comensales');
  await expect(headers).not.toHaveCount(total);
  await search().locator('input').fill('ninguna-tarea-dice-esto');
  await expect(page.getByTestId('help-flow-empty')).toContainText('Nada coincide con tu búsqueda');
  await page.getByTestId('help-flow-clear').click();
  await expect(headers).toHaveCount(total);

  const first = headers.first();
  const flowTitle = (await first.textContent())?.trim() ?? '';
  await first.click();
  await expect(first).toHaveAttribute('aria-expanded', 'true');
  const turnsBefore = assistantTurns.length;
  const question = `¿Cómo hago esto: ${flowTitle}?`;
  await askAssistant(question);
  expect(assistantTurns).toHaveLength(turnsBefore);
  await expect(page.getByTestId('assistant-thread')).not.toContainText(flowTitle);
  await page.getByTestId('assistant-close').click();

  await openHelp();
  await first.click();
  await expect(first).toHaveAttribute('aria-expanded', 'true');
  await askAssistant(question);
  expect(assistantTurns).toHaveLength(turnsBefore);
  await page.getByTestId('assistant-close').click();
});

test('the help and assistant icons share a colour in light and dark at desktop and phone sizes', async () => {
  await atTables();
  for (const width of [1440, 390]) {
    for (const dark of [false, true]) {
      const mode = dark ? 'dark' : 'light';
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await theme(dark);
      const assistant = page.getByTestId('assistant-button');
      if (width === 390) await page.getByTestId('topbar-more').click();
      await expect(assistant).toBeVisible();
      const helpColour = await page.getByTestId('help-button').locator('ion-icon').evaluate(
        (icon) => getComputedStyle(icon).color,
      );
      const assistantColour = await assistant.locator('ion-icon').evaluate((icon) => getComputedStyle(icon).color);
      expect(helpColour).toBe(assistantColour);
      if (width === 390) {
        await page.keyboard.press('Escape');
        await expect(page.getByTestId('topbar-more-menu')).toBeHidden();
      }
      await snapHeader(`header-${width}-${mode}`);
    }
  }
});

test('an aborted help request shows the error and retry loads the same window', async () => {
  await page.goto(`${A}/table/floor-plan`);
  await page.route('**/api/help?app=table', (route) => route.abort('failed'));
  await page.reload();
  await page.getByTestId('help-button').click();
  await expect(page.getByTestId('help-error')).toContainText('No se ha podido cargar la ayuda.');
  await page.unroute('**/api/help?app=table');
  await page.getByTestId('help-retry').click();
  await expect(content()).toBeVisible();
  await expect(page.getByTestId('help-error')).toHaveCount(0);
  await closeHelp();
});

test('a video stays local until its poster creates one sandboxed no-cookie frame', async () => {
  const videoId = 'dQw4w9WgXcQ';
  const embedUrl =
    `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0&playsinline=1&cc_load_policy=1&cc_lang_pref=es&hl=es`;
  await page.goto(`${A}/table/floor-plan`);
  await page.route('**/api/help?app=table', async (route) => {
    const response = await route.fetch();
    const answer = (await response.json()) as { video: string | null };
    await route.fulfill({ response, json: { ...answer, video: videoId } });
  });
  await page.route('https://www.youtube-nocookie.com/embed/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>Video</title>' }),
  );
  await page.reload();
  const before = googleRequests.length;
  await openHelp();
  const poster = page.locator('.youtube-embed__poster');
  await expect(poster).toBeVisible();
  expect(googleRequests).toHaveLength(before);

  await poster.click();
  const frame = page.locator('iframe.youtube-embed__player');
  await expect(frame).toHaveCount(1);
  await expect(frame).toHaveAttribute('src', embedUrl);
  await expect(frame).toHaveAttribute(
    'sandbox',
    'allow-scripts allow-same-origin allow-presentation allow-popups allow-popups-to-escape-sandbox',
  );
  await expect(frame).toHaveAttribute('allowfullscreen', '');
  await expect(frame).toHaveAttribute('allow', 'autoplay; encrypted-media; picture-in-picture; fullscreen');
  await expect(frame).toHaveAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
  expect(googleRequests.slice(before)).toEqual([embedUrl]);
  const csp = await page.evaluate(() => (window as unknown as { helpCsp?: string[] }).helpCsp ?? []);
  expect(csp).toEqual([]);
  await closeHelp();
  await page.unroute('**/api/help?app=table');
  await page.unroute('https://www.youtube-nocookie.com/embed/**');
});

test('with the browser offline a reopening after changing tab reads the cached text', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${A}/table/floor-plan`);
  await page.reload();
  await openHelp();
  await closeHelp();
  await page.getByTestId('tab-tables').click();
  await expect(page).toHaveURL(/\/table\/tables$/);
  await expect(page.getByTestId('help-button')).toBeVisible();
  await context.setOffline(true);
  try {
    await openHelp();
    await expect(content()).toHaveAttribute('lang', 'es');
    await expect(page.getByTestId('help-current-screen')).toContainText('En esta pantalla · Mesas');
    await expect(page.getByTestId('help-error')).toHaveCount(0);
    await closeHelp();
  } finally {
    await context.setOffline(false);
  }
});

test('only the requested video frame reached an external video host; no application or CSP error occurs', async () => {
  expect(googleRequests).toHaveLength(1);
  expect(googleRequests[0]).toContain('/embed/dQw4w9WgXcQ');
  expect(pageErrors).toEqual([]);
  const csp = await page.evaluate(() => (window as unknown as { helpCsp?: string[] }).helpCsp ?? []);
  expect(csp).toEqual([]);
  const unexpected = consoleErrors.filter(
    (message) => !/net::ERR_FAILED|net::ERR_INTERNET_DISCONNECTED/.test(message),
  );
  expect(unexpected).toEqual([]);
});
