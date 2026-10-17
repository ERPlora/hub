// The tax of the business's territory as every app names it (TAX-F11): «IGIC» in the Canary Islands, «IPSI»
// in Ceuta and Melilla, «VAT» («IVA») anywhere else. Taxes keeps it (`tax.settings.get`, Taxes → Settings)
// and is the one place that publishes it: the till, the sections, the settings of Sales and the lines of a
// manual invoice read it from here, never from an operation of their own. Live (one subscription shared by
// the whole tab): a change of territory renames every screen. Every role that sells or invoices may read it
// (`tax.view`). A failed re-read keeps the territory already read.
import { useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

import type { TerritoryTaxKind } from '../operations';
import { useT } from './useT';

/** The key of a family's short name («VAT», «IGIC», «IPSI»), for a tax that is not the territory's (the one
 *  a period's sales were declared with). */
export function taxNameKey(kind: TerritoryTaxKind): string {
  return `tax.common.taxName.${kind}`;
}

/** The family of the business's territory; unknown until it is read (or when it cannot be). */
export function useTaxKind(): ComputedRef<TerritoryTaxKind | undefined> {
  const { data } = useLive('tax.settings.get', {});
  return computed(() => data.value?.tax_kind);
}

/** The short name of the territory's tax; the national VAT, the server's own default, until it is read. */
export function useTaxName(): ComputedRef<string> {
  const t = useT();
  const kind = useTaxKind();
  return computed(() => t(taxNameKey(kind.value ?? 'vat')));
}
