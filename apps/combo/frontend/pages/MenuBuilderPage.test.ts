// The menu's builder (WORKBOOK «Pantallas · Constructor del menú»; COMBO-F05, F06, F12): opened from
// a row of Menus, it follows `combo.combo.get` live. The top bar goes back to Menus (one way back, as every
// detail of the Hub); on top of the page, the name and the price, what
// the menu does on the receipt and, when the till does not offer it yet, why. Then «Courses», one card
// each in their order (the handle and the arrows save the whole order at once; «Withdraw» asks first),
// and «Add a course», which edits the course whose «Edit details» was pressed.
import { ConfirmDialog, InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountCombo } from '../__tests__/mount-combo';
import CourseCard from '../components/CourseCard.vue';
import CourseForm from '../components/CourseForm.vue';
import type { ComboDetailOut, GroupOut } from '../operations';
import MenuBuilderPage from './MenuBuilderPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'combo.combo.get';

const course = (id: string, name: string, sort_order: number): GroupOut => ({
  id,
  combo_id: 'm1',
  name,
  min_choices: 1,
  max_choices: 1,
  allow_repeat: false,
  sort_order,
  options: [],
});

const MENU: ComboDetailOut = {
  id: 'm1',
  name: 'Menu of the day',
  kitchen_name: '',
  price: 1350,
  supply_kind: 'service',
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restaurant — food',
  sort_order: 0,
  is_active: true,
  group_count: 3,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
  groups: [course('g1', 'Starters', 0), course('g2', 'Mains', 1), course('g3', 'Drink', 2)],
  sellable: false,
  blockers: [{ code: 'combo.group_short', message: 'The course “Starters” has fewer choices on offer than it asks for.', group_id: 'g1' }],
};

async function setup(options: MountOptions = {}) {
  const m = await mountCombo(MenuBuilderPage, { path: '/combo/menus/m1', props: { id: 'm1' }, ...options });
  await m.live();
  const show = (data: unknown) => m.result(OP, data);
  const cards = () => m.wrapper.findAllComponents(CourseCard);
  const posts = () => m.sent().filter((call) => call.method === 'POST');
  return { ...m, show, cards, posts };
}

describe('MenuBuilderPage', () => {
  it('follows the menu and says what it does on the receipt and why the till does not offer it', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ id: 'm1' }]);
    expect(s.inDoc('combo-builder-loading')?.textContent).toContain('Loading courses…');
    await s.show(MENU);
    expect(s.inDoc('combo-builder-name')?.textContent).toBe('Menu of the day');
    expect(s.inDoc('combo-builder-price')?.textContent).toBe('€13.50');
    expect(s.inDoc('combo-builder-supply')?.textContent).toContain(
      'This menu is billed as a single service: one line at its VAT category, whatever the components are taxed at.',
    );
    const blockers = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'combo-builder-blockers');
    expect(blockers?.props('heading')).toBe('Not on the till yet');
    expect(blockers?.text()).toContain('The course “Starters” has fewer choices on offer than it asks for.');
    // The way back is the top bar's arrow, never a second one inside the page.
    expect(s.wrapper.findComponent(AppPage).props('backHref')).toBe('/combo/menus');
    expect(s.inDoc('combo-builder-back')).toBeNull();
  });

  it('a menu to take away says its price will be split, and one on the till says nothing more', async () => {
    const s = await setup();
    await s.show({ ...MENU, supply_kind: 'goods', sellable: true, blockers: [] });
    expect(s.inDoc('combo-builder-supply')?.textContent).toContain('This menu is billed as goods');
    expect(s.inDoc('combo-builder-blockers')).toBeNull();
  });

  it('one card per course, in order; no course says how to start', async () => {
    const s = await setup();
    await s.show(MENU);
    expect(s.cards().map((card) => [card.props('course').name, card.props('index'), card.props('count')])).toEqual([
      ['Starters', 0, 3],
      ['Mains', 1, 3],
      ['Drink', 2, 3],
    ]);
    await s.show({ ...MENU, groups: [] });
    expect(s.inDoc('combo-builder-empty')?.textContent).toContain('No courses yet.');
  });

  it('the arrows and the handle save the whole order of the courses', async () => {
    const s = await setup();
    await s.show(MENU);
    s.answer(200, MENU);
    s.cards()[0].vm.$emit('move', 1);
    await flush();
    const complete = vi.fn();
    s.inDoc('combo-builder-courses')?.dispatchEvent(new CustomEvent('ionItemReorder', { detail: { from: 2, to: 0, complete } }));
    await flush();
    expect(complete).toHaveBeenCalled();
    expect(s.posts().map((call) => [call.path, call.body])).toEqual([
      ['/api/combo/groups/reorder', { id: 'm1', group_ids: ['g2', 'g1', 'g3'] }],
      ['/api/combo/groups/reorder', { id: 'm1', group_ids: ['g3', 'g1', 'g2'] }],
    ]);
  });

  it('«Edit details» opens the course in the form at the foot', async () => {
    const s = await setup();
    await s.show(MENU);
    expect(s.wrapper.findComponent(CourseForm).props()).toMatchObject({ comboId: 'm1', course: null });
    s.cards()[1].vm.$emit('edit');
    await flush();
    expect(s.wrapper.findComponent(CourseForm).props('course')).toEqual(MENU.groups[1]);
    s.wrapper.findComponent(CourseForm).vm.$emit('done');
    await flush();
    expect(s.wrapper.findComponent(CourseForm).props('course')).toBeNull();
  });

  it('«Withdraw» removes a course after its confirmation', async () => {
    const s = await setup();
    await s.show(MENU);
    s.cards()[2].vm.$emit('remove');
    await flush();
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === 'combo-course-delete')!;
    expect([dialog.props('title'), dialog.props('message')]).toEqual(['Remove this course?', 'Remove the course «Drink» and its choices?']);
    s.answer(200, { id: 'g3' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.posts().map((call) => [call.path, call.body])).toEqual([['/api/combo/groups/delete', { id: 'g3' }]]);
  });

  it('a menu that cannot be read says so', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.inDoc('combo-builder-error')?.textContent).toContain('The courses of this menu could not be loaded.');
    expect(s.inDoc('combo-builder-gone')).toBeNull();
  });

  it('a menu withdrawn from another device while open says it no longer exists, with nothing left to edit', async () => {
    const s = await setup();
    await s.show(MENU);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'not_found'));
    await flush();
    const gone = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'combo-builder-gone');
    expect(gone?.props('heading')).toBe('This menu no longer exists');
    expect(gone?.text()).toContain('It has been withdrawn, perhaps from another device.');
    expect(s.cards()).toHaveLength(0);
    expect(s.wrapper.findComponent(CourseForm).exists()).toBe(false);
    expect([s.inDoc('combo-builder-name'), s.inDoc('combo-builder-supply'), s.inDoc('combo-builder-error')]).toEqual([null, null, null]);
    // Nothing left here: the notice itself offers the way back.
    expect(gone?.find('[data-testid="combo-builder-back"]').text()).toContain('All menus');
  });

  it('a menu that no longer exists when opened says so', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'not_found'));
    await flush();
    expect(s.inDoc('combo-builder-gone')?.textContent).toContain('This menu no longer exists');
    expect([s.inDoc('combo-builder-loading'), s.inDoc('combo-builder-error')]).toEqual([null, null]);
  });

  it('an employee reads the menu without the form', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(MENU);
    expect(s.wrapper.findComponent(CourseForm).exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(MENU);
    expect(s.inDoc('combo-builder-supply')?.textContent).toContain('Este menú se factura como un único servicio');
    s.net.lastStream().push(errorFrame(s.subId(OP), 'not_found'));
    await flush();
    expect(s.inDoc('combo-builder-back')?.textContent).toContain('Todos los menús');
    expect(s.inDoc('combo-builder-gone')?.textContent).toContain('Este menú ya no existe');
    expect(s.inDoc('combo-builder-gone')?.textContent).toContain('Se ha retirado, quizá desde otro dispositivo.');
  });
});
