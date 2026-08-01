// ADR-0160 / hub#224 — evidencia Playwright de ambos lados visibles: editor autenticado Vue y
// página SSR real de Axum. El segundo test usa `crates/server/examples/public_e2e_server.rs`.

import { expect, test, type Page, type Route } from '@playwright/test';

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockAuthenticatedHub(page: Page, writes: string[]): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('erplora.hub_session', 'pw-session');
    localStorage.setItem('erplora.pwa.hideInstallModal', '1');
    localStorage.setItem(
      'erplora.session',
      JSON.stringify({ id: 'owner', name: 'Owner', email: 'owner@example.test', role: 'owner', permissions: ['*'] }),
    );
  });
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/hub/context') {
      return json(route, {
        hub_id: 'hub-pw', machine_registered: true, registration_required: false,
        country: 'ES', region: null, currency: 'EUR', language: 'es', pin_users: [],
      });
    }
    if (url.pathname === '/api/settings') return json(route, {
      currency: 'EUR', language: 'es', api_docs_enabled: false, country_code: 'ES',
      region_code: null, business_tax_id: '', business_legal_name: 'Bar Pepe',
      business_address: 'Calle Mayor 1', theme_palette: 'erplora',
      'public.landing.visible': true,
    });
    if (url.pathname === '/api/public-pages/inicio') {
      if (route.request().method() === 'PUT') {
        writes.push(route.request().postData() ?? '');
        return json(route, { ok: true });
      }
      return json(route, {
        ok: true,
        data: { blocks: [{ type: 'paragraph', data: { text: 'Bienvenido a Bar Pepe' } }] },
      });
    }
    if (url.pathname === '/api/entitlement') return json(route, { modules: [] });
    if (url.pathname === '/api/modules' || url.pathname === '/api/navigation') {
      return json(route, { ok: true, data: [] });
    }
    return json(route, { ok: true, data: [] });
  });
}

test('el admin carga y guarda una página desde el editor visible', async ({ page }) => {
  const writes: string[] = [];
  await mockAuthenticatedHub(page, writes);
  await page.goto('/settings#hub');

  await page.getByTestId('public-page-open').click();
  const modal = page.getByTestId('public-page-modal');
  await expect(modal).toBeVisible();
  await expect(modal.getByTestId('page-editor')).toBeVisible();
  await expect(modal.getByText('Bienvenido a Bar Pepe')).toBeVisible();

  await modal.getByTestId('public-page-save').click();
  await expect.poll(() => writes.length).toBe(1);
  expect(JSON.parse(writes[0])).toMatchObject({
    blocks: [{ type: 'paragraph', data: { text: 'Bienvenido a Bar Pepe' } }],
  });
});

test('Axum sirve landing y página SSR sin scripts y con CSP estricta', async ({ page }) => {
  const publicUrl = process.env.HUB_PUBLIC_URL;
  test.skip(!publicUrl, 'requiere public_e2e_server');

  const landing = await page.goto(`${publicUrl}/`);
  expect(landing?.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Bar Pepe' })).toBeVisible();
  await expect(page.getByText('Calle Mayor 1')).toBeVisible();
  expect(await page.locator('script').count()).toBe(0);
  expect(landing?.headers()['content-security-policy']).toContain("script-src 'none'");

  const publicPage = await page.goto(`${publicUrl}/p/carta`);
  expect(publicPage?.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Nuestra carta' })).toBeVisible();
  await expect(page.getByText('Café recién molido')).toBeVisible();
  expect(await page.locator('script').count()).toBe(0);
  expect(publicPage?.headers()['content-security-policy']).toContain("script-src 'none'");
});
