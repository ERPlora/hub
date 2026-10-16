// The modifier app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screen showed (the old module's `locales/*.json`, «Modificadores» renamed
// «Suplementos», as Sales already called it) are kept.
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

describe('modifier catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['modifier']);
    expect(Object.keys(es)).toEqual(['modifier']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(modifier\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(modifier\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('keep the old screen’s words: title, columns, form, search, empty state, rule', () => {
    const words: Array<[string, string, string]> = [
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
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
