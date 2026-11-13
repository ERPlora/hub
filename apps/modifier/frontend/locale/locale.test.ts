// The modifier app's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper uses exists, and the screen's established words are kept («Suplementos», as
// Sales calls them, rather than «Modificadores»).
import { describe, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('modifier', en, es);

describe('modifier catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('keep the old screen’s words: title, columns, form, search, empty state, rule', () => {
    expectWords(CATALOGUES, [
      ['modifier.title', 'Modifiers', 'Suplementos'],
      ['modifier.groups.columns.name', 'Name', 'Nombre'],
      ['modifier.groups.columns.kitchen', 'On the kitchen ticket', 'En la comanda'],
      ['modifier.groups.columns.choice', 'Choice', 'Elección'],
      ['modifier.groups.columns.order', 'Order', 'Orden'],
      ['modifier.groups.form.name', 'Name', 'Nombre'],
      ['modifier.groups.form.kitchenName', 'Kitchen ticket name', 'Nombre en la comanda'],
      ['modifier.groups.form.min', 'Minimum (1 or more = required)', 'Mínimo (1 o más = obligatorio)'],
      ['modifier.groups.form.max', 'Maximum (0 = no ceiling)', 'Máximo (0 = sin techo)'],
      ['modifier.groups.search', 'Search…', 'Buscar…'],
      ['modifier.groups.empty', 'No modifier groups yet.', 'Todavía no hay grupos de suplementos.'],
      ['modifier.rule.required', 'Required (min. {min})', 'Obligatorio (mín. {min})'],
      ['modifier.rule.optional', 'Optional', 'Opcional'],
      ['modifier.rule.max', 'max. {max}', 'máx. {max}'],
      ['modifier.loading', 'Loading…', 'Cargando…'],
      ['modifier.noResults', 'No results', 'Sin resultados'],
      ['modifier.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['modifier.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['modifier.noPermission', 'You do not have permission', 'No tienes permiso'],
    ]);
  });
});
