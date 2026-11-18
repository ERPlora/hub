import { mkdirSync, rmSync, writeFileSync } from 'node:fs';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, settled, signedInSpanish, turnOffTurnedOn, turnOnMissing } from './helpers';

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
] as const;
const SHOTS = '/tmp/help-window-shots';

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
const flowHeading = () => page.locator('[data-help-section="flows"] > h3');

async function snap(name: string): Promise<void> {
  const png = await capture(page, name);
  writeFileSync(`${SHOTS}/${name}.png`, png);
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

async function atTables(): Promise<void> {
  await page.goto(`${A}/table/floor-plan`);
  await expect(page.getByTestId('help-button')).toBeVisible();
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  rmSync(SHOTS, { recursive: true, force: true });
  mkdirSync(SHOTS, { recursive: true });
  ({ context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/table/floor-plan'));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.hostname.includes('youtube') || url.hostname.includes('ytimg')) googleRequests.push(request.url());
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

test('Spanish progressive disclosure and every capture at three sizes in light and dark', async () => {
  await openHelp();
  await expect(page.getByTestId('help-current-screen')).toContainText('En esta pantalla · Plano de sala');
  await expect(page.getByTestId('help-current-screen')).toContainText('Estás aquí');
  await expect(page.getByTestId('help-summary-purpose-toggle')).toHaveText('Ver más');
  await expect(page.getByTestId('help-summary-current-toggle')).toHaveText('Ver más');
  await expect(page.locator('[data-help-section="video"]')).toHaveCount(0);
  await expect(content()).toHaveAttribute('lang', 'es');

  for (const size of SIZES) {
    for (const dark of [false, true]) {
      const mode = dark ? 'dark' : 'light';
      await closeHelp();
      await page.setViewportSize({ width: size.width, height: size.height });
      await theme(dark);
      await openHelp();
      await snap(`help-window-${size.label}-${mode}-open`);

      if (size.width >= 834) {
        await expect(page.locator('[data-help-section="purpose"]')).toBeInViewport();
        await expect(page.getByTestId('help-current-screen')).toBeInViewport();
        await expect(flowHeading()).toBeInViewport();
        await expect(search()).toBeInViewport();
      }

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
    await expect(page.getByTestId('topbar-chrome-more')).toBeVisible();
    await expect(page.getByTestId('assistant-button')).toHaveCount(0);
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
  await page.getByTestId('help-ask-assistant').click();
  await expect(modal()).toBeHidden();
  await expect(page.getByTestId('assistant-panel')).toHaveAttribute('data-open', 'true');
  await expect(page.getByTestId('assistant-input').locator('textarea')).toHaveValue(`¿Cómo hago esto: ${flowTitle}?`);
  expect(assistantTurns).toHaveLength(turnsBefore);
  await expect(page.getByTestId('assistant-thread')).not.toContainText(flowTitle);
  await page.getByTestId('assistant-close').click();
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

test('with the browser offline a reopening reads the cached text immediately', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${A}/table/floor-plan`);
  await page.reload();
  await openHelp();
  await closeHelp();
  await context.setOffline(true);
  try {
    await openHelp();
    await expect(content()).toHaveAttribute('lang', 'es');
    await expect(page.getByTestId('help-current-screen')).toContainText('Plano de sala');
    await expect(page.getByTestId('help-error')).toHaveCount(0);
    await closeHelp();
  } finally {
    await context.setOffline(false);
  }
});

test('no YouTube request, application error, or CSP violation occurs', async () => {
  expect(googleRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
  const csp = await page.evaluate(() => (window as unknown as { helpCsp?: string[] }).helpCsp ?? []);
  expect(csp).toEqual([]);
  const unexpected = consoleErrors.filter(
    (message) => !/net::ERR_FAILED|net::ERR_INTERNET_DISCONNECTED/.test(message),
  );
  expect(unexpected).toEqual([]);
});
