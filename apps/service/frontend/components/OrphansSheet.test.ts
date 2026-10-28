// SERVICE-F30 «Rescatar los bonos sin cliente»: the sheet follows `service.grant.list_orphans` live, the
// most recent first: what is left («{n} session(s) left», «No session limit» or «Fully used»), the
// voucher, the amount, when the card was deleted, «Expired» if it is, and the customer's reference.
import { describe, expect, it, vi } from 'vitest';

import type { OrphanOut } from '../operations';
import type { Business } from '../../../../base/frontend/operations';
import { business, JAPANESE, mountService, page, settle } from '../__tests__/mount-service';
import OrphansSheet from './OrphansSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'service.grant.list_orphans';
const orphan = (id: string, over: Partial<OrphanOut> = {}): OrphanOut => ({
  id,
  package_id: 'p1',
  package_name: 'Bono 5 cortes',
  customer_id: 'cust-1',
  customer_deleted_at: '2026-10-09T10:00:00Z',
  granted_at: '2026-10-01T10:00:00Z',
  amount: 9000,
  remaining: 3,
  is_expired: false,
  ...over,
});
const ROWS = [orphan('o1'), orphan('o2', { remaining: null, customer_id: 'cust-2' }), orphan('o3', { remaining: 0, is_expired: true })];

async function setup(locale: 'en' | 'es' = 'en', answer: Business | null = business()) {
  const m = await mountService(OrphansSheet, { props: { open: true }, locale, business: answer });
  await settle();
  await m.live();
  const text = (id: string) => m.inDoc(`service-orphans-row-${id}`)?.textContent ?? '';
  return { ...m, text, show: (data: unknown) => m.result(OP, data) };
}

describe('OrphansSheet', () => {
  // flow service-business-currency: the amount paid is the business's currency (the yen without decimals).
  it('paints the amount paid in yen for a business in Japan', async () => {
    const s = await setup('en', business(JAPANESE));
    await s.show(page(ROWS, 30));
    expect(s.text('o1')).toContain('¥9,000');
  });

  it('follows the vouchers whose card was deleted, 20 first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 20, offset: 0 }]);
    expect(s.inDoc('service-orphans-title')?.textContent).toContain('Vouchers with no customer');
  });

  it('paints what is left, the voucher, the amount, when the card went and the reference', async () => {
    const s = await setup();
    await s.show(page(ROWS, 30));
    for (const part of ['3 session(s) left', 'Bono 5 cortes', '€90.00', 'Customer deleted on Oct 9, 2026', 'Customer reference: cust-1']) {
      expect(s.text('o1'), part).toContain(part);
    }
    expect(s.text('o2')).toContain('No session limit');
    expect(s.text('o3')).toContain('Fully used');
    expect(s.text('o3')).toContain('Expired');
    expect(s.inDoc('service-orphans-count')?.textContent).toContain('3 of 30');
  });

  it('says when no voucher lost its customer', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.inDoc('service-orphans-empty')?.textContent).toContain('No voucher has lost its customer.');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.show(page(ROWS));
    expect(s.text('o1')).toContain('Quedan 3 sesión(es)');
    expect(s.text('o3')).toContain('Agotado');
  });
});
