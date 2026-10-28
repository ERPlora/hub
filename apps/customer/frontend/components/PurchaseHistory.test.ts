// «Purchases» on the card (CUSTOMER-F23): each sale with its date, amount and status («Paid» or
// «Voided»), newest first, 50 at a time, filterable by status; «No purchases.» when there are none. Each amount in
// the currency its sale was paid in, with the decimals the server counts (customer-business-currency); one without
// a currency of its own, in the business's.
import { formatDateTime, StatusPill } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { pageOf } from '../__tests__/fixtures';
import { business, errorFrame, flush, type MountOptions, mountCustomer, POLISH, subId } from '../__tests__/mount-customer';
import { formatMoney, type Money } from '../lib/money';
import type { PurchaseRow } from '../operations';
import PurchaseHistory from './PurchaseHistory.vue';

const purchase = (id: string, status: PurchaseRow['status'], amount: number): PurchaseRow => ({
  id,
  customer_id: 'c1',
  sale_id: `s-${id}`,
  amount,
  currency: 'EUR',
  currency_decimals: 2,
  status,
  recorded_at: '2026-10-01T10:00:00Z',
  voided_at: null,
  void_reason: '',
});
const LIST = 'customer.purchase.list';
const EUR: Money = { currency: 'EUR', decimals: 2 };

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(PurchaseHistory, { props: { customerId: 'c1' }, ...options });
  const call = await m.live();
  const filter = async (value: string) => {
    m.wrapper.get('[data-testid="customer-purchases-filter"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  };
  return { ...m, call, filter };
}

describe('PurchaseHistory: the currency of each sale (customer-business-currency)', () => {
  const amounts = (s: Awaited<ReturnType<typeof setup>>) =>
    s.wrapper.findAll('.customer-purchases__amount').map((a) => a.text().replace(/\s/g, ' '));

  it('in Poland a sale is in złoty; one paid in euros before keeps its euros; the yen has no decimals', async () => {
    const s = await setup({ locale: 'es' });
    await s.result(s.call, 'base.business.get', business(POLISH));
    await s.result(
      s.call,
      LIST,
      pageOf([
        { ...purchase('p1', 'confirmed', 2550), currency: 'PLN', currency_decimals: 2 },
        purchase('p2', 'confirmed', 1000),
        { ...purchase('p3', 'confirmed', 2550), currency: 'JPY', currency_decimals: 0 },
      ]),
    );
    expect(amounts(s)).toEqual(['25,50 zł', '10,00 €', '2550 ¥']);
  });

  it('a sale without a currency of its own is in the business\'s, and a bare figure until it answers', async () => {
    const s = await setup();
    await s.result(s.call, LIST, pageOf([{ ...purchase('p1', 'confirmed', 2550), currency: '', currency_decimals: null }]));
    expect(amounts(s)).toEqual(['25.50']);
    await s.result(s.call, 'base.business.get', business(POLISH));
    expect(amounts(s)).toEqual(['zł 25.50']);
  });
});

describe('PurchaseHistory', () => {
  it('follows the card\'s purchases, newest first, 50 at a time', async () => {
    const s = await setup();
    expect(s.params(LIST)).toEqual([{ customer_id: 'c1', limit: 50, offset: 0 }]);
  });

  it('paints date, amount and status of each sale', async () => {
    const s = await setup();
    await s.result(s.call, LIST, pageOf([purchase('p1', 'confirmed', 2550), purchase('p2', 'voided', 1000)]));
    const rows = s.wrapper.findAll('[data-testid="customer-purchase"]');
    expect(rows.map((r) => r.get('.customer-purchases__date').text())).toEqual([
      formatDateTime('2026-10-01T10:00:00Z', 'en'),
      formatDateTime('2026-10-01T10:00:00Z', 'en'),
    ]);
    expect(rows.map((r) => r.get('.customer-purchases__amount').text())).toEqual([formatMoney(2550, 'en', EUR), formatMoney(1000, 'en', EUR)]);
    expect(s.wrapper.findAllComponents(StatusPill).map((p) => [p.props('label'), p.props('tone')])).toEqual([
      ['Paid', 'success'],
      ['Voided', 'neutral'],
    ]);
  });

  it('a refund is a line of its own, its amount negative, marked «Refund» (CUSTOMER-F22)', async () => {
    const s = await setup();
    await s.result(s.call, LIST, pageOf([purchase('p3', 'refunded', -1210)]));
    expect(s.wrapper.get('.customer-purchases__amount').text()).toBe(formatMoney(-1210, 'en', EUR));
    expect(s.wrapper.findAllComponents(StatusPill).map((p) => [p.props('label'), p.props('tone')])).toEqual([['Refund', 'warning']]);
    expect(s.wrapper.findAll('[data-testid="customer-purchases-filter"] ion-select-option').map((o) => o.text())).toEqual([
      'All',
      'Paid',
      'Voided',
      'Refund',
    ]);
  });

  it('filters by status on the server; «All» drops it', async () => {
    const s = await setup();
    await s.filter('voided');
    expect(s.params(LIST)).toEqual([{ customer_id: 'c1', status: 'voided', limit: 50, offset: 0 }]);
    await s.filter('all');
    expect(s.params(LIST)).toEqual([{ customer_id: 'c1', limit: 50, offset: 0 }]);
  });

  it('«Show more» grows the window, never asking for more than 100 at once', async () => {
    const s = await setup();
    await s.result(s.call, LIST, { ...pageOf([purchase('p1', 'confirmed', 1)]), total: 300 });
    for (let i = 0; i < 2; i++) {
      await s.wrapper.get('[data-testid="customer-purchases-more"]').trigger('click');
      await flush();
    }
    const windows = s.params(LIST) as { limit: number; offset: number }[];
    expect(windows.map((w) => [w.offset, w.limit]).sort((a, b) => a[0] - b[0])).toEqual([
      [0, 100],
      [100, 50],
    ]);
  });

  it('says «No purchases.»; a failed load says so', async () => {
    const s = await setup();
    await s.result(s.call, LIST, pageOf([]));
    expect(s.wrapper.get('[data-testid="customer-purchases-empty"]').text()).toBe('No purchases.');
    s.call.push(errorFrame(subId(s.client, LIST), 'boom'));
    await flush();
    expect(s.wrapper.get('[data-testid="customer-purchases-error"]').text()).toContain('The purchases could not be loaded');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.result(s.call, LIST, pageOf([purchase('p1', 'confirmed', 1)]));
    expect(s.wrapper.get('h3').text()).toBe('Compras');
    expect(s.wrapper.findComponent(StatusPill).props('label')).toBe('Cobrada');
  });
});
