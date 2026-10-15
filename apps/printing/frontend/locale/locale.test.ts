// The printing app's UI texts: English source + Spanish (PLAN §5). This test is their guardrail: same
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

describe('printing catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['printing']);
    expect(Object.keys(es)).toEqual(['printing']);
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
      for (const [, key] of source.matchAll(/\$?\bt\(\s*'(printing\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\$?\bt\(\s*`(printing\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every function, connection, state, status and document the server knows', () => {
    for (const usage of ['receipt', 'kitchen', 'bar', 'label']) expect(EN.has(`printing.usage.${usage}`), usage).toBe(true);
    for (const kind of ['network', 'usb', 'bluetooth', 'system']) expect(EN.has(`printing.kind.${kind}`), kind).toBe(true);
    for (const state of ['ready', 'waiting', 'failing', 'inactive']) expect(EN.has(`printing.state.${state}`), state).toBe(true);
    for (const status of ['pending', 'sent', 'done', 'failed', 'cancelled']) expect(EN.has(`printing.status.${status}`), status).toBe(true);
    const documents = ['receipt', 'kitchen_order', 'invoice', 'delivery_note', 'barcode_label', 'cash_session_report', 'prebill', 'generic'];
    for (const document of [...documents, 'test_page', 'drawer']) expect(EN.has(`printing.documents.${document}`), document).toBe(true);
  });

  it('keep the old screen’s words (the WORKBOOK’s screens)', () => {
    expect(ES.get('printing.printers.heading')).toBe('Impresoras');
    expect(ES.get('printing.summary.heading')).toBe('Cola de impresión');
    expect(ES.get('printing.summary.loadError')).toBe('No se pudo leer la cola de impresión.');
    expect(ES.get('printing.summary.stalled')).toBe('En cola, sin impresora');
    expect(ES.get('printing.settings.heading')).toBe('Ajustes del ticket');
    expect(ES.get('printing.settings.fields.print_receipt_on_sale')).toBe('Imprimir ticket al cobrar');
    expect(ES.get('printing.settings.fields.open_drawer_on_sale')).toBe('Abrir cajón al cobrar');
    expect(ES.get('printing.settings.save')).toBe('Guardar ajustes');
    expect(ES.get('printing.settings.receiptText')).toBe(
      'El encabezado y el pie del tique forman parte de los ajustes de Ventas, que es de donde sale el tique.',
    );
    expect(ES.get('printing.settings.receiptLink')).toBe('Abrir los ajustes del tique');
    expect(ES.get('printing.printers.actions.test')).toBe('Probar');
    expect(ES.get('printing.printers.testFailed')).toBe('Falló la impresión de prueba');
    expect(ES.get('printing.modal.paper')).toBe('Ancho de papel');
    expect(ES.get('printing.jobs.actions.retry')).toBe('Reintentar');
    expect(ES.get('printing.jobs.cancel.reason')).toBe('Motivo (opcional)');
    expect(ES.get('printing.jobs.lastError')).toBe('Último error: {error}');
    expect(ES.get('printing.documents.kitchen_order')).toBe('Comanda de cocina');
    expect(ES.get('printing.documents.prebill')).toBe('Cuenta preliminar');
    expect(ES.get('printing.usage.receipt')).toBe('Recibo');
  });
});
