// What keeps a list page from filling its page between the topbar and the tabbar (FIX-DATATABLE-HUB): the
// page's test asserts `expect(listFillProblems(wrapper)).toEqual([])`. The height chain (polish.css) needs
// AppPage `content-layout="fill"`, a DataTable `fill`, and only `.page-fill` stacks between the two.
import { DataTable } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import type { VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';

/** The DataTable's box hangs from AppPage's stack (`.hub-detail-shell--fill > .page-fill`) through stacks only. */
function inPageStack(table: Element): boolean {
  let box = table.parentElement;
  if (!box?.classList.contains('page-fill')) return false;
  while (box.parentElement?.classList.contains('page-fill')) box = box.parentElement;
  return box.parentElement?.classList.contains('hub-detail-shell--fill') ?? false;
}

/** Every reason the mounted page's list does not fill the page; none = it does. */
export function listFillProblems(wrapper: VueWrapper): string[] {
  const page = wrapper.findComponent(AppPage);
  if (!page.exists()) return ['no AppPage'];
  const problems: string[] = [];
  const layout = page.props('contentLayout');
  if (layout !== 'fill') problems.push(`AppPage content-layout is "${String(layout)}", not "fill"`);
  const tables = wrapper
    .findAllComponents(DataTable as unknown as Component)
    .filter((table) => (table.props() as Record<string, unknown>).fill === true);
  if (tables.length === 0) return [...problems, 'no DataTable with `fill` on the page'];
  for (const table of tables) {
    if (!inPageStack(table.element)) problems.push('the DataTable `fill` is not in the page stack: AppPage > .page-fill > … > .data-table');
  }
  return problems;
}
