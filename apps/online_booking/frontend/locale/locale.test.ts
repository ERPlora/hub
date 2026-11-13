// The online booking app's UI texts: English source + Spanish, kept by hand next to the pages. This test
// is their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper of the app uses exists, and the screens' established texts are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('online_booking', en, es);
const { EN, ES } = CATALOGUES;

describe('online booking catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only' });

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
