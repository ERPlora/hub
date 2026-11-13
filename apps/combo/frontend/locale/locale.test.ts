// The combo app's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a component or
// a helper uses exists, and the screens' established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import { pluralsInParentheses } from '../../../../base/frontend/__tests__/catalogue-plurals';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('combo', en, es);
const { EN, ES } = CATALOGUES;

describe('combo catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('in Spanish a course of a menu is a «plato», never a «curso»', () => {
    for (const [key, message] of ES) expect(message, key).not.toMatch(/\bcursos?\b/i);
  });

  it('say a count in the singular or the plural, never «(s)»', () => {
    expect(pluralsInParentheses(EN, ES)).toEqual([]);
  });

  it('name every course rule, choice state and way of selling the server knows', () => {
    for (const status of ['sold_out', 'product_inactive', 'product_sold_out', 'product_deleted', 'not_by_unit', 'untaxed']) expect(EN.has(`combo.choices.status.${status}`), status).toBe(true);
    for (const kind of ['service', 'goods']) expect(EN.has(`combo.supply.${kind}`), kind).toBe(true);
  });

  it('keep the old screens’ words', () => {
    expectWords(CATALOGUES, [
      ['combo.title', 'Menus', 'Menús'],
      ['combo.menus.search', 'Search a menu…', 'Buscar un menú…'],
      ['combo.menus.empty', 'No menus yet. Create the first one with the + button.', 'Aún no hay menús. Crea el primero con el botón +.'],
      ['combo.menus.columns.price', 'Closed price', 'Precio cerrado'],
      ['combo.menus.columns.supply', 'How it is sold', 'Cómo se vende'],
      ['combo.menus.columns.active', 'On sale', 'A la venta'],
      ['combo.menus.actions.edit', 'Edit details', 'Editar datos'],
      ['combo.menus.actions.delete', 'Withdraw', 'Retirar'],
      ['combo.supply.service', 'Eat in', 'En el local'],
      ['combo.supply.goods', 'Take away', 'Para llevar'],
      ['combo.form.titleNew', 'New menu', 'Menú nuevo'],
      ['combo.form.titleEdit', 'Menu · {name}', 'Menú · {name}'],
      ['combo.form.kitchenNameHelp', 'Leave it empty and the kitchen ticket uses the commercial name.', 'Déjalo vacío y la comanda usa el nombre comercial.'],
      ['combo.form.supplyService', 'Eaten in (hospitality service)', 'Se consume en el local (servicio de restauración)'],
      ['combo.form.supplyGoods', 'Sold as a product / to take away', 'Se vende como producto / para llevar'],
      ['combo.form.noTaxCategory', 'A menu eaten in needs its own VAT category: without it, it cannot be billed.', 'Un menú que se consume en el local necesita su propio tipo de IVA: sin él no se puede facturar.'],
      ['combo.builder.back', 'All menus', 'Todos los menús'],
      ['combo.builder.serviceWarning', 'This menu is billed as a single service: one line at its VAT category, whatever the components are taxed at.', 'Este menú se factura como un único servicio: una sola línea a su tipo de IVA, tributen como tributen sus componentes.'],
      ['combo.courses.title', 'Courses', 'Platos'],
      ['combo.courses.empty', 'No courses yet. Add the first one — a menu with no course has nothing to pick.', 'Aún no hay platos. Añade el primero: un menú sin platos no tiene nada que elegir.'],
      ['combo.courses.loadError', 'The courses of this menu could not be loaded.', 'No se han podido cargar los platos de este menú.'],
      ['combo.courseForm.titleNew', 'Add a course', 'Añadir un plato'],
      ['combo.courseForm.repeat', 'The same option may be picked more than once', 'Se puede elegir la misma opción más de una vez'],
      ['combo.rule.required', 'Compulsory · pick {min}', 'Obligatorio · elige {min}'],
      ['combo.choices.empty', 'No choices yet: nobody can resolve this course.', 'Aún no hay elecciones: nadie puede resolver este plato.'],
      ['combo.choices.add', 'Add choice', 'Añadir elección'],
      ['combo.bulk.open', 'Add several', 'Añadir varios'],
      ['combo.bulk.addCount', 'Add {n} selected | Add {n} selected', 'Añadir {n} seleccionado | Añadir {n} seleccionados'],
      ['combo.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['combo.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['combo.noPermission', 'You do not have permission', 'No tienes permiso'],
    ]);
  });
});
