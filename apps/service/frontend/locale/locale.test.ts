// The service app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (the old module's `locales/*.json`) are kept.
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

describe('service catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['service']);
    expect(Object.keys(es)).toEqual(['service']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(service\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(service\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every pricing, status, discount and movement the server knows', () => {
    for (const type of ['fixed', 'hourly', 'from', 'variable', 'free']) expect(EN.has(`service.pricing.${type}`), type).toBe(true);
    for (const status of ['active', 'unconfigured', 'archived']) expect(EN.has(`service.services.status.${status}`), status).toBe(true);
    for (const status of ['active', 'archived', 'deleted']) expect(EN.has(`service.packages.status.${status}`), status).toBe(true);
    for (const status of ['active', 'voided']) expect(EN.has(`service.grants.status.${status}`), status).toBe(true);
    for (const kind of ['consumed', 'adjusted', 'corrected']) expect(EN.has(`service.movements.kind.${kind}`), kind).toBe(true);
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states, buttons', () => {
    const words: Array<[string, string, string]> = [
      ['service.tabs.services', 'Services', 'Servicios'],
      ['service.tabs.categories', 'Categories', 'Categorías'],
      ['service.tabs.packages', 'Packages', 'Bonos y paquetes'],
      ['service.services.search', 'Search service…', 'Buscar servicio…'],
      ['service.services.empty', 'No services.', 'Sin servicios.'],
      ['service.services.new', 'New service', 'Nuevo servicio'],
      ['service.services.columns.pricingType', 'Pricing', 'Tarifa'],
      ['service.services.columns.duration', 'Duration (min)', 'Duración (min)'],
      ['service.services.status.unconfigured', 'Not configured', 'Sin configurar'],
      ['service.services.statusReason', 'No tax category: it cannot be charged', 'Sin categoría fiscal: no se puede cobrar'],
      ['service.services.form.create', 'Create service', 'Crear servicio'],
      ['service.services.form.titleEdit', 'Editing service — {name}', 'Editando servicio — {name}'],
      ['service.services.form.taxMissing', 'There are no tax categories yet. Set them up in Taxes before adding services.', 'Todavía no hay categorías fiscales. Configúralas en Impuestos antes de añadir servicios.'],
      ['service.services.archive.title', 'Archive service', 'Archivar servicio'],
      ['service.categories.search', 'Search category…', 'Buscar categoría…'],
      ['service.categories.empty', 'No categories.', 'No hay categorías.'],
      ['service.categories.form.noParent', 'No parent (root)', 'Sin padre (raíz)'],
      ['service.categories.delete.impact', '{count} service(s) will be left without a category.', '{count} servicio(s) se quedarán sin categoría.'],
      ['service.packages.search', 'Search package…', 'Buscar paquete…'],
      ['service.packages.empty', 'No packages.', 'No hay paquetes.'],
      ['service.packages.form.noLines', 'Add at least one service: a package with no lines cannot be redeemed.', 'Añade al menos un servicio: un paquete sin líneas no se puede canjear.'],
      ['service.packages.orphans', 'Vouchers with no customer', 'Bonos sin cliente'],
      ['service.grants.title', 'Sold vouchers', 'Bonos vendidos'],
      ['service.grants.empty', 'Nobody has bought this voucher yet.', 'Nadie ha comprado este bono todavía.'],
      ['service.movements.empty', 'This voucher has not been used yet.', 'Este bono aún no se ha usado.'],
      ['service.orphans.empty', 'No voucher has lost its customer.', 'Ningún bono se ha quedado sin cliente.'],
      ['service.loading', 'Loading…', 'Cargando…'],
      ['service.noResults', 'No results', 'Sin resultados'],
      ['service.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['service.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['service.noPermission', 'You do not have permission', 'No tienes permiso'],
      ['service.settings.saved', 'Settings saved.', 'Ajustes guardados.'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
