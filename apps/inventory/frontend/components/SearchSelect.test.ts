// A picker over a list the server pages (tax categories, product categories). While the list fits in
// one query (`complete`) it is the plain outlined select of the old screens. A longer list cannot be
// held whole: the field opens a dialog with a search box that asks the server (`update:search`) and
// the matching options; tapping one picks it (single) or toggles it (multiple). The labels of the
// options picked stay known while the search changes. Stand-in for a shared `SearchSelect`
// (UI-REQUESTS.md).
import { IonSelect } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import SearchSelect from './SearchSelect.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

type Control = HTMLElement & { value?: unknown; label?: string; placeholder?: string; errorText?: string; readonly?: boolean };

const OPTIONS = [
  { value: 'a', label: 'Apples' },
  { value: 'b', label: 'Bread' },
];

async function setup(props: Record<string, unknown>) {
  const m = await mountInventory(SearchSelect, {
    props: { modelValue: '', options: OPTIONS, complete: true, label: 'Category', placeholder: 'Pick one', testid: 'pick', ...props },
    attach: true,
  });
  const el = (id: string) => document.querySelector<Control>(`[data-testid="${id}"]`);
  return { ...m, el };
}

describe('SearchSelect: a list that fits', () => {
  it('is the outlined select with the fixed options first', async () => {
    const s = await setup({ fixedOptions: [{ value: '', label: '— (default)' }] });
    const select = s.wrapper.findComponent(IonSelect);
    expect([select.props('label'), select.props('placeholder'), select.props('fill'), select.attributes('mode')]).toEqual([
      'Category',
      'Pick one',
      'outline',
      'md',
    ]);
    expect(s.wrapper.findAll('ion-select-option').map((o) => o.text())).toEqual(['— (default)', 'Apples', 'Bread']);
    await select.setValue('b');
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['b']]);
  });
});

describe('SearchSelect: a long list', () => {
  it('shows what is picked and opens a dialog that searches on the server', async () => {
    const s = await setup({ complete: false, modelValue: 'b' });
    expect(s.wrapper.findComponent(IonSelect).exists()).toBe(false);
    const field = s.el('pick')!;
    expect([field.label, field.value, field.readonly]).toEqual(['Category', 'Bread', true]);
    field.click();
    await flush();
    expect(s.el('pick-picker')?.getAttribute('aria-label')).toBe('Category');
    const search = s.el('pick-search')!;
    search.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'app' } }));
    await flush();
    expect(s.wrapper.emitted('update:search')).toEqual([['app']]);
    expect([...document.querySelectorAll('[data-testid="pick-option"]')].map((o) => [o.getAttribute('data-value'), o.textContent?.trim()])).toEqual([
      ['a', 'Apples'],
      ['b', 'Bread'],
    ]);
  });

  it('single: a tap picks the option and closes the dialog', async () => {
    const s = await setup({ complete: false });
    s.el('pick')!.click();
    await flush();
    (document.querySelector('[data-testid="pick-option"][data-value="a"]') as HTMLElement).click();
    await flush();
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['a']]);
    expect(s.el('pick-option')).toBeNull();
  });

  it('multiple: a tap toggles; what was picked keeps its name when the search changes', async () => {
    const s = await setup({ complete: false, multiple: true, modelValue: ['a'] });
    s.el('pick')!.click();
    await flush();
    (document.querySelector('[data-testid="pick-option"][data-value="b"]') as HTMLElement).click();
    await flush();
    expect(s.wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']]]);
    await s.wrapper.setProps({ modelValue: ['a', 'b'], options: [{ value: 'c', label: 'Cheese' }] });
    expect(s.el('pick')?.value).toBe('Apples, Bread');
  });

  it('is a combobox that opens a dialog, named so for screen readers', async () => {
    const s = await setup({ complete: false });
    // Ionic hands ARIA attributes to the field's own input, the element that takes the focus.
    const input = s.el('pick')!.querySelector('input')!;
    expect([input.getAttribute('role'), input.getAttribute('aria-haspopup')]).toEqual(['combobox', 'dialog']);
  });

  it('Enter and Space open it from the keyboard, and the key never reaches the form around it', async () => {
    const s = await setup({ complete: false });
    const reached = vi.fn();
    document.body.addEventListener('keydown', reached);
    for (const key of ['Enter', ' ']) {
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
      s.el('pick')!.dispatchEvent(event);
      await flush();
      expect([key, event.defaultPrevented]).toEqual([key, true]);
      expect(s.el('pick-search')).not.toBeNull();
      s.el('pick-close')!.click();
      await flush();
    }
    expect(reached).not.toHaveBeenCalled();
    document.body.removeEventListener('keydown', reached);
  });

  it('Enter in the search box picks the first match and stays inside the dialog', async () => {
    const s = await setup({ complete: false });
    s.el('pick')!.click();
    await flush();
    const reached = vi.fn();
    document.body.addEventListener('keydown', reached);
    const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    s.el('pick-search')!.dispatchEvent(event);
    await flush();
    expect(event.defaultPrevented).toBe(true);
    expect(reached).not.toHaveBeenCalled();
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['a']]);
    expect(s.el('pick-option')).toBeNull();
    document.body.removeEventListener('keydown', reached);
  });

  it("paints the server's message for the field", async () => {
    const s = await setup({ complete: false, errorText: 'Not valid' });
    expect(s.el('pick')?.errorText).toBe('Not valid');
  });
});
