// BASE-F64, BASE-F02: choosing a language applies it to the whole open shell. «My apps» and the setup checklist
// take their server-rendered names again in that language, in both directions, without reloading the document.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, hostPage, shown } from './helpers';

async function openProfile(page: Page): Promise<void> {
  await page.locator('ion-menu [data-testid="user-menu-trigger"]').click();
  await page.locator('ion-popover [data-testid="user-menu-profile"]').click();
  await expect(shown(page).getByTestId('profile-language')).toBeVisible();
}

const LABELS = { '': 'Use the business’s language', en: 'English', es: 'Español' } as const;
type Language = keyof typeof LABELS;

async function chooseLanguage(page: Page, label: (typeof LABELS)[Language]): Promise<void> {
  const saving = page.waitForResponse(
    (response) => response.url().endsWith('/api/me/preferences') && response.request().method() === 'POST',
  );
  await shown(page).getByTestId('profile-language').click();
  await page.locator('ion-select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) }).click();
  expect((await saving).status()).toBe(200);
  // The next choice opens a popover of its own: a select tapped while this one is still leaving opens none.
  await expect(page.locator('ion-select-popover')).toHaveCount(0);
}

async function backHome(page: Page): Promise<void> {
  await shown(page).getByTestId('topbar-back').click();
  await expect(shown(page).getByTestId('home-my-apps')).toBeVisible();
}

async function savedLanguage(page: Page): Promise<Language> {
  return (await shown(page)
    .getByTestId('profile-language')
    .evaluate((select) => (select as HTMLElement & { value: string }).value)) as Language;
}

/** Leaves the owner of `a` with the language it had: the choice is saved for the person, and other specs sign in as them. */
async function restoreLanguage(page: Page, language: Language): Promise<void> {
  if ((await savedLanguage(page)) === language) return;
  // The label of «the business's» is said in the current language: English here, where every test of this file ends.
  await chooseLanguage(page, LABELS[language]);
}

/** «My profile» of the owner of `a`, opened by its address, with English chosen; `initial` is what it had saved. */
async function profileInEnglish(browser: Browser): Promise<{ context: BrowserContext; page: Page; initial: Language }> {
  const { context, page } = await hostPage(browser, A, { viewport: { width: 1440, height: 900 }, next: '/profile' });
  await expect(shown(page).getByTestId('profile-language')).toBeVisible();
  const initial = await savedLanguage(page);
  if (initial !== 'en') await chooseLanguage(page, 'English');
  return { context, page, initial };
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
  const { context, page, initial } = await profileInEnglish(browser);
  try {
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
    await openProfile(page);
    await restoreLanguage(page, initial);
  } finally {
    await context.close();
  }
});

// The server writes every live read's texts in the stream's language: the choice reopens the tab's stream at once,
// also with no Home behind «My profile» (its address opened directly), so whatever is on screen answers in it.
test('BASE-F64: choosing a language on «My profile» opened by its address reopens the live stream at once', async ({
  browser,
}) => {
  const { context, page, initial } = await profileInEnglish(browser);
  try {
    await page.reload();
    await expect(shown(page).getByTestId('profile-language')).toBeVisible();
    await expect(shown(page).getByTestId('home-my-apps')).toHaveCount(0);

    let saved = false;
    page.on('response', (response) => {
      if (response.url().endsWith('/api/me/preferences') && response.request().method() === 'POST') saved = true;
    });
    const reopened = page.waitForRequest((request) => saved && new URL(request.url()).pathname === '/api/live');
    await chooseLanguage(page, 'Español');
    await reopened;
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    await expect(page).toHaveURL(/\/profile$/);

    await chooseLanguage(page, 'English');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await restoreLanguage(page, initial);
  } finally {
    await context.close();
  }
});
