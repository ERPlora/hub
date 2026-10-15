// The invoice app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
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

describe('invoice catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['invoice']);
    expect(Object.keys(es)).toEqual(['invoice']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(invoice\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      // `t(`invoice.status.${status}`)`: the prefix must hold keys.
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(invoice\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every type, status, source and kind of document the server knows', () => {
    for (const type of ['F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5']) {
      expect(EN.has(`invoice.types.${type}`), type).toBe(true);
      expect(EN.has(`invoice.typeNames.${type}`), type).toBe(true);
    }
    for (const status of ['issued', 'paid', 'cancelled']) expect(EN.has(`invoice.status.${status}`), status).toBe(true);
    for (const source of ['sale', 'manual', 'substitution', 'rectification', 'refund', 'void']) {
      expect(EN.has(`invoice.sources.${source}`), source).toBe(true);
    }
    for (const idType of ['02', '03', '04', '05', '06', '07']) expect(EN.has(`invoice.recipient.idTypes.${idType}`), idType).toBe(true);
  });

  it('keep the old screens’ words (WORKBOOK «Pantallas»)', () => {
    expect(ES.get('invoice.title')).toBe('Facturación');
    expect(ES.get('invoice.tabs.invoices')).toBe('Facturas');
    expect(ES.get('invoice.tabs.series')).toBe('Series');
    expect(ES.get('invoice.list.search')).toBe('Buscar facturas…');
    expect(ES.get('invoice.list.empty')).toBe('Aún no hay facturas.');
    expect(ES.get('invoice.list.actions.markPaid')).toBe('Marcar pagada');
    expect(ES.get('invoice.detail.print')).toBe('Imprimir / PDF');
    expect(ES.get('invoice.detail.missingTaxId')).toBe(
      'Esta factura no tiene el NIF del cliente: la impresora de tiques no puede sacarla como factura completa.',
    );
    expect(ES.get('invoice.markPaid.title')).toBe('¿Marcar {number} como pagada?');
    expect(ES.get('invoice.markPaid.message')).toBe('El cobro se registra con la fecha y la hora de ahora.');
    expect(ES.get('invoice.rectify.title')).toBe('Rectificar {number}');
    expect(ES.get('invoice.rectify.submit')).toBe('Emitir rectificativa');
    expect(ES.get('invoice.rectify.isRectifying')).toBe('Una rectificativa no se puede rectificar.');
    expect(ES.get('invoice.rectify.cancelled')).toBe('La factura ya está cancelada.');
    expect(ES.get('invoice.create.title')).toBe('Nueva factura manual');
    expect(ES.get('invoice.create.submit')).toBe('Emitir factura');
    expect(ES.get('invoice.series.empty')).toBe('Aún no hay series. Crea la primera para numerar tus facturas.');
    expect(ES.get('invoice.series.loading')).toBe('Cargando series…');
    expect(ES.get('invoice.series.search')).toBe('Buscar código, nombre…');
    expect(ES.get('invoice.series.form.createTitle')).toBe('Nueva serie de numeración');
    expect(ES.get('invoice.series.form.editTitle')).toBe('Editar serie {code}');
    expect(ES.get('invoice.series.form.create')).toBe('Crear serie');
  });
});
