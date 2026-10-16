// The payment app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail (the old module's
// `every_string_has_its_translation`): same keys and placeholders in both languages, nothing empty, no
// Spanish that is the English pasted across, every key a page, a component or a helper uses exists,
// and the words the old screen showed (its `locales/*.json`) are kept.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from './en.json';
import es from './es.json';

type Catalogue = { [key: string]: string | Catalogue };

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..');
/** Keys whose Spanish IS the English, on purpose, and why. */
const SAME_IN_BOTH: Record<string, string> = {
  'payment.types.sepa': 'SEPA is the scheme’s own name in both languages',
  'payment.types.check': '«Cheque» is the Spanish word too',
};

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

describe('payment catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['payment']);
    expect(Object.keys(es)).toEqual(['payment']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message, and no Spanish that is the English pasted across', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
    for (const [key, message] of EN) if (!(key in SAME_IN_BOTH)) expect(ES.get(key), key).not.toBe(message);
  });

  it('keep the same placeholders in both languages', () => {
    for (const [key, message] of EN) expect(placeholders(ES.get(key) ?? ''), key).toEqual(placeholders(message));
  });

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(5);
    let found = 0;
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'(payment\.[^']+)'/g)) {
        found += 1;
        expect(EN.has(key), `${file}: ${key}`).toBe(true);
      }
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(payment\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
    expect(found, 'the scanner found no key: it is broken').toBeGreaterThan(20);
  });

  it('name every status and every method type the server knows', () => {
    for (const status of ['draft', 'approved', 'sent', 'completed', 'cancelled']) expect(EN.has(`payment.status.${status}`), status).toBe(true);
    for (const type of ['cash', 'transfer', 'card', 'sepa', 'check', 'other']) expect(EN.has(`payment.types.${type}`), type).toBe(true);
  });

  it('keep the old screen’s words', () => {
    const words: Array<[string, string, string]> = [
      ['payment.title', 'Outgoing payments', 'Pagos salientes'],
      ['payment.tabs.payments', 'Payments', 'Pagos'],
      ['payment.payments.columns.reference', 'Reference', 'Referencia'],
      ['payment.payments.columns.date', 'Date', 'Fecha'],
      ['payment.payments.columns.beneficiary', 'Beneficiary', 'Beneficiario'],
      ['payment.payments.columns.amount', 'Amount', 'Importe'],
      ['payment.payments.columns.status', 'Status', 'Estado'],
      ['payment.payments.columns.method', 'Method', 'Método'],
      ['payment.payments.form.concept', 'Concept', 'Concepto'],
      ['payment.status.draft', 'Draft', 'Borrador'],
      ['payment.status.approved', 'Approved', 'Aprobado'],
      ['payment.status.sent', 'Sent', 'Enviado'],
      ['payment.status.completed', 'Completed', 'Completado'],
      ['payment.status.cancelled', 'Cancelled', 'Cancelado'],
      ['payment.payments.new', 'New payment', 'Nuevo pago'],
      ['payment.payments.form.methodPlaceholder', 'Method…', 'Método…'],
      ['payment.payments.search', 'Search reference or beneficiary…', 'Buscar referencia o beneficiario…'],
      ['payment.loading', 'Loading…', 'Cargando…'],
      ['payment.payments.empty', 'No payments.', 'Sin pagos.'],
      ['payment.payments.cancelForm.reason', 'Cancellation reason', 'Motivo de cancelación'],
      ['payment.money.notAmount', 'This is not an amount. Type a figure, for example 12.50.', 'Esto no es un importe. Escribe una cifra, por ejemplo 12,50.'],
      ['payment.money.notPositive', 'The amount of a payment must be greater than 0.', 'El importe de un pago tiene que ser mayor que 0.'],
      ['payment.payments.form.methodsError', 'Payment methods could not be loaded.', 'No se han podido cargar los métodos de pago.'],
      ['payment.live.retry', 'Retry', 'Reintentar'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
