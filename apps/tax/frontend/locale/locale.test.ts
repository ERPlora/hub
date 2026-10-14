// The tax app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON (as the demo's). This test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page, a component or a
// helper of the app uses exists, and the texts the old screens showed are kept word for word.
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

describe('tax catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['tax']);
    expect(Object.keys(es)).toEqual(['tax']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(tax\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      // `t(`tax.rules.types.${type}`)`: the prefix must hold keys.
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(tax\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every family and every qualification the server knows', () => {
    for (const type of ['vat', 'igic', 'ipsi', 'surcharge', 'sales_tax', 'withholding', 'excise', 'import_duty']) {
      expect(EN.has(`tax.types.${type}`), type).toBe(true);
    }
    for (const cls of ['subject', 'subject_reverse', 'exempt', 'not_subject', 'not_subject_location']) {
      expect(EN.has(`tax.classes.${cls}`), cls).toBe(true);
    }
  });

  it('keep the old screens’ words (the WORKBOOK’s screens): read-only notice, empty states, deactivation', () => {
    expect(ES.get('tax.readOnly')).toBe('Puedes consultar las reglas fiscales pero no modificarlas.');
    expect(ES.get('tax.categories.empty')).toBe('Sin categorías fiscales.');
    expect(ES.get('tax.rules.empty')).toBe('Sin reglas fiscales.');
    expect(ES.get('tax.aliases.empty')).toBe('Sin alias de categorías.');
    expect(ES.get('tax.rules.deactivate.title')).toBe('Desactivar regla fiscal');
    expect(ES.get('tax.rules.deactivate.confirm')).toBe('Desactivar regla');
    expect(ES.get('tax.rules.end.submit')).toBe('Guardar fecha de fin');
    expect(ES.get('tax.rules.form.rateNoTax')).toBe('Esta operación no lleva impuesto, así que su tipo es 0 %.');
  });
});
