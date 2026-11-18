import { mkdirSync, writeFileSync } from 'node:fs';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, login, settled, turnOffTurnedOn, turnOnMissing } from './helpers';

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
  mkdirSync(SHOTS, { recursive: true });
  context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  page = await context.newPage();
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
  await login(page, A, '/table/floor-plan');
  await turnOnMissing(context, A, ['table'], turnedOn);
  await atTables();
});

test.afterAll(async () => {
  if (context) {
    await turnOffTurnedOn(context, A, turnedOn);
    await context.close();
  }
});

test('the entry is contextual, the current screen leads, and the window fits all sizes in light and dark', async () => {
  await openHelp();
  await expect(page.getByTestId('help-current-screen')).toContainText('On this screen · Floor plan');
  await expect(page.getByTestId('help-current-screen')).toContainText('You are here');
  await expect(page.locator('[data-help-section="purpose"]')).toBeInViewport();
  await expect(page.getByTestId('help-current-screen')).toBeInViewport();
  await expect(page.locator('.help-flow-group__title').first()).toHaveText('Floor plan');
  await expect(page.locator('[data-help-section="video"]')).toHaveCount(0);
  await expect(content()).toHaveAttribute('lang', 'en');

  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await settled(page);
    await expect(content()).toBeVisible();
    const light = await capture(page, `help-window-${size.label}-light`);
    writeFileSync(`${SHOTS}/help-window-${size.label}-light.png`, light);
    await page.evaluate(() => document.documentElement.classList.add('ion-palette-dark'));
    await settled(page);
    const dark = await capture(page, `help-window-${size.label}-dark`);
    writeFileSync(`${SHOTS}/help-window-${size.label}-dark.png`, dark);
    await page.evaluate(() => document.documentElement.classList.remove('ion-palette-dark'));
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(modal()).toHaveAttribute('data-phone-layout', 'sheet');
  await closeHelp();
  await expect(page.getByTestId('help-button')).toBeVisible();
  await expect(page.getByTestId('hub-bell')).toBeVisible();
  await expect(page.getByTestId('topbar-chrome-more')).toBeVisible();
  await expect(page.getByTestId('assistant-button')).toHaveCount(0);

  const title = page.locator('ion-header.app-topbar ion-title').last();
  const titleLayout = await title.evaluate((element) => {
    element.textContent = 'An extremely long restaurant module name that must stay on one line';
    const box = element.getBoundingClientRect();
    const inner = element.shadowRoot?.querySelector('.toolbar-title') ?? element;
    const style = getComputedStyle(inner);
    return { right: box.right, width: box.width, whiteSpace: style.whiteSpace, overflow: style.textOverflow };
  });
  expect(titleLayout.right).toBeLessThanOrEqual(390);
  expect(titleLayout.width).toBeGreaterThan(0);
  expect(titleLayout.whiteSpace).toBe('nowrap');
  expect(titleLayout.overflow).toBe('ellipsis');

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
  const search = page.getByTestId('help-flow-search');
  await expect(search).toBeVisible();
  await search.locator('input').fill('guest');
  await expect(headers).not.toHaveCount(total);
  await search.locator('input').fill('no-such-help-task-anywhere');
  await expect(page.getByTestId('help-flow-empty')).toContainText('Nothing matches your search');
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
  await expect(page.getByTestId('assistant-input').locator('textarea')).toHaveValue(`How do I do this: ${flowTitle}?`);
  expect(assistantTurns).toHaveLength(turnsBefore);
  await expect(page.getByTestId('assistant-thread')).not.toContainText(flowTitle);
  await page.getByTestId('assistant-close').click();
});

test('an aborted help request shows the error and retry loads the same window', async () => {
  await page.goto(`${A}/table/floor-plan`);
  await page.route('**/api/help?app=table', (route) => route.abort('failed'));
  await page.reload();
  await page.getByTestId('help-button').click();
  await expect(page.getByTestId('help-error')).toContainText('Could not load the help.');
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
    await expect(content()).toHaveAttribute('lang', 'en');
    await expect(page.getByTestId('help-current-screen')).toContainText('Floor plan');
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
