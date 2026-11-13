// The staff app's UI texts: English source + Spanish, kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (WORKBOOK «Pantallas», the old module's
// `locales/*.json`) are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('staff', en, es);
const { EN, ES } = CATALOGUES;

describe('staff catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

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
    expectWords(CATALOGUES, [
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
    ]);
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

  it('no longer carry the eight retired settings, which changed nothing', () => {
    const settings = [...EN.keys()].filter((key) => key.startsWith('staff.settings.fields.') || key.startsWith('staff.settings.hints.'));
    expect(new Set(settings.map((key) => key.split('.').at(-1)))).toEqual(new Set(['default_work_start', 'default_work_end', 'default_break_duration']));
    expect(EN.has('staff.settings.visibility')).toBe(false);
  });
});
