// Sales & POS → Sell without a connection (SALE-F01, SALE-F11, SALE-F20; WORKBOOK «Estados de cada pantalla»): the
// till keeps what it shows, says «Reconnecting…» above its grid while the live connection recovers, and a tap on a
// product or «Charge» that cannot reach the server says the connection is missing, never that the product's options
// or the kitchen failed.
import { toast, toastError } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { BYE, flush, MANAGER, settle } from '../__tests__/mount-sale';
import { CHECK, freshEachTest, setup } from '../__tests__/pos-page';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import { product } from '../components/pos/__tests__/fixtures';

freshEachTest();
afterEach(() => {
  document.documentElement.lang = '';
});

const NO_CONNECTION = 'No se pudo conectar con el servidor. Revisa tu conexión y vuelve a intentarlo en unos segundos.';
/** The till in Spanish, as the shell keeps the page's language in step with the person's. */
async function tillInSpanish(session = MANAGER) {
  document.documentElement.lang = 'es';
  return setup({ session, locale: 'es' });
}
const unreachable = () => Promise.reject(new TypeError('Failed to fetch'));

describe('PosPage without a connection', () => {
  it('says «Reconnecting…» above the grid while the live connection recovers, and the check stays', async () => {
    const s = await tillInSpanish();
    await s.addProduct();
    expect(s.find('pos-reconnecting').exists()).toBe(false);
    s.net.lastStream().push(BYE);
    await flush();
    expect(s.find('pos-reconnecting').text()).toBe('Reconectando…');
    expect(s.wrapper.findComponent(PosCart).props('order')).toMatchObject({ id: 'o1' });
  });

  it('a tap on a product says the connection is missing and adds nothing', async () => {
    const s = await tillInSpanish();
    s.net.onApi(unreachable);
    s.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
    await settle();
    expect(toastError).toHaveBeenCalledExactlyOnceWith(NO_CONNECTION);
    expect(s.wrapper.findComponent(PosCart).props('order')).toBeNull();
  });

  it('a tap on a product with options says the connection is missing, not that its options could not be read', async () => {
    const withModifiers = { ...MANAGER, permissions: [...MANAGER.permissions, 'modifier.view'], apps: [{ label: 'modifier', state: 'on' as const }] };
    const s = await tillInSpanish(withModifiers);
    s.net.onApi((call) => (call.url.startsWith('/api/modifier/groups/for_target') ? unreachable() : Response.json(CHECK)));
    s.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
    await settle();
    expect(s.writes()).toEqual([]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith(NO_CONNECTION);
  });

  it('«Charge» with Kitchen on says the connection is missing at the top and opens no checkout', async () => {
    const withKitchen = { ...MANAGER, permissions: [...MANAGER.permissions, 'kitchen.add_ticket'], apps: [{ label: 'kitchen', state: 'on' as const }] };
    const s = await tillInSpanish(withKitchen);
    await s.addProduct();
    s.net.onApi((call) => (call.url.startsWith('/api/kitchen/tickets/send') ? unreachable() : Response.json(CHECK)));
    s.wrapper.findComponent(PosCart).vm.$emit('charge');
    await settle();
    expect(s.wrapper.findComponent({ name: 'CheckoutSheet' }).props('open')).toBe(false);
    expect(toastError).toHaveBeenCalledExactlyOnceWith(NO_CONNECTION, { position: 'top' });
    expect(toast).not.toHaveBeenCalled();
  });
});
