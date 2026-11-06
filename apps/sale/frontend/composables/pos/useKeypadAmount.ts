// The amount typed on the till's keypad, in the business's money: the open-price, discount and service-price sheets.
// `cents` is what the sheet hands up, read only once the business has answered its money and 0 until then, so the
// sheet's button waits in grey (hub#921: «1500» yen read with two decimals would go up as 150000); `shown` is what was
// typed, for the figure on top and the button's label (a figure without a sign until the business answers).
//   const { business, cents, shown } = useKeypadAmount(typed);
import { computed, type Ref } from 'vue';

import { centsFromAmount, formatMoney, keypadCents, useBusinessMoney } from '../../lib/format';
import { useLocale } from '../useT';

export function useKeypadAmount(typed: Readonly<Ref<string>>) {
  const locale = useLocale();
  const business = useBusinessMoney();
  const cents = computed(() => (business.value ? keypadCents(typed.value, business.value) : 0));
  const shown = computed(() => formatMoney(centsFromAmount(typed.value.replace(/\.$/, ''), business.value) ?? 0, locale.value, business.value));
  return { business, cents, shown };
}
