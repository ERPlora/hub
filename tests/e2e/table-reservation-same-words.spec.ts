// flow: TABLE-F01, RESERVATION-F06 — hub#888: in a window, fields refused with the same words lose their marks one by
// one as each is corrected, in Tables and Reservations too: every field carries the name the server refuses it by, so
// the window tells which refused field a keystroke corrects. Seen in Tables › Zones › «+» (a window that paints its
// own footer: Delete · Cancel · Save) and in Reservations › «New reservation», at 390, 834 and 1440: the save is
// refused for three fields with the same words; typing in one takes the mark from it alone, then another, and the
// third keeps its own. The refusal is answered in the browser (`page.route`), so nothing is created. Once more in
// Spanish, whose session the fleet's visual sweep reads (`E2E_SAVE_STORAGE_STATE`).
import { type SameWordsWindow, testTheMarksGoOneByOne } from './same-words-helpers';
import { stamp } from './sale-helpers';

const TAG = `E2E888 ${stamp()}`;

const ZONE: SameWordsWindow = {
  app: 'TABLE',
  page: '/table/zones',
  add: 'table-zones-add',
  testid: 'table-zone-form',
  save: '**/api/table/zones',
  fill: async (form) => {
    await form.locator('[data-testid=table-zone-form-name] input').fill(`${TAG} Terrace`);
    await form.locator('[data-testid=table-zone-form-description] input').fill('By the window');
  },
  keys: ['sort_order', 'name', 'description'],
  created: `select count(*) from table_zone where name like '${TAG}%'`,
};

const RESERVATION: SameWordsWindow = {
  app: 'RESERVATION',
  page: '/reservation/reservations',
  add: 'reservation-list-add',
  testid: 'reservation-form',
  save: '**/api/reservation/reservations',
  fill: async (form) => {
    await form.locator('[data-testid=reservation-form-guest_name] input').fill(`${TAG} Ana`);
    await form.locator('[data-testid=reservation-form-guest_phone] input').fill('600111222');
    await form.locator('[data-testid=reservation-form-time] input').fill('21:00');
  },
  keys: ['guest_phone', 'guest_name', 'time'],
  created: `select count(*) from reservation_reservation where guest_name like '${TAG}%'`,
};

testTheMarksGoOneByOne([ZONE, RESERVATION]);
