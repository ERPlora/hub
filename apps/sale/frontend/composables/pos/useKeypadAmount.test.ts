// The amount typed on the till's keypad (the open-price, discount and service-price sheets): what the sheet hands up,
// in cents read only in the business's money (hub#921: «1500» yen read before it answers would go up as 150000), and
// the figure it shows, a figure without a sign until the business answers.
import { describe, expect, it } from 'vitest';
import { shallowRef } from 'vue';

import { business, JAPANESE, mountComposable } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { useKeypadAmount } from './useKeypadAmount';

async function setup(typedText: string) {
  const typed = shallowRef(typedText);
  let amount!: ReturnType<typeof useKeypadAmount>;
  const m = await mountComposable(() => (amount = useKeypadAmount(typed)), { business: null });
  await m.live();
  const read = () => [amount.cents.value, plain(amount.shown.value)];
  return { ...m, typed, read };
}

describe('useKeypadAmount', () => {
  it('hands nothing up until the business answers its money; then «1500» is 1500 yen', async () => {
    const s = await setup('1500');
    expect(s.read()).toEqual([0, '1,500.00']);
    await s.result('base.business.get', business(JAPANESE));
    expect(s.read()).toEqual([1500, '¥1,500']);
  });

  it('reads a dot still being typed in the business’s decimals, and follows what is typed', async () => {
    const s = await setup('12.');
    await s.result('base.business.get', business());
    expect(s.read()).toEqual([1200, '€12.00']);
    s.typed.value = '';
    expect(s.read()).toEqual([0, '€0.00']);
  });
});
