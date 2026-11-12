// The shared check that no catalogue spells a plural with «(s)» (hub#1124): what it catches and what it lets through,
// and the guard of every catalogue of the Hub's SPA (hub#1147): the platform's and each app's, in `en` and `es`.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { pluralsInParentheses } from './catalogue-plurals';

const catalogue = (entries: Record<string, string>): Map<string, string> => new Map(Object.entries(entries));

type Messages = { [key: string]: string | Messages };

/** The Hub's root (this file is base/frontend/__tests__/). */
const HUB = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

/** Every SPA catalogue of the Hub: `base/frontend/locale/<lang>.json` and `apps/<id>/frontend/locale/<lang>.json`. */
function hubCatalogues(): string[] {
  const apps = readdirSync(join(HUB, 'apps'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => join(HUB, 'apps', entry.name, 'frontend', 'locale'));
  return [join(HUB, 'base', 'frontend', 'locale'), ...apps].flatMap((dir) => {
    let names: string[];
    try {
      names = readdirSync(dir);
    } catch {
      return [];
    }
    return names.filter((name) => /^[a-z]{2}\.json$/.test(name)).map((name) => join(dir, name));
  });
}

/** A catalogue flattened to «file › key» → message, so a finding names where it is. */
function flattened(file: string): Map<string, string> {
  const out = new Map<string, string>();
  const walk = (messages: Messages, prefix: string): void => {
    for (const [key, value] of Object.entries(messages)) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (typeof value === 'string') out.set(`${relative(HUB, file)} › ${path}`, value);
      else walk(value, path);
    }
  };
  walk(JSON.parse(readFileSync(file, 'utf8')) as Messages, '');
  return out;
}

describe('pluralsInParentheses', () => {
  it('names every message that spells a plural in parentheses, in each catalogue it is given', () => {
    const en = catalogue({ 'a.import': 'Import {n} product(s)', 'a.links': 'It stops applying to {count} category(ies)', 'a.ok': 'Add {n} selected' });
    const es = catalogue({ 'a.import': 'Importar {n} producto(s)', 'a.options': 'Se borrarán {count} opción(es)', 'a.ok': 'Añadir {n} seleccionado | Añadir {n} seleccionados' });
    expect(pluralsInParentheses(en, es)).toEqual([
      'a.import: Import {n} product(s)',
      'a.links: It stops applying to {count} category(ies)',
      'a.import: Importar {n} producto(s)',
      'a.options: Se borrarán {count} opción(es)',
    ]);
  });

  it('lets through the forms of vue-i18n and the parentheses that are not a plural', () => {
    const messages = catalogue({
      plural: '{n} row | {n} rows',
      count: 'Tick all of «{category}» ({n})',
      note: 'Slug (optional)',
      unit: 'Price (€)',
      sent: 'Send the order (3)',
    });
    expect(pluralsInParentheses(messages)).toEqual([]);
  });
});

describe('every catalogue of the Hub (hub#1147)', () => {
  it('reads the platform’s and every app’s catalogue, in English and in Spanish', () => {
    const files = hubCatalogues().map((file) => relative(HUB, file));
    expect(files).toContain(join('base', 'frontend', 'locale', 'en.json'));
    expect(files).toContain(join('apps', 'service', 'frontend', 'locale', 'es.json'));
    expect(files.length).toBeGreaterThan(40);
  });

  it('says a count in the singular or the plural, never «(s)»', () => {
    expect(pluralsInParentheses(...hubCatalogues().map(flattened))).toEqual([]);
  });
});
