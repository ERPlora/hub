// CategoryPicker: which categories of the catalog's source the website shows (none chosen = all), read from
// `website.catalog.categories` each time the source changes.
import { describe, expect, it } from 'vitest';

import { ionValue, mountWebsite, settle } from '../__tests__/mount-website';
import CategoryPicker from './CategoryPicker.vue';

const SERVICES = { categories: [{ id: 'c1', name: 'Hair' }, { id: 'c2', name: 'Nails' }] };

async function picker(props: Record<string, unknown> = {}, answer: () => Response = () => Response.json(SERVICES)) {
  const mounted = await mountWebsite(CategoryPicker, { props: { source: 'service', modelValue: [], ...props }, api: answer });
  await settle();
  return mounted;
}

describe('CategoryPicker', () => {
  it('reads the categories of the source and offers them, «all» when none is chosen', async () => {
    const { wrapper, net } = await picker();
    expect(net.api.map((call) => call.url)).toEqual(['/api/website/catalog/categories?source=service']);
    await wrapper.setProps({ source: 'inventory' });
    await settle();
    expect(net.api.at(-1)?.url).toBe('/api/website/catalog/categories?source=inventory');
    const options = wrapper.findAll('ion-select-option');
    expect(options.map((option) => (option.element as HTMLElement & { value?: string }).value)).toEqual(['c1', 'c2']);
    expect(options.map((option) => option.element.textContent?.trim())).toEqual(['Hair', 'Nails']);
    const select = wrapper.get('[data-testid="website-catalog-categories"]').element as HTMLElement & { placeholder?: string; interface?: string; multiple?: boolean };
    expect([select.placeholder, select.interface, select.multiple]).toEqual(['All categories', 'popover', true]);
  });

  it('emits the chosen ids', async () => {
    const { wrapper } = await picker();
    await ionValue(wrapper.get('[data-testid="website-catalog-categories"]').element, ['c2']);
    expect(wrapper.emitted('update:modelValue')).toEqual([[['c2']]]);
  });

  it('says so when the categories could not be read', async () => {
    const { wrapper } = await picker({}, () => Response.json({ error: { code: 'internal_error', message: 'Internal error' } }, { status: 500 }));
    expect(wrapper.get('[data-testid="website-catalog-categories-error"]').text()).toContain('could not be loaded');
  });
});
