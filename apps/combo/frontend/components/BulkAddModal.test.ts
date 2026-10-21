// COMBO-F06 «Añadir varios»: a dialog with a search on the server, a box per active product of
// Inventory and «Add N selected»; what the course already offers is ticked, greyed and says so. They go
// in at once, in the order ticked and without supplement (`combo.option.bulk_create`). Nothing ticked
// answers why instead of sending.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, ionChecked, ionValue, mountCombo, page, settle } from '../__tests__/mount-combo';
import type { GroupOut } from '../operations';
import BulkAddModal from './BulkAddModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const COURSE: GroupOut = {
  id: 'g1',
  combo_id: 'm1',
  name: 'Starters',
  min_choices: 1,
  max_choices: 1,
  allow_repeat: false,
  sort_order: 0,
  options: [
    {
      id: 'o1',
      group_id: 'g1',
      product_id: 'p1',
      product_name: 'Lentils',
      sku: 'LEN',
      catalog_price: 700,
      price_delta: 0,
      is_available: true,
      sort_order: 0,
      status: 'offered',
    },
  ],
};

const PORTION = { unit: 'ud', pricing_unit: 'ud', price_quantity: '1.000' };
const PRODUCTS = [
  { id: 'p1', name: 'Lentils', sku: 'LEN', price: 700, ...PORTION },
  { id: 'p2', name: 'Salad', sku: 'SAL', price: 650, ...PORTION },
  { id: 'p3', name: 'Soup', sku: 'SOU', price: 600, ...PORTION },
];

async function setup(locale: 'en' | 'es' = 'en', catalogue: [number, unknown] = [200, page(PRODUCTS)]) {
  const m = await mountCombo(BulkAddModal, { props: { open: false, course: COURSE }, locale, answers: { '/api/inventory/products': catalogue } });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await settle();
  const box = (id: string) => m.inDoc(`combo-bulk-row-${id}`) as HTMLElement & { checked?: boolean; disabled?: boolean };
  const submit = () => m.inDoc('combo-bulk-submit') as HTMLElement;
  return { ...m, box, submit };
}

/** Chooses a category in the dialog's category field (`Combo`, tested in @erplora/ui), after asking its search
 *  for `query` as the field does while the person types: the options must name the category. */
async function pickCategory(s: Awaited<ReturnType<typeof setup>>, query: string, id: string): Promise<void> {
  const field = s.wrapper.findComponent(Combo);
  expect(field.props('testid')).toBe('combo-bulk-category');
  const search = field.props('search');
  expect(search, 'the category field searches Inventory').toBeDefined();
  const options: ComboOption[] = await search!(query);
  const option = options.find((o) => o.id === id);
  expect(option, `the search for «${query}» offers ${id}`).toBeDefined();
  field.vm.$emit('update:modelValue', option);
  await settle();
  await settle();
}

describe('BulkAddModal', () => {
  it('lists the active products, the ones already in the course ticked and greyed', async () => {
    const s = await setup();
    // A sold-out article can still be added as a choice (INVENTORY-F29): only the till hides it.
    expect(s.sent()[0]).toMatchObject({ method: 'GET', path: '/api/inventory/products', query: { is_active: 'true', include_sold_out: 'true', limit: '50' } });
    expect(s.inDoc('combo-bulk')?.getAttribute('aria-label')).toBe('Add products to this course');
    expect([s.box('p1').checked, s.box('p1').disabled]).toEqual([true, true]);
    expect(s.inDoc('combo-bulk-item-p1')?.textContent).toContain('Already in this course');
    expect([s.box('p2').checked, s.box('p2').disabled]).toEqual([false, false]);
    expect(s.submit().textContent).toContain('Add 0 selected');
  });

  it('nothing ticked answers why, and sends nothing', async () => {
    const s = await setup();
    await click(s.submit());
    expect(s.inDoc('combo-bulk-reason')?.textContent).toContain('Tick at least one product first.');
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([]);
  });

  it('adds what was ticked, in the order ticked, and closes', async () => {
    const s = await setup();
    await ionChecked(s.box('p3'), true);
    await ionChecked(s.box('p2'), true);
    expect(s.submit().textContent).toContain('Add 2 selected');
    s.answerBy({ '/api/combo/options/bulk_create': [201, { ...COURSE }] });
    await click(s.submit());
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      { method: 'POST', path: '/api/combo/options/bulk_create', query: {}, body: { group_id: 'g1', product_ids: ['p3', 'p2'] } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('searches the catalogue on the server', async () => {
    const s = await setup();
    // ion-searchbar waits for the typing to stop (its `debounce`) before it says ionInput.
    await ionValue(s.inDoc('combo-bulk-search'), 'sou', 'ionInput');
    await settle();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/inventory/products', query: { search: 'sou', is_active: 'true', include_sold_out: 'true', limit: '50' } });
  });

  it('a catalogue that fails says so and offers «Retry»', async () => {
    const s = await setup('en', [500, { error: { code: 'internal_error', message: 'Internal error' } }]);
    expect(s.inDoc('combo-bulk-load-error')?.textContent).toContain('The product catalogue could not be loaded.');
    s.answerBy({ '/api/inventory/products': [200, page(PRODUCTS)] });
    await click(s.inDoc('combo-bulk-retry'));
    await settle();
    expect(s.inDoc('combo-bulk-load-error')).toBeNull();
    expect(s.box('p2')).not.toBeNull();
  });

  it('says «Loading…» while the catalogue is on its way, never «empty»', async () => {
    const m = await mountCombo(BulkAddModal, { props: { open: false, course: COURSE } });
    let answer: (value: Response) => void = () => {};
    m.net.onApi(() => new Promise<Response>((resolve) => (answer = resolve)));
    await m.wrapper.setProps({ open: true });
    await settle();
    expect(m.inDoc('combo-bulk-loading')?.textContent).toContain('Loading…');
    expect(m.inDoc('combo-bulk-empty')).toBeNull();
    answer(Response.json(page(PRODUCTS)));
    await settle();
    await settle();
    expect(m.inDoc('combo-bulk-loading')).toBeNull();
  });

  it('an answer that arrives after a newer search is dropped', async () => {
    const m = await mountCombo(BulkAddModal, { props: { open: false, course: COURSE } });
    const pending: Array<(value: Response) => void> = [];
    m.net.onApi(() => new Promise<Response>((resolve) => pending.push(resolve)));
    await m.wrapper.setProps({ open: true });
    await settle();
    await ionValue(m.inDoc('combo-bulk-search'), 'sou', 'ionInput');
    // The newer search answers first; the first one, late, must not paint over it.
    pending[1](Response.json(page([PRODUCTS[2]])));
    await settle();
    pending[0](Response.json(page(PRODUCTS)));
    await settle();
    await settle();
    expect(m.inDoc('combo-bulk-row-p1')).toBeNull();
    expect(m.inDoc('combo-bulk-row-p3')).not.toBeNull();
  });

  it('offers only portions: products sold by weight or per several units are left out', async () => {
    const weighed = { id: 'p9', name: 'Ham', sku: 'HAM', price: 3000, unit: 'kg', pricing_unit: 'kg', price_quantity: '1.000' };
    const s = await setup('en', [200, page([...PRODUCTS, weighed])]);
    expect(s.inDoc('combo-bulk-row-p9')).toBeNull();
    expect(s.inDoc('combo-bulk-row-p3')).not.toBeNull();
  });

  it('combos#12: a whole category at once — its products listed, «Tick all» ticks the ones not in the course yet', async () => {
    const s = await setup();
    s.answerBy({
      '/api/inventory/categories': [200, page([{ id: 'c1', name: 'Starters', product_count: 3 }])],
      '/api/inventory/products': [200, page(PRODUCTS)],
    });
    expect(s.inDoc('combo-bulk-tick-all')).toBeNull();
    await pickCategory(s, 'sta', 'c1');
    expect(s.sent().find((call) => call.path === '/api/inventory/categories')?.query).toEqual({ search: 'sta', limit: '20', sort: 'name' });
    expect(s.sent().at(-1)).toMatchObject({
      path: '/api/inventory/products',
      query: { category_id: 'c1', is_active: 'true', include_sold_out: 'true', limit: '100' },
    });
    // Lentils already offer: two of the three go in.
    expect(s.inDoc('combo-bulk-tick-all')?.textContent).toContain('Tick all of “Starters” (2)');
    await click(s.inDoc('combo-bulk-tick-all'));
    expect([s.box('p2').checked, s.box('p3').checked]).toEqual([true, true]);
    expect(s.submit().textContent).toContain('Add 2 selected');
    // Everything of the category is ticked: nothing left to tick.
    expect(s.inDoc('combo-bulk-tick-all')).toBeNull();
    s.answerBy({ '/api/combo/options/bulk_create': [201, { ...COURSE }] });
    await click(s.submit());
    expect(s.sent().filter((call) => call.method === 'POST').at(-1)?.body).toEqual({ group_id: 'g1', product_ids: ['p2', 'p3'] });
  });

  it('a search or a category that finds nothing says «No products match», not that the catalogue is empty', async () => {
    const s = await setup();
    s.answerBy({ '/api/inventory/products': [200, page([])] });
    await ionValue(s.inDoc('combo-bulk-search'), 'zzz', 'ionInput');
    await settle();
    expect(s.inDoc('combo-bulk-empty')?.textContent).toContain('No products match.');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('combo-bulk')?.getAttribute('aria-label')).toBe('Añadir productos a este plato');
    expect(s.submit().textContent).toContain('Añadir 0 seleccionados');
    s.answerBy({
      '/api/inventory/categories': [200, page([{ id: 'c1', name: 'Primeros', product_count: 3 }])],
      '/api/inventory/products': [200, page(PRODUCTS)],
    });
    await pickCategory(s, 'pri', 'c1');
    expect(s.inDoc('combo-bulk-tick-all')?.textContent).toContain('Marcar todos los de «Primeros» (2)');
  });
});
