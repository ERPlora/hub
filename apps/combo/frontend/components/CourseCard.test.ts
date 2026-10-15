// A course in the menu's builder (WORKBOOK «Constructor del menú»; COMBO-F05, F06, F12): its name and
// rule («Compulsory · pick 1 · up to 1 · no repeats»), and with the right to manage the handle, «Move
// up», «Move down», «Edit details» and «Withdraw» (the page acts on them). Inside, «Choices»: a row per
// product with its supplement and why it is not offered, and per row the handle, up, down, «Sold out» /
// «Available», edit and remove (after its confirmation); below, the product picker, «Supplement», «Add
// choice» and «Add several». A refusal is said inside the course.
import { Combo, ConfirmDialog } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, ionValue, type MountOptions, mountCombo, settle } from '../__tests__/mount-combo';
import type { GroupOut, OptionOut } from '../operations';
import BulkAddModal from './BulkAddModal.vue';
import CourseCard from './CourseCard.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const option = (fields: Partial<OptionOut>): OptionOut => ({
  id: 'o1',
  group_id: 'g1',
  product_id: 'p1',
  product_name: 'Hake',
  sku: 'HAK',
  catalog_price: 1400,
  price_delta: 0,
  is_available: true,
  sort_order: 0,
  status: 'offered',
  ...fields,
});

const COURSE: GroupOut = {
  id: 'g1',
  combo_id: 'm1',
  name: 'Mains',
  min_choices: 1,
  max_choices: 1,
  allow_repeat: false,
  sort_order: 0,
  options: [
    option({ id: 'o1', product_id: 'p1', product_name: 'Hake', price_delta: 200 }),
    option({ id: 'o2', product_id: 'p2', product_name: 'Chicken', sku: 'CHI', sort_order: 1, is_available: false, status: 'sold_out' }),
    option({ id: 'o3', product_id: 'p3', product_name: 'Pork', sku: 'POR', sort_order: 2, status: 'product_inactive' }),
  ],
};

async function setup(course: GroupOut = COURSE, options: MountOptions = {}) {
  const m = await mountCombo(CourseCard, { props: { course, index: 0, count: 2 }, ...options });
  const el = (testid: string) => m.inDoc(testid) as HTMLElement & { disabled?: boolean; errorText?: string; value?: unknown };
  const picker = () => m.wrapper.findComponent(Combo);
  const posts = () => m.sent().filter((call) => call.method === 'POST');
  return { ...m, el, picker, posts };
}

describe('CourseCard: the course', () => {
  it('says its name and its rule, and offers its actions to whoever manages', async () => {
    const s = await setup();
    expect(s.el('combo-course-g1-name').textContent).toBe('Mains');
    expect(s.el('combo-course-g1-rule').textContent?.trim()).toBe('Compulsory · pick 1 · up to 1 · no repeats');
    expect(s.el('combo-course-g1-up').disabled).toBe(true);
    expect(s.el('combo-course-g1-down').disabled).toBe(false);
    await click(s.el('combo-course-g1-down'));
    await click(s.el('combo-course-g1-edit'));
    await click(s.el('combo-course-g1-delete'));
    expect([s.wrapper.emitted('move'), s.wrapper.emitted('edit'), s.wrapper.emitted('remove')]).toEqual([[[1]], [[]], [[]]]);
  });

  it('an employee only reads it', async () => {
    const s = await setup(COURSE, { session: EMPLOYEE });
    expect(s.inDoc('combo-course-g1-edit')).toBeNull();
    expect(s.inDoc('combo-choice-o1-delete')).toBeNull();
    expect(s.picker().exists()).toBe(false);
  });
});

describe('CourseCard: its choices', () => {
  it('a row per product, with its supplement and why it is not offered', async () => {
    const s = await setup();
    // What the row reads (the label; the row's own buttons come after it).
    const label = (id: string) => s.el(`combo-choice-${id}`).querySelector('.combo-course__choice')?.innerHTML.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    expect(label('o1')).toBe('Hake +€2.00');
    expect(label('o2')).toContain('Chicken');
    expect(s.el('combo-choice-o2-status').textContent?.trim()).toBe('Sold out');
    expect(s.el('combo-choice-o3-status').textContent?.trim()).toBe('Deactivated in Inventory');
    expect(s.inDoc('combo-choice-o1-status')).toBeNull();
  });

  it('a course without choices says nobody can resolve it', async () => {
    const s = await setup({ ...COURSE, options: [] });
    expect(s.el('combo-course-g1-empty').textContent).toContain('No choices yet: nobody can resolve this course.');
  });

  it('«Sold out» and «Available» switch the choice on the server', async () => {
    const s = await setup();
    s.answer(200, option({}));
    await click(s.el('combo-choice-o1-availability'));
    await click(s.el('combo-choice-o2-availability'));
    expect(s.posts().map((call) => call.body)).toEqual([
      { id: 'o1', is_available: false },
      { id: 'o2', is_available: true },
    ]);
    expect(s.el('combo-choice-o2-availability').textContent).toContain('Available');
  });

  it('up and down save the whole new order at once', async () => {
    const s = await setup();
    s.answer(200, COURSE);
    expect(s.el('combo-choice-o1-up').disabled).toBe(true);
    await click(s.el('combo-choice-o1-down'));
    expect(s.posts()).toEqual([
      { method: 'POST', path: '/api/combo/options/reorder', query: {}, body: { group_id: 'g1', option_ids: ['o2', 'o1', 'o3'] } },
    ]);
  });

  it('dragging a row saves the order it was dropped in', async () => {
    const s = await setup();
    s.answer(200, COURSE);
    const complete = vi.fn();
    s.el('combo-course-g1-choices').dispatchEvent(new CustomEvent('ionItemReorder', { detail: { from: 2, to: 0, complete } }));
    await settle();
    expect(complete).toHaveBeenCalled();
    expect(s.posts().map((call) => call.body)).toEqual([{ group_id: 'g1', option_ids: ['o3', 'o1', 'o2'] }]);
  });

  it('removes a choice after its confirmation', async () => {
    const s = await setup();
    await click(s.el('combo-choice-o2-delete'));
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('title'), dialog.props('message')]).toEqual(['Remove this choice?', 'Remove «Chicken» from the course «Mains»?']);
    s.answer(200, { id: 'o2' });
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.posts().map((call) => [call.path, call.body])).toEqual([['/api/combo/options/delete', { id: 'o2' }]]);
  });
});

describe('CourseCard: adding and editing a choice', () => {
  it('adds the product picked with its supplement, last', async () => {
    const s = await setup();
    expect(s.picker().props('label')).toBe('Catalogue product');
    s.answer(201, option({ id: 'o9' }));
    s.picker().vm.$emit('update:modelValue', { id: 'p9', label: 'Sole' });
    await settle();
    await ionValue(s.el('combo-course-g1-delta'), '1,50', 'ionInput');
    await click(s.el('combo-course-g1-save'));
    expect(s.posts()).toEqual([
      { method: 'POST', path: '/api/combo/options', query: {}, body: { group_id: 'g1', product_id: 'p9', price_delta: 150 } },
    ]);
    // The form is empty again for the next one.
    expect(s.picker().props('modelValue')).toBeNull();
  });

  it('a supplement may be negative', async () => {
    const s = await setup();
    s.answer(201, option({ id: 'o9' }));
    s.picker().vm.$emit('update:modelValue', { id: 'p9', label: 'Sole' });
    await ionValue(s.el('combo-course-g1-delta'), '-0.5', 'ionInput');
    await click(s.el('combo-course-g1-save'));
    expect(s.posts()[0].body).toEqual({ group_id: 'g1', product_id: 'p9', price_delta: -50 });
  });

  it('answers why before sending: no product picked, or one the course already offers', async () => {
    const s = await setup();
    await click(s.el('combo-course-g1-save'));
    expect(s.el('combo-course-g1-reason').textContent).toContain('Pick a catalogue product first.');
    s.picker().vm.$emit('update:modelValue', { id: 'p1', label: 'Hake' });
    await click(s.el('combo-course-g1-save'));
    expect(s.el('combo-course-g1-reason').textContent).toContain('This course already offers that product.');
    expect(s.posts()).toEqual([]);
  });

  it('the server’s refusal is said inside the course', async () => {
    const s = await setup();
    const message = '“Sole” is deactivated in Inventory: activate it before putting it in a menu.';
    s.answer(409, { error: { code: 'combo.product_inactive', message, fields: { product_id: message } } });
    s.picker().vm.$emit('update:modelValue', { id: 'p9', label: 'Sole' });
    await click(s.el('combo-course-g1-save'));
    expect(s.picker().props('errorText')).toBe(message);
  });

  it('editing a choice keeps its place and sends only what changed', async () => {
    const s = await setup();
    await click(s.el('combo-choice-o1-edit'));
    expect(s.el('combo-course-g1-editing').textContent).toContain('Editing «Hake». It keeps its position in the course.');
    expect(s.picker().props('modelValue')).toEqual({ id: 'p1', label: 'Hake' });
    expect(s.el('combo-course-g1-delta').value).toBe('2.00');
    s.answer(200, option({}));
    await ionValue(s.el('combo-course-g1-delta'), '2,50', 'ionInput');
    await click(s.el('combo-course-g1-save'));
    expect(s.posts()).toEqual([{ method: 'POST', path: '/api/combo/options/update', query: {}, body: { id: 'o1', price_delta: 250 } }]);
  });

  it('«Add several» opens the picker of the catalogue for this course', async () => {
    const s = await setup();
    await click(s.el('combo-course-g1-bulk'));
    expect([s.wrapper.findComponent(BulkAddModal).props('open'), s.wrapper.findComponent(BulkAddModal).props('course')]).toEqual([true, COURSE]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(COURSE, { locale: 'es' });
    expect(s.el('combo-course-g1-rule').textContent?.trim()).toBe('Obligatorio · elige 1 · hasta 1 · sin repetir');
    expect(s.el('combo-choice-o3-status').textContent?.trim()).toBe('Desactivado en Inventario');
    expect(s.el('combo-course-g1-save').textContent).toContain('Añadir elección');
  });
});
