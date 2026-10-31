// The table app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
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

describe('table catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['table']);
    expect(Object.keys(es)).toEqual(['table']);
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

  it('count things in the singular and the plural: «1 guest», never «1 guests» (hub#462)', () => {
    // A `{count}` before a noun needs both forms (`one | other`, vue-i18n picks one by `count`), and they
    // differ: a copied «{count} guests | {count} guests» still says «1 guests». «pax» is the same for one
    // and many, and «Seat {count} at once» / «Sentar {count} de un toque» count no noun.
    const SAME_FOR_ONE = new Set(['pax', 'at', 'de']);
    for (const [key, message] of [...EN, ...ES]) {
      for (const [, word] of message.matchAll(/\{count\} (\p{L}+)/gu)) {
        if (SAME_FOR_ONE.has(word)) continue;
        const [one, other, ...rest] = message.split('|').map((form) => form.trim());
        expect(rest, `${key}: «{count} ${word}» needs exactly «one | other»`).toEqual([]);
        expect(other, `${key}: «{count} ${word}» has no plural form`).toBeDefined();
        expect(one, `${key}: the singular is the plural`).not.toBe(other);
      }
    }
  });

  it('cover every key the app’s sources use, literal or built from a known prefix', () => {
    const files = sources(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'(table\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(table\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status, shape, colour and check status the server knows', () => {
    for (const status of ['available', 'occupied', 'reserved', 'blocked']) expect(EN.has(`table.status.${status}`), status).toBe(true);
    for (const shape of ['square', 'round', 'rectangle']) expect(EN.has(`table.shape.${shape}`), shape).toBe(true);
    for (const color of ['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'medium']) expect(EN.has(`table.color.${color}`), color).toBe(true);
    for (const status of ['open', 'closed', 'transferred', 'merged', 'parked']) expect(EN.has(`table.sessionStatus.${status}`), status).toBe(true);
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states, buttons', () => {
    const words: Array<[string, string, string]> = [
      ['table.tabs.floor_plan', 'Floor plan', 'Plano de sala'],
      ['table.tabs.zones', 'Zones', 'Zonas'],
      ['table.tabs.tables', 'Tables', 'Mesas'],
      ['table.tabs.sessions', 'Sessions', 'Sesiones'],
      ['table.floor.hint', 'Drag to position · click a table to edit or delete it. Changes are saved instantly.', 'Arrastra para colocar · clic en una mesa para editarla o borrarla. Los cambios se guardan al momento.'],
      ['table.floor.emptyZones', 'Create a zone to start placing tables.', 'Crea una zona para empezar a colocar mesas.'],
      ['table.floor.emptyTables', 'No tables in this zone. Tap “Add table”.', 'Sin mesas en esta zona. Pulsa «Añadir mesa».'],
      ['table.floor.taken', 'Another device has just taken that table. The floor plan has been refreshed.', 'Otro dispositivo acaba de ocupar esa mesa. Se ha actualizado el plano.'],
      ['table.add.numberPlaceholder', 'Auto-numbered', 'Se numera sola'],
      ['table.form.titleEdit', 'Edit table', 'Editar mesa'],
      ['table.form.name', 'Name (optional)', 'Nombre (opcional)'],
      ['table.zones.search', 'Search zone…', 'Buscar zona…'],
      ['table.zones.empty', 'No zones. Tap «+» to create the first one (Dining room, Terrace, Bar…).', 'No hay zonas. Pulsa «+» para crear la primera (Salón, Terraza, Barra…).'],
      ['table.zones.delete.title', 'Delete zone?', '¿Borrar la zona?'],
      ['table.tables.empty', 'No tables.', 'Sin mesas.'],
      ['table.sessions.noTable', 'No table (parked)', 'Sin mesa (aparcada)'],
      ['table.sessions.close.title', 'Close the session?', '¿Cerrar la sesión?'],
      ['table.sheet.guestsTitle', 'Guests at table {number}', 'Comensales en la mesa {number}'],
      ['table.sheet.seat', 'Seat {count}', 'Sentar {count}'],
      ['table.sheet.overCapacity', 'Above the table capacity ({capacity})', 'Supera el aforo de la mesa ({capacity})'],
      ['table.sheet.blocked', 'Table out of service: it cannot be seated until it is unblocked.', 'Mesa fuera de servicio: no se puede sentar hasta que se desbloquee.'],
      ['table.erasedCustomer', 'Deleted customer', 'Cliente borrado'],
      ['table.settings.promptGuests', 'Ask for the guests when seating a table', 'Preguntar los comensales al sentar una mesa'],
      ['table.settings.warning', 'Amber warning (minutes)', 'Aviso ámbar (minutos)'],
      ['table.settings.critical', 'Red warning (minutes)', 'Aviso rojo (minutos)'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
