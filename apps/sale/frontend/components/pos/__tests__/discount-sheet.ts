// The till's discount sheet, open and mounted in the sale app's harness as the till opens it: for the ticket (no line
// name), nothing applied yet. `open` is whether it is still open.
import { h, ref } from 'vue';

import { mountSale, type MountOptions } from '../../../__tests__/mount-sale';
import DiscountSheet from '../DiscountSheet.vue';

export async function mountDiscountSheet(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const open = ref(true);
  const m = await mountSale(
    {
      setup: () => () =>
        h(DiscountSheet, {
          open: open.value,
          'onUpdate:open': (v: boolean) => (open.value = v),
          name: null,
          amount: 0,
          pending: false,
          error: null,
          ...props,
        }),
    },
    options,
  );
  return { ...m, open };
}
