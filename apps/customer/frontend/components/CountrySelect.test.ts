// The country of the card (CUSTOMER-F01): picked by its name from a searchable list (the product's
// `ok-combo`), stored as its ISO code. A field that shows the country's name; tapping it opens the
// list with a search box (Spain first); «No country» clears it. A stored code it does not know is
// kept and shown as stored.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountCustomer } from '../__tests__/mount-customer';
import CountrySelect from './CountrySelect.vue';
import source from './CountrySelect.vue?raw';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(initial = '', props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const value = ref(initial);
  const Host = defineComponent({
    setup: () => () =>
      h(CountrySelect, {
        modelValue: value.value,
        'onUpdate:modelValue': (v: string) => (value.value = v),
        label: 'Country',
        testid: 'customer-form-country',
        ...props,
      }),
  });
  const m = await mountCustomer(Host, { locale, attachTo: document.body });
  const el = <T extends HTMLElement = HTMLElement>(id: string) => document.querySelector<T>(`[data-testid="${id}"]`);
  const field = () => el<HTMLElement & { value?: string; label?: string; errorText?: string }>('customer-form-country')!;
  const options = () => [...document.querySelectorAll('[data-testid^="customer-form-country-option-"]')].map((o) => o.textContent?.trim());
  async function open() {
    field().click();
    await flush();
  }
  async function search(text: string) {
    const bar = el<HTMLElement & { value?: string }>('customer-form-country-search')!;
    bar.value = text;
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
    await flush();
  }
  return { ...m, value, el, field, options, open, search };
}

describe('CountrySelect', () => {
  it('shows the stored country by its name in the page language', async () => {
    const s = await setup('FR');
    expect([s.field().label, s.field().value]).toEqual(['Country', 'France']);
  });

  it('in Spanish too', async () => {
    const s = await setup('FR', {}, 'es');
    expect(s.field().value).toBe('Francia');
  });

  it('opens the list: «No country», then Spain, then the rest by name', async () => {
    const s = await setup();
    expect(s.el('customer-form-country-list')).toBeNull();
    await s.open();
    expect(s.options().slice(0, 3)).toEqual(['No country', 'Spain', 'Afghanistan']);
  });

  it('finds a country by its name, without accents or case, or by its code', async () => {
    const s = await setup('', {}, 'es');
    await s.open();
    await s.search('alemania');
    expect(s.options()).toEqual(['Alemania']);
    await s.search('peru');
    expect(s.options()).toEqual(['Perú']);
    await s.search('GB');
    expect(s.options()).toContain('Reino Unido');
  });

  it('a pick stores its code and closes; «No country» clears it', async () => {
    const s = await setup('FR');
    await s.open();
    await s.search('germany');
    s.el('customer-form-country-option-DE')!.click();
    await flush();
    expect(s.value.value).toBe('DE');
    expect(s.el('customer-form-country-list')).toBeNull();
    await s.open();
    s.el('customer-form-country-option-none')!.click();
    await flush();
    expect(s.value.value).toBe('');
  });

  it('a stored code it does not know is shown as stored', async () => {
    const s = await setup('XQ');
    expect(s.field().value).toBe('XQ');
  });

  it('carries the server\'s message under the field', async () => {
    const s = await setup('', { error: 'Choose a country from the list.' });
    expect(s.field().errorText).toBe('Choose a country from the list.');
    expect(s.field().classList.contains('ion-invalid')).toBe(true);
  });

  it('has no OutfitKit tag and every filled control declares mode="md"', () => {
    expect(source).not.toMatch(/<ok[-]/);
    for (const tag of source.match(/<ion-(input|select|textarea)\b[^>]*>/gs) ?? []) if (/fill=/.test(tag)) expect(tag).toMatch(/mode="md"/);
  });
});
