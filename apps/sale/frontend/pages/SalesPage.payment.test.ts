// Sales & POS → Sales, the «Payment» column (SALE-F28, SALE-F03): a sale charged with several methods says them all
// («Efectivo + Tarjeta», 111 px), and at a tablet's width the table folds its row actions before cutting that text.
import { DataTable } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { mountSale } from '../__tests__/mount-sale';
import SalesPage from './SalesPage.vue';

describe('SalesPage: the Payment column', () => {
  it('keeps the room to read both methods of a split sale whole, and no other column asks for more', async () => {
    const m = await mountSale(SalesPage, { path: '/sale/sales' });
    await m.live();
    const table = m.wrapper.findComponent(DataTable as unknown as Component);
    const columns = (table.props() as Record<string, unknown>).columns as Array<{ key: string; minWidth?: string }>;
    expect(columns.filter((column) => column.minWidth).map((column) => [column.key, column.minWidth])).toEqual([
      ['payment_method_name', '9.5rem'],
    ]);
  });
});
