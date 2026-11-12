// «Party» of a reservation (RESERVATION-F06, F08) and of a waitlist entry (RESERVATION-F14): how many people come, a
// whole number from 1 in an outlined md box, handed back as text, with its window's refusal under it, red. What the
// host puts on it — its hook, its name in the form (hub#888: the window tells by it which refused field a person
// corrected) and `disabled` — lands on the field.
import { describe, expect, it } from 'vitest';

import { ionValue, mountReservation } from '../__tests__/mount-reservation';
import PartyField from './PartyField.vue';

type Control = HTMLElement & {
  label?: string;
  value?: unknown;
  type?: string;
  min?: unknown;
  inputmode?: string;
  fill?: string;
  labelPlacement?: string;
  errorText?: string;
  name?: string;
  disabled?: boolean;
};

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountReservation(PartyField, { props: { modelValue: '2', 'data-testid': 'party', name: 'party_size', ...props }, locale });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: string) => m.wrapper.setProps({ modelValue: value }) });
  return { ...m, field: () => m.wrapper.element as Control };
}

describe('PartyField', () => {
  it('is an outlined md number box from 1 under «Party», with the hook and name its host gives', async () => {
    const field = (await setup()).field();
    expect([
      field.tagName,
      field.label,
      field.fill,
      field.getAttribute('mode'),
      field.labelPlacement,
      field.type,
      field.inputmode,
      String(field.min),
      field.value,
      field.name,
      field.dataset.testid,
      field.disabled,
    ]).toEqual(['ION-INPUT', 'Party', 'outline', 'md', 'floating', 'number', 'numeric', '1', '2', 'party_size', 'party', false]);
  });

  it('hands what is typed back to its host as text', async () => {
    const s = await setup();
    await ionValue(s.field(), '6', 'ionInput');
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['6']);
    await ionValue(s.field(), null, 'ionInput');
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['']);
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

  it('is off when its host says so (a reservation that only takes its notes)', async () => {
    expect((await setup({ disabled: true })).field().disabled).toBe(true);
  });

  it('speaks Spanish', async () => {
    expect((await setup({}, 'es')).field().label).toBe('Pax');
  });
});
