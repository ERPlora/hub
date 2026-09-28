// Regression test for ERPlora/hub#2253 — «Apply» in the Apps filters, on a phone.
//
// In «Add apps» on a phone, the person opened «Filters», picked a category and could not tap
// «Apply»: the panel's «Clear» / «Apply» footer sat under the page's tab bar («My apps · Add apps ·
// Paid»), so the tap switched tabs instead, and closing the panel with × drops the pick. The
// catalog could not be filtered on a phone at all.
//
// Every step here is a REAL click (no `dispatchEvent`): Playwright refuses a click whose point is
// covered by another element, which is exactly the person's tap landing on the tab bar.
//
// The catalog comes from the Cloud, and this bench boots an EMPTY hub with the Cloud pointed at a
// closed port, so the catalog is answered here. Everything else is the real thing.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

test.use({ locale: 'es-ES' });

const CATALOG_SIZE = 23;
const CATEGORIES = ['Ventas', 'Automatizaciones', 'Clientes', 'Inventario'];
/** Apps 01, 05, 09, 13, 17, 21 are «Ventas». */
const SALES_APPS = 6;

function catalog(): Record<string, unknown>[] {
  return Array.from({ length: CATALOG_SIZE }, (_, i) => ({
    module_id: `e2e_app_${String(i + 1).padStart(2, '0')}`,
    name: `App ${String(i + 1).padStart(2, '0')}`,
    description: 'Una app de pruebas con una descripción de longitud normal para el catálogo.',
    module_type: 'free',
    is_free: true,
    category: CATEGORIES[i % CATEGORIES.length],
    installed: false,
    available: true,
    version: '1.2.3',
    capabilities: {},
  }));
}

async function openCatalog(page: Page): Promise<void> {
  await page.route(/\/api\/marketplace\/catalog(\?|$)/, (route) => route.fulfill({ json: catalog() }));
  await page.route(/\/api\/modules\?locale=/, (route) => route.fulfill({ json: { ok: true, data: [] } }));
  await loggedInSession(page);
  await page.goto('/apps#all');
  await expect(catalogTable(page).getByText('App 01', { exact: true })).toBeVisible();
}

/** «Add apps» is the second `ok-data-table` of the page («My apps» is the first). */
const catalogTable = (page: Page) => page.locator('ok-data-table').nth(1);
const filtersPanel = (page: Page) => page.getByRole('dialog', { name: 'Filtros' });

/** Opens «Filters» and picks Category = Ventas, leaving the pick in the panel's draft. */
async function pickSalesCategory(page: Page): Promise<void> {
  await catalogTable(page).getByRole('button', { name: 'Filtros' }).click();
  await expect(filtersPanel(page)).toBeVisible();
  await page
    .locator('ion-select')
    .filter({ has: page.getByRole('button', { name: 'Categoría, Seleccionar' }) })
    .click();
  await page.getByRole('checkbox', { name: 'Ventas' }).click();
  // The category list is a modal that applies each tick as it goes; its only button closes it.
  await page.getByRole('button', { name: 'Cancelar' }).click();
  await expect(filtersPanel(page).getByRole('button', { name: /^Categoría, Ventas/ })).toBeVisible();
}

test.describe('Apps filters on a phone (hub#2253)', () => {
  for (const { width, height } of VIEWPORTS) {
    test(`#all: «Limpiar» and «Aplicar» sit above the tab bar and a real tap on «Aplicar» filters at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      await openCatalog(page);
      await pickSalesCategory(page);

      // The promise of the issue, measured: the whole footer of the panel ends above the tab bar.
      const tabBar = await page.locator('#apps-footer').boundingBox();
      if (!tabBar) throw new Error('tab bar not laid out');
      for (const name of ['Limpiar', 'Aplicar']) {
        const b = await filtersPanel(page).getByRole('button', { name }).boundingBox();
        if (!b) throw new Error(`${name} not laid out`);
        expect(b.y + b.height, `${name} ends above the tab bar`).toBeLessThanOrEqual(tabBar.y + 0.5);
      }

      await filtersPanel(page).getByRole('button', { name: 'Aplicar' }).click();

      await expect(filtersPanel(page)).toBeHidden();
      // Still on «Add apps»: the tap did not land on a tab.
      await expect(page).toHaveURL(/\/apps#all$/);
      await expect(
        catalogTable(page)
          .getByText(/\d+ registros/)
          .first(),
      ).toHaveText(new RegExp(`(^|\\D)${SALES_APPS} registros`));
      await expect(catalogTable(page).getByText('App 02', { exact: true })).toHaveCount(0);
    });
  }
});
