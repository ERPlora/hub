// The book and the waitlist and the guests' phone and email (RESERVATION-F06, F14, BASE-F119): the «Phone» column only
// for whoever sees the customers' contact details, never sortable, and a search box that says what it looks into.
import { DataTable } from '@erplora/ui/components';
import type { SessionMe } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, mountReservation, OWNER, WITHOUT_CONTACT } from '../__tests__/mount-reservation';
import ReservationsPage from './ReservationsPage.vue';
import WaitlistPage from './WaitlistPage.vue';

const PAGES = [
  ['ReservationsPage', ReservationsPage, '/reservation/reservations'],
  ['WaitlistPage', WaitlistPage, '/reservation/waitlist'],
] as const;

/** The table `page` paints for `session`, in `locale`: its columns (key, sortable) and its search hint. */
async function painted(page: Component, path: string, session: SessionMe, locale: 'en' | 'es' = 'en') {
  const m = await mountReservation(page, { path, session, locale });
  await m.live();
  const prop = <T>(name: string) => (m.wrapper.findComponent(DataTable as unknown as Component).props() as Record<string, unknown>)[name] as T;
  const columns = prop<{ key: string; sortable?: boolean }[]>('columns');
  return {
    phone: columns.filter((c) => c.key === 'guest_phone').map((c) => !!c.sortable),
    placeholder: prop<string>('searchPlaceholder'),
  };
}

describe.each(PAGES)('%s: the guests’ contact details', (_, page, path) => {
  it.each([OWNER, EMPLOYEE])('whoever sees them has «Phone», not sortable, and a search into them', async (session) => {
    const s = await painted(page, path, session);
    expect(s).toEqual({ phone: [false], placeholder: 'Search guest, phone or email…' });
  });

  it('whoever does not has no «Phone» and a search by the guest’s name, in both languages', async () => {
    expect(await painted(page, path, WITHOUT_CONTACT)).toEqual({ phone: [], placeholder: 'Search guest…' });
    expect((await painted(page, path, WITHOUT_CONTACT, 'es')).placeholder).toBe('Buscar cliente…');
  });
});
