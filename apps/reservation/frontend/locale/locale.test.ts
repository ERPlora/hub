// The reservation app's UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON. This test is their guardrail: same keys and
// placeholders in both languages, nothing empty, every key a page, a component or a helper uses
// exists, and the words the old screens showed (the old module's `locales/*.json`) are kept.
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

describe('reservation catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['reservation']);
    expect(Object.keys(es)).toEqual(['reservation']);
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
      for (const [, key] of source.matchAll(/\bt\(\s*'(reservation\.[^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
      for (const [, prefix] of source.matchAll(/\bt\(\s*`(reservation\.[^`$]+)\$\{/g)) {
        expect([...EN.keys()].some((key) => key.startsWith(prefix)), `${file}: ${prefix}…`).toBe(true);
      }
    }
  });

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
    const words: Array<[string, string, string]> = [
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
    ];
    for (const [key, english, spanish] of words) {
      expect(EN.get(key), key).toBe(english);
      expect(ES.get(key), key).toBe(spanish);
    }
  });
});
