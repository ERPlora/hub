// Test helper of Sell: the page mounted with its till settings read and a check open, the one the server answers to
// the first product added.
import type { SessionMe } from '@erplora/ui/shell';

import PosCatalog from '../components/pos/PosCatalog.vue';
import { product, settings } from '../components/pos/__tests__/fixtures';
import type { OrderOut } from '../operations';
import PosPage from '../pages/PosPage.vue';
import { MANAGER, mountSale, settle } from './mount-sale';

export async function posWithCheck(check: OrderOut, options: { session?: SessionMe; locale?: 'en' | 'es' } = {}) {
  const m = await mountSale(PosPage, { session: options.session ?? MANAGER, locale: options.locale });
  await m.live();
  await m.result('sale.pos_settings.get', settings());
  m.net.onApi(() => Response.json(check));
  m.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
  await settle();
  await m.reopen();
  return m;
}
