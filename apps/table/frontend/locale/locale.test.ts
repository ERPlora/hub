// The table app's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a component or
// a helper uses exists, and the screens' established words are kept.
import { describe, expect, it } from 'vitest';

import { appCatalogues, expectWords, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('table', en, es);
const { EN, ES } = CATALOGUES;

describe('table catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('count things in the singular and the plural: «1 guest», never «1 guests»', () => {
    // A `{count}` before a noun needs both forms (`one | other`, vue-i18n picks one by `count`), and they
    // differ: a copied «{count} guests | {count} guests» still says «1 guests». «pax» is the same for one
    // and many, and «Seat {count} at once» / «Sentar {count} de un toque» count no noun.
    const SAME_FOR_ONE = new Set(['pax', 'at', 'de']);
    for (const [key, message] of [...EN, ...ES]) {
      for (const [, word] of message.matchAll(/\{count\} (\p{L}+)/gu)) {
        if (SAME_FOR_ONE.has(word)) continue;
        const [one, other, ...rest] = message.split('|').map((form) => form.trim());
        expect(rest, `${key}: «{count} ${word}» needs exactly «one | other»`).toEqual([]);
        expect(other, `${key}: «{count} ${word}» has no plural form`).toBeDefined();
        expect(one, `${key}: the singular is the plural`).not.toBe(other);
      }
    }
  });

  it('name every status, shape, colour and check status the server knows', () => {
    for (const status of ['available', 'occupied', 'reserved', 'blocked']) expect(EN.has(`table.status.${status}`), status).toBe(true);
    for (const shape of ['square', 'round', 'rectangle']) expect(EN.has(`table.shape.${shape}`), shape).toBe(true);
    for (const color of ['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'medium']) expect(EN.has(`table.color.${color}`), color).toBe(true);
    for (const status of ['open', 'closed', 'transferred', 'merged', 'parked']) expect(EN.has(`table.sessionStatus.${status}`), status).toBe(true);
  });

  it('keep the old screens’ words: tabs, columns, searches, empty states, buttons', () => {
    expectWords(CATALOGUES, [
      ['table.tabs.floor_plan', 'Floor plan', 'Plano de sala'],
      ['table.tabs.zones', 'Zones', 'Zonas'],
      ['table.tabs.tables', 'Tables', 'Mesas'],
      ['table.tabs.sessions', 'Sessions', 'Sesiones'],
      ['table.floor.hint', 'Drag to position · click a table to edit or delete it. Changes are saved instantly.', 'Arrastra para colocar · clic en una mesa para editarla o borrarla. Los cambios se guardan al momento.'],
      ['table.floor.emptyZones', 'Create a zone to start placing tables.', 'Crea una zona para empezar a colocar mesas.'],
      ['table.floor.emptyTables', 'No tables in this zone. Tap “Add table”.', 'Sin mesas en esta zona. Pulsa «Añadir mesa».'],
      ['table.floor.taken', 'Another device has just taken that table. The floor plan has been refreshed.', 'Otro dispositivo acaba de ocupar esa mesa. Se ha actualizado el plano.'],
      ['table.add.numberPlaceholder', 'Auto-numbered', 'Se numera sola'],
      ['table.form.titleEdit', 'Edit table', 'Editar mesa'],
      ['table.form.name', 'Name (optional)', 'Nombre (opcional)'],
      ['table.zones.search', 'Search zone…', 'Buscar zona…'],
      ['table.zones.empty', 'No zones. Tap «+» to create the first one (Dining room, Terrace, Bar…).', 'No hay zonas. Pulsa «+» para crear la primera (Salón, Terraza, Barra…).'],
      ['table.zones.delete.title', 'Delete zone?', '¿Borrar la zona?'],
      ['table.tables.empty', 'No tables.', 'Sin mesas.'],
      ['table.sessions.noTable', 'No table (parked)', 'Sin mesa (aparcada)'],
      ['table.sessions.close.title', 'Close the session?', '¿Cerrar la sesión?'],
      ['table.sheet.guestsTitle', 'Guests at table {number}', 'Comensales en la mesa {number}'],
      ['table.sheet.seat', 'Seat {count}', 'Sentar {count}'],
      ['table.sheet.overCapacity', 'Above the table capacity ({capacity})', 'Supera el aforo de la mesa ({capacity})'],
      ['table.sheet.blocked', 'Table out of service: it cannot be seated until it is unblocked.', 'Mesa fuera de servicio: no se puede sentar hasta que se desbloquee.'],
      ['table.erasedCustomer', 'Deleted customer', 'Cliente borrado'],
      ['table.settings.promptGuests', 'Ask for the guests when seating a table', 'Preguntar los comensales al sentar una mesa'],
      ['table.settings.warning', 'Amber warning (minutes)', 'Aviso ámbar (minutos)'],
      ['table.settings.critical', 'Red warning (minutes)', 'Aviso rojo (minutos)'],
    ]);
  });
});
