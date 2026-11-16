// The schedule app's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper of the app uses exists, and the screens' established texts are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('schedule', en, es);
const { EN, ES } = CATALOGUES;

describe('schedule catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

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

  it('keep the old screens’ words', () => {
    expect(ES.get('schedule.tabs.hours')).toBe('Horario');
    expect(ES.get('schedule.tabs.special_days')).toBe('Días especiales');
    expect(ES.get('schedule.tabs.settings')).toBe('Ajustes');
    expect(ES.get('schedule.notSet')).toBe('Sin definir');
    expect(ES.get('schedule.open24h')).toBe('Abierto 24 horas');
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
    expect(ES.get('schedule.specialDays.form.namePlaceholder')).toBe('Nombre (p. ej. Navidad)');
    expect(ES.get('schedule.specialDays.form.openWithHours')).toBe('Abierto (con horario)');
    expect(ES.get('schedule.specialDays.form.recurring')).toBe('Se repite cada año');
    expect(ES.get('schedule.specialDays.form.submit')).toBe('Añadir día');
    expect(ES.get('schedule.overrides.form.submit')).toBe('Añadir cambio temporal');
    expect(ES.get('schedule.delete.message')).toBe('Se eliminará «{name}». No se puede deshacer.');
    expect(ES.get('schedule.settings.timezone')).toBe('Zona horaria del negocio');
    expect(ES.get('schedule.settings.weekStarts')).toBe('Semana empieza');
  });

  it('promise of the default week only what holds while it is unconfirmed: appointments are refused outside it', () => {
    // Not «las reservas fuera de él se rechazan»: Reservations does not apply the week until it is saved or
    // confirmed; Appointments (and Online booking through it) does (hub#172).
    expect(ES.get('schedule.hours.defaultWeek.message')).toBe(
      'Este es un horario por defecto que hemos puesto por ti. Comprueba que coincide con el de tu negocio: las citas fuera de él se rechazan.',
    );
    expect(EN.get('schedule.hours.defaultWeek.message')).toBe(
      'These are default opening hours we set up for you. Check they match your business — appointments outside them are refused.',
    );
  });
});
