// The «Position» of the sale app's back-office lists (a section, SALE-F35; a quick note, SALE-F36): a whole number
// from 0 (the server's `sort_order`) in an outlined md box under its host's label, handed back as text, with its
// window's refusal under it, red. What the host puts on it — its hook and its name in the form (hub#888: the window
// tells by it which refused field a person corrected) — lands on the field.
import { describe, expect, it } from 'vitest';

import { ionValue, mountSale } from '../../__tests__/mount-sale';
import PositionField from './PositionField.vue';

type Control = HTMLElement & {
  label?: string;
  value?: unknown;
  type?: string;
  min?: unknown;
  step?: unknown;
  fill?: string;
  labelPlacement?: string;
  errorText?: string;
  name?: string;
};

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountSale(PositionField, { props: { modelValue: '3', label: 'Position', 'data-testid': 'order', name: 'sort_order', ...props } });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: string) => m.wrapper.setProps({ modelValue: value }) });
  return { ...m, field: () => m.wrapper.element as Control };
}

describe('PositionField', () => {
  it('is an outlined md number box from 0 in steps of 1, under its host’s label, with the hook and name its host gives', async () => {
    const field = (await setup()).field();
    expect([
      field.tagName,
      field.label,
      field.fill,
      field.getAttribute('mode'),
      field.labelPlacement,
      field.type,
      String(field.min),
      String(field.step),
      field.value,
      field.name,
      field.dataset.testid,
    ]).toEqual(['ION-INPUT', 'Position', 'outline', 'md', 'floating', 'number', '0', '1', '3', 'sort_order', 'order']);
  });

  it('hands what is typed back to its host as text', async () => {
    const s = await setup();
    await ionValue(s.field(), '12', 'ionInput');
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['12']);
  });

  it('says its window’s refusal under it, red, and nothing without one', async () => {
    const refused = (await setup({ errorText: 'Enter a whole number.' })).field();
    expect([refused.errorText, refused.classList.contains('ion-invalid'), refused.classList.contains('ion-touched')]).toEqual([
      'Enter a whole number.',
      true,
      true,
    ]);
    const fine = (await setup()).field();
    expect([fine.errorText ?? '', fine.classList.contains('ion-invalid')]).toEqual(['', false]);
  });
});
