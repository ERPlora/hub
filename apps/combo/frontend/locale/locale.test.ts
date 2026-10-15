// The combo app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (the old module's `locales/*.json`) are kept.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from './en.json';
import es from './es.json';

type Catalogue = { [key: string]: string | Catalogue };

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..');

function flatten(catalogue: Catalogue, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

function placeholders(message: string): string[] {
  return [...new Set([...message.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort();
}

/** The app's sources that may name a key: pages, components, composables and helpers (no tests). */
function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.(vue|ts)$/.test(entry.name) && !/\.(test|d)\.ts$/.test(entry.name) ? [path] : [];
  });
}

const EN = flatten(en as Catalogue);
const ES = flatten(es as Catalogue);

describe('combo catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['combo']);
    expect(Object.keys(es)).toEqual(['combo']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
  });

  it('keep the same placeholders and plural forms in both languages', () => {
    for (const [key, message] of EN) {
      const spanish = ES.get(key) ?? '';
      expect(placeholders(spanish), key).toEqual(placeholders(message));
      expect(spanish.split('|').length, key).toBe(message.split('|').length);
    }
  });

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'(combo\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(combo\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every course rule, choice state and way of selling the server knows', () => {
    for (const status of ['sold_out', 'product_inactive', 'product_deleted', 'not_by_unit', 'untaxed']) expect(EN.has(`combo.choices.status.${status}`), status).toBe(true);
    for (const kind of ['service', 'goods']) expect(EN.has(`combo.supply.${kind}`), kind).toBe(true);
  });

  it('keep the old screens’ words (the old module’s locales/*.json)', () => {
    const words: Array<[string, string, string]> = [
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
      ['combo.bulk.addCount', 'Add {n} selected', 'Añadir {n} seleccionados'],
      ['combo.money.notAmount', 'This is not an amount. Type a figure, for example 12.50.', 'Esto no es un importe. Escribe una cifra, por ejemplo 12,50.'],
      ['combo.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['combo.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['combo.noPermission', 'You do not have permission', 'No tienes permiso'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
