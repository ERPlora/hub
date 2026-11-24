import { describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountInventory, ok, product as row, refusal } from '../__tests__/mount-inventory';
import { useFlagActions } from './useFlagActions';

type Product = Parameters<ReturnType<typeof useFlagActions>['run']>[1];
const product = (fields: Record<string, unknown> = {}) => row(fields) as Product;

async function setup() {
  let flags: ReturnType<typeof useFlagActions> | undefined;
  const error = ref('');
  const Probe = defineComponent({
    setup() {
      flags = useFlagActions(error);
      return () => h('div');
    },
  });
  const m = await mountInventory(Probe);
  return { ...m, flags: () => flags!, error };
}

const SOLD = product({ is_sold_out: true });
const HIDDEN = product({ show_on_website: false });

describe('useFlagActions', () => {
  it('offers one action of each pair, by what the product is now, all in «⋮»', async () => {
    const s = await setup();
    const offered = (one: Product) => s.flags().actions.value.filter((a) => !a.hidden?.(one)).map((a) => a.id);

    expect(offered(product())).toEqual(['sold_out', 'hide_from_website']);
    expect(offered(SOLD)).toEqual(['back_on_sale', 'hide_from_website']);
    expect(offered(HIDDEN)).toEqual(['sold_out', 'show_on_website']);
    expect(s.flags().actions.value.every((a) => a.menuOnly)).toBe(true);
  });

  it('runs each action by its own operation and leaves any other to the page', async () => {
    const s = await setup();
    s.net.onApi(() => ok(product()));

    expect(['sold_out', 'back_on_sale', 'hide_from_website', 'show_on_website', 'edit'].map((id) => s.flags().run(id, product()))).toEqual([true, true, true, true, false]);
    await flush();
    expect(s.calls('/api/inventory/products/sold_out').map((call) => s.body(call))).toEqual([
      { id: 'p1', sold_out: true },
      { id: 'p1', sold_out: false },
    ]);
    expect(s.calls('/api/inventory/products/update').map((call) => s.body(call))).toEqual([
      { id: 'p1', show_on_website: false },
      { id: 'p1', show_on_website: true },
    ]);
  });

  it('says a refusal, and clears it on the next try', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(403, 'permission_denied', 'You do not have permission.'));
    s.flags().run('hide_from_website', product());
    await flush();
    expect(s.error.value).toBe('You do not have permission.');

    s.net.onApi(() => ok(product()));
    s.flags().run('show_on_website', HIDDEN);
    expect(s.error.value).toBe('');
  });
});
