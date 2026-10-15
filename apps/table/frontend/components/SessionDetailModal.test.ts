// «Details» of a check (WORKBOOK «Sesiones»; TABLE-F22): zone, server, status, guests, opened, closed, time,
// charged, customer and notes, in the business's hours; a parked one says it has no table.
import { describe, expect, it, vi } from 'vitest';

import { mountTable, settle } from '../__tests__/mount-table';
import { NOW, sessionRow, SETTINGS } from '../__tests__/tables';
import type { SessionOut } from '../operations';
import SessionDetailModal from './SessionDetailModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function detail(session: SessionOut, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(SessionDetailModal, { props: { open: true, session, settings: SETTINGS, now: NOW }, locale });
  await settle();
  const value = (name: string) => m.inDoc(`table-session-detail-${name}`)?.textContent?.trim();
  return { ...m, value };
}

describe('SessionDetailModal', () => {
  it('shows every field of a closed check in the business’s hours', async () => {
    const d = await detail(
      sessionRow({ status: 'closed', closed_at: '2026-10-14T19:35:00Z', paid_total: 4250, notes: 'Allergy: nuts', customer_name: 'Ana García' }),
      'es',
    );
    expect(d.inDoc('table-session-detail')?.getAttribute('aria-label')).toBe('Sesión · Mesa 4');
    expect([d.value('zone'), d.value('waiter'), d.value('status'), d.value('guests')]).toEqual(['Dining room', 'Luis', 'Cerrada', '3']);
    expect([d.value('opened'), d.value('closed'), d.value('duration')]).toEqual(['21:05', '21:35', '30 min']);
    expect([d.value('paid'), d.value('customer'), d.value('notes')]).toEqual(['42,50 €', 'Ana García', 'Allergy: nuts']);
  });

  it('a parked open check has no table, no close and nothing charged yet', async () => {
    const d = await detail(sessionRow({ status: 'parked', table_id: null, table_number: null, zone_name: null }));
    expect(d.inDoc('table-session-detail')?.getAttribute('aria-label')).toBe('Session · No table (parked)');
    expect([d.value('zone'), d.value('closed'), d.value('paid'), d.value('notes')]).toEqual(['—', '—', '—', '—']);
  });
});
