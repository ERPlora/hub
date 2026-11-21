// Sell by weight (SALE-F10): a quantity typed on a line that does not fit the step of its unit is refused with the
// server's reason, and the line and its field stay as they were.
import { toastError } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MANAGER, mountSale, settle } from '../__tests__/mount-sale';
import PosCatalog from '../components/pos/PosCatalog.vue';
import QtyStepper from '../components/pos/QtyStepper.vue';
import { line, memoryStorage, order, product, refused, settings } from '../components/pos/__tests__/fixtures';
import PosPage from './PosPage.vue';

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));

const PRAWNS = line({ id: 'l1', unit: 'kg', quantity: '0.532', pricing_unit: 'kg' });
const CHECK = order({ id: 'o1', lines: [PRAWNS] });
const OFF_GRID = 'La cantidad no encaja con el escalón del producto (0,001 kg).';

async function sellingPrawns() {
  const m = await mountSale(PosPage, { session: MANAGER, locale: 'es' });
  await m.live();
  await m.result('sale.pos_settings.get', settings());
  m.net.onApi(() => Response.json(CHECK));
  m.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
  await settle();
  await m.reopen();
  const field = () => m.wrapper.findComponent(QtyStepper).find('input').element as HTMLInputElement;
  const lineWrites = () =>
    m
      .sent()
      .filter((call) => call.path === '/api/sale/orders/update_line')
      .map((call) => call.body);
  return { ...m, field, lineWrites };
}

async function confirm(el: HTMLInputElement, value: string) {
  el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  await settle();
}

describe('PosPage: a typed weight that does not fit the step of its unit', () => {
  it('says why in the server’s words and leaves the line and its field as they were', async () => {
    const s = await sellingPrawns();
    expect(s.field().value).toBe('0,532');
    s.net.onApi(() => refused('sale.quantity_off_grid', OFF_GRID));
    await confirm(s.field(), '1,2505');
    expect(s.lineWrites()).toEqual([{ order_id: 'o1', line_id: 'l1', quantity: '1.2505' }]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith(OFF_GRID);
    expect(s.field().value).toBe('0,532');
  });
});
