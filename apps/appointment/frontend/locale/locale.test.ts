// The appointment app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses exists,
// and the words the old screens showed (the old module's `locales/*.json`) are kept.
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

describe('appointment catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['appointment']);
    expect(Object.keys(es)).toEqual(['appointment']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(appointment\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(appointment\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status, history action, repetition and weekday the server knows', () => {
    for (const status of ['pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show']) {
      expect(EN.has(`appointment.status.${status}`), status).toBe(true);
    }
    const actions = ['created', 'confirmed', 'started', 'completed', 'cancelled', 'no_show', 'rescheduled'];
    for (const action of [...actions, 'staff_changed', 'service_changed', 'unassigned', 'charged', 'uncharged', 'deleted']) {
      expect(EN.has(`appointment.history.action.${action}`), action).toBe(true);
    }
    for (const frequency of ['daily', 'weekly', 'biweekly', 'monthly']) expect(EN.has(`appointment.series.frequency.${frequency}`)).toBe(true);
    for (const day of [0, 1, 2, 3, 4, 5, 6]) expect(EN.has(`appointment.weekday.${day}`)).toBe(true);
  });

  it('keep the old screens’ words', () => {
    const words: Array<[string, string, string]> = [
      ['appointment.title', 'Appointments', 'Citas'],
      ['appointment.views.list', 'List', 'Lista'],
      ['appointment.views.staff', 'By professional', 'Por profesional'],
      ['appointment.views.series', 'Repeating', 'Periódicas'],
      ['appointment.toolbar.add', 'Add appointment', 'Añadir cita'],
      ['appointment.toolbar.filterStatus', 'Filter by status', 'Filtrar por estado'],
      ['appointment.list.search', 'Search no., customer or service…', 'Buscar nº, cliente o servicio…'],
      ['appointment.list.empty', 'No appointments for this day.', 'Sin citas para este día.'],
      ['appointment.list.erasedCustomer', 'Deleted customer', 'Cliente borrado'],
      ['appointment.actions.charge', 'Charge', 'Cobrar'],
      ['appointment.actions.no_show', 'No-show', 'No-show'],
      ['appointment.grid.noStaff', 'No bookable professionals yet.', 'Aún no hay profesionales reservables.'],
      ['appointment.form.titleEdit', 'Edit appointment', 'Editar la cita'],
      ['appointment.form.save', 'Save changes', 'Guardar cambios'],
      ['appointment.slots.label', 'Free times', 'Horas libres'],
      ['appointment.overlap.title', 'Overlapping appointment', 'Cita solapada'],
      ['appointment.overlap.confirm', 'Book anyway', 'Reservar igual'],
      ['appointment.scope.thisOnly', 'This appointment only', 'Solo esta cita'],
      ['appointment.scope.following', 'This and all following appointments', 'Esta y todas las siguientes'],
      ['appointment.history.title', 'Appointment history', 'Historial de la cita'],
      ['appointment.series.empty', 'No repeating appointments yet.', 'Todavía no hay citas periódicas.'],
      ['appointment.series.noEnd', 'No end', 'Sin fin'],
      ['appointment.series.form.create', 'Create repeating appointment', 'Crear cita periódica'],
      ['appointment.series.form.save', 'Save from this occurrence on', 'Guardar de esta cita en adelante'],
      ['appointment.settings.saved', 'Settings saved.', 'Ajustes guardados.'],
      ['appointment.visits.title', 'Visit history', 'Historial de visitas'],
      ['appointment.visits.empty', 'No appointments yet for this customer.', 'Este cliente aún no tiene citas.'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
