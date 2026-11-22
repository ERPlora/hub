// Test helper of the booking panel (ReservationFormModal): mounted closed and then opened, as the book opens it, with
// what it reads answered: the free tables and the card picked from Customers.
import type { SessionMe } from '@erplora/ui/shell';

import ReservationFormModal from '../components/ReservationFormModal.vue';
import { mountReservation, settle } from './mount-reservation';

export interface PanelOptions {
  props?: Record<string, unknown>;
  locale?: 'en' | 'es';
  session?: SessionMe;
  /** What `reservation.availability.tables` answers. */
  tables: unknown;
  /** What `customer.customer.detail` answers for the card picked. */
  card: unknown;
}

export async function openBookingPanel(options: PanelOptions) {
  const m = await mountReservation(ReservationFormModal, {
    props: { open: false, reservation: null, day: '2026-10-15', ...options.props },
    locale: options.locale,
    ...(options.session ? { session: options.session } : {}),
  });
  m.answerBy({
    '/api/reservation/availability/tables': [200, options.tables],
    '/api/customer/customers/detail': [200, options.card],
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const bodies = (path: string) => m.sent().filter((call) => call.path === path).map((call) => call.body);
  return { ...m, bodies };
}
