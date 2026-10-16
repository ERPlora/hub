// Modifiers (WORKBOOK «Pantallas · Suplementos»; MODIFIER-F01 to F03): the live `modifier.group.list` in a
// server-side DataTable with the old screen's columns — Name (sorted and filtered), «On the kitchen ticket»
// (the name when empty), Choice (the rule) and Order — plus Options and «Applies to»; «Search…», by order
// then name, 50 a page. «New group» and Edit (whoever may manage) open the form; Delete asks first, saying
// what goes with it; a row opens the group's sheet, to everyone. Empty: «No modifier groups yet.».
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import { type Component, defineComponent } from 'vue';

import type { GroupOut } from '../operations';
import { EMPLOYEE, flush, type MountOptions, mountModifier, page } from '../__tests__/mount-modifier';
import GroupFormModal from '../components/GroupFormModal.vue';
import GroupSheet from '../components/GroupSheet.vue';
import GroupsPage from './GroupsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'modifier.group.list';
const group = (id: string, over: Partial<GroupOut> = {}): GroupOut => ({
  id,
  name: 'Doneness',
  kitchen_name: 'POINT',
  min_choices: 1,
  max_choices: 1,
  allow_repeat: false,
  is_required: true,
  sort_order: 1,
  option_count: 3,
  default_count: 1,
  link_count: 2,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
  ...over,
});
const ROWS = [
  group('g1'),
  group('g2', { name: 'Sauces', kitchen_name: '', min_choices: 0, max_choices: 3, allow_repeat: true, is_required: false, sort_order: 2, option_count: 0, link_count: 0 }),
];

async function setup(options: MountOptions = {}) {
  const m = await mountModifier(GroupsPage, { path: '/modifier/groups', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="modifier-groups-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, rows, cells, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('GroupsPage', () => {
  it('follows the groups by their order, with the old columns plus Options and Applies to', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'sort_order', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New group');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['kitchen_name', 'On the kitchen ticket'],
      ['min_choices', 'Choice'],
      ['option_count', 'Options'],
      ['link_count', 'Applies to'],
      ['sort_order', 'Order'],
    ]);
    expect(s.cells(0).slice(0, 6)).toEqual(['Doneness', 'POINT', 'Required (min. 1) · max. 1', '3', '2', '1']);
    // An empty kitchen name is the name (Toast's rule, as the old screen).
    expect(s.cells(1).slice(0, 3)).toEqual(['Sauces', 'Sauces', 'Optional · max. 3 · repeats']);
  });

  it('searches, sorts and filters on the server; none at all says «No modifier groups yet.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No modifier groups yet.');
    s.table().vm.$emit('sortChange', { sort: 'name', dir: 'desc' });
    s.table().vm.$emit('update:search', 'sau');
    s.table().vm.$emit('filtersChange', { name: 'sa', required: 'true' });
    await flush();
    expect(s.list()).toEqual([{ name: 'sa', required: true, search: 'sau', sort: '-name', limit: 50, offset: 0 }]);
    await s.reopen();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('the Choice filter offers Required and Optional', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const choice = s.prop<Array<{ key: string; filter?: { type: string; key?: string; options?: Array<{ value: string; label: string }> } }>>('columns')[2];
    expect(choice.filter).toEqual({
      type: 'select',
      key: 'required',
      options: [
        { value: 'true', label: 'Required' },
        { value: 'false', label: 'Optional' },
      ],
    });
  });

  it('«New group» and Edit open the form; a row opens the group’s sheet', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const form = () => s.wrapper.findComponent(GroupFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([form().props('open'), form().props('group')]).toEqual([true, null]);
    form().vm.$emit('update:open', false);
    s.table().vm.$emit('action', { actionId: 'edit', row: ROWS[1] });
    await flush();
    expect([form().props('open'), form().props('group')]).toEqual([true, ROWS[1]]);
    s.table().vm.$emit('rowClick', ROWS[0]);
    await flush();
    const sheet = s.wrapper.findComponent(GroupSheet);
    expect([sheet.props('open'), sheet.props('group')]).toEqual([true, ROWS[0]]);
  });

  it('the sheet is unmounted only once it says it was dismissed', async () => {
    // A stand-in that does not dismiss by itself: unmounting a presented modal leaves its overlay on
    // screen, so closing first lets Ionic dismiss it and only `closed` removes it.
    const Sheet = defineComponent({ name: 'GroupSheet', props: { open: Boolean, group: { type: Object, default: null } }, emits: ['update:open', 'closed'], render: () => null });
    const s = await setup({ stubs: { GroupSheet: Sheet } });
    await s.show(page(ROWS));
    s.table().vm.$emit('rowClick', ROWS[0]);
    await flush();
    const sheet = () => s.wrapper.findComponent(Sheet);
    sheet().vm.$emit('update:open', false);
    await flush();
    expect([sheet().exists(), sheet().props('open')]).toEqual([true, false]);
    sheet().vm.$emit('closed');
    await flush();
    expect(sheet().exists()).toBe(false);
  });

  it('deletes after its confirmation, saying what goes with the group', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[0] });
    await flush();
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('title'), dialog.props('message'), dialog.props('consequences'), dialog.props('confirmLabel')]).toEqual([
      'Delete group',
      'Doneness — the group disappears with its options and stops being asked in the till. What was already ordered keeps it.',
      ['3 option(s) will be deleted with it.', 'It will stop applying to 2 product(s) or category(ies).'],
      'Delete',
    ]);
    s.answer(200, { id: 'g1' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/modifier/groups/delete', query: {}, body: { id: 'g1' } }]);
  });

  it('an empty group says nothing more when deleted', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[1] });
    await flush();
    expect(s.wrapper.findComponent(ConfirmDialog).props('consequences')).toEqual([]);
  });

  it('an employee reads and opens the sheet, but neither adds, edits nor deletes', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable'), s.prop<unknown[]>('actions')]).toEqual([false, true, []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar…', 'Nuevo grupo']);
    expect(s.cells(0)[2]).toBe('Obligatorio (mín. 1) · máx. 1');
  });
});

describe('GroupsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
