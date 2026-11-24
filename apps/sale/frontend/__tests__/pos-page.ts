// Test helper of Sell: the page mounted with the till settings read, a product added from the catalogue, and the
// checks and the customer its tests share. The pieces they mount in place of others are in `pos-page-stubs.ts`.
import { afterEach, beforeEach, vi } from 'vitest';

import PosCatalog from '../components/pos/PosCatalog.vue';
import { line, memoryStorage, order, product, settings } from '../components/pos/__tests__/fixtures';
import PosPage from '../pages/PosPage.vue';
import { MANAGER, mountSale, settle } from './mount-sale';

/** Every test starts on a device that keeps nothing, and the globals a test stubs go with it. */
export function freshEachTest(): void {
  beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
  afterEach(() => {
    vi.unstubAllGlobals();
  });
}

export const CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: 'p1' })] });
export const TWO = order({ id: 'o1', version: 2, lines: [line({ id: 'l1' }), line({ id: 'l2', product_id: 'p2', name: 'Tea' })] });
export const LUCIA = {
  customer_id: 'c1',
  customer_name: 'Lucía',
  customer_tax_id: '',
  customer_address: '',
  customer_country: 'ES',
};

export async function setup(
  options: { settings?: Parameters<typeof settings>[0]; session?: typeof MANAGER; locale?: 'en' | 'es'; ready?: boolean; path?: string } = {},
) {
  const m = await mountSale(PosPage, { session: options.session, locale: options.locale, path: options.path });
  await m.live();
  if (options.ready !== false) await m.result('sale.pos_settings.get', settings(options.settings));
  const component = <T>(c: T) => m.wrapper.findComponent(c as never);
  const writes = () => m.sent().filter((c) => c.method === 'POST').map((c) => [c.path, c.body]);
  /** Every POST answers `body`. */
  const reply = (body: unknown) => m.net.onApi(() => Response.json(body));
  async function addProduct(id = 'p1', answer = CHECK) {
    reply(answer);
    m.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id }));
    await settle();
    await m.reopen();
  }
  return { ...m, component, writes, reply, addProduct };
}
