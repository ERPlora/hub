// The staff app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
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

describe('staff catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['staff']);
    expect(Object.keys(es)).toEqual(['staff']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(staff\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(staff\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name every status, leave type, request status and weekday the server knows', () => {
    for (const status of ['active', 'inactive', 'on_leave']) expect(EN.has(`staff.memberStatus.${status}`), status).toBe(true);
    for (const type of ['vacation', 'sick', 'personal', 'training', 'other']) expect(EN.has(`staff.leaveType.${type}`), type).toBe(true);
    for (const status of ['pending', 'approved', 'rejected', 'cancelled']) expect(EN.has(`staff.requestStatus.${status}`), status).toBe(true);
    for (let day = 0; day < 7; day++) {
      expect(EN.has(`staff.days.long.${day}`), `long ${day}`).toBe(true);
      expect(EN.has(`staff.days.short.${day}`), `short ${day}`).toBe(true);
    }
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states', () => {
    const words: Array<[string, string, string]> = [
      ['staff.tabs.staff', 'Staff', 'Personal'],
      ['staff.tabs.roles', 'Roles', 'Roles'],
      ['staff.tabs.time_off', 'Time Off', 'Ausencias'],
      ['staff.tabs.schedules', 'Schedules', 'Horarios'],
      ['staff.members.search', 'Search member…', 'Buscar miembro…'],
      ['staff.members.empty', 'No staff members.', 'Sin miembros del staff.'],
      ['staff.members.columns.hourlyRate', 'Rate/h', 'Tarifa/h'],
      ['staff.roles.search', 'Search role…', 'Buscar rol…'],
      ['staff.roles.empty', 'No roles defined.', 'Sin roles definidos.'],
      ['staff.timeOff.empty', 'No time-off requests.', 'Sin solicitudes de ausencia.'],
      ['staff.schedules.empty', 'This member has no schedules yet.', 'Este miembro aún no tiene horarios.'],
      ['staff.schedules.noMembers.title', 'No staff members yet', 'Aún no hay miembros del staff'],
      ['staff.loading', 'Loading…', 'Cargando…'],
      ['staff.noResults', 'No results', 'Sin resultados'],
      ['staff.live.reconnecting', 'Reconnecting…', 'Reconectando…'],
      ['staff.live.appInactive', 'This app is not active in this business', 'Esta app no está activa en este negocio'],
      ['staff.noPermission', 'You do not have permission', 'No tienes permiso'],
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });

  it('keep the old forms’ labels and confirmations', () => {
    const words: Array<[string, string]> = [
      ['staff.members.form.titleEdit', 'Editar · {name}'],
      ['staff.members.form.employeeNumber', 'Nº de empleado'],
      ['staff.members.form.roleNone', 'Sin rol'],
      ['staff.members.form.hubUser', 'Usuario del Hub'],
      ['staff.members.form.hubUserNone', 'Sin acceso al Hub'],
      ['staff.members.form.bookingBuffer', 'Margen entre citas (min)'],
      ['staff.members.form.hourlyRate', 'Tarifa por hora'],
      ['staff.members.form.commission', 'Comisión (%)'],
      ['staff.members.deactivate.message', '¿Sacar a {name} de la agenda? Deja de ser reservable; no se borra nada.'],
      ['staff.members.terminate.date', 'Último día (hoy si se deja vacío)'],
      ['staff.members.terminate.reason', 'Motivo (opcional)'],
      ['staff.timeOff.form.fullDay', 'Día completo'],
      ['staff.timeOff.form.startTime', 'Desde (hora)'],
      ['staff.timeOff.form.endTime', 'Hasta (hora)'],
      ['staff.schedules.form.defaultName', 'Horario habitual'],
      ['staff.schedules.form.create', 'Crear horario'],
      ['staff.schedules.form.notWorking', 'No trabaja'],
      ['staff.schedules.delete.message', '¿Eliminar el horario «{name}»? Sus horas dejan de contar para la disponibilidad.'],
      ['staff.settings.fields.default_work_start', 'Inicio de jornada (HH:MM)'],
      ['staff.settings.fields.default_work_end', 'Fin de jornada (HH:MM)'],
      ['staff.settings.fields.default_break_duration', 'Duración del descanso (minutos)'],
    ];
    for (const [key, spanish] of words) expect(ES.get(key), key).toBe(spanish);
  });

  it('no longer carry the eight retired settings (FIX-STAFF-SETTINGS-ORPHANS: they changed nothing)', () => {
    const settings = [...EN.keys()].filter((key) => key.startsWith('staff.settings.fields.') || key.startsWith('staff.settings.hints.'));
    expect(new Set(settings.map((key) => key.split('.').at(-1)))).toEqual(new Set(['default_work_start', 'default_work_end', 'default_break_duration']));
    expect(EN.has('staff.settings.visibility')).toBe(false);
  });
});
