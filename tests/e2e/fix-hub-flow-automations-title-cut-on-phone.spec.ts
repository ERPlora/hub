// flow: flow-automations-list
// — On a phone, in Spanish, the bar of «Automatizaciones» read «A» (375 px) or «A…» (390 px): its one action, «Nueva
// automatización» with its icon and its text, took the whole width. The owner of hub `a` opens the list in Spanish at
// 375, 390, 834 and 1440 px: the title is read whole (its `.toolbar-title` not cut with «…») and «Nueva automatización»
// is still one tap away, by its name. On a phone it is only its «+» (Material's top app bar, iOS's navigation bars),
// from a tablet on, its icon and its text. No sideways scroll. Each width leaves its capture
// `FIX-HUB-FLOW-AUTOMATIONS-TITLE-CUT-ON-PHONE-<width>`. Nothing is created.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, login, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-HUB-FLOW-AUTOMATIONS-TITLE-CUT-ON-PHONE';
const SIZES = [
  { label: '375', width: 375, height: 667, phone: true },
  { label: '390', width: 390, height: 844, phone: true },
  { label: '834', width: 834, height: 1112, phone: false },
  { label: '1440', width: 1440, height: 900, phone: false },
];

/** The owner on `a` in Spanish at `viewport`, on «Automatizaciones». */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/flow/automations');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/flow/automations`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

for (const size of SIZES) {
  test(`flow-automations-list at ${size.label}: «Automatizaciones» read whole, «Nueva automatización» one tap away`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      const add = shown(page).getByRole('button', { name: 'Nueva automatización', exact: true });
      await expect(add).toBeVisible();
      // The list as the owner reads it: its gallery painted, nothing still loading.
      await expect(shown(page).locator('[data-testid^=flow-card-open-]').first()).toBeVisible();
      await expect(shown(page).locator('.flow-page__loading')).toHaveCount(0);
      await untilStill(page);

      const heading = shown(page).locator('ion-title').first();
      await expect(heading).toContainText('Automatizaciones');
      const cut = await heading.evaluate((el) => {
        const box = (el.shadowRoot?.querySelector('.toolbar-title') ?? el) as HTMLElement;
        return box.scrollWidth > box.clientWidth;
      });
      expect(cut, `the title «Automatizaciones» at ${size.label} is read whole`).toBe(false);

      // On a phone the action is its «+» alone; from a tablet on, its words are on screen too.
      const words = await shown(page).locator('[data-testid=flow-new]').evaluate((el) => (el as HTMLElement).innerText.trim());
      expect(words, `the words of the action at ${size.label}`).toBe(size.phone ? '' : 'Nueva automatización');

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      await add.click();
      await page.waitForURL(/\/flow\/automations\/new$/);
    } finally {
      await context.close();
    }
  });
}
