// The three suggestions of one payment method on the Settings screen (TIP-F01): each one «%» or «Amount» and its value,
// the amount in the business's money; what is wrong with one is said under its own field.
import { describe, expect, it } from 'vitest';

import { ionValue } from '../../../../base/frontend/__tests__/mount-in-shell';
import { OWNER, mountTip } from '../__tests__/mount-tip';
import type { MethodFields } from '../lib/suggestions';
import MethodSuggestions from './MethodSuggestions.vue';

const CARD: MethodFields = {
  method_id: 'm-card',
  method_name: 'Card',
  suggestions: [
    { kind: 'percent', text: '3' },
    { kind: 'percent', text: '5' },
    { kind: 'amount', text: '2.00' },
  ],
};

type Field = Element & Record<string, unknown>;

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTip(MethodSuggestions, { props: { method: CARD, errors: {}, disabled: false, ...props }, locale, session: OWNER });
  await m.live();
  const field = (testid: string) => m.inDoc(testid) as unknown as Field;
  const last = () => m.wrapper.emitted<[MethodFields]>('update:method')?.at(-1)?.[0];
  return { ...m, field, last };
}

describe('MethodSuggestions', () => {
  it('names the method and paints each suggestion with its kind and its value', async () => {
    const s = await setup();
    expect(s.find('tip-settings-method-m-card').text()).toContain('Card');
    expect(s.field('tip-settings-m-card-0-kind').value).toBe('percent');
    expect(s.field('tip-settings-m-card-0-value').value).toBe('3');
    expect([s.field('tip-settings-m-card-0-value').label, s.field('tip-settings-m-card-0-value').fill]).toEqual(['Suggestion 1', 'outline']);
    expect(s.field('tip-settings-m-card-0-value').getAttribute('mode')).toBe('md');
    expect(s.field('tip-settings-m-card-2-kind').value).toBe('amount');
    expect(s.field('tip-settings-m-card-2-value').value).toBe('2.00');
  });

  it('a new value or a new kind gives the method back with that suggestion changed', async () => {
    const s = await setup();
    await ionValue(s.inDoc('tip-settings-m-card-1-value'), '7', 'ionInput');
    expect(s.last()?.suggestions).toEqual([
      { kind: 'percent', text: '3' },
      { kind: 'percent', text: '7' },
      { kind: 'amount', text: '2.00' },
    ]);
    await ionValue(s.inDoc('tip-settings-m-card-0-kind'), 'amount');
    expect(s.last()?.suggestions[0]).toEqual({ kind: 'amount', text: '3' });
  });

  it('says what is wrong under its field', async () => {
    const s = await setup({ errors: { 'm-card.1': 'tip.settings.errors.same' } });
    expect(s.field('tip-settings-m-card-1-value').errorText).toBe('That suggestion is already there.');
    expect(s.field('tip-settings-m-card-0-value').errorText).toBeFalsy();
  });

  it('blocked, nothing can be changed', async () => {
    const s = await setup({ disabled: true });
    expect([s.field('tip-settings-m-card-0-kind').disabled, s.field('tip-settings-m-card-0-value').disabled]).toEqual([true, true]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.field('tip-settings-m-card-2-value').label).toBe('Sugerencia 3');
  });
});
