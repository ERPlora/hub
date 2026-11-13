// The attendance app's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper uses exists, and the screens' words (WORKBOOK «Pantallas») are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('attendance', en, es);
const { EN } = CATALOGUES;

describe('attendance catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every status the server knows once, for Records and Clock in alike', () => {
    for (const status of ['open', 'closed', 'needs_review']) {
      expect(EN.has(`attendance.status.${status}`), status).toBe(true);
      expect(EN.has(`attendance.clock.status.${status}`), status).toBe(false);
    }
  });

  it('keep the old screens’ words: menu, buttons, columns, states and messages', () => {
    expectWords(CATALOGUES, [
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
    ]);
  });
});
