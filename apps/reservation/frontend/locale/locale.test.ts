// The reservation app's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper uses exists, and the screens' established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('reservation', en, es);
const { EN } = CATALOGUES;

describe('reservation catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every status, source and weekday the server knows', () => {
    for (const status of ['pending', 'confirmed', 'seated', 'completed', 'cancelled', 'no_show']) {
      expect(EN.has(`reservation.status.${status}`), status).toBe(true);
    }
    for (const source of ['phone', 'in_person', 'waitlist', 'whatsapp', 'online']) {
      expect(EN.has(`reservation.source.${source}`), source).toBe(true);
    }
    for (const day of ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']) {
      expect(EN.has(`reservation.weekday.${day}`), day).toBe(true);
    }
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states, buttons', () => {
    expectWords(CATALOGUES, [
      ['reservation.tabs.reservations', 'Reservations', 'Reservas'],
      ['reservation.tabs.waitlist', 'Waitlist', 'Lista de espera'],
      ['reservation.tabs.availability', 'Availability', 'Disponibilidad'],
      ['reservation.availability.occupancy', 'Occupancy', 'Ocupación'],
      ['reservation.availability.slots', 'Time slots', 'Franjas horarias'],
      ['reservation.availability.blocked', 'Blocked dates', 'Fechas bloqueadas'],
      ['reservation.list.columns.date', 'Date', 'Fecha'],
      ['reservation.list.columns.time', 'Time', 'Hora'],
      ['reservation.waitlist.columns.time', 'Pref. time', 'Hora pref.'],
      ['reservation.list.columns.guest', 'Guest', 'Cliente'],
      ['reservation.list.columns.phone', 'Phone', 'Teléfono'],
      ['reservation.list.columns.party', 'Party', 'Pax'],
      ['reservation.waitlist.columns.contacted', 'Contacted', 'Contactado'],
      ['reservation.availability.columns.slot', 'Slot', 'Franja'],
      ['reservation.availability.columns.reserved', 'Reserved', 'Reservadas'],
      ['reservation.availability.columns.available', 'Available', 'Disponibles'],
      ['reservation.availability.full', 'Full', 'Lleno'],
      ['reservation.erasedCustomer', 'Deleted customer', 'Cliente borrado'],
      ['reservation.actions.confirm', 'Confirm', 'Confirmar'],
      ['reservation.actions.seat', 'Seat', 'Sentar'],
      ['reservation.actions.complete', 'Complete', 'Completar'],
      ['reservation.actions.cancel', 'Cancel', 'Cancelar'],
      ['reservation.waitlist.actions.convert', 'Convert', 'Convertir'],
      ['reservation.waitlist.actions.remove', 'Remove', 'Quitar'],
      ['reservation.form.submitNew', 'Reserve', 'Reservar'],
      ['reservation.availability.addSlot', 'Add slot', 'Añadir franja'],
      ['reservation.availability.slotForm.submit', 'Create slot', 'Crear franja'],
      ['reservation.availability.addBlocked', 'Add blocked date', 'Añadir fecha bloqueada'],
      ['reservation.availability.blockedForm.submit', 'Block date', 'Bloquear fecha'],
      ['reservation.waitlist.add', 'Add guest', 'Añadir cliente'],
      ['reservation.waitlist.form.submit', 'Add to waitlist', 'Añadir a la lista de espera'],
      ['reservation.waitlist.empty', 'Waitlist is empty.', 'Lista de espera vacía.'],
      ['reservation.availability.emptySlots', 'No time slots.', 'Sin franjas horarias.'],
      ['reservation.availability.emptyBlocked', 'No blocked dates.', 'Sin fechas bloqueadas.'],
      ['reservation.list.new', 'New reservation', 'Nueva reserva'],
      ['reservation.list.emptyTitle', 'No reservations this day', 'No hay reservas este día'],
      ['reservation.list.noResultsTitle', 'No reservations match your search', 'Ninguna reserva coincide con la búsqueda'],
      ['reservation.list.clearFilters', 'Clear filters', 'Limpiar filtros'],
      ['reservation.day.covers', 'covers', 'cubiertos'],
      ['reservation.day.bookings', 'bookings', 'reservas'],
      ['reservation.day.nextSlot', 'next slot', 'próxima franja'],
      ['reservation.day.over', 'No more service today', 'No queda servicio hoy'],
      ['reservation.day.noService', 'No service this day', 'Sin servicio este día'],
      ['reservation.day.closed', 'Closed this day', 'Cerrado este día'],
      ['reservation.day.previous', 'Previous day', 'Día anterior'],
      ['reservation.day.next', 'Next day', 'Día siguiente'],
      ['reservation.day.today', 'Today', 'Hoy'],
    ]);
  });
});
