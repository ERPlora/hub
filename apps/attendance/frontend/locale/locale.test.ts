// The attendance app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (WORKBOOK «Pantallas», the old module's
// `locales/*.json`) are kept word for word.
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

describe('attendance catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['attendance']);
    expect(Object.keys(es)).toEqual(['attendance']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(attendance\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(attendance\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status the server knows, in the records and on the clock', () => {
    for (const status of ['open', 'closed', 'needs_review']) {
      expect(EN.has(`attendance.status.${status}`), status).toBe(true);
      expect(EN.has(`attendance.clock.status.${status}`), status).toBe(true);
    }
  });

  it('keep the old screens’ words: menu, buttons, columns, states and messages', () => {
    const words: Array<[string, string, string]> = [
      ['attendance.tabs.clock', 'Clock in', 'Fichar'],
      ['attendance.tabs.records', 'Records', 'Registros'],
      ['attendance.clock.greeting', 'Hello, {name}', 'Hola, {name}'],
      ['attendance.clock.now', 'It is {time}', 'Son las {time}'],
      ['attendance.clock.statusOut', 'You are clocked out', 'No has fichado la entrada'],
      ['attendance.clock.statusIn', 'Clocked in since {time}', 'Dentro desde las {time}'],
      ['attendance.clock.clockIn', 'Clock in', 'Fichar entrada'],
      ['attendance.clock.clockOut', 'Clock out', 'Fichar salida'],
      ['attendance.clock.breakStart', 'Start break', 'Empezar pausa'],
      ['attendance.clock.breakEnd', 'End break', 'Terminar pausa'],
      ['attendance.clock.clockedIn', 'Clocked in at {time}.', 'Entrada fichada a las {time}.'],
      ['attendance.clock.recent', 'Recent days', 'Últimas jornadas'],
      ['attendance.clock.status.open', 'In progress', 'En curso'],
      ['attendance.status.open', 'Open', 'Abierta'],
      ['attendance.status.needs_review', 'Needs review', 'Por revisar'],
      ['attendance.records.columns.breaks', 'Breaks (min)', 'Pausas (min)'],
      ['attendance.records.columns.location', 'Location', 'Ubicación'],
      ['attendance.records.radius.none', 'No location recorded', 'Sin ubicación registrada'],
      ['attendance.records.exportCsv', 'Export CSV', 'Exportar CSV'],
      ['attendance.correct.title', 'Correct working day', 'Corregir jornada'],
      ['attendance.correct.clockOut', 'Clock-out (empty = still open)', 'Salida (vacía = sigue abierta)'],
      ['attendance.correct.save', 'Save correction', 'Guardar corrección'],
      ['attendance.history.title', 'Correction history', 'Historial de correcciones'],
      ['attendance.history.empty', 'This working day has never been corrected.', 'Esta jornada no se ha corregido nunca.'],
      ['attendance.presence.title', 'Clocked in now', 'Fichados ahora'],
      ['attendance.settings.useMyLocation', 'Use my current location', 'Usar mi ubicación actual'],
      ['attendance.settings.autoClose', 'Flag for review after (hours)', 'Marcar a revisar tras (horas)'],
      ['attendance.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['attendance.noPermission', 'You do not have permission', 'No tienes permiso'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
