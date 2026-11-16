// The service app's UI texts: English source + Spanish, kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (the old module's `locales/*.json`) are kept.
import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { appCatalogues, appSources, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('service', en, es);
const { EN } = CATALOGUES;

describe('service catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('keep no error message that no page, component or helper paints', () => {
    // A confirmation or a form shows the server's reason, not a title of its own: an unused «Could not…»
    // is dead text a WORKBOOK ends up quoting as visible.
    const code = appSources(CATALOGUES.frontend).map((file) => readFileSync(file, 'utf8')).join('\n');
    const errors = [...EN.keys()].filter((key) => /error$/i.test(key.slice(key.lastIndexOf('.') + 1)));
    expect(errors.length).toBeGreaterThan(0);
    expect(errors.filter((key) => !code.includes(key))).toEqual([]);
  });

  it('name every pricing, status, discount and movement the server knows', () => {
    for (const type of ['fixed', 'hourly', 'from', 'variable', 'free']) expect(EN.has(`service.pricing.${type}`), type).toBe(true);
    for (const status of ['active', 'unconfigured', 'archived']) expect(EN.has(`service.services.status.${status}`), status).toBe(true);
    for (const status of ['active', 'archived', 'deleted']) expect(EN.has(`service.packages.status.${status}`), status).toBe(true);
    for (const status of ['active', 'voided']) expect(EN.has(`service.grants.status.${status}`), status).toBe(true);
    for (const kind of ['consumed', 'adjusted', 'corrected']) expect(EN.has(`service.movements.kind.${kind}`), kind).toBe(true);
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states, buttons', () => {
    expectWords(CATALOGUES, [
      ['service.tabs.services', 'Services', 'Servicios'],
      ['service.tabs.categories', 'Categories', 'Categorías'],
      ['service.tabs.packages', 'Packages', 'Bonos y paquetes'],
      ['service.services.search', 'Search service…', 'Buscar servicio…'],
      ['service.services.empty', 'No services.', 'Sin servicios.'],
      ['service.services.new', 'New service', 'Nuevo servicio'],
      ['service.services.columns.pricingType', 'Pricing', 'Tarifa'],
      ['service.services.columns.duration', 'Duration (min)', 'Duración (min)'],
      ['service.services.status.unconfigured', 'Not configured', 'Sin configurar'],
      ['service.services.statusReason', 'No tax category: it cannot be charged', 'Sin categoría fiscal: no se puede cobrar'],
      ['service.services.form.create', 'Create service', 'Crear servicio'],
      ['service.services.form.titleEdit', 'Editing service — {name}', 'Editando servicio — {name}'],
      ['service.services.form.taxMissing', 'There are no tax categories yet. Set them up in Taxes before adding services.', 'Todavía no hay categorías fiscales. Configúralas en Impuestos antes de añadir servicios.'],
      ['service.services.archive.title', 'Archive service', 'Archivar servicio'],
      ['service.categories.search', 'Search category…', 'Buscar categoría…'],
      ['service.categories.empty', 'No categories.', 'No hay categorías.'],
      ['service.categories.form.noParent', 'No parent (root)', 'Sin padre (raíz)'],
      // Never «service(s)»: one is said in the singular and several in the plural.
      [
        'service.categories.delete.impact',
        '{count} service will be left without a category. | {count} services will be left without a category.',
        '{count} servicio se quedará sin categoría. | {count} servicios se quedarán sin categoría.',
      ],
      ['service.packages.search', 'Search package…', 'Buscar paquete…'],
      ['service.packages.empty', 'No packages.', 'No hay paquetes.'],
      ['service.packages.form.noLines', 'Add at least one service: a package with no lines cannot be redeemed.', 'Añade al menos un servicio: un paquete sin líneas no se puede canjear.'],
      ['service.packages.orphans', 'Vouchers with no customer', 'Bonos sin cliente'],
      ['service.grants.title', 'Sold vouchers', 'Bonos vendidos'],
      ['service.grants.empty', 'Nobody has bought this voucher yet.', 'Nadie ha comprado este bono todavía.'],
      ['service.movements.empty', 'This voucher has not been used yet.', 'Este bono aún no se ha usado.'],
      ['service.orphans.empty', 'No voucher has lost its customer.', 'Ningún bono se ha quedado sin cliente.'],
      ['service.loading', 'Loading…', 'Cargando…'],
      ['service.noResults', 'No results', 'Sin resultados'],
      ['service.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['service.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['service.noPermission', 'You do not have permission', 'No tienes permiso'],
      ['service.settings.saved', 'Settings saved.', 'Ajustes guardados.'],
    ]);
  });
});
