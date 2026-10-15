// The cash register app's UI texts: English source + Spanish (PLAN §5). This test is their guardrail: same
// keys and placeholders in both languages, nothing empty, every key a page, a component or a helper of the
// app uses exists, and the texts the old screens showed are kept word for word.
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

describe('cash register catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['cash_register']);
    expect(Object.keys(es)).toEqual(['cash_register']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
  });

  it('keep the same placeholders in both languages', () => {
    for (const [key, message] of EN) expect(placeholders(ES.get(key) ?? ''), key).toEqual(placeholders(message));
  });

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\$?\bt\(\s*'(cash_register\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\$?\bt\(\s*`(cash_register\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status, type, payment method and count type the server knows', () => {
    for (const status of ['open', 'closed']) expect(EN.has(`cash_register.status.${status}`), status).toBe(true);
    for (const type of ['in', 'out', 'sale', 'refund', 'void']) expect(EN.has(`cash_register.types.${type}`), type).toBe(true);
    for (const method of ['cash', 'card', 'transfer', 'other']) expect(EN.has(`cash_register.methods.${method}`), method).toBe(true);
    for (const kind of ['opening', 'closing']) expect(EN.has(`cash_register.countTypes.${kind}`), kind).toBe(true);
  });

  it('keep the old screens’ words (the WORKBOOK’s screens)', () => {
    expect(ES.get('cash_register.sessions.open')).toBe('Abrir sesión');
    expect(ES.get('cash_register.sessions.alreadyOpen')).toBe('Ya hay una sesión de caja abierta. Ciérrala antes de abrir otra.');
    expect(ES.get('cash_register.sessions.empty')).toBe('Sin sesiones de caja.');
    expect(ES.get('cash_register.sessions.search')).toBe('Buscar sesión…');
    expect(ES.get('cash_register.open.title')).toBe('Abrir sesión de caja');
    expect(ES.get('cash_register.open.balance')).toBe('Fondo de apertura');
    expect(ES.get('cash_register.count.submit')).toBe('Registrar arqueo');
    expect(ES.get('cash_register.close.countedRequired')).toBe('Escribe el efectivo contado para cerrar la sesión.');
    expect(ES.get('cash_register.close.anyway')).toBe('Cerrar de todos modos');
    expect(ES.get('cash_register.review.confirm')).toBe('El turno se cerrará igualmente. Pulsa otra vez para confirmar.');
    expect(ES.get('cash_register.detail.noMovements')).toBe('Sin movimientos en esta sesión.');
    expect(ES.get('cash_register.detail.noCounts')).toBe('Sin arqueos en esta sesión.');
    expect(ES.get('cash_register.settings.saved')).toBe('Ajustes guardados.');
    expect(ES.get('cash_register.money.notAnAmount')).toBe('Esto no es un importe. Escribe una cifra, por ejemplo 12,50.');
  });
});
