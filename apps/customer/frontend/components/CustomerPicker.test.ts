// The customer picker (WORKBOOK «La búsqueda de texto de la lista»: F13, F17, F18): a search box and
// the first 20 cards by name, live; typing searches as the list does (name, phone, email, tax id,
// company). It tells «searching» from «no matches» from «down» (with Retry, keeping the text) and from
// «no permission». Tapping a card hands it up. Used by «Merge with…» and the till's CustomerSearch.
import { describe, expect, it, vi } from 'vitest';

import { customerRow, pageOf } from '../__tests__/fixtures';
import { errorFrame, flush, type MountOptions, mountCustomer, subId } from '../__tests__/mount-customer';
import CustomerPicker from './CustomerPicker.vue';
import source from './CustomerPicker.vue?raw';

const LIST = 'customer.customer.list';
const ROWS = pageOf([customerRow('c1', 'Ana García'), customerRow('c2', 'Luis', { phone: '', email: 'luis@x.es' }), customerRow('c3', 'Eva')]);

async function setup(props: Record<string, unknown> = {}, options: MountOptions = {}) {
  const m = await mountCustomer(CustomerPicker, { props, ...options });
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="customer-picker-${id}"]`);
  const results = () => m.wrapper.findAll('[data-testid^="customer-picker-result-"]');
  async function type(text: string) {
    const bar = testid('search').element as HTMLElement & { value?: string };
    bar.value = text;
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
    await flush();
  }
  return { ...m, call, testid, results, type };
}

describe('CustomerPicker', () => {
  it('shows the first 20 cards by name, «Loading…» until they arrive', async () => {
    const s = await setup();
    expect(s.params(LIST)).toEqual([{ limit: 20, sort: 'name' }]);
    expect(s.testid('searching').text()).toBe('Loading…');
    await s.result(s.call, LIST, ROWS);
    expect(s.results().map((r) => [r.find('h3').text(), r.find('p').text()])).toEqual([
      ['Ana García', '+34 600 111 222'],
      ['Luis', 'luis@x.es'],
      ['Eva', '+34 600 111 222'],
    ]);
  });

  it('searches as the list does, with the trimmed text, and says what it is looking at', async () => {
    const s = await setup();
    expect((s.testid('search').element as HTMLElement & { placeholder?: string }).placeholder).toBe('Search by name, phone, email…');
    await s.type(' 600 111 ');
    expect(s.params(LIST)).toEqual([{ search: '600 111', limit: 20, sort: 'name' }]);
    expect(s.wrapper.emitted('update:term')?.at(-1)).toEqual([' 600 111 ']);
  });

  it('leaves out the cards it is told to (the open card in «Merge with…»)', async () => {
    const s = await setup({ exclude: ['c1'] });
    await s.result(s.call, LIST, ROWS);
    expect(s.results().map((r) => r.attributes('data-testid'))).toEqual(['customer-picker-result-c2', 'customer-picker-result-c3']);
  });

  it('a tap hands the card up', async () => {
    const s = await setup();
    await s.result(s.call, LIST, ROWS);
    await s.results()[1].trigger('click');
    expect(s.wrapper.emitted('pick')).toEqual([[ROWS.rows[1]]]);
  });

  it('marks the card already chosen', async () => {
    const s = await setup({ selectedId: 'c2' });
    await s.result(s.call, LIST, ROWS);
    expect(s.results()[1].classes()).toContain('customer-picker__item--selected');
    expect(s.results()[1].find('[data-testid="customer-picker-selected"]').exists()).toBe(true);
  });

  it('no match says «No results.» with a search, «No customers.» without; and the empty slot can say otherwise', async () => {
    const s = await setup();
    await s.result(s.call, LIST, pageOf([]));
    expect(s.testid('empty').text()).toBe('No customers.');
    await s.type('zz');
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), LIST, pageOf([]));
    expect(s.testid('empty').text()).toBe('No results.');
    const merge = await setup({ emptyMessage: 'No other customer matches.' });
    await merge.result(merge.call, LIST, pageOf([]));
    expect(merge.testid('empty').text()).toBe('No other customer matches.');
  });

  it('down: the reason and «Retry», which keeps the text', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, LIST), 'boom'));
    await flush();
    expect(s.testid('error').text()).toContain('msg boom');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.testid('retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('no permission to look up customers is said as such, with no Retry', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, LIST), 'permission_denied'));
    await flush();
    expect(s.testid('error').text()).toBe('You do not have permission to look up customers.');
    expect(s.testid('retry').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, { locale: 'es' });
    await s.result(s.call, LIST, pageOf([]));
    expect(s.testid('empty').text()).toBe('No hay clientes.');
  });

  it('has no OutfitKit tag', () => {
    expect(source).not.toMatch(/<ok[-]/);
  });
});
