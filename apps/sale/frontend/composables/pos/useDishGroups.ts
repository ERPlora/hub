// The groups of Modifiers of the dishes picked in a menu (SALE-F42): read once per product while the menu sheet is open,
// as the options sheet of a product sold on its own reads them (MODIFIER-F06). Someone who may not read Modifiers, or a
// business without it, gets the dishes without options; any other failure is said under its dish and read again on
// «Retry». An answer that arrives after the sheet started again is dropped.
import { useCommand } from '@erplora/ui/sdk';
import { shallowRef } from 'vue';

import type { TargetGroupOut } from '../../../../modifier/frontend/operations';
import { refusal } from '../../lib/refusal';

export type DishGroups =
  | { readonly state: 'loading' }
  | { readonly state: 'error' }
  | { readonly state: 'ready'; readonly groups: readonly TargetGroupOut[] };

/** What leaves a dish without options instead of an error: Modifiers off, or no right to read it. */
const WITHOUT_OPTIONS = new Set(['app_inactive', 'permission_denied']);

export function useDishGroups() {
  const forTarget = useCommand('modifier.group.for_target');
  const byProduct = shallowRef<Readonly<Record<string, DishGroups>>>({});
  let round = 0;

  function set(productId: string, groups: DishGroups): void {
    byProduct.value = { ...byProduct.value, [productId]: groups };
  }

  async function read(productId: string): Promise<void> {
    const mine = round;
    set(productId, { state: 'loading' });
    try {
      const { groups } = await forTarget.run({ product_id: productId });
      if (mine === round) set(productId, { state: 'ready', groups });
    } catch (error) {
      if (mine !== round) return;
      const code = refusal(error, '')?.code;
      set(productId, code && WITHOUT_OPTIONS.has(code) ? { state: 'ready', groups: [] } : { state: 'error' });
    }
  }

  /** Reads the products not read yet. */
  function want(productIds: readonly string[]): void {
    for (const productId of productIds) if (!byProduct.value[productId]) void read(productId);
  }

  function of(productId: string): DishGroups | null {
    return byProduct.value[productId] ?? null;
  }

  function reset(): void {
    round += 1;
    byProduct.value = {};
  }

  return { want, of, retry: (productId: string) => void read(productId), reset };
}
