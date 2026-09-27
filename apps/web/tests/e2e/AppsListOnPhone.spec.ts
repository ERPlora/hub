// Regression test for ERPlora/hub#2245 — the Apps list view on a phone.
//
// In «Add apps», list view, at phone width the table was wider than the phone: status and the
// row's action sat off to the right with nothing saying the table scrolls sideways.
// (The other half of hub#2245 — the list folding back to its first 10 rows after an install — was
// OutfitKit's table restarting «Load more» on any new `rows` array; it is anchored by OutfitKit's
// own test, `mobile-load-more.test.ts`, since this bench installs `@erplora/outfitkit@latest`.)
//
// The catalog comes from the Cloud, and this bench boots an EMPTY hub with the Cloud pointed at a
// closed port, so the catalog (and, for «My apps», the installed list) is answered here. Everything else — the shell,
// the page, OutfitKit's table — is the real thing.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

test.use({ locale: 'es-ES' });

const CATALOG_SIZE = 23;
const CATEGORIES = ['Ventas', 'Automatizaciones', 'Clientes', 'Inventario'];

function catalog(): Record<string, unknown>[] {
  return Array.from({ length: CATALOG_SIZE }, (_, i) => {
    const id = `e2e_app_${String(i + 1).padStart(2, '0')}`;
    return {
      module_id: id,
      name: `App ${String(i + 1).padStart(2, '0')}`,
      description: 'Una app de pruebas con una descripción de longitud normal para el catálogo.',
      module_type: 'free',
      is_free: true,
      category: CATEGORIES[i % CATEGORIES.length],
      installed: false,
      available: true,
      version: '1.2.3',
      capabilities: {},
    };
  });
}

/** Answers the catalog, with nothing installed yet. */
async function withCatalog(page: Page): Promise<void> {
  await page.route(/\/api\/marketplace\/catalog(\?|$)/, (route) => route.fulfill({ json: catalog() }));
}

/** Answers the runtime's installed list («My apps») with the last three apps, active. */
async function withInstalled(page: Page): Promise<void> {
  const data = [21, 22, 23].map((n) => ({ id: `e2e_app_${n}`, name: `App ${n}`, status: 'active', version: '1.2.3' }));
  await page.route(/\/api\/modules\?locale=/, (route) => route.fulfill({ json: { ok: true, data } }));
}

/** The two tables of the page: «My apps» is the first `ok-data-table`, «Add apps» the second. */
const TABS = [
  { hash: 'mine', index: 0, app: 'App 21', status: 'Activo', field: 'Versión' },
  { hash: 'all', index: 1, app: 'App 01', status: 'Disponible', field: 'Categoría' },
] as const;
type Tab = (typeof TABS)[number];

const tableOf = (page: Page, tab: Tab) => page.locator('ok-data-table').nth(tab.index);

/** The tab's first app, as a row of the list view. */
const appRow = (page: Page, tab: Tab) =>
  tableOf(page, tab).getByRole('row').filter({ has: page.getByRole('cell', { name: tab.app, exact: true }) });

async function openList(page: Page, tab: Tab): Promise<void> {
  await withCatalog(page);
  await withInstalled(page);
  await loggedInSession(page);
  await page.goto(`/apps#${tab.hash}`);
  const table = tableOf(page, tab);
  await expect(table).toBeVisible();
  await table.getByRole('button', { name: 'Vista lista' }).click();
  await expect(appRow(page, tab)).toBeVisible();
}

/** The first app's status and its row action (the last button of the row) sit inside the table's box. */
async function statusAndActionFit(page: Page, tab: Tab): Promise<void> {
  const box = await tableOf(page, tab).boundingBox();
  if (!box) throw new Error('table not laid out');
  const right = box.x + box.width;
  const row = appRow(page, tab);
  for (const target of [row.getByText(tab.status, { exact: true }), row.getByRole('button').last()]) {
    const b = await target.boundingBox();
    if (!b) throw new Error('target not laid out');
    expect(b.x).toBeGreaterThanOrEqual(box.x);
    expect(b.x + b.width).toBeLessThanOrEqual(right + 0.5);
  }
}

test.describe('Apps list view on a phone (hub#2245)', () => {
  for (const tab of TABS) {
    for (const { width, height } of VIEWPORTS)
      test(`#${tab.hash}: the list view shows every row's status and action without scrolling sideways at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height });
        await openList(page, tab);
        await statusAndActionFit(page, tab);
      });

    // A tablet turned to a phone-sized window: the table switches itself to cards there without
    // telling the page (OutfitKit #274), so the page follows the same screen step on its own.
    test(`#${tab.hash}: a screen that shrinks to a phone keeps every field on the cards and fits the list`, async ({ page }) => {
      await page.setViewportSize({ width: 834, height: 1194 });
      await openList(page, tab);

      await page.setViewportSize({ width: 390, height: 844 });
      const table = tableOf(page, tab);
      // The cards are on screen, and they still carry a field the narrow list leaves out.
      await expect(table.getByRole('row')).toHaveCount(0);
      await expect(table.getByText(tab.field, { exact: true }).first()).toBeVisible();

      await table.getByRole('button', { name: 'Vista lista' }).click();
      await expect(appRow(page, tab)).toBeVisible();
      await statusAndActionFit(page, tab);
    });
  }

  // rv-2250: dropping the columns the narrow list has no room for also dropped their filter —
  // Category = Sales picked on the cards, then «List view», and all 23 apps came back. The narrow
  // list hides those columns instead: the filter keeps narrowing the list and keeps its control.
  test('#all: a category filter picked on the cards survives switching to the list view at 390px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await withCatalog(page);
    await withInstalled(page);
    await loggedInSession(page);
    await page.goto('/apps#all');
    const table = tableOf(page, TABS[1]);
    await expect(table.getByText('App 01', { exact: true })).toBeVisible();

    const filters = page.getByRole('dialog', { name: 'Filtros' });
    await table.getByRole('button', { name: 'Filtros' }).click();
    await page.locator('ion-select').filter({ has: page.getByRole('button', { name: 'Categoría, Seleccionar' }) }).click();
    await page.getByRole('checkbox', { name: 'Ventas' }).click();
    await page.getByRole('button', { name: 'Cancelar' }).click();
    // A real tap: the panel's footer ends above the page's tab bar (hub#2253).
    await filters.getByRole('button', { name: 'Aplicar' }).click();
    // The footer counts what the list holds: «6 registros» filtered, «Mostrando 1–10 de 23 …» not.
    const footer = table.getByText(/\d+ registros/).first();
    await expect(footer).toHaveText(/(^|\D)6 registros/);

    await table.getByRole('button', { name: 'Vista lista' }).click();
    await expect(appRow(page, TABS[1])).toBeVisible();
    await expect(footer).toHaveText(/(^|\D)6 registros/);
    await expect(table.getByRole('cell', { name: 'App 02', exact: true })).toHaveCount(0);

    // The Category control is still in the panel, with Sales picked.
    await table.getByRole('button', { name: 'Filtros' }).click();
    await expect(filters.getByRole('button', { name: /^Categoría, Ventas/ })).toBeVisible();
  });
});
