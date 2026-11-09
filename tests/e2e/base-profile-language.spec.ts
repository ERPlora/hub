// BASE-F64, BASE-F02: choosing a language applies it to the whole open shell. «My apps» and the setup checklist
// take their server-rendered names again in that language, in both directions, without reloading the document.
import { expect, type Page, test } from '@playwright/test';

import { A, hostPage, shown } from './helpers';

async function openProfile(page: Page): Promise<void> {
  await page.locator('ion-menu [data-testid="user-menu-trigger"]').click();
  await page.locator('ion-popover [data-testid="user-menu-profile"]').click();
  await expect(shown(page).getByTestId('profile-language')).toBeVisible();
}

async function chooseLanguage(page: Page, label: 'English' | 'Español'): Promise<void> {
  const saving = page.waitForResponse(
    (response) => response.url().endsWith('/api/me/preferences') && response.request().method() === 'POST',
  );
  await shown(page).getByTestId('profile-language').click();
  await page.locator('ion-select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }).click();
  expect((await saving).status()).toBe(200);
}

async function backHome(page: Page): Promise<void> {
  await shown(page).getByTestId('topbar-back').click();
  await expect(shown(page).getByTestId('home-my-apps')).toBeVisible();
}

function appTile(page: Page, name: string) {
  return shown(page).getByTestId('home-my-app').filter({ hasText: new RegExp(`^\\s*${name}\\s*$`) });
}

function verifactuStep(page: Page) {
  return shown(page).locator('[data-testid="setup-row"][data-key="verifactu.sending_route"]');
}

test('BASE-F64: Mis apps and the setup checklist change language with the open shell, in both directions', async ({
  browser,
}) => {
  const { context, page } = await hostPage(browser, A, { viewport: { width: 1440, height: 900 }, next: '/profile' });
  try {
    if (
      (await shown(page)
        .getByTestId('profile-language')
        .evaluate((select) => (select as HTMLElement & { value: string }).value)) !== 'en'
    ) {
      await chooseLanguage(page, 'English');
    }
    await backHome(page);
    // Setup only: establish an English baseline before measuring the no-reload transition.
    await page.reload();
    await expect(appTile(page, 'Tables')).toBeVisible();
    await expect(verifactuStep(page)).toContainText('Set up VeriFactu');
    await page.evaluate(() => {
      document.documentElement.dataset.issue1038SameDocument = 'yes';
    });

    await openProfile(page);
    await chooseLanguage(page, 'Español');
    await backHome(page);
    await expect(shown(page).getByTestId('home-my-apps').locator('h2')).toHaveText('Mis apps');
    await expect(appTile(page, 'Mesas')).toBeVisible();
    await expect(appTile(page, 'Tables')).toHaveCount(0);
    await expect(verifactuStep(page)).toContainText('Configura VeriFactu');
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    await expect(page.locator('html')).toHaveAttribute('data-issue1038-same-document', 'yes');

    await openProfile(page);
    await chooseLanguage(page, 'English');
    await backHome(page);
    await expect(shown(page).getByTestId('home-my-apps').locator('h2')).toHaveText('My apps');
    await expect(appTile(page, 'Tables')).toBeVisible();
    await expect(appTile(page, 'Mesas')).toHaveCount(0);
    await expect(verifactuStep(page)).toContainText('Set up VeriFactu');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.locator('html')).toHaveAttribute('data-issue1038-same-document', 'yes');
  } finally {
    await context.close();
  }
});
