// The guard every list page's test runs (FIX-DATATABLE-HUB): a list fills its page between the topbar
// and the tabbar only when AppPage gets `content-layout="fill"`, its DataTable gets `fill` and every box
// between them is a `.page-fill` stack (polish.css: a plain wrapper breaks the height chain).
import { DataTable } from '@erplora/ui/components';
import { AppPage, createShellI18n } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';

import { listFillProblems } from './list-fill';

/** A page: AppPage with `layout`, a notice above and `body` as its view (DataTable as `<DataTable>`). */
async function mountList(layout: string | undefined, body: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] });
  await router.push('/');
  await router.isReady();
  const Page = {
    components: { AppPage, DataTable },
    data: () => ({ layout, columns: [{ key: 'name', label: 'Name' }], rows: [] }),
    template: `<AppPage title="List" :content-layout="layout"><p class="notice">Above</p>${body}</AppPage>`,
  };
  return mount(Page, { global: { plugins: [router, createShellI18n({ locale: 'en' })] } });
}

const TABLE = '<DataTable :columns="columns" :rows="rows" fill />';

describe('listFillProblems', () => {
  it('none when AppPage fills and its DataTable `fill` sits right in the stack', async () => {
    expect(listFillProblems(await mountList('fill', TABLE))).toEqual([]);
  });

  it('none when the DataTable sits in a nested `.page-fill` stack (a heading and the list in a section)', async () => {
    const body = `<section class="page-fill"><h2>Heading</h2>${TABLE}</section>`;
    expect(listFillProblems(await mountList('fill', body))).toEqual([]);
  });

  it('AppPage without `content-layout="fill"`', async () => {
    expect(listFillProblems(await mountList(undefined, TABLE))).toEqual([
      'AppPage content-layout is "fluid", not "fill"',
      'the DataTable `fill` is not in the page stack: AppPage > .page-fill > … > .data-table',
    ]);
    expect(listFillProblems(await mountList('detail-fill', TABLE))[0]).toBe('AppPage content-layout is "detail-fill", not "fill"');
  });

  it('a DataTable without `fill`', async () => {
    expect(listFillProblems(await mountList('fill', '<DataTable :columns="columns" :rows="rows" />'))).toEqual([
      'no DataTable with `fill` on the page',
    ]);
  });

  it('a DataTable `fill` inside a plain wrapper', async () => {
    expect(listFillProblems(await mountList('fill', `<div class="list">${TABLE}</div>`))).toEqual([
      'the DataTable `fill` is not in the page stack: AppPage > .page-fill > … > .data-table',
    ]);
  });

  it('no list at all', async () => {
    expect(listFillProblems(await mountList('fill', '<p>Nothing</p>'))).toEqual(['no DataTable with `fill` on the page']);
  });
});
