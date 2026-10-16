// The cart_checkout app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages
// until Django's `djangojs` catalogues are exported to JSON. This test is their guardrail (the old
// module's `every_string_has_its_translation`): same keys and placeholders in both languages, nothing
// empty, no Spanish that is the English pasted across, every key a page, a component or a helper uses
// exists, and the words the old screens showed (its `locales/*.json`) are kept.
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
  'cart_checkout.carts.columns.email': 'the old Spanish screen said «Email» too',
  'cart_checkout.carts.form.email': 'the old Spanish form said «Email» too',
  'cart_checkout.orders.columns.email': 'the old Spanish screen said «Email» too',
  'cart_checkout.carts.columns.total': '«Total» is the Spanish word too',
  'cart_checkout.orders.columns.total': '«Total» is the Spanish word too',
  'cart_checkout.carts.form.sessionPlaceholder': 'an example code, the same in any language',
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

describe('cart_checkout catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['cart_checkout']);
    expect(Object.keys(es)).toEqual(['cart_checkout']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(cart_checkout\.[^']+)'/g)) {
        found += 1;
        expect(EN.has(key), `${file}: ${key}`).toBe(true);
      }
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(cart_checkout\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
    expect(found, 'the scanner found no key: it is broken').toBeGreaterThan(20);
  });

  it('name every status the server knows', () => {
    for (const status of ['active', 'abandoned', 'converted', 'expired']) expect(EN.has(`cart_checkout.cartStatus.${status}`), status).toBe(true);
    for (const status of ['initiated', 'paid', 'failed', 'completed']) expect(EN.has(`cart_checkout.orderStatus.${status}`), status).toBe(true);
  });

  it('keep the old screens’ words', () => {
    const words: Array<[string, string, string]> = [
      ['cart_checkout.tabs.carts', 'Carts', 'Carritos'],
      ['cart_checkout.tabs.orders', 'Orders', 'Pedidos'],
      ['cart_checkout.carts.title', 'Carts', 'Carritos'],
      ['cart_checkout.orders.title', 'Orders', 'Pedidos'],
      ['cart_checkout.carts.columns.session', 'Session', 'Sesión'],
      ['cart_checkout.carts.columns.email', 'Email', 'Email'],
      ['cart_checkout.carts.columns.status', 'Status', 'Estado'],
      ['cart_checkout.carts.columns.items', 'Items', 'Ítems'],
      ['cart_checkout.carts.columns.total', 'Total', 'Total'],
      ['cart_checkout.orders.columns.order', 'Order', 'Pedido'],
      ['cart_checkout.orders.columns.payment', 'Payment', 'Pago'],
      ['cart_checkout.cartStatus.active', 'Active', 'Activo'],
      ['cart_checkout.cartStatus.abandoned', 'Abandoned', 'Abandonado'],
      ['cart_checkout.cartStatus.converted', 'Converted', 'Convertido'],
      ['cart_checkout.cartStatus.expired', 'Expired', 'Expirado'],
      ['cart_checkout.orderStatus.initiated', 'Initiated', 'Iniciado'],
      ['cart_checkout.orderStatus.paid', 'Paid', 'Pagado'],
      ['cart_checkout.orderStatus.failed', 'Failed', 'Fallido'],
      ['cart_checkout.orderStatus.completed', 'Completed', 'Completado'],
      ['cart_checkout.carts.actions.abandon', 'Abandon', 'Abandonar'],
      ['cart_checkout.carts.actions.delete', 'Delete', 'Borrar'],
      ['cart_checkout.orders.actions.markPaid', 'Mark paid', 'Marcar pagado'],
      ['cart_checkout.orders.actions.complete', 'Complete', 'Completar'],
      ['cart_checkout.orders.actions.fail', 'Fail', 'Fallar'],
      ['cart_checkout.carts.form.name', 'Name', 'Nombre'],
      ['cart_checkout.carts.form.sessionPlaceholder', 'sess_a1b2c3', 'sess_a1b2c3'],
      // vue-i18n reads a bare «@» as a linked message: the catalogue writes it as a literal, {'@'}.
      ['cart_checkout.carts.form.emailPlaceholder', "customer{'@'}example.com", "cliente{'@'}ejemplo.com"],
      ['cart_checkout.carts.form.namePlaceholder', 'John Doe', 'Ana García'],
      ['cart_checkout.carts.form.submit', 'Save', 'Guardar'],
      ['cart_checkout.carts.search', 'Search session or email…', 'Buscar sesión o email…'],
      ['cart_checkout.orders.search', 'Search order or email…', 'Buscar pedido o email…'],
      ['cart_checkout.loading', 'Loading…', 'Cargando…'],
      ['cart_checkout.carts.empty', 'No carts.', 'Sin carritos.'],
      ['cart_checkout.orders.empty', 'No orders.', 'Sin pedidos.'],
      ['cart_checkout.carts.actionError', 'Could not complete the action', 'No se pudo completar la acción'],
      ['cart_checkout.live.retry', 'Retry', 'Reintentar'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
