// SERVICE-F16 «Ver quién ha comprado un bono»: the sheet «Sold vouchers» of a package follows
// `service.grant.list` live, the most recent first: Active or Voided, the customer (or their reference
// when the card is gone), the date, the amount, the sessions used and left (or «no limit»), the sale,
// the expiry, what was given or corrected afterwards and, on a voided one, who, when and why. Adjust
// and Void show where they apply and for whoever may; they open their dialogs.
import { StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { Business } from '../../../../base/frontend/operations';
import { business, click, flush, MANAGER, EMPLOYEE, mountService, OWNER, page, POLISH, settle } from '../__tests__/mount-service';
import { grant } from '../__tests__/grant';
import { PACKAGE } from '../__tests__/package';
import GrantAdjustModal from './GrantAdjustModal.vue';
import GrantRedeemModal from './GrantRedeemModal.vue';
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

async function setup(session = MANAGER, locale: 'en' | 'es' = 'en', answer: Business | null = business()) {
  const m = await mountService(GrantsSheet, { props: { open: true, pkg: PACKAGE }, session, locale, business: answer });
  await settle();
  await m.live();
  const text = (id: string) => m.inDoc(`service-grants-row-${id}`)?.textContent ?? '';
  return { ...m, text, show: (data: unknown) => m.result(OP, data) };
}

describe('GrantsSheet', () => {
  // flow service-business-currency: what was paid is the business's currency, never a euro fixed in the app.
  it('paints the amount paid in złoty for a business in Poland', async () => {
    const s = await setup(MANAGER, 'en', business(POLISH));
    await s.show(page(ROWS));
    expect(s.text('g1').replace(/\s/g, ' ')).toContain('zł 90.00');
    expect(s.text('g1')).not.toContain('€');
  });

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
    for (const part of ['Active', 'Customer: Lucía Pérez', 'Oct 1, 2026', '€90.00', '2 used · 3 left', 'Sale: sale-9', 'Expires Mar 30, 2027', 'Given afterwards: +2 sessions, +30 days']) {
      expect(first, part).toContain(part);
    }
    expect(s.text('g2')).toContain('Customer reference: cust-2');
    expect(s.text('g2')).toContain('0 used · no limit');
    expect(s.text('g2')).toContain('Never expires');
    expect(s.text('g3')).toContain('Voided by boss on Oct 5, 2026');
    expect(s.text('g3')).toContain('wrong customer');
    expect(s.text('g3')).toContain('Corrected afterwards: −1 session');
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

  // SERVICE-F21 (hub#1058): a session is spent outside the till from the row of a live voucher, by whoever may spend one.
  it('offers «Spend a session» on every voucher that can still be used, and opens its dialog on that voucher and package', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(['g1', 'g2', 'g3'].map((id) => s.inDoc(`service-grants-redeem-${id}`)?.textContent?.trim() ?? null)).toEqual([
      'Spend a session',
      'Spend a session',
      null,
    ]);
    await click(s.inDoc('service-grants-redeem-g2'));
    await flush();
    const redeeming = s.wrapper.findComponent(GrantRedeemModal);
    expect([redeeming.props('open'), redeeming.props('grant'), redeeming.props('pkg')]).toEqual([true, ROWS[1], PACKAGE]);
  });

  // The market's pattern (and this sheet's: Adjust and Void show only where they apply): a voucher that has expired or
  // has no sessions left offers nothing to spend; its row already says why, and Adjust gives it sessions or days back.
  it('offers no «Spend a session» on a voucher that has expired or has no sessions left; an unlimited one keeps it', async () => {
    const s = await setup();
    await s.show(
      page([
        grant({ id: 'spent', used: 5, remaining: 0 }),
        grant({ id: 'late', is_expired: true, expires_at: '2026-10-30T10:00:00Z' }),
        grant({ id: 'open', max_uses: null, remaining: null }),
      ]),
    );
    expect(['spent', 'late', 'open'].map((id) => s.inDoc(`service-grants-redeem-${id}`) !== null)).toEqual([false, false, true]);
    expect(s.inDoc('service-grants-adjust-spent')).not.toBeNull();
  });

  it('an employee spends sessions too; who may not spend them sees no button', async () => {
    const employee = await setup(EMPLOYEE);
    await employee.show(page(ROWS));
    expect(employee.inDoc('service-grants-redeem-g1')).not.toBeNull();
    const reader = await setup({ ...OWNER, permissions: OWNER.permissions.filter((p) => p !== 'service.redeem_package') });
    await reader.show(page(ROWS));
    expect(reader.inDoc('service-grants-redeem-g1')).toBeNull();
  });

  it('an employee sees the sales but neither adjusts nor voids', async () => {
    const s = await setup(EMPLOYEE);
    await s.show(page(ROWS));
    expect(s.text('g1')).toContain('Lucía Pérez');
    expect([s.inDoc('service-grants-adjust-g1'), s.inDoc('service-grants-void-g2')]).toEqual([null, null]);
  });

  // hub#1147: what was given or corrected afterwards says one in the singular and several in the plural.
  it.each([
    { locale: 'en' as const, uses: 1, days: 1, given: 'Given afterwards: +1 session, +1 day', corrected: 'Corrected afterwards: −1 session' },
    { locale: 'en' as const, uses: 2, days: 30, given: 'Given afterwards: +2 sessions, +30 days', corrected: 'Corrected afterwards: −2 sessions' },
    { locale: 'es' as const, uses: 1, days: 1, given: 'Regalado después: +1 sesión, +1 día', corrected: 'Corregido después: −1 sesión' },
    { locale: 'es' as const, uses: 2, days: 30, given: 'Regalado después: +2 sesiones, +30 días', corrected: 'Corregido después: −2 sesiones' },
  ])('$uses and $days afterwards ($locale): «$given», «$corrected»', async ({ locale, uses, days, given, corrected }) => {
    const s = await setup(MANAGER, locale);
    await s.show(page([grant({ uses_added: uses, days_added: days, uses_removed: uses })]));
    expect([s.text('g1').includes(given), s.text('g1').includes(corrected)]).toEqual([true, true]);
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
    expect(s.inDoc('service-grants-redeem-g1')?.textContent?.trim()).toBe('Gastar una sesión');
  });
});
