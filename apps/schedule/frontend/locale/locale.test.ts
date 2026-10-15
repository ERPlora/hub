// The schedule app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper of the app
// uses exists, and the texts the old screens showed are kept word for word.
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

describe('schedule catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['schedule']);
    expect(Object.keys(es)).toEqual(['schedule']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(schedule\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(schedule\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

  it('name the seven days, Monday = 0', () => {
    expect([0, 1, 2, 3, 4, 5, 6].map((d) => EN.get(`schedule.days.${d}`))).toEqual([
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ]);
    expect([0, 1, 2, 3, 4, 5, 6].map((d) => ES.get(`schedule.days.${d}`))).toEqual([
      'Lunes',
      'Martes',
      'Miércoles',
      'Jueves',
      'Viernes',
      'Sábado',
      'Domingo',
    ]);
  });

  it('keep the old screens’ words (locales/es.json of the old module)', () => {
    expect(ES.get('schedule.tabs.hours')).toBe('Horario');
    expect(ES.get('schedule.tabs.special_days')).toBe('Días especiales');
    expect(ES.get('schedule.tabs.settings')).toBe('Ajustes');
    expect(ES.get('schedule.notSet')).toBe('Sin definir');
    expect(ES.get('schedule.open24h')).toBe('Abierto 24 horas');
    expect(ES.get('schedule.hours.defaultWeek.message')).toBe(
      'Este es un horario por defecto que hemos puesto por ti. Comprueba que coincide con el de tu negocio: las reservas fuera de él se rechazan.',
    );
    expect(ES.get('schedule.hours.defaultWeek.confirm')).toBe('Sí, este es mi horario');
    expect(ES.get('schedule.hours.form.title')).toBe('Editar horario — {day}');
    expect(ES.get('schedule.hours.form.submit')).toBe('Guardar día');
    expect(ES.get('schedule.intervals.add')).toBe('+ Añadir tramo');
    expect(ES.get('schedule.intervals.hint')).toBe(
      'Jornada partida: una línea por tramo (10:00–14:00 y 17:00–20:00). Un cierre anterior a la apertura pasa de medianoche (22:00–02:00).',
    );
    expect(ES.get('schedule.intervals.incomplete')).toBe('Indica la hora de apertura y cierre, o márcalo como cerrado');
    expect(ES.get('schedule.specialDays.empty')).toBe('Sin días especiales.');
    expect(ES.get('schedule.overrides.empty')).toBe('Sin cambios temporales.');
    expect(ES.get('schedule.specialDays.search')).toBe('Buscar día especial…');
    expect(ES.get('schedule.overrides.search')).toBe('Buscar cambio temporal…');
    expect(ES.get('schedule.specialDays.form.namePlaceholder')).toBe('Nombre (p.ej. Navidad)');
    expect(ES.get('schedule.specialDays.form.openWithHours')).toBe('Abierto (con horario)');
    expect(ES.get('schedule.specialDays.form.recurring')).toBe('Se repite cada año');
    expect(ES.get('schedule.specialDays.form.submit')).toBe('Añadir día');
    expect(ES.get('schedule.overrides.form.submit')).toBe('Añadir cambio temporal');
    expect(ES.get('schedule.delete.message')).toBe('Se eliminará «{name}». No se puede deshacer.');
    expect(ES.get('schedule.settings.timezone')).toBe('Zona horaria del negocio');
    expect(ES.get('schedule.settings.weekStarts')).toBe('Semana empieza');
  });
});
