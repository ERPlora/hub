// Deleting a price list or a discount rule (apps/pricing/services/price_lists.py and rules.py), written by hand as
// `operations.d.ts`: the answer is its id and the code it had, free now for a new one.
import type { DeletedOut, PriceListRefIn, RuleRefIn } from './operations';

export interface CodedDeletedOut extends DeletedOut {
  code: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'pricing.price_list.delete': { input: PriceListRefIn; output: CodedDeletedOut };
    'pricing.rule.delete': { input: RuleRefIn; output: CodedDeletedOut };
  }
}
