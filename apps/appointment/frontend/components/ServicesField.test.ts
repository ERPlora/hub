// The «Services» field of the booking and series panels: the services chosen, in order, as chips that
// can be removed, and a search of the bookable catalog to add one more (each once).
import { Combo } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import type { ServiceFacts } from '../lib/pickers';
import { click, mountAppointment, page, settle } from '../__tests__/mount-appointment';
import ServicesField from './ServicesField.vue';

async function setup(modelValue = [{ id: 'cut', label: 'Haircut' }]) {
  const facts = new Map<string, ServiceFacts>();
  const m = await mountAppointment(ServicesField, { props: { modelValue, facts, testid: 'appointment-form' } });
  m.answerBy({ '/api/service/services/for_sale': [200, page([{ id: 'colour', name: 'Colour', price: 4500, duration_minutes: 60, is_bookable: true }])] });
  const combo = () => m.wrapper.findComponent(Combo);
  return { ...m, facts, combo };
}

describe('ServicesField', () => {
  it('shows the services chosen and adds one from the catalog, keeping its facts', async () => {
    const s = await setup();
    expect(s.find('appointment-form-service-cut').html()).toContain('Haircut');
    expect(s.combo().props('label')).toBe('Add a service');
    await (s.combo().props('search') as (q: string) => Promise<unknown>)('col');
    s.combo().vm.$emit('update:modelValue', { id: 'colour', label: 'Colour' });
    await settle();
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[{ id: 'cut', label: 'Haircut' }, { id: 'colour', label: 'Colour' }]]);
    expect(s.facts.get('colour')).toEqual({ name: 'Colour', minutes: 60, price: 4500 });
  });

  it('empties the search after a pick, in the same field (a new one would orphan its open list)', async () => {
    const s = await setup();
    const field = s.wrapper.get('ion-input[data-testid="appointment-form-service-add"]').element as HTMLElement & { value?: string };
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Col' } }));
    await new Promise((resolve) => setTimeout(resolve, 200));
    await settle();
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await settle();
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[{ id: 'cut', label: 'Haircut' }, expect.objectContaining({ id: 'colour', label: 'Colour' })]]);
    expect(field.value).toBe('');
    expect(s.wrapper.get('ion-input[data-testid="appointment-form-service-add"]').element).toBe(field);
  });

  it('never adds a service twice, and removes one', async () => {
    const s = await setup();
    s.combo().vm.$emit('update:modelValue', { id: 'cut', label: 'Haircut' });
    await settle();
    expect(s.wrapper.emitted('update:modelValue')).toBeUndefined();
    await click(s.wrapper.find('[aria-label="Remove Haircut"]').element);
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[]]);
  });

  it('asks for the first service by its own name', async () => {
    const s = await setup([]);
    expect(s.combo().props('label')).toBe('Service');
  });
});
