import type { DataTableAction } from '@erplora/ui/components';
import { type OutputOf, useCommand } from '@erplora/ui/sdk';
import { computed, type Ref } from 'vue';

import { useT } from './useT';

type Product = OutputOf<'inventory.product.list'>['rows'][number];

interface Flag {
  id: string;
  label: string;
  icon: string;
  hidden: (row: Product) => boolean;
  write: (row: Product) => Promise<unknown>;
  failed: string;
}

/** The pairs of «⋮» actions that turn a mark of a product on or off, one of each pair by what it is now: sold out
 *  (INVENTORY-F29) and shown on the website (INVENTORY-F36). A refusal is said in `error`; the row comes back by the
 *  stream. */
export function useFlagActions(error: Ref<string>) {
  const { t } = useT();
  const soldOut = useCommand('inventory.product.set_sold_out');
  const update = useCommand('inventory.product.update');
  const flags: Flag[] = [
    { id: 'sold_out', label: 'inventory.products.actions.soldOut', icon: 'ion:ban-outline', hidden: (row) => !!row.is_sold_out, write: (row) => soldOut.run({ id: row.id, sold_out: true }), failed: 'inventory.products.soldOutError' },
    { id: 'back_on_sale', label: 'inventory.products.actions.backOnSale', icon: 'ion:refresh-outline', hidden: (row) => !row.is_sold_out, write: (row) => soldOut.run({ id: row.id, sold_out: false }), failed: 'inventory.products.soldOutError' },
    { id: 'hide_from_website', label: 'inventory.products.actions.hideFromWebsite', icon: 'ion:globe-outline', hidden: (row) => !row.show_on_website, write: (row) => update.run({ id: row.id, show_on_website: false }), failed: 'inventory.products.updateError' },
    { id: 'show_on_website', label: 'inventory.products.actions.showOnWebsite', icon: 'ion:globe-outline', hidden: (row) => row.show_on_website, write: (row) => update.run({ id: row.id, show_on_website: true }), failed: 'inventory.products.updateError' },
  ];
  const actions = computed<DataTableAction<Product>[]>(() =>
    flags.map(({ id, label, icon, hidden }) => ({ id, label: t(label), icon, hidden, menuOnly: true })),
  );

  /** Runs `actionId` on `row` when it is one of these; false leaves it to the page. */
  function run(actionId: string, row: Product): boolean {
    const flag = flags.find((one) => one.id === actionId);
    if (!flag) return false;
    error.value = '';
    flag.write(row).catch((failure: unknown) => {
      error.value = failure instanceof Error ? failure.message : t(flag.failed);
    });
    return true;
  }

  return { actions, run };
}
