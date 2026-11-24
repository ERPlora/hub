// The bill the device printed, as Sales notes it (apps/sale/schemas/orders.py): `sale.order.note_bill` takes the
// open check and answers which check and when its bill was first printed (TABLE-F34). Checked by the type checker.
import type { InputOf, OutputOf } from '@erplora/ui/sdk';
import { describe, expectTypeOf, it } from 'vitest';

import type { OrderRefIn } from '../operations';
import type { BillNoteOut } from './bill';

describe('a bill the device printed', () => {
  it('is noted on its open check, which says when', () => {
    expectTypeOf<InputOf<'sale.order.note_bill'>>().toEqualTypeOf<OrderRefIn>();
    expectTypeOf<OutputOf<'sale.order.note_bill'>>().toEqualTypeOf<BillNoteOut>();
    expectTypeOf<BillNoteOut>().toEqualTypeOf<{ order_id: string; bill_printed_at: string }>();
  });
});
