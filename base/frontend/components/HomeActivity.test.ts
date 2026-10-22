// «Activity» on the Home (BASE-G129): the last 100 sales of Sales (`sale.sale.list`, live), only while Sales is
// on in this hub, with the words of the sales history; a failed read says so with «Retry», never «no sales».
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountBase, OWNER, subId } from '../__tests__/mount-base';
import HomeActivity from './HomeActivity.vue';

const WITH_SALES: SessionMe = { ...OWNER, permissions: [...OWNER.permissions, 'sale.view'], apps: [{ label: 'sale', state: 'on' }] };

function sale(id: string, fields: Record<string, unknown> = {}) {
  return {
    id,
    number: `T-${id}`,
    business_day: '2026-10-22',
    created_at: '2026-10-22T09:30:00+02:00',
    status: 'completed',
    document_type: 'simplified',
    customer_id: null,
    customer_name: 'Ana',
    payment_method_name: 'Efectivo',
    staff_id: null,
    total: 1250,
    tax_total: 217,
    refunded_total: 0,
    refundable_total: 1250,
    sessions_to_return: 0,
    has_refunds: false,
    invoice_status: 'issued',
    documents_pending: false,
    ...fields,
  };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('HomeActivity', () => {
  it('follows the last 100 sales, newest first, while Sales is on', async () => {
    const m = await mountBase(HomeActivity, { session: WITH_SALES });
    await m.live();
    expect(m.client.stream.subscriptions('sale.sale.list').map((sub) => sub.params)).toEqual([
      { limit: 100, offset: 0, sort: 'created_at', dir: 'desc' },
    ]);
  });

  it('paints date, sale, customer, method, amount in euros and the status in the history’s words', async () => {
    const m = await mountBase(HomeActivity, { session: WITH_SALES, locale: 'es' });
    const call = await m.live();
    await m.result(call, 'sale.sale.list', {
      rows: [sale('1'), sale('2', { status: 'voided', total: 500 }), sale('3', { status: 'parked' })],
      total: 3,
      limit: 100,
      offset: 0,
    });
    const rows = m.wrapper.findAll('[data-testid="home-activity-row"]');
    expect(rows).toHaveLength(3);
    expect(rows[0].text()).toContain('T-1');
    expect(rows[0].text()).toContain('Ana');
    expect(rows[0].text()).toContain('Efectivo');
    expect(rows[0].text()).toContain('12,50 €');
    expect(m.wrapper.findAll('[data-testid="home-activity-status"]').map((pill) => [pill.text(), pill.attributes('data-tone')])).toEqual([
      ['Completada', 'success'],
      ['Anulada', 'danger'],
      ['Otro', 'neutral'],
    ]);
  });

  it('without Sales on, asks nothing and shows the empty table', async () => {
    const m = await mountBase(HomeActivity, { session: { ...OWNER, apps: [{ label: 'sale', state: 'off' }] } });
    await flush();
    expect(m.client.stream.subscriptions('sale.sale.list')).toEqual([]);
    expect(m.wrapper.findAll('[data-testid="home-activity-row"]')).toHaveLength(0);
    expect(m.wrapper.find('[data-testid="home-activity-error"]').exists()).toBe(false);
  });

  it('a failed read says so with «Retry», never as «no sales»', async () => {
    const m = await mountBase(HomeActivity, { session: WITH_SALES, locale: 'es' });
    const call = await m.live();
    call.push(errorFrame(subId(m.client, 'sale.sale.list'), 'internal'));
    await flush();
    const error = m.wrapper.get('[data-testid="home-activity-error"]');
    expect(error.text()).toContain('No se han podido cargar las últimas ventas');
    expect(error.find('[data-testid="home-activity-retry"]').exists()).toBe(true);
  });
});
