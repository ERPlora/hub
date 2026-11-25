// The help on the Hub's own screens (BASE-F115): the same «?» and window of the modules, with the help of the screen and
// tab in view and how its tasks are done, only those the person's role does, at three sizes and in both languages; and no
// «?» where there is no help to show.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, EMPLOYEE, horizontalOverflow, hostPage, saveSessionForTheSweep, settled, signedInSpanish, testid } from './helpers';

const DESK = { width: 1440, height: 900 };
const TABLET = { width: 820, height: 1180 };
const PHONE = { width: 375, height: 667 };

/** The screens the help is on from the first day: address, what the capture is called, its current screen. */
const SCREENS = [
  ['/', 'home', 'Inicio · Resumen'],
  ['/settings', 'settings', 'Ajustes · General'],
  ['/employees', 'employees', 'Empleados · Personal'],
  ['/profile', 'profile', 'Mi perfil'],
] as const;

const help = (page: Page) => testid(page, 'help-button');
const current = (page: Page) => page.getByTestId('help-current-screen');
/** The titles of the groups of tasks, and a task of one of them, folded. */
const taskGroups = (page: Page) => page.locator('[data-help-section="flows"] .help-flow-group__title');
const task = (page: Page, screen: string, flow: string) => page.getByTestId(`help-flow-${screen}-${flow}`);

async function openHelp(page: Page): Promise<void> {
  await help(page).click();
  await expect(page.getByTestId('help-content')).toBeVisible();
  await expect(page.getByTestId('help-loading')).toHaveCount(0);
  await settled(page);
}

async function closeHelp(page: Page): Promise<void> {
  await page.getByTestId('help-close').click();
  await expect(page.locator('ion-modal[data-testid="help-window"]').last()).toBeHidden();
}

/** The help button sits in the bar of the page in view, inside it, and the page fits its width. */
async function inTheBar(page: Page): Promise<void> {
  await expect(help(page)).toBeVisible();
  const bar = (await testid(page, 'help-button').locator('xpath=ancestor::ion-header').boundingBox())!;
  const button = (await help(page).boundingBox())!;
  expect(button.x).toBeGreaterThanOrEqual(bar.x);
  expect(button.x + button.width).toBeLessThanOrEqual(bar.x + bar.width);
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
}

async function inSpanish(browser: Browser, next: string): Promise<{ context: BrowserContext; page: Page }> {
  return signedInSpanish(browser, DESK, next);
}

for (const [path, name, title] of SCREENS) {
  test(`${name} opens its own help with its tasks, at three sizes`, async ({ browser }) => {
    const { context, page } = await inSpanish(browser, path);
    await saveSessionForTheSweep(context);
    for (const size of [DESK, TABLET, PHONE]) {
      await page.setViewportSize(size);
      await inTheBar(page);
      await capture(page, `base-help-platform-${name}-bar-${size.width}x${size.height}`);
      await openHelp(page);
      await expect(page.locator('.help-window__title-text').last()).toHaveText('Ayuda · ERPlora');
      await expect(current(page)).toContainText(`En esta pantalla · ${title}`);
      await expect(page.getByTestId('help-content')).toHaveAttribute('lang', 'es');
      await expect(page.locator('[data-help-section="screens"] .help-section__title')).toHaveText('Otras pantallas');
      await capture(page, `base-help-platform-${name}-open-${size.width}x${size.height}`);
      await expect(page.locator('[data-help-section="flows"] .help-section__title')).toHaveText('Cómo se hace');
      await expect(taskGroups(page).first()).toHaveText(title);
      const first = page.locator('.help-flow-header').first();
      await first.click();
      await expect(first).toHaveAttribute('aria-expanded', 'true');
      await settled(page);
      await capture(page, `base-help-platform-${name}-task-${size.width}x${size.height}`);
      await closeHelp(page);
    }
    await context.close();
  });
}

test('the help follows the tab in view and the screen the person moves to, back included', async ({ browser }) => {
  const { context, page } = await inSpanish(browser, '/');
  await expect(help(page)).toBeVisible();
  await page.getByTestId('nav-settings').first().click();
  await expect(page).toHaveURL(/\/settings/);
  await expect(help(page)).toBeVisible();
  await openHelp(page);
  await expect(current(page)).toContainText('Ajustes · General');
  await closeHelp(page);

  await testid(page, 'tab-data').click();
  await expect(page).toHaveURL(/#data/);
  await openHelp(page);
  await expect(current(page)).toContainText('Ajustes · Datos y copias');
  await closeHelp(page);

  await page.getByTestId('nav-employees').first().click();
  await expect(page).toHaveURL(/\/employees/);
  await expect(help(page)).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/settings/);
  await expect(help(page)).toBeVisible();
  await openHelp(page);
  await expect(current(page)).toContainText('Ajustes · Datos y copias');
  await closeHelp(page);
  await page.getByTestId('nav-home').first().click();
  await expect(help(page)).toBeVisible();
  await openHelp(page);
  await expect(current(page)).toContainText('Inicio · Resumen');
  await context.close();
});

test('a task of Settings opens with its steps, and a search finds one of another screen', async ({ browser }) => {
  const { context, page } = await inSpanish(browser, '/settings#data');
  await openHelp(page);
  await expect(taskGroups(page).first()).toHaveText('Ajustes · Datos y copias');
  await task(page, 'settings_data', 'BASE-F34').click();
  const steps = page.getByTestId('help-flow-content-settings_data-BASE-F34');
  await expect(steps).toContainText('En «Restablecer», «Deshacer una importación»');
  await expect(steps).not.toContainText('BASE-');
  await page.getByTestId('help-flow-search').locator('input').fill('activar una app');
  await expect(task(page, 'apps', 'BASE-F18')).toBeVisible();
  await context.close();
});

test('a person is shown only the tasks their role does', async ({ browser }) => {
  const owner = await inSpanish(browser, '/apps');
  await openHelp(owner.page);
  await expect(task(owner.page, 'apps', 'BASE-F18')).toBeVisible();
  await owner.context.close();

  const employee = await hostPage(browser, A, { next: '/apps', viewport: DESK, credentials: EMPLOYEE });
  await openHelp(employee.page);
  await expect(task(employee.page, 'apps', 'BASE-F15')).toBeVisible();
  await expect(task(employee.page, 'apps', 'BASE-F18')).toHaveCount(0);
  await expect(task(employee.page, 'settings_general', 'BASE-F66')).toHaveCount(0);
  await employee.context.close();
});

test('the help comes in English to whoever reads English', async ({ browser }) => {
  const { context, page } = await hostPage(browser, A, { next: '/settings', viewport: DESK });
  await context.addCookies([{ name: 'django_language', value: 'en', domain: new URL(A).hostname, path: '/' }]);
  await page.reload();
  await openHelp(page);
  await expect(page.locator('.help-window__title-text').last()).toHaveText('Help · ERPlora');
  await expect(page.getByTestId('help-content')).toHaveAttribute('lang', 'en');
  await expect(current(page)).toContainText('On this screen · Settings · General');
  await expect(page.locator('[data-help-section="flows"] .help-section__title')).toHaveText('How to');
  await expect(taskGroups(page).first()).toHaveText('Settings · General');
  await expect(task(page, 'settings_general', 'BASE-F69')).toHaveText('Name a device');
  await capture(page, 'base-help-platform-settings-open-en');
  await context.close();
});

test('there is no help button where there is no help to show', async ({ browser }) => {
  const { context, page } = await inSpanish(browser, '/api-docs');
  await expect(page.locator('.app-topbar').last()).toBeVisible();
  await settled(page);
  await expect(page.getByTestId('help-button')).toHaveCount(0);
  await context.close();

  const employee = await hostPage(browser, A, { next: '/system', viewport: DESK, credentials: EMPLOYEE });
  await expect(testid(employee.page, 'no-access')).toBeVisible();
  await expect(employee.page.getByTestId('help-button')).toHaveCount(0);
  await employee.context.close();
});

test('says it could not be read and reads it on asking again', async ({ browser }) => {
  const { context, page } = await inSpanish(browser, '/employees');
  await expect(help(page)).toBeVisible();
  let refused = true;
  await page.route('**/api/help?app=base', (route) =>
    refused
      ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":{"code":"base.hub_busy","message":"busy"}}' })
      : route.continue(),
  );
  await help(page).click();
  await expect(page.getByTestId('help-error')).toContainText('No se ha podido cargar la ayuda.');
  await capture(page, 'base-help-platform-employees-error');
  refused = false;
  await page.getByTestId('help-retry').click();
  await expect(current(page)).toContainText('Empleados · Personal');
  await context.close();
});
