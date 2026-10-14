// The customer app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages
// until V6 exports Django's `djangojs` catalogues to JSON, like the demo's. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper names exists, and no vue-i18n special character left unescaped.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import OPERATIONS from '../../../../frontend/generated/operations.json';
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

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
    return /\.vue$|(?<!\.test)(?<!\.d)\.ts$/.test(entry.name) ? [path] : [];
  });
}

const EN = flatten(en as Catalogue);
const ES = flatten(es as Catalogue);

describe('customer catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['customer']);
    expect(Object.keys(es)).toEqual(['customer']);
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

  it('use no vue-i18n linked-message sign (@) nor a stray brace: they would break the message', () => {
    for (const [key, message] of [...EN, ...ES]) {
      expect(message, key).not.toMatch(/@|\$/);
      expect(message.replace(/\{\w+\}/g, ''), key).not.toMatch(/[{}]/);
    }
  });

  it('cover every key the pages, components and helpers use', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    let keys = 0;
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/(?:\$t|\bt)\(\s*'(customer\.[^']+)'/g)) {
        keys++;
        expect(EN.has(key), `${file}: ${key}`).toBe(true);
      }
    }
    expect(keys).toBeGreaterThan(0);
  });

  it('cover every key held in a literal too (tables of labels), operation names aside', () => {
    const operations = new Set(Object.keys(OPERATIONS));
    for (const file of sources(FRONTEND)) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/'(customer\.[a-z][\w]*\.[\w.]+)'/g)) {
        if (operations.has(key) || key.endsWith('.')) continue;
        expect(EN.has(key), `${file}: ${key}`).toBe(true);
      }
    }
  });
});
