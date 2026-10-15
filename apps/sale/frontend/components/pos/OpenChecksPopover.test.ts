// «Open checks» (WORKBOOK «Cuentas abiertas»; SALE-F17, F18): «Park this check» with its hint, «Tap a
// check to resume it.» and a row per open check of the business (title or amount, time and amount),
// newest first, 20 at a time, with its bin: a first tap arms it for 3 seconds, a second voids the check.
import { describe, expect, it } from 'vitest';

import { click, EMPLOYEE, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { orderRow, page, refused } from './__tests__/fixtures';
import OpenChecksPopover from './OpenChecksPopover.vue';

const OP = 'sale.order.list';

async function setup(props: Record<string, unknown> = {}, options: { locale?: 'en' | 'es'; session?: typeof EMPLOYEE } = {}) {
  const m = await mountSale(OpenChecksPopover, {
    props: { currentId: 'o1', parkingEnabled: true, hasLines: true, ...props },
    locale: options.locale,
    session: options.session,
  });
  await m.live();
  return m;
}

const ROWS = [
  orderRow({ id: 'o1', label: 'Current' }),
  orderRow({ id: 'o2', label: 'Ana — terrace', provisional_total: 1250, created_at: '2026-10-14T08:30:00' }),
  orderRow({ id: 'o3', label: '', provisional_total: 480, created_at: '2026-10-14T09:15:00' }),
];

describe('OpenChecksPopover: the list', () => {
  it('follows the open checks, 20 at a time', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ status: 'open', limit: 20, offset: 0 }]);
  });

  it('a row per open check but the one on screen: its title (or amount), time and amount', async () => {
    const m = await setup({}, { locale: 'es' });
    await m.result(OP, page(ROWS));
    expect(m.find('pos-parked-o1').exists()).toBe(false);
    const titled = m.find('pos-parked-o2');
    expect(titled.find('.pos-checks__name').text()).toBe('Ana — terrace');
    expect(plain(titled.find('.pos-checks__meta').text())).toBe('8:30 · 12,50 €');
    const untitled = m.find('pos-parked-o3');
    expect(plain(untitled.find('.pos-checks__name').text())).toBe('4,80 €');
    expect(untitled.find('.pos-checks__meta').text()).toBe('9:15');
  });

  it('a tap resumes that check', async () => {
    const m = await setup();
    await m.result(OP, page(ROWS));
    await click(m.find('pos-parked-o2').element);
    expect(m.wrapper.emitted('resume')).toEqual([[ROWS[1]]]);
  });

  it('says «No open checks» when there is none besides this one', async () => {
    const m = await setup({}, { locale: 'es' });
    await m.result(OP, page([ROWS[0]]));
    expect(m.find('pos-checks-empty').text()).toBe('No hay cuentas abiertas');
  });

  it('asks the next 20 when there are more', async () => {
    const m = await setup();
    await m.result(OP, page(ROWS, 45, 20));
    await click(m.find('pos-checks-more').element);
    await m.reopen();
    expect(m.params(OP).map((p) => p.offset)).toEqual([0, 20]);
  });
});

describe('OpenChecksPopover: parking', () => {
  it('«Park this check» with its hint, only where parked tickets are allowed', async () => {
    const m = await setup({}, { locale: 'es' });
    expect(m.find('pos-checks-park').text()).toBe('Aparcar esta cuenta');
    expect(m.find('pos-checks-hint').text()).toBe('Aparca la cuenta actual para retomarla más tarde. El título es opcional.');
    await click(m.find('pos-checks-park').element);
    expect(m.wrapper.emitted('park')).toHaveLength(1);
    const off = await setup({ parkingEnabled: false });
    expect(off.find('pos-checks-park').exists()).toBe(false);
  });
});

describe('OpenChecksPopover: deleting', () => {
  it('a first tap on the bin arms it; untouched for 3 seconds it disarms', async () => {
    const m = await setup();
    await m.result(OP, page(ROWS));
    const bin = () => m.find('pos-parked-o2-delete');
    expect(bin().attributes('aria-label')).toBe('Delete check');
    await click(bin().element);
    expect(bin().attributes('aria-label')).toBe('Tap again to delete — this voids the check');
    expect(m.sent()).toEqual([]);
    await m.clock.advance(3000);
    expect(bin().attributes('aria-label')).toBe('Delete check');
  });

  it('a second tap voids the check (it leaves the list with the next result)', async () => {
    const m = await setup();
    await m.result(OP, page(ROWS));
    m.answer(200, {});
    await click(m.find('pos-parked-o2-delete').element);
    await click(m.find('pos-parked-o2-delete').element);
    expect(m.sent()).toEqual([{ method: 'POST', path: '/api/sale/orders/void', query: {}, body: { order_id: 'o2' } }]);
  });

  it('a refusal says the check is still there, on top of the list', async () => {
    const m = await setup({}, { locale: 'es' });
    await m.result(OP, page(ROWS));
    m.net.onApi(() => refused('sale.order_unavailable', 'Esa cuenta ya no está abierta.'));
    await click(m.find('pos-parked-o2-delete').element);
    await click(m.find('pos-parked-o2-delete').element);
    expect(m.find('pos-checks-error').text()).toBe('Esa cuenta ya no está abierta.');
  });

  it('without the permission to void there is no bin on a check with something on it', async () => {
    const m = await setup({}, { session: EMPLOYEE });
    await m.result(OP, page(ROWS));
    expect(m.find('pos-parked-o2-delete').exists()).toBe(false);
  });

  it('an empty check is deleted by whoever builds checks (a party that left without ordering)', async () => {
    const m = await setup({}, { session: EMPLOYEE });
    await m.result(OP, page([...ROWS, orderRow({ id: 'o4', label: 'Table 4', provisional_total: 0, lines_count: 0 })]));
    expect(m.find('pos-parked-o3-delete').exists()).toBe(false);
    m.answer(200, {});
    await click(m.find('pos-parked-o4-delete').element);
    await click(m.find('pos-parked-o4-delete').element);
    expect(m.sent()).toEqual([{ method: 'POST', path: '/api/sale/orders/void', query: {}, body: { order_id: 'o4' } }]);
  });

  it('nobody who cannot build checks gets the bin, not even on an empty one', async () => {
    const m = await setup({}, { session: { ...EMPLOYEE, permissions: ['sale.view_sale'] } });
    await m.result(OP, page([orderRow({ id: 'o4', lines_count: 0, provisional_total: 0 })]));
    expect(m.find('pos-parked-o4-delete').exists()).toBe(false);
  });
});

describe('OpenChecksPopover: closing', () => {
  it('a tap outside closes it', async () => {
    const m = await setup();
    await click(m.find('pos-checks-backdrop').element);
    expect(m.wrapper.emitted('close')).toHaveLength(1);
  });
});
