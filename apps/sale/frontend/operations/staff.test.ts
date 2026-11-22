// Who serves a check, as Sales answers it (apps/sale/schemas/orders.py): the check carries the person and the name
// it had when chosen, it opens with them, and `sale.order.set_staff` changes them. Checked by the type checker.
import type { InputOf, OutputOf } from '@erplora/ui/sdk';
import { describe, expectTypeOf, it } from 'vitest';

import type { OrderOpenIn, OrderOut } from '../operations';

describe('who serves a check', () => {
  it('comes back with the check, and a check opens with them', () => {
    expectTypeOf<OrderOut['staff_id']>().toEqualTypeOf<string | null>();
    expectTypeOf<OrderOut['staff_name']>().toEqualTypeOf<string>();
    expectTypeOf<OrderOpenIn['staff_id']>().toEqualTypeOf<string | null | undefined>();
  });

  it('is changed on an open check, «me» being nobody', () => {
    expectTypeOf<InputOf<'sale.order.set_staff'>>().toEqualTypeOf<{ order_id: string; staff_id: string | null }>();
    expectTypeOf<OutputOf<'sale.order.set_staff'>>().toEqualTypeOf<OrderOut>();
  });
});
