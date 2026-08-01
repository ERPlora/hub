// ADR-0060 / hub#68 — evidencia Playwright del flujo visible: el Cloud devuelve un plan con
// dependencias, el Hub pide consentimiento ANTES de instalar y solo llama request-install tras
// confirmar. Un plan premium bloqueado nunca expone el botón de confirmar ni inicia descarga.

import { expect, test, type Page, type Route } from '@playwright/test';

const MODULE = {
  id: 10,
  module_id: 'verifactu',
  name: 'VeriFactu',
  description: 'Cumplimiento fiscal',
  version: '2.0.0',
  module_type: 'free',
  is_free: true,
  is_active: true,
  countries: ['ES'],
  country_links: [{ country: 'ES', regions: [], excluded_regions: ['PV', 'NA'] }],
};

async function session(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('erplora.hub_session', 'pw-session');
    localStorage.setItem(
      'erplora.session',
      JSON.stringify({ id: 'owner', name: 'Owner', email: 'owner@example.test', role: 'owner', permissions: ['*'] }),
    );
  });
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockShell(page: Page, plan: Record<string, unknown>, installs: string[]): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/hub/context') {
      return json(route, {
        hub_id: 'hub-pw', machine_registered: true, registration_required: false,
        country: 'ES', region: null, currency: 'EUR', language: 'es', pin_users: [],
      });
    }
    if (url.pathname === '/api/marketplace/catalog') return json(route, { results: [MODULE] });
    if (url.pathname === '/api/modules/install-plan') return json(route, { ok: true, data: plan });
    if (url.pathname === '/api/modules/request-install') {
      installs.push(route.request().postData() ?? '');
      return json(route, { ok: true, module_id: 'verifactu', version: '2.0.0', status: 'installed' });
    }
    if (url.pathname === '/api/modules/verifactu/capabilities') {
      return json(route, { module_id: 'verifactu', capabilities: [] });
    }
    if (url.pathname === '/api/modules') return json(route, { ok: true, data: [] });
    if (url.pathname === '/api/navigation') return json(route, { ok: true, data: [] });
    if (url.pathname === '/api/settings') return json(route, {
      currency: 'EUR', language: 'es', api_docs_enabled: false, country_code: 'ES',
      region_code: null, business_tax_id: '', business_legal_name: '', business_address: '',
      theme_palette: 'erplora',
    });
    if (url.pathname === '/api/entitlement') return json(route, { modules: ['verifactu', 'invoice'] });
    return json(route, { ok: true, data: [] });
  });
}

async function openInstall(page: Page): Promise<void> {
  await page.goto('/apps#all');
  const table = page.locator('ok-data-table').nth(1);
  await expect(table).toBeVisible();
  await table.evaluate((element, row) => {
    element.dispatchEvent(new CustomEvent('rowAction', {
      bubbles: true,
      detail: { actionId: 'install', row },
    }));
  }, {
    id: 'verifactu', name: 'VeriFactu', desc: 'Cumplimiento fiscal', price: 'Gratis', paid: false,
    installed: false, available: true, cat: 'Fiscal', version: '2.0.0', countries: ['ES'],
    coverage: 'ES', state: 'available', stateLabel: 'Disponible', progress: null,
  });
}

test('dependencias gratis requieren confirmación y se instalan solo después', async ({ page }) => {
  const installs: string[] = [];
  await session(page);
  await mockShell(page, {
    requested: 'verifactu',
    plan: [
      { module_id: 'invoice', version: '1.0.0', sha256: 'aa', tier: 'free', entitled: true, requires_purchase: false, reason: 'dependency' },
      { module_id: 'verifactu', version: '2.0.0', sha256: 'bb', tier: 'free', entitled: true, requires_purchase: false, reason: 'requested' },
    ],
    already_satisfied: [], blocked: false, blocked_on: [],
  }, installs);

  await openInstall(page);
  const modal = page.getByTestId('install-plan-modal');
  await expect(modal).toBeVisible();
  await expect(modal.getByText('invoice')).toBeVisible();
  expect(installs).toHaveLength(0);

  await modal.getByTestId('install-plan-confirm').click();
  await expect.poll(() => installs.length).toBe(1);
  expect(JSON.parse(installs[0])).toMatchObject({ module_id: 'verifactu', version: '2.0.0' });
});

test('plan bloqueado ofrece compra y no instala nada', async ({ page }) => {
  const installs: string[] = [];
  await session(page);
  await mockShell(page, {
    requested: 'verifactu',
    plan: [{
      module_id: 'verifactu', version: '2.0.0', sha256: 'bb', tier: 'premium',
      entitled: false, requires_purchase: true, reason: 'requested',
      purchase: { module_type: 'subscription', price: '19.99', currency: 'EUR', purchase_url: '/modules/verifactu' },
    }],
    already_satisfied: [], blocked: true, blocked_on: ['verifactu'],
  }, installs);

  await openInstall(page);
  const modal = page.getByTestId('install-plan-modal');
  await expect(modal).toBeVisible();
  await expect(modal.getByTestId('install-plan-purchase')).toBeVisible();
  await expect(modal.getByTestId('install-plan-confirm')).toHaveCount(0);
  expect(installs).toHaveLength(0);
});
