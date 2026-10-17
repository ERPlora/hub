// `useTaxName()`: the short name of the tax the business's sales are declared with — its territory's, as
// Taxes → Settings keeps it (TAX-F11): «IGIC» in the Canary Islands, «IPSI» in Ceuta and Melilla, «VAT»
// («IVA») anywhere else. What every sale screen names the tax by (the figures of Sales, the till's notices,
// the sections, the settings). Live (`sale.sale.tax_kind`, one subscription shared by the whole tab): a
// change of territory renames them all. Until it is read, or if it cannot be, the national VAT — the
// server's own default for a business without a territory; a failed re-read keeps the one already read.
import { useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

import { useT } from './useT';

export function useTaxName(): ComputedRef<string> {
  const t = useT();
  const { data } = useLive('sale.sale.tax_kind', {});
  return computed(() => t(`sale.common.taxName.${data.value?.tax ?? 'vat'}`));
}
