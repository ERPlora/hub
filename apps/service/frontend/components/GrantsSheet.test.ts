// SERVICE-F16 «Ver quién ha comprado un bono»: the sheet «Sold vouchers» of a package follows
// `service.grant.list` live, the most recent first: Active or Voided, the customer (or their reference
// when the card is gone), the date, the amount, the sessions used and left (or «no limit»), the sale,
// the expiry, what was given or corrected afterwards and, on a voided one, who, when and why. Adjust
// and Void show where they apply and for whoever may; they open their dialogs.
import { StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, flush, MANAGER, EMPLOYEE, mountService, page, settle } from '../__tests__/mount-service';
import { grant } from '../__tests__/grant';
import { PACKAGE } from '../__tests__/package';
import GrantAdjustModal from './GrantAdjustModal.vue';
import GrantVoidModal from './GrantVoidModal.vue';
import GrantsSheet from './GrantsSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'service.grant.list';
const ROWS = [
  grant({ uses_added: 2, days_added: 30, sale_id: 'sale-9' }),
  grant({ id: 'g2', customer_name: null, customer_id: 'cust-2', max_uses: null, remaining: null, expires_at: null, used: 0, can_void: true, can_adjust: false }),
  grant({ id: 'g3', status: 'voided', voided_at: '2026-10-05T10:00:00Z', voided_by: 'boss', void_reason: 'wrong customer', can_adjust: false, uses_removed: 1 }),
];

async function setup(session = MANAGER, locale: 'en' | 'es' = 'en') {
  const m = await mountService(GrantsSheet, { props: { open: true, pkg: PACKAGE }, session, locale });
  await settle();
  await m.live();
  const text = (id: string) => m.inDoc(`service-grants-row-${id}`)?.textContent ?? '';
  return { ...m, text, show: (data: unknown) => m.result(OP, data) };
}

describe('GrantsSheet', () => {
  it('follows the sales of the package, 20 first, named after it', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ package_id: 'p1', limit: 20, offset: 0 }]);
    expect(s.inDoc('service-grants-title')?.textContent).toContain('Sold vouchers — Bono 5 cortes');
    expect(s.inDoc('service-grants-loading')?.textContent).toContain('Loading…');
  });

  it('paints each purchase as the old sheet did', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const first = s.text('g1');
    for (const part of ['Active', 'Customer: Lucía Pérez', 'Oct 1, 2026', '€90.00', '2 used · 3 left', 'Sale: sale-9', 'Expires Mar 30, 2027', 'Given afterwards: +2 session(s), +30 day(s)']) {
      expect(first, part).toContain(part);
    }
    expect(s.text('g2')).toContain('Customer reference: cust-2');
    expect(s.text('g2')).toContain('0 used · no limit');
    expect(s.text('g2')).toContain('Never expires');
    expect(s.text('g3')).toContain('Voided by boss on Oct 5, 2026');
    expect(s.text('g3')).toContain('wrong customer');
    expect(s.text('g3')).toContain('Corrected afterwards: −1 session(s)');
    const pills = s.wrapper.findAllComponents(StatusPill).map((p) => p.props('label'));
    expect(pills).toEqual(['Active', 'Active', 'Voided']);
  });

  it('offers Adjust and Void where they apply, and opens their dialogs', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect([s.inDoc('service-grants-adjust-g1'), s.inDoc('service-grants-void-g1')].map(Boolean)).toEqual([true, false]);
    expect([s.inDoc('service-grants-adjust-g2'), s.inDoc('service-grants-void-g2')].map(Boolean)).toEqual([false, true]);
    expect([s.inDoc('service-grants-adjust-g3'), s.inDoc('service-grants-void-g3')].map(Boolean)).toEqual([false, false]);
    await click(s.inDoc('service-grants-void-g2'));
    await flush();
    const voiding = s.wrapper.findComponent(GrantVoidModal);
    expect([voiding.props('open'), voiding.props('grant')]).toEqual([true, ROWS[1]]);
    await click(s.inDoc('service-grants-adjust-g1'));
    await flush();
    const adjusting = s.wrapper.findComponent(GrantAdjustModal);
    expect([adjusting.props('open'), adjusting.props('grant')]).toEqual([true, ROWS[0]]);
  });

  it('an employee sees the sales but neither adjusts nor voids', async () => {
    const s = await setup(EMPLOYEE);
    await s.show(page(ROWS));
    expect(s.text('g1')).toContain('Lucía Pérez');
    expect([s.inDoc('service-grants-adjust-g1'), s.inDoc('service-grants-void-g2')]).toEqual([null, null]);
  });

  it('says when nobody bought it, and when the sales cannot be loaded', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.inDoc('service-grants-empty')?.textContent).toContain('Nobody has bought this voucher yet.');
  });

  it('speaks Spanish', async () => {
    const s = await setup(MANAGER, 'es');
    await s.show(page(ROWS));
    expect(s.text('g1')).toContain('2 usadas · quedan 3');
    expect(s.text('g1')).toContain('Cliente: Lucía Pérez');
    expect(s.inDoc('service-grants-title')?.textContent).toContain('Bonos vendidos — Bono 5 cortes');
  });
});
