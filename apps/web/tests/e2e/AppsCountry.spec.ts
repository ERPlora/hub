// ADR-0062 / hub#69 — evidencia Playwright del filtro visible del Marketplace.
// El país y la región del Hub son el valor inicial; al elegir otro país la región anterior no se
// arrastra a la consulta siguiente.

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
  countries: ['FR', 'ES'],
  country_links: [
    { country: 'FR', regions: ['IDF'], excluded_regions: [] },
    { country: 'ES', regions: [], excluded_regions: [] },
  ],
};

function json(route: Route, body: unknown) {
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockHub(page: Page, catalogRequests: string[]): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('erplora.hub_session', 'pw-session');
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
        country: 'FR', region: 'IDF', country_code: 'FR', region_code: 'IDF',
        currency: 'EUR', language: 'es', pin_users: [],
      });
    }
    if (url.pathname === '/api/marketplace/catalog') {
      catalogRequests.push(url.search);
      return json(route, { results: [MODULE] });
    }
    if (url.pathname === '/api/modules') return json(route, { ok: true, data: [] });
    if (url.pathname === '/api/navigation') return json(route, { ok: true, data: [] });
    if (url.pathname === '/api/settings') {
      return json(route, {
        currency: 'EUR', language: 'es', api_docs_enabled: false,
        country_code: 'FR', region_code: 'IDF', business_tax_id: '',
        business_legal_name: '', business_address: '', theme_palette: 'erplora',
      });
    }
    if (url.pathname === '/api/entitlement') return json(route, { modules: ['verifactu'] });
    return json(route, { ok: true, data: [] });
  });
}

test('usa país/región del Hub y limpia la región al elegir otro país', async ({ page }) => {
  const catalogRequests: string[] = [];
  await mockHub(page, catalogRequests);

  await page.goto('/apps#all');

  const filter = page.getByTestId('marketplace-country-filter');
  await expect(filter).toBeVisible();
  const country = filter.locator('ion-select');
  await expect(country).toHaveJSProperty('value', 'FR');
  await expect.poll(() => catalogRequests.some((query) => query.includes('countries=FR') && query.includes('region=IDF'))).toBe(true);

  await country.evaluate((element) => {
    (element as HTMLIonSelectElement).value = 'ES';
    element.dispatchEvent(new CustomEvent('ionChange', { bubbles: true, detail: { value: 'ES' } }));
  });

  await expect(country).toHaveJSProperty('value', 'ES');
  await expect.poll(() => catalogRequests.some((query) => query.includes('countries=ES') && !query.includes('region='))).toBe(true);
});
