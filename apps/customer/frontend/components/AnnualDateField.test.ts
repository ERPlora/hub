// The birthday and the anniversary of the card's form (CUSTOMER-F01, F04): the day, the month and, only if it is
// known, the year, typed in three number fields in the order the page language writes a day.
import { InlineFeedback } from '@erplora/ui/components';
import { IonInput } from '@ionic/vue';
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountCustomer } from '../__tests__/mount-customer';
import AnnualDateField from './AnnualDateField.vue';
import source from './AnnualDateField.vue?raw';

afterEach(() => {
  document.body.replaceChildren();
});

interface Setup {
  value?: string;
  locale?: 'en' | 'es';
  errorText?: string;
}

async function setup(options: Setup = {}) {
  const value = ref(options.value ?? '');
  const Host = defineComponent({
    setup: () => () =>
      h(AnnualDateField, {
        modelValue: value.value,
        'onUpdate:modelValue': (v: string) => (value.value = v),
        label: 'Birthday',
        testid: 'customer-form-birthday',
        errorText: options.errorText,
      }),
  });
  const m = await mountCustomer(Host, { locale: options.locale, attachTo: document.body });
  const inputs = () => m.wrapper.findAllComponents(IonInput);
  const part = (name: string) => inputs().find((c) => c.attributes('data-testid') === `customer-form-birthday-${name}`)!;
  return { ...m, value, inputs, part };
}

describe('AnnualDateField', () => {
  it('asks the day, the month and the year in the order the page language writes a day, the year optional', async () => {
    const es = await setup({ locale: 'es' });
    expect(es.inputs().map((input) => input.props('label'))).toEqual(['Día', 'Mes', 'Año']);
    expect(es.inputs().map((input) => [input.props('inputmode'), input.props('maxlength')])).toEqual([
      ['numeric', 2],
      ['numeric', 2],
      ['numeric', 4],
    ]);
    expect(es.wrapper.get('fieldset legend').text()).toBe('Birthday');
    // Only the year says it may stay empty (a helper Ionic is not given reads as its own placeholder, no text).
    expect(es.inputs().map((input) => input.props('helperText')).filter((text) => typeof text === 'string')).toEqual(['Opcional']);
    expect(es.part('year').props('helperText')).toBe('Opcional');
    document.body.replaceChildren();
    const en = await setup({ locale: 'en' });
    expect(en.inputs().map((input) => input.props('label'))).toEqual(['Month', 'Day', 'Year']);
  });

  it('a day and a month go up without the year; the year makes it the whole day; nothing typed is none', async () => {
    const s = await setup();
    await s.part('day').setValue('12');
    await s.part('month').setValue('3');
    expect(s.value.value).toBe('--03-12');
    await s.part('year').setValue('1990');
    expect(s.value.value).toBe('1990-03-12');
    for (const name of ['day', 'month', 'year']) await s.part(name).setValue('');
    expect(s.value.value).toBe('');
  });

  it('shows the day the card keeps, and the one another change brings', async () => {
    const s = await setup({ value: '--03-12' });
    expect(['day', 'month', 'year'].map((name) => s.part(name).props('modelValue'))).toEqual(['12', '3', '']);
    s.value.value = '1990-11-04';
    await flush();
    expect(['day', 'month', 'year'].map((name) => s.part(name).props('modelValue'))).toEqual(['4', '11', '1990']);
  });

  it('a part still missing is kept as typed while the person goes on', async () => {
    const s = await setup();
    await s.part('month').setValue('3');
    expect(s.value.value).toBe('--03-');
    expect(['day', 'month', 'year'].map((name) => s.part(name).props('modelValue'))).toEqual(['', '3', '']);
  });

  it('paints the server’s refusal under the three fields and marks them', async () => {
    const s = await setup({ errorText: 'Enter a valid date.' });
    expect(s.wrapper.findComponent(InlineFeedback).props()).toMatchObject({ tone: 'danger', role: 'alert' });
    expect(s.wrapper.findComponent(InlineFeedback).text()).toBe('Enter a valid date.');
    expect(s.inputs().every((input) => input.classes().includes('ion-invalid'))).toBe(true);
  });

  it('each of the three fields is outlined, in the mode that paints the outline', async () => {
    const s = await setup();
    expect(s.inputs().map((c) => c.props('fill'))).toEqual(['outline', 'outline', 'outline']);
    // Ionic reads the mode from the tag, not from a prop: the shell runs in iOS mode, where an outline is not painted.
    const tags = [...source.matchAll(/<ion-input\b[^>]*>/g)].map((match) => match[0]);
    expect(tags.map((tag) => tag.includes('mode="md"'))).toEqual([true]);
  });
});
