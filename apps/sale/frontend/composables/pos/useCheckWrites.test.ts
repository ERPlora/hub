import { toastError } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { freshEachTest, setup } from '../../__tests__/till';
import { product, refused } from '../../components/pos/__tests__/fixtures';

freshEachTest();

describe('useTill: adding products', () => {
  it('a refused product says the server’s words and the check stays as it was', async () => {
    const s = await setup();
    s.net.onApi(() => refused('sale.product_not_available', 'That product is no longer in the catalogue.'));
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('That product is no longer in the catalogue.');
    expect(s.till().order.value).toBeNull();
  });

  it('a failure nobody worded (a proxy’s error page) says «tap again»', async () => {
    const s = await setup();
    s.net.onApi(() => new Response('Bad gateway', { status: 502 }));
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(toastError).toHaveBeenCalledExactlyOnceWith("Couldn't save that item — tap again");
  });
});
