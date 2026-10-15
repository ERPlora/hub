// The filters of the sessions list: the funnel button with the count of filters in use, opening a panel
// with Status (Any · Open · Closed), Session number and the four amounts from–to (as the person types
// money; the difference may be negative). A change applies at once; «Clear» drops them all; «Done»
// closes. An amount that is not one, or what the server refused, is said under its field.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountCash } from '../__tests__/mount-cash-register';
import SessionFilters from './SessionFilters.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

async function setup(modelValue: Record<string, string> = {}, fieldErrors: Record<string, string> = {}) {
  const m = await mountCash(SessionFilters, { props: { modelValue, fieldErrors } });
  const last = () => m.wrapper.emitted('update:modelValue')?.at(-1)?.[0];
  return { ...m, last };
}

describe('SessionFilters', () => {
  it('counts the filters in use on its button and opens the panel', async () => {
    const s = await setup({ status: 'closed', difference_max: '-1' });
    expect(s.find('cash-register-filters-count').text()).toBe('2');
    await click(s.inDoc('cash-register-filters'));
    expect(s.inDoc('cash-register-filters-panel')?.getAttribute('aria-label')).toBe('Filter sessions');
    expect(prop(s.inDoc('cash-register-filter-status'), 'value')).toBe('closed');
  });

  it('a change applies at once; a blank one drops the filter; «Clear» drops them all', async () => {
    const s = await setup({ status: 'open' });
    await click(s.inDoc('cash-register-filters'));
    await ionValue(s.inDoc('cash-register-filter-opening_min'), '100', 'ionInput');
    expect(s.last()).toEqual({ status: 'open', opening_min: '100' });
    await ionValue(s.inDoc('cash-register-filter-status'), '');
    expect(s.last()).toEqual({ opening_min: '100' });
    await click(s.inDoc('cash-register-filters-clear'));
    expect(s.last()).toEqual({});
  });

  it('says under its field an amount that is not one, or what the server refused', async () => {
    const s = await setup({ counted_min: 'abc' }, { number: 'Ensure this value has at most 24 characters.' });
    await click(s.inDoc('cash-register-filters'));
    expect(prop(s.inDoc('cash-register-filter-counted_min'), 'errorText')).toBe('This is not an amount.');
    expect(prop(s.inDoc('cash-register-filter-number'), 'errorText')).toBe('Ensure this value has at most 24 characters.');
  });
});
