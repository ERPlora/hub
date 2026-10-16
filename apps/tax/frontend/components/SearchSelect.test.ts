// SearchSelect: a choice among MANY options (the 249 countries, the business's categories) — the
// pattern Ionic recommends for long lists: a field that opens a modal with a searchbar and the list.
// The options are filtered here as one types, or, with `v-model:query`, asked to the server (the page
// passes the answer as `options`). The chosen option keeps its name even when a later search no longer
// lists it.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountTax, settle } from '../__tests__/mount-tax';
import SearchSelect from './SearchSelect.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; placeholder?: string; fill?: string; errorText?: string; readonly?: boolean };

const COUNTRIES = [
  { value: 'ES', label: 'Spain (ES)' },
  { value: 'PT', label: 'Portugal (PT)' },
  { value: 'FR', label: 'France (FR)' },
];

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTax(SearchSelect, {
    props: { modelValue: '', options: COUNTRIES, label: 'Country', placeholder: 'Choose a country', testid: 'country', ...props },
    locale,
  });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: string) => m.wrapper.setProps({ modelValue: value }) });
  const field = () => m.inDoc('country') as Control;
  const options = () => m.wrapper.findAll('[data-testid="country-option"]').map((o) => [o.attributes('data-value'), o.text().trim()]);
  const open = async () => {
    await click(field());
    await settle();
  };
  const search = (text: string) => ionValue(m.inDoc('country-search'), text, 'ionInput');
  return { ...m, field, options, open, search };
}

describe('SearchSelect', () => {
  it('is an outlined md field, read-only, showing the name of the chosen option', async () => {
    const s = await setup({ modelValue: 'PT' });
    expect([s.field().tagName, s.field().label, s.field().fill, s.field().getAttribute('mode'), s.field().readonly]).toEqual([
      'ION-INPUT',
      'Country',
      'outline',
      'md',
      true,
    ]);
    expect(s.field().value).toBe('Portugal (PT)');
    expect((await setup()).field().placeholder).toBe('Choose a country');
  });

  it('opens a list with a searchbar, and filters it as one types (by name or by code)', async () => {
    const s = await setup();
    expect(s.inDoc('country-modal')?.querySelector('[data-testid="country-search"]') ?? null).toBeNull();
    await s.open();
    expect(s.inDoc('country-search')).not.toBeNull();
    expect(s.options()).toEqual([
      ['ES', 'Spain (ES)'],
      ['PT', 'Portugal (PT)'],
      ['FR', 'France (FR)'],
    ]);
    await s.search('port');
    expect(s.options()).toEqual([['PT', 'Portugal (PT)']]);
    await s.search(' es');
    expect(s.options()).toEqual([['ES', 'Spain (ES)']]);
    await s.search('xx');
    expect(s.options()).toEqual([]);
    expect(s.inDoc('country-empty')?.textContent?.trim()).toBe('No results');
  });

  it('choosing an option sets it and closes the list', async () => {
    const s = await setup();
    await s.open();
    await click(s.wrapper.find('[data-testid="country-option"][data-value="FR"]').element);
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['FR']);
    expect(s.inDoc('country-search')).toBeNull();
    expect(s.field().value).toBe('France (FR)');
  });

  it('with v-model:query the search goes to the server: it emits the text and filters nothing itself', async () => {
    const s = await setup({ query: '' });
    await s.wrapper.setProps({ 'onUpdate:query': (query: string) => s.wrapper.setProps({ query }) });
    await s.open();
    await s.search('  food ');
    expect(s.wrapper.emitted('update:query')?.at(-1)).toEqual(['food']);
    expect(s.options()).toHaveLength(3);
    // The chosen option keeps its name when the next answer no longer lists it.
    await click(s.inDoc('country-option'));
    await s.wrapper.setProps({ options: [{ value: 'IT', label: 'Italy (IT)' }] });
    expect(s.field().value).toBe('Spain (ES)');
  });

  it('paints an error under the field; disabled, it does not open', async () => {
    const s = await setup({ errorText: 'Choose one', disabled: true });
    expect([s.field().errorText, s.field().classList.contains('ion-invalid')]).toEqual(['Choose one', true]);
    await s.open();
    expect(s.inDoc('country-search')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    await s.open();
    expect((s.inDoc('country-search') as HTMLElement & { placeholder?: string }).placeholder).toBe('Buscar…');
    await s.search('xx');
    expect(s.inDoc('country-empty')?.textContent?.trim()).toBe('Sin resultados');
  });
});

describe('SearchSelect: Enter in the searchbar', () => {
  /** Enter in the searchbar, and whether it got past it (to a form around). */
  async function enterInSearch(s: Awaited<ReturnType<typeof setup>>): Promise<{ escaped: boolean; prevented: boolean }> {
    const host = s.inDoc('country-modal')!;
    let escaped = false;
    host.addEventListener('keydown', () => (escaped = true));
    const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    s.inDoc('country-search')!.dispatchEvent(event);
    await settle();
    return { escaped, prevented: event.defaultPrevented };
  }

  it('chooses the first match, and goes no further (no form around submits)', async () => {
    const s = await setup();
    await s.open();
    await s.search('port');
    expect(await enterInSearch(s)).toEqual({ escaped: false, prevented: true });
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['PT']);
    expect(s.inDoc('country-search')).toBeNull();
  });

  it('with nothing that matches it chooses nothing and the list stays open', async () => {
    const s = await setup();
    await s.open();
    await s.search('xx');
    expect((await enterInSearch(s)).escaped).toBe(false);
    expect(s.wrapper.emitted('update:modelValue')).toBeUndefined();
    expect(s.inDoc('country-search')).not.toBeNull();
  });
});

