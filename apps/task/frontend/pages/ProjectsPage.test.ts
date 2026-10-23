// Tasks → Projects (WORKBOOK «Pantallas · Proyectos»; TASK-F12 to F14): the live `task.project.list` in
// a server-side DataTable — Code, Name, Color (with its swatch) and Active (Yes / No, a list filter) —,
// the newest first, «Search code or name…», list or cards, 50 a page. A row and its «Open» open the
// project's sheet; «+» (whoever manages projects) opens «New project».
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, mountTask, type MountOptions, page } from '../__tests__/mount-task';
import { project } from '../__tests__/project';
import ProjectFormModal from '../components/ProjectFormModal.vue';
import ProjectSheet from '../components/ProjectSheet.vue';
import ProjectsPage from './ProjectsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'task.project.list';
const ROWS = [project(), project({ id: 'p2', code: 'refit', name: 'Summer refit', color: '', is_active: false })];

async function setup(options: MountOptions = {}) {
  const m = await mountTask(ProjectsPage, { path: '/task/projects', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="task-projects-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, rows, cells, show: (data: unknown) => m.result(OP, data) };
}

describe('ProjectsPage', () => {
  it('follows the projects, the newest first, 50 from the first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'task-projects', total: 2, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search code or name…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New project');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Tasks');
  });

  it('paints Code, Name, Color and Active', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['code', 'Code'],
      ['name', 'Name'],
      ['color', 'Color'],
      ['is_active', 'Active'],
    ]);
    expect(s.cells(0).slice(0, 4)).toEqual(['opening', 'Opening', '#AA3300', 'Yes']);
    expect(s.cells(1).slice(2, 4)).toEqual(['—', 'No']);
  });

  it('filters by column, «Active» chosen from Yes / No, and searches and sorts on the server', async () => {
    const s = await setup();
    const active = s.prop<Array<{ key: string; filter?: { options?: Array<{ value: string; label: string }> } }>>('columns').find((c) => c.key === 'is_active');
    expect(active?.filter?.options).toEqual([
      { value: 'true', label: 'Yes' },
      { value: 'false', label: 'No' },
    ]);
    // Code, Name and Color are free text: the server filters them by «contains».
    s.table().vm.$emit('filtersChange', { code: 'open', name: 'grand', is_active: 'false' });
    s.table().vm.$emit('sortChange', { sort: 'name', dir: 'asc' });
    s.table().vm.$emit('update:search', 'op');
    await flush();
    expect(s.params(OP)).toEqual([{ code: 'open', name: 'grand', is_active: false, search: 'op', sort: 'name', limit: 50, offset: 0 }]);
  });

  it('keeps the filters behind the toolbar funnel, as the old table did, until it is pressed', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop('filterable')).toBe(true);
    expect(s.wrapper.find('[data-testid="task-projects-filter-is_active"]').exists()).toBe(false);
    await s.wrapper.find('[data-testid="task-projects-filters-toggle"]').trigger('click');
    await flush();
    expect(s.wrapper.find('[data-testid="task-projects-filters-panel"] [data-testid="task-projects-filter-is_active"]').exists()).toBe(true);
  });

  it("wears the old module's icons: «Open» opens, the folder on its cards and its empty list", async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ id: string; icon?: string }>>('actions').map((a) => [a.id, a.icon])).toEqual([['open', 'open-outline']]);
    expect(s.prop<() => string>('cardIcon')()).toBe('folder-outline');
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('icon')).toBe('folder-outline');
  });

  it('no project at all says «No projects.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No projects.');
  });

  it('a row and its «Open» open the project; «+» opens «New project»', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ id: string; label: string }>>('actions').map((a) => [a.id, a.label])).toEqual([['open', 'Open']]);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect(s.wrapper.findComponent(ProjectSheet).props()).toMatchObject({ open: true, projectId: 'p2' });
    s.table().vm.$emit('action', { actionId: 'open', row: ROWS[0] });
    await flush();
    expect(s.wrapper.findComponent(ProjectSheet).props('projectId')).toBe('p1');
    s.table().vm.$emit('add');
    await flush();
    expect(s.wrapper.findComponent(ProjectFormModal).props('open')).toBe(true);
  });

  it('an employee reads the projects without «+»', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.prop('addable')).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.cells(0)[3]).toBe('Sí');
    expect(s.prop('searchPlaceholder')).toBe('Buscar código o nombre…');
  });
});

describe('ProjectsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
