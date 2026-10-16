// The online booking app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
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

describe('online booking catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['online_booking']);
    expect(Object.keys(es)).toEqual(['online_booking']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(online_booking\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(online_booking\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status the diary knows', () => {
    for (const status of ['pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show']) {
      expect(EN.has(`online_booking.bookings.status.${status}`), status).toBe(true);
    }
  });

  it('keep the old screens’ words (the WORKBOOK’s screens)', () => {
    expect(ES.get('online_booking.tabs.bookings')).toBe('Reservas');
    expect(ES.get('online_booking.settings.title')).toBe('Configuración de la página de reservas');
    expect(ES.get('online_booking.settings.saved')).toBe('Configuración guardada.');
    expect(ES.get('online_booking.settings.loadError')).toBe('Error cargando la configuración');
    expect(ES.get('online_booking.settings.saveError')).toBe('No se pudo guardar');
    expect(ES.get('online_booking.settings.fields.is_enabled')).toBe('Página pública activada');
    expect(ES.get('online_booking.settings.fields.allow_staff_selection')).toBe('Permitir elegir profesional');
    expect(ES.get('online_booking.bookings.actions.confirm')).toBe('Confirmar');
    expect(ES.get('online_booking.bookings.status.no_show')).toBe('No-show');
  });
});
