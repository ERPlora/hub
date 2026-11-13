// The pricing app's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a component or
// a helper uses exists, and the screen's established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('pricing', en, es);
const { EN } = CATALOGUES;

describe('pricing catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every rule type and scope the server knows', () => {
    for (const type of ['percent', 'fixed', 'buy_x_get_y', 'tiered']) expect(EN.has(`pricing.rules.type.${type}`), type).toBe(true);
    for (const scope of ['all', 'products', 'services', 'category', 'product', 'service']) expect(EN.has(`pricing.rules.scope.${scope}`), scope).toBe(true);
  });

  it('keep the old screen’s words: title, tables, columns, search, empty states, buttons', () => {
    expectWords(CATALOGUES, [
      ['pricing.title', 'Price Lists', 'Tarifas'],
      ['pricing.lists.heading', 'Price lists', 'Listas de precios'],
      ['pricing.rules.heading', 'Discount rules', 'Reglas de descuento'],
      ['pricing.lists.columns.code', 'Code', 'Código'],
      ['pricing.lists.columns.name', 'Name', 'Nombre'],
      ['pricing.lists.columns.currency', 'Currency', 'Divisa'],
      ['pricing.lists.columns.tax', 'Tax', 'Impuesto'],
      ['pricing.taxBasis.included', 'Tax included', 'Impuesto incluido'],
      ['pricing.taxBasis.excluded', 'Tax excluded', 'Impuesto no incluido'],
      ['pricing.rules.columns.type', 'Type', 'Tipo'],
      ['pricing.rules.columns.value', 'Value', 'Valor'],
      ['pricing.rules.columns.priority', 'Priority', 'Prioridad'],
      ['pricing.rules.type.percent', 'Percentage', 'Porcentaje'],
      ['pricing.rules.type.buy_x_get_y', 'Buy X, get Y', 'Compra X, llévate Y'],
      ['pricing.rules.type.tiered', 'Tiered', 'Por tramos'],
      ['pricing.lists.search', 'Search code or name…', 'Buscar código o nombre…'],
      ['pricing.lists.empty', 'No price lists.', 'Sin listas de precios.'],
      ['pricing.rules.empty', 'No discount rules.', 'Sin reglas de descuento.'],
      ['pricing.loading', 'Loading…', 'Cargando…'],
      ['pricing.lists.form.save', 'Save', 'Guardar'],
      ['pricing.none', '—', '—'],
      ['pricing.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['pricing.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['pricing.noPermission', 'You do not have permission', 'No tienes permiso'],
    ]);
  });
});
