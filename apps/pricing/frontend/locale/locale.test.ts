// The pricing app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screen showed (the old module's `locales/*.json`) are kept.
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

describe('pricing catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['pricing']);
    expect(Object.keys(es)).toEqual(['pricing']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(pricing\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(pricing\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every rule type and scope the server knows', () => {
    for (const type of ['percent', 'fixed', 'buy_x_get_y', 'tiered']) expect(EN.has(`pricing.rules.type.${type}`), type).toBe(true);
    for (const scope of ['all', 'products', 'services', 'category', 'product', 'service']) expect(EN.has(`pricing.rules.scope.${scope}`), scope).toBe(true);
  });

  it('keep the old screen’s words: title, tables, columns, search, empty states, buttons', () => {
    const words: Array<[string, string, string]> = [
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
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
