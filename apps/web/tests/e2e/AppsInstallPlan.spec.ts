// ADR-0060 / hub#68 — navegador real contra Vite + Axum + mini-SaaS firmado.
// Arranque: `cargo run -p erplora-server --example marketplace_e2e_server` y `pnpm --dir
// apps/web dev`. Esta spec NO intercepta `/api`: prueba consentimiento, descarga, firma y Runtime.

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

test('consiente el plan y Axum instala activas la dependencia y el módulo firmado', async ({ page }) => {
  test.skip(!enabled, 'requiere marketplace_e2e_server y HUB_MARKETPLACE_E2E=1');
  await ownerSession(page);
  await page.goto('/apps#all');

  const filter = page.getByTestId('marketplace-country-filter');
  await expect(filter).toBeVisible();
  await expect(filter.locator('ion-select')).toHaveJSProperty('value', 'ES');
  await expect(page.getByText('VeriFactu', { exact: true })).toBeVisible();

  const card = page.locator('ion-card').filter({ hasText: 'VeriFactu' });
  await card.getByRole('button', { name: 'Instalar' }).click();

  const modal = page.getByTestId('install-plan-modal');
  await expect(modal).toBeVisible();
  await expect(modal.getByText('invoice', { exact: true })).toBeVisible();

  // El consentimiento debe ocurrir antes de cualquier efecto local.
  const headers = { 'X-User-Id': 'owner', 'X-Hub-Id': 'hub-marketplace-playwright' };
  const before = await page.request.get('http://127.0.0.1:8787/api/modules', { headers });
  expect((await before.json()).data).toEqual([]);

  await modal.getByTestId('install-plan-confirm').click();
  await expect(page.getByText('VeriFactu instalado correctamente.')).toBeVisible();

  await expect.poll(async () => {
    const response = await page.request.get('http://127.0.0.1:8787/api/modules', { headers });
    const body = await response.json() as { data: Array<{ id: string; status: string }> };
    return Object.fromEntries(body.data.map((module) => [module.id, module.status]));
  }).toEqual({ invoice: 'active', verifactu: 'active' });
});
