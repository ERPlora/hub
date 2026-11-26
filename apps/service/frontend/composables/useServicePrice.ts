// A service's price as it is sold, the same on the till's tile and on the public booking page: a fixed price is its
// amount (already written in the business's money by the caller); any other says how it is priced.
import type { PricingType } from '../operations';
import { useT } from './useT';

export function useServicePrice(): (amount: string, type: PricingType) => string {
  const t = useT();
  return (amount, type) => (type === 'fixed' ? amount : t(`service.price.${type}`, { price: amount }));
}
