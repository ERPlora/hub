// A ticket's detail (WORKBOOK «Pantallas · Comandas»): tapping a row opens it, live
// (`kitchen.ticket.get`): its destination, type, status, waiter and when it was sent, its notes and its
// dishes with their quantity, station and state (a voided one with its reason).
import { describe, expect, it, vi } from 'vitest';

import { item, SETTINGS, ticket } from '../__tests__/kitchen';
import { errorFrame, flush, mountKitchen, settle } from '../__tests__/mount-kitchen';
import TicketDetailModal from './TicketDetailModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(TicketDetailModal, { props: { open: true, ticketId: 't1', timezone: SETTINGS.timezone }, locale });
  await m.live();
  await settle();
  return m;
}

describe('TicketDetailModal', () => {
  it('follows the ticket and lists its dishes with their station and state', async () => {
    const m = await setup();
    expect(m.params('kitchen.ticket.get')).toEqual([{ ticket_id: 't1' }]);
    await m.result(
      'kitchen.ticket.get',
      ticket('t1', {
        notes: 'Allergic to nuts',
        items: [
          item('i1', { name: 'Burger', quantity: '2.000', station_name: 'Grill', status: 'ready' }),
          item('i2', { name: 'Fries', status: 'voided', void_reason: 'Cold' }),
        ],
      }),
    );
    await flush();
    expect(m.inDoc('kitchen-ticket-detail')?.getAttribute('aria-label')).toBe('Ticket 20261014-0012');
    const body = m.inDoc('kitchen-ticket-detail-body')?.textContent ?? '';
    for (const words of ['Table 4', 'Dine in', 'To prepare', 'luis', 'Allergic to nuts', 'Burger', 'Grill', 'Ready', 'Fries', 'Voided', 'Cold']) {
      expect(body, words).toContain(words);
    }
  });

  it('says when it could not load', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId('kitchen.ticket.get'), 'not_found'));
    await flush();
    expect(m.inDoc('kitchen-ticket-detail-error')?.textContent).toContain('Could not load the ticket');
  });

  it('speaks Spanish', async () => {
    const m = await setup('es');
    await m.result('kitchen.ticket.get', ticket('t1'));
    await flush();
    expect(m.inDoc('kitchen-ticket-detail')?.getAttribute('aria-label')).toBe('Comanda 20261014-0012');
    expect(m.inDoc('kitchen-ticket-detail-body')?.textContent).toContain('Por preparar');
  });
});
