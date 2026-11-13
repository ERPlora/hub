// The appointment app's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper uses exists, and the screens' established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('appointment', en, es);
const { EN } = CATALOGUES;

describe('appointment catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only' });

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
    expectWords(CATALOGUES, [
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
    ]);
  });
});
