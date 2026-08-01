// ADR-0062 / hub#69 — filtro visible contra Vite → Axum → mini-SaaS real, sin interceptar `/api`.
// El mini-SaaS solo devuelve Factur-X para FR sin región: verlo demuestra que no se arrastró ES-MD.

import { expect, test, type Page } from '@playwright/test';

const enabled = process.env.HUB_MARKETPLACE_E2E === '1';

async function ownerSession(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('erplora.hub_session', 'pw-session');
    localStorage.setItem('erplora.pwa.hideInstallModal', '1');
    localStorage.setItem(
      'erplora.session',
      JSON.stringify({
        id: 'owner',
        name: 'Owner',
        email: 'owner@example.test',
        role: 'owner',
        permissions: ['*'],
      }),
    );
  });
}

test('filtra el catálogo real por país y limpia la región al cambiar de ES a FR', async ({ page }) => {
  test.skip(!enabled, 'requiere marketplace_e2e_server y HUB_MARKETPLACE_E2E=1');
  await ownerSession(page);
  await page.goto('/apps#all');

  const filter = page.getByTestId('marketplace-country-filter');
  await expect(filter).toBeVisible();
  const country = filter.locator('ion-select');
  await expect(country).toHaveJSProperty('value', 'ES');
  await expect(page.getByText('VeriFactu', { exact: true })).toBeVisible();

  await country.evaluate((element) => {
    (element as HTMLIonSelectElement).value = 'FR';
    element.dispatchEvent(new CustomEvent('ionChange', { bubbles: true, detail: { value: 'FR' } }));
  });

  await expect(country).toHaveJSProperty('value', 'FR');
  await expect(page.getByText('Factur-X', { exact: true })).toBeVisible();
  await expect(page.getByText('VeriFactu', { exact: true })).toHaveCount(0);
});

test('el selector de país del Hub ofrece también Alemania e Italia', async ({ page }) => {
  test.skip(!enabled, 'requiere marketplace_e2e_server y HUB_MARKETPLACE_E2E=1');
  await ownerSession(page);
  await page.goto('/settings#hub');

  await page.getByTestId('hub-country').click();
  await expect(page.getByRole('radio', { name: 'Alemania' })).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Italia' })).toBeVisible();
});
